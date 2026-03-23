"""
ARIA SQLite Database — source of truth and deduplication engine.
No investor ever gets contacted twice.
"""

import sqlite3
import uuid
import os
from datetime import datetime, timedelta

import pandas as pd

from config import DB_PATH


def _connect():
    """Return a connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _connect()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS investors (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        linkedin_url TEXT,
        first_name TEXT,
        last_name TEXT,
        title TEXT,
        company TEXT,
        past_companies TEXT,
        location TEXT,
        bio TEXT,
        source TEXT,
        apollo_id TEXT,
        tier INTEGER DEFAULT 0,
        score INTEGER DEFAULT 0,
        investor_type TEXT,
        channel TEXT DEFAULT 'EMAIL',
        personalization_hook TEXT,
        research_hook TEXT,
        research_confidence TEXT DEFAULT 'LOW',
        recent_activity TEXT,
        portfolio_signal TEXT,
        subject_a TEXT,
        subject_b TEXT,
        email_body TEXT,
        linkedin_message TEXT,
        predicted_reply_tier TEXT,
        verified INTEGER DEFAULT 0,
        email_valid INTEGER DEFAULT 0,
        status TEXT DEFAULT 'NEW',
        first_contacted TEXT,
        last_contacted TEXT,
        email_count INTEGER DEFAULT 0,
        followup_count INTEGER DEFAULT 0,
        instantly_lead_id TEXT,
        replied INTEGER DEFAULT 0,
        reply_text TEXT,
        reply_sentiment TEXT,
        meeting_booked INTEGER DEFAULT 0,
        meeting_date TEXT,
        airtable_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS sends (
        id TEXT PRIMARY KEY,
        investor_id TEXT,
        channel TEXT,
        subject TEXT,
        body TEXT,
        sent_at TEXT,
        instantly_campaign_id TEXT,
        FOREIGN KEY (investor_id) REFERENCES investors(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS daily_runs (
        id TEXT PRIMARY KEY,
        run_date TEXT,
        found INTEGER DEFAULT 0,
        verified INTEGER DEFAULT 0,
        scored_tier1 INTEGER DEFAULT 0,
        scored_tier2 INTEGER DEFAULT 0,
        scored_tier3 INTEGER DEFAULT 0,
        researched INTEGER DEFAULT 0,
        emails_written INTEGER DEFAULT 0,
        sent_to_instantly INTEGER DEFAULT 0,
        linkedin_prepped INTEGER DEFAULT 0,
        replies_received INTEGER DEFAULT 0,
        hot_replies INTEGER DEFAULT 0,
        meetings_booked INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


def add_investor(row: dict) -> tuple:
    """
    Dedup before insert.
    Returns (False, 'dup_email'|'dup_linkedin'|'dup_name') or (True, investor_id).
    """
    conn = _connect()
    c = conn.cursor()

    email = (row.get("email") or "").strip().lower()
    linkedin = (row.get("linkedin_url") or "").strip()
    first = (row.get("first_name") or "").strip()
    last = (row.get("last_name") or "").strip()
    company = (row.get("company") or "").strip()

    # Dedup 1: email
    if email:
        c.execute("SELECT id FROM investors WHERE email = ?", (email,))
        if c.fetchone():
            conn.close()
            return (False, "dup_email")

    # Dedup 2: linkedin
    if linkedin:
        c.execute("SELECT id FROM investors WHERE linkedin_url = ?", (linkedin,))
        if c.fetchone():
            conn.close()
            return (False, "dup_linkedin")

    # Dedup 3: first + last + company
    if first and last and company:
        c.execute(
            "SELECT id FROM investors WHERE lower(first_name)=? AND lower(last_name)=? AND lower(company)=?",
            (first.lower(), last.lower(), company.lower()),
        )
        if c.fetchone():
            conn.close()
            return (False, "dup_name")

    investor_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    c.execute(
        """INSERT INTO investors (
            id, email, linkedin_url, first_name, last_name, title, company,
            past_companies, location, bio, source, apollo_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            investor_id,
            email or None,
            linkedin or None,
            first or None,
            last or None,
            (row.get("title") or "").strip() or None,
            company or None,
            (row.get("past_companies") or "").strip() or None,
            (row.get("location") or "").strip() or None,
            (row.get("bio") or "").strip() or None,
            (row.get("source") or "apollo").strip(),
            (row.get("apollo_id") or "").strip() or None,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return (True, investor_id)


def get_investor(investor_id: str) -> dict:
    """Get a single investor by ID."""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM investors WHERE id = ?", (investor_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_investor_by_email(email: str) -> dict:
    """Get investor by email address."""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM investors WHERE email = ?", (email.strip().lower(),))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def update_investor(investor_id: str, fields: dict):
    """Update arbitrary fields on an investor."""
    conn = _connect()
    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [investor_id]
    conn.execute(f"UPDATE investors SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def is_safe_to_contact(investor_id: str) -> tuple:
    """
    Returns (False, reason) if unsafe, (True, 'safe') otherwise.
    """
    inv = get_investor(investor_id)
    if not inv:
        return (False, "not_found")

    if inv["status"] not in ("NEW", "QUEUED", "VERIFIED", "SCORED", "WRITTEN"):
        return (False, f"status_{inv['status']}")

    if inv["email_count"] >= 3:
        return (False, "max_emails_reached")

    if inv["email_valid"] == 0 and inv["verified"] == 1:
        return (False, "email_invalid")

    if inv["replied"] == 1:
        return (False, "already_replied")

    if inv["meeting_booked"] == 1:
        return (False, "meeting_already_booked")

    if inv["last_contacted"]:
        try:
            last = datetime.fromisoformat(inv["last_contacted"])
            if datetime.utcnow() - last < timedelta(days=5):
                return (False, "contacted_recently")
        except ValueError:
            pass

    return (True, "safe")


def get_ready_to_contact(limit: int = 25, tier: int = None) -> list:
    """Get investors safe to contact, ordered by score DESC."""
    conn = _connect()
    c = conn.cursor()

    query = """
        SELECT * FROM investors
        WHERE status IN ('SCORED', 'WRITTEN', 'VERIFIED')
        AND email_body IS NOT NULL
        AND (verified = 0 OR email_valid = 1)
        AND email_count < 3
        AND replied = 0
        AND meeting_booked = 0
    """
    params = []

    if tier is not None:
        query += " AND tier = ?"
        params.append(tier)

    query += " ORDER BY score DESC LIMIT ?"
    params.append(limit)

    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    # Filter by contact recency
    safe = []
    for row in rows:
        ok, _ = is_safe_to_contact(row["id"])
        if ok:
            safe.append(row)
        if len(safe) >= limit:
            break

    return safe


def get_followup_candidates() -> list:
    """
    Investors who got 1 email, no follow-up, 5-8 days ago,
    no reply, valid email.
    """
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow()
    day5 = (now - timedelta(days=8)).isoformat()
    day8 = (now - timedelta(days=5)).isoformat()

    c.execute(
        """SELECT * FROM investors
        WHERE email_count = 1
        AND followup_count = 0
        AND last_contacted BETWEEN ? AND ?
        AND replied = 0
        AND email_valid = 1
        ORDER BY score DESC""",
        (day5, day8),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def mark_verified(investor_id: str, valid: bool):
    """Update after Millionverifier check."""
    update_investor(investor_id, {
        "verified": 1,
        "email_valid": 1 if valid else 0,
        "status": "VERIFIED" if valid else "INVALID",
    })


def mark_scored(investor_id: str, tier: int, score: int,
                investor_type: str, channel: str,
                personalization_hook: str):
    """Update after scoring."""
    update_investor(investor_id, {
        "tier": tier,
        "score": score,
        "investor_type": investor_type,
        "channel": channel,
        "personalization_hook": personalization_hook,
        "status": "SCORED",
    })


def mark_researched(investor_id: str, research_hook: str,
                    research_confidence: str, recent_activity: str,
                    portfolio_signal: str):
    """Update after SerpAPI research."""
    update_investor(investor_id, {
        "research_hook": research_hook,
        "research_confidence": research_confidence,
        "recent_activity": recent_activity,
        "portfolio_signal": portfolio_signal,
    })


def mark_written(investor_id: str, subject_a: str, subject_b: str,
                 email_body: str, linkedin_message: str = None,
                 predicted_reply_tier: str = None):
    """Update after email generation."""
    update_investor(investor_id, {
        "subject_a": subject_a,
        "subject_b": subject_b,
        "email_body": email_body,
        "linkedin_message": linkedin_message,
        "predicted_reply_tier": predicted_reply_tier,
        "status": "WRITTEN",
    })


def mark_contacted(investor_id: str, channel: str, subject: str,
                   body: str, instantly_id: str = None):
    """Update after confirmed send. Also log to sends table."""
    now = datetime.utcnow().isoformat()
    inv = get_investor(investor_id)
    if not inv:
        return

    conn = _connect()
    c = conn.cursor()

    # Update investor record
    email_count = (inv["email_count"] or 0) + 1
    followup_count = inv["followup_count"] or 0
    if email_count > 1:
        followup_count += 1

    c.execute(
        """UPDATE investors SET
            status = 'CONTACTED',
            first_contacted = COALESCE(first_contacted, ?),
            last_contacted = ?,
            email_count = ?,
            followup_count = ?,
            instantly_lead_id = COALESCE(?, instantly_lead_id),
            updated_at = ?
        WHERE id = ?""",
        (now, now, email_count, followup_count, instantly_id, now, investor_id),
    )

    # Log to sends table
    send_id = str(uuid.uuid4())
    c.execute(
        """INSERT INTO sends (id, investor_id, channel, subject, body, sent_at, instantly_campaign_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (send_id, investor_id, channel, subject, body, now, instantly_id),
    )

    conn.commit()
    conn.close()


def mark_replied(investor_id: str, reply_text: str, sentiment: str):
    """Update when reply received."""
    update_investor(investor_id, {
        "replied": 1,
        "reply_text": reply_text,
        "reply_sentiment": sentiment,
        "status": "REPLIED",
    })


def get_stats() -> dict:
    """Full pipeline stats."""
    conn = _connect()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM investors")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM investors WHERE verified = 1 AND email_valid = 1")
    verified = c.fetchone()[0]

    tiers = {}
    for t in (1, 2, 3):
        c.execute("SELECT COUNT(*) FROM investors WHERE tier = ?", (t,))
        tiers[t] = c.fetchone()[0]

    statuses = {}
    for s in ("NEW", "VERIFIED", "SCORED", "WRITTEN", "CONTACTED", "REPLIED", "MEETING", "INVALID"):
        c.execute("SELECT COUNT(*) FROM investors WHERE status = ?", (s,))
        statuses[s] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM investors WHERE replied = 1")
    replied = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM investors WHERE meeting_booked = 1")
    meetings = c.fetchone()[0]

    contacted = statuses.get("CONTACTED", 0) + replied + meetings
    reply_rate = (replied / contacted * 100) if contacted > 0 else 0.0
    meeting_rate = (meetings / contacted * 100) if contacted > 0 else 0.0

    c.execute("""SELECT COUNT(*) FROM investors
        WHERE status IN ('SCORED', 'WRITTEN', 'VERIFIED')
        AND email_body IS NOT NULL
        AND (verified = 0 OR email_valid = 1)
        AND email_count < 3 AND replied = 0 AND meeting_booked = 0""")
    ready = c.fetchone()[0]

    followups = len(get_followup_candidates())

    conn.close()

    return {
        "total": total,
        "verified": verified,
        "by_tier": tiers,
        "by_status": statuses,
        "contacted": contacted,
        "replied": replied,
        "meetings": meetings,
        "reply_rate": reply_rate,
        "meeting_rate": meeting_rate,
        "ready_today": ready,
        "followups_due": followups,
    }


def load_from_csv(csv_path: str) -> dict:
    """
    Load Apollo/SalesNav CSV. Normalize columns. Dedup each row.
    Returns: {added, duplicates, skipped}
    """
    df = pd.read_csv(csv_path)

    # Normalize column names
    col_map = {
        "First Name": "first_name",
        "Last Name": "last_name",
        "Title": "title",
        "Company": "company",
        "Company Name for Emails": "company",
        "Email": "email",
        "Person Linkedin Url": "linkedin_url",
        "LinkedIn URL": "linkedin_url",
        "City": "city",
        "State": "state",
        "Country": "country",
        "Employment History": "past_companies",
        "Headline": "bio",
    }

    added = 0
    duplicates = 0
    skipped = 0

    for _, raw_row in df.iterrows():
        row = {}
        for orig_col, new_col in col_map.items():
            if orig_col in raw_row.index:
                row[new_col] = str(raw_row[orig_col]) if pd.notna(raw_row[orig_col]) else ""

        # Build location
        parts = [row.get("city", ""), row.get("state", ""), row.get("country", "")]
        row["location"] = ", ".join(p for p in parts if p)

        # Need at least email or linkedin
        if not row.get("email") and not row.get("linkedin_url"):
            skipped += 1
            continue

        row["source"] = "csv"
        success, reason = add_investor(row)
        if success:
            added += 1
        elif "dup" in reason:
            duplicates += 1
        else:
            skipped += 1

    return {"added": added, "duplicates": duplicates, "skipped": skipped}


def get_unscored(limit: int = 100) -> list:
    """Get investors that haven't been scored yet."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM investors WHERE tier = 0 AND status IN ('NEW', 'VERIFIED') ORDER BY created_at LIMIT ?",
        (limit,),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_unverified(limit: int = 100) -> list:
    """Get investors with unverified emails."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM investors WHERE verified = 0 AND email IS NOT NULL AND email != '' ORDER BY created_at LIMIT ?",
        (limit,),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_unresearched(limit: int = 10, min_tier: int = 1, max_tier: int = 2) -> list:
    """Get scored investors that haven't been researched yet."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """SELECT * FROM investors
        WHERE research_confidence = 'LOW'
        AND research_hook IS NULL
        AND tier BETWEEN ? AND ?
        AND status IN ('SCORED', 'VERIFIED')
        ORDER BY score DESC LIMIT ?""",
        (min_tier, max_tier, limit),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_unwritten(limit: int = 25) -> list:
    """Get scored/researched investors without emails written."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """SELECT * FROM investors
        WHERE email_body IS NULL
        AND score > 0
        AND status IN ('SCORED', 'VERIFIED')
        AND (verified = 0 OR email_valid = 1)
        ORDER BY score DESC LIMIT ?""",
        (limit,),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# Initialize DB on import
init_db()


if __name__ == "__main__":
    # Test with mock data
    init_db()

    mock_investors = [
        {
            "email": "sarah@example.com",
            "first_name": "Sarah",
            "last_name": "Chen",
            "title": "Angel Investor, ex-VP Sales",
            "company": "Chen Ventures",
            "past_companies": "Gong, Salesforce",
            "linkedin_url": "https://linkedin.com/in/sarahchen",
            "bio": "Angel investor focused on AI and sales tech",
            "source": "apollo",
        },
        {
            "email": "marcus@homewell.com",
            "first_name": "Marcus",
            "last_name": "Williams",
            "title": "CEO",
            "company": "HomeWell Senior Care",
            "location": "Dallas, TX",
            "source": "apollo",
        },
        {
            "email": "priya@aifund.vc",
            "first_name": "Priya",
            "last_name": "Kumar",
            "title": "Partner",
            "company": "AI Seed Fund",
            "bio": "Pre-seed investor in AI automation and vertical SaaS",
            "source": "apollo",
        },
        {
            "email": "john@techcorp.com",
            "first_name": "John",
            "last_name": "Smith",
            "title": "Senior Designer",
            "company": "TechCorp",
            "source": "csv",
        },
        {
            "email": "lisa@outreach.io",
            "first_name": "Lisa",
            "last_name": "Park",
            "title": "Angel, ex-Head of Revenue",
            "company": "Park Capital",
            "past_companies": "Outreach, HubSpot",
            "linkedin_url": "https://linkedin.com/in/lisapark",
            "bio": "Operator angel. Backed 12 startups in GTM space.",
            "source": "apollo",
        },
    ]

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("ARIA DB TEST — 5 MOCK INVESTORS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    for inv in mock_investors:
        success, result = add_investor(inv)
        status = f"ADDED ({result[:8]})" if success else f"SKIPPED ({result})"
        print(f"  {inv['first_name']} {inv['last_name']:12s} | {status}")

    print("\n  --- DUPLICATE TEST ---")
    for inv in mock_investors[:2]:
        success, result = add_investor(inv)
        status = f"ADDED ({result[:8]})" if success else f"BLOCKED ({result})"
        print(f"  {inv['first_name']} {inv['last_name']:12s} | {status}")

    stats = get_stats()
    print(f"\n  STATS:")
    print(f"    Total: {stats['total']}")
    print(f"    By status: {stats['by_status']}")
    print(f"    Reply rate: {stats['reply_rate']:.1f}%")
    print(f"    Ready today: {stats['ready_today']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
