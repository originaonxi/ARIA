"""
ARIA v1 — Autonomous Relationship Intelligence Agent
Main CLI for investor outreach.

Commands:
  aria run          Full pipeline: find → verify → score → research → write → send
  aria run --auto   Same but skip email preview (send all automatically)
  aria status       Full pipeline dashboard
  aria replies      Check Instantly for new replies, classify, alert on HOT
  aria followup     Process day 5-8 follow-ups
  aria linkedin     Generate HeyReach CSV for today
  aria briefing     Send daily briefing now
  aria load PATH    Manual CSV import fallback
  aria stats        Detailed analytics
  aria verify       Run Millionverifier on unverified emails
  aria score        Score all unscored investors
  aria research N   Research top N Tier 1+2 investors
  aria write N      Write emails for top N scored investors
  aria send         Push today's batch to Instantly
"""

import argparse
import sys
import os
from datetime import datetime

import aria_db as db
from investor_scorer import score_investor
from investor_researcher import research_investor
from investor_writer import write_cold_email, write_linkedin_message, write_followup
from millionverifier import verify_batch
from instantly_client import get_or_create_campaign, add_lead, get_campaign_stats
from airtable_sync import sync_investor
from hunter_client import daily_prospect_harvest
from linkedin_prep import prep_heyreach_csv
from reply_processor import process_replies
from briefing import send_daily_briefing
from config import DATA_DIR, INSTANTLY_CAMPAIGN_ID

# MemCollab — cross-agent shared memory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "memcollab"))
try:
    from memcollab import record as mc_record, Trajectory, Outcome
    MEMCOLLAB_AVAILABLE = True
except ImportError:
    MEMCOLLAB_AVAILABLE = False


def cmd_run(auto: bool = False, per_query: int = 50, send_limit: int = 25):
    """Full pipeline: find → verify → score → research → write → send."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("ARIA RUN — Full Pipeline")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Step 1: Hunter harvest
    print("\n[1/7] FINDING INVESTORS (Hunter)...")
    harvest_stats = daily_prospect_harvest(per_query=per_query)
    print(f"  Found: {harvest_stats['found']} | Added: {harvest_stats['added']} | Dups: {harvest_stats['duplicates']}")

    # Step 2: Verify emails
    print("\n[2/7] VERIFYING EMAILS (Millionverifier)...")
    verify_stats = verify_batch(limit=100)
    print(f"  Valid: {verify_stats['valid']} | Invalid: {verify_stats['invalid']} | Unknown: {verify_stats['unknown']}")

    # Step 3: Score
    print("\n[3/7] SCORING INVESTORS...")
    unscored = db.get_unscored(limit=500)
    tier_counts = {1: 0, 2: 0, 3: 0, 0: 0}
    for inv in unscored:
        scored = score_investor(inv)
        if scored["go"]:
            db.mark_scored(
                inv["id"], scored["tier"], scored["score"],
                scored["investor_type"], scored["channel"],
                scored["personalization_hook"],
            )
            tier_counts[scored["tier"]] = tier_counts.get(scored["tier"], 0) + 1
        else:
            db.update_investor(inv["id"], {"tier": 0, "score": scored.get("score", 0), "status": "SKIPPED"})
            tier_counts[0] += 1
    print(f"  Scored: {len(unscored)} | T1: {tier_counts[1]} | T2: {tier_counts[2]} | T3: {tier_counts[3]} | Skip: {tier_counts[0]}")

    # Step 4: Research Tier 1+2
    print("\n[4/7] RESEARCHING TOP INVESTORS (SerpAPI)...")
    unresearched = db.get_unresearched(limit=10)
    for inv in unresearched:
        result = research_investor(inv)
        db.mark_researched(
            inv["id"],
            result.get("research_hook") or "",
            result.get("research_confidence", "LOW"),
            result.get("recent_activity") or "",
            result.get("portfolio_signal") or "",
        )
    print(f"  Researched: {len(unresearched)} investors")

    # Step 5: Write emails
    print("\n[5/7] WRITING EMAILS (Claude)...")
    unwritten = db.get_unwritten(limit=send_limit)
    written = 0
    for inv in unwritten:
        try:
            email = write_cold_email(inv)
            li_msg = None
            if inv.get("channel") in ("BOTH", "LINKEDIN"):
                li_msg = write_linkedin_message(inv)

            db.mark_written(
                inv["id"],
                email["subject_a"], email["subject_b"],
                email["body"], li_msg,
                email["predicted_reply_tier"],
            )
            written += 1
        except Exception as e:
            print(f"  [write] Error for {inv.get('first_name', '?')}: {e}")
    print(f"  Written: {written} emails")

    # Step 6: Preview and send
    print("\n[6/7] SENDING TO INSTANTLY...")
    ready = db.get_ready_to_contact(limit=send_limit)

    if not ready:
        print("  No investors ready to send.")
    else:
        campaign_id = INSTANTLY_CAMPAIGN_ID or get_or_create_campaign()
        if not campaign_id:
            print("  [send] Could not get/create campaign — skipping send")
        else:
            sent = 0
            for i, inv in enumerate(ready, 1):
                if not auto:
                    # Show preview
                    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    tier_label = {1: "HOT", 2: "WARM", 3: "COLD"}.get(inv["tier"], "?")
                    print(f"INVESTOR [{i}/{len(ready)}] | TIER {inv['tier']} | {tier_label}")
                    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    print(f"{inv['first_name']} {inv['last_name']} | {inv['company']}")
                    print(f"Score: {inv['score']}/10 | Type: {inv['investor_type']}")
                    if inv.get("research_hook"):
                        print(f"Research: \"{inv['research_hook'][:80]}\" ({inv.get('research_confidence', 'LOW')})")
                    print(f"\nSUBJECT A: {inv['subject_a']}")
                    print(f"SUBJECT B: {inv['subject_b']}")
                    print(f"──────────────────────────────────")
                    print(inv["email_body"])
                    print(f"──────────────────────────────────")

                    choice = input("Send? (y/n/s=stop/e=edit subject): ").strip().lower()
                    if choice == "s":
                        print("  Stopping sends.")
                        break
                    elif choice == "n":
                        continue
                    elif choice == "e":
                        new_subj = input("  New subject: ").strip()
                        if new_subj:
                            inv["subject_a"] = new_subj
                            db.update_investor(inv["id"], {"subject_a": new_subj})

                # Send to Instantly
                lead_id = add_lead(campaign_id, inv)
                if lead_id:
                    db.mark_contacted(inv["id"], "EMAIL", inv["subject_a"], inv["email_body"], lead_id)
                    # Sync to Airtable
                    inv_fresh = db.get_investor(inv["id"])
                    airtable_id = sync_investor(inv_fresh)
                    if airtable_id:
                        db.update_investor(inv["id"], {"airtable_id": airtable_id})
                    sent += 1
                    if not auto:
                        print(f"  ✓ Sent to {inv['email']}")
                else:
                    if not auto:
                        print(f"  ✗ Failed for {inv['email']}")

            print(f"\n  Total sent: {sent}/{len(ready)}")

    # Step 7: LinkedIn prep
    print("\n[7/7] LINKEDIN PREP...")
    li_path = prep_heyreach_csv(limit=25)
    if li_path:
        print(f"  HeyReach CSV: {li_path}")

    # Final stats
    print("\n")
    cmd_status()


def cmd_status():
    """Full pipeline dashboard."""
    stats = db.get_stats()
    today = datetime.now().strftime("%B %d, %Y")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"ARIA STATUS — {today}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"\n  Total investors: {stats['total']}")
    print(f"  Verified emails: {stats['verified']}")
    print(f"  Tier 1 (Operator Angels):  {stats['by_tier'].get(1, 0)}")
    print(f"  Tier 2 (SMB Operators):    {stats['by_tier'].get(2, 0)}")
    print(f"  Tier 3 (AI/GTM Investors): {stats['by_tier'].get(3, 0)}")
    print(f"\n  Pipeline:")
    for status, count in stats["by_status"].items():
        if count > 0:
            print(f"    {status:12s}: {count}")
    print(f"\n  Contacted: {stats['contacted']}")
    print(f"  Replied:   {stats['replied']} ({stats['reply_rate']:.1f}%)")
    print(f"  Meetings:  {stats['meetings']} ({stats['meeting_rate']:.1f}%)")
    print(f"\n  Ready to send today: {stats['ready_today']}")
    print(f"  Follow-ups due:      {stats['followups_due']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def _smart_read_file(file_path: str):
    """Read any CSV or Excel file into a list of normalized investor dicts."""
    import re
    import pandas as pd

    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path)

    # ── Column mapping: find the best match for each field ──
    col_lower = {c: c.lower().strip() for c in df.columns}

    def _find_col(*candidates):
        """Find first matching column name (case-insensitive, partial match)."""
        for c, cl in col_lower.items():
            for cand in candidates:
                if cand == cl or cand in cl:
                    return c
        return None

    email_col = _find_col(
        "email", "mail", "e-mail", "email address", "work email",
        "enriched email", "contact_email", "contact email",
        "custom address", "personal email",
    )
    first_col = _find_col("first name", "first_name", "firstname", "first")
    last_col = _find_col("last name", "last_name", "lastname", "last")
    full_name_col = _find_col("full name", "full_name", "fullname", "contact person", "name")
    company_col = _find_col(
        "company", "organization", "firm", "company name",
        "company_name", "account",
    )
    title_col = _find_col(
        "title", "job title", "job_title", "designation",
        "position", "role",
    )
    linkedin_col = _find_col(
        "linkedin", "linkedin url", "linkedin_url",
        "person linkedin url", "profile url", "li url",
    )
    location_col = _find_col(
        "location", "city", "region", "geography",
    )
    bio_col = _find_col(
        "headline", "bio", "about", "summary", "description",
    )

    investors = []
    for _, row in df.iterrows():
        # Extract email — handle "Name <email>" format
        raw_email = ""
        if email_col and pd.notna(row.get(email_col)):
            raw_email = str(row[email_col]).strip()
        email = ""
        if raw_email and "@" in raw_email:
            match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', raw_email)
            if match:
                email = match.group(0).lower()

        # Extract names
        first = ""
        last = ""
        if first_col and pd.notna(row.get(first_col)):
            first = str(row[first_col]).strip()
        if last_col and pd.notna(row.get(last_col)):
            last = str(row[last_col]).strip()
        if not first and full_name_col and pd.notna(row.get(full_name_col)):
            parts = str(row[full_name_col]).strip().split(" ", 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""

        # Skip rows with no name at all
        if not first and not last:
            continue
        # Skip "Team" or "nan" names
        if first.lower() in ("nan", "none", ""):
            continue

        company = ""
        if company_col and pd.notna(row.get(company_col)):
            company = str(row[company_col]).strip()

        title = ""
        if title_col and pd.notna(row.get(title_col)):
            title = str(row[title_col]).strip()

        linkedin = ""
        if linkedin_col and pd.notna(row.get(linkedin_col)):
            val = str(row[linkedin_col]).strip()
            if "linkedin.com" in val:
                linkedin = val

        location = ""
        if location_col and pd.notna(row.get(location_col)):
            location = str(row[location_col]).strip()

        bio = ""
        if bio_col and pd.notna(row.get(bio_col)):
            bio = str(row[bio_col]).strip()[:500]
        if not bio and title and company:
            bio = f"{title} at {company}"

        investors.append({
            "email": email,
            "first_name": first,
            "last_name": last,
            "title": title or "Investor",
            "company": company,
            "linkedin_url": linkedin,
            "location": location,
            "bio": bio,
            "source": os.path.basename(file_path),
        })

    return investors


def load_and_launch(file_path: str):
    """
    One command to do everything:
    Read → Normalize → Dedup → Verify → Score → Write → Create Campaign → Send → Launch
    """
    import requests
    from config import INSTANTLY_API_KEY

    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    filename = os.path.basename(file_path)
    today = datetime.now().strftime("%Y-%m-%d")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"ARIA LOAD — {filename}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ── STEP 1: Read + Normalize ─────────────────────────
    print(f"\n[1/8] READING FILE...")
    investors = _smart_read_file(file_path)
    total_read = len(investors)
    with_email = sum(1 for i in investors if i.get("email"))
    print(f"  Rows: {total_read} | With email: {with_email}")

    # ── STEP 2: Dedup + Insert ───────────────────────────
    print(f"\n[2/8] DEDUPLICATING...")
    added_ids = []
    duplicates = 0
    skipped = 0
    for inv in investors:
        if not inv.get("email") and not inv.get("linkedin_url"):
            skipped += 1
            continue
        success, result = db.add_investor(inv)
        if success:
            added_ids.append(result)
        elif "dup" in result:
            duplicates += 1
        else:
            skipped += 1
    print(f"  Added: {len(added_ids)} | Duplicates: {duplicates} | Skipped: {skipped}")

    if not added_ids:
        print("\n  No new investors to process.")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return

    # ── STEP 3: Verify Emails ────────────────────────────
    print(f"\n[3/8] VERIFYING EMAILS (Millionverifier)...")
    verify_stats = verify_batch(limit=len(added_ids) + 50)
    valid_count = verify_stats["valid"]
    invalid_count = verify_stats["invalid"]
    print(f"  Valid: {valid_count} | Invalid: {invalid_count}")

    # ── STEP 4: Score ────────────────────────────────────
    print(f"\n[4/8] SCORING...")
    unscored = db.get_unscored(limit=5000)
    tier_counts = {1: 0, 2: 0, 3: 0, 0: 0}
    for inv in unscored:
        scored = score_investor(inv)
        if scored["go"]:
            db.mark_scored(
                inv["id"], scored["tier"], scored["score"],
                scored["investor_type"], scored["channel"],
                scored["personalization_hook"],
            )
            tier_counts[scored["tier"]] = tier_counts.get(scored["tier"], 0) + 1
        else:
            db.update_investor(inv["id"], {"tier": 0, "score": scored.get("score", 0), "status": "SKIPPED"})
            tier_counts[0] += 1
    go_count = tier_counts.get(1, 0) + tier_counts.get(2, 0) + tier_counts.get(3, 0)
    print(f"  T1: {tier_counts.get(1, 0)} | T2: {tier_counts.get(2, 0)} | T3: {tier_counts.get(3, 0)} | Skip: {tier_counts.get(0, 0)}")

    # ── STEP 5: Write Emails ─────────────────────────────
    print(f"\n[5/8] WRITING EMAILS (Claude Haiku)...")
    from aria_db import get_unwritten
    unwritten = get_unwritten(limit=500)
    written = 0
    write_errors = 0
    for inv in unwritten:
        try:
            email_data = write_cold_email(inv)
            db.mark_written(
                inv["id"],
                email_data["subject_a"], email_data["subject_b"],
                email_data["body"], None,
                email_data["predicted_reply_tier"],
            )
            written += 1
        except Exception as e:
            write_errors += 1
    print(f"  Written: {written} | Errors: {write_errors}")

    # ── STEP 6: Create Instantly Campaign ─────────────────
    print(f"\n[6/8] CREATING INSTANTLY CAMPAIGN...")
    campaign_name = f"ARIA — {today} — {os.path.splitext(filename)[0]}"

    campaign_id = None
    if INSTANTLY_API_KEY:
        headers = {
            "Authorization": f"Bearer {INSTANTLY_API_KEY}",
            "Content-Type": "application/json",
        }
        # Create campaign
        r = requests.post(
            "https://api.instantly.ai/api/v2/campaigns",
            headers=headers,
            json={
                "name": campaign_name,
                "campaign_schedule": {
                    "schedules": [{
                        "name": "Weekday mornings",
                        "timing": {"from": "09:00", "to": "11:00"},
                        "days": {"1": True, "2": True, "3": True, "4": True, "5": True},
                        "timezone": "America/Detroit",
                    }],
                },
            },
            timeout=15,
        )
        if r.status_code == 200:
            campaign_id = r.json().get("id")
            print(f"  Created: {campaign_name}")

            # Add sequence
            requests.patch(
                f"https://api.instantly.ai/api/v2/campaigns/{campaign_id}",
                headers=headers,
                json={
                    "sequences": [{
                        "steps": [{
                            "type": "email",
                            "delay": 0,
                            "variants": [{
                                "subject": "{{subject_line}}",
                                "body": "{{email_body}}",
                            }],
                        }],
                    }],
                },
                timeout=15,
            )
        else:
            # Fallback: find existing ARIA campaign
            print(f"  Campaign creation failed — using fallback...")
            r2 = requests.get(
                "https://api.instantly.ai/api/v2/campaigns",
                headers=headers,
                params={"limit": 50},
                timeout=15,
            )
            if r2.status_code == 200:
                for c in r2.json().get("items", []):
                    if "ARIA" in c.get("name", ""):
                        campaign_id = c["id"]
                        campaign_name = c["name"]
                        print(f"  Using existing: {campaign_name}")
                        break
    else:
        print("  No Instantly API key — skipping send")

    # ── STEP 7: Add Leads to Campaign ─────────────────────
    pushed = 0
    if campaign_id and INSTANTLY_API_KEY:
        print(f"\n[7/8] PUSHING TO INSTANTLY...")
        ready = db.get_ready_to_contact(limit=500)
        for inv in ready:
            r = requests.post(
                "https://api.instantly.ai/api/v2/leads",
                headers=headers,
                json={
                    "email": inv["email"],
                    "first_name": inv.get("first_name", ""),
                    "last_name": inv.get("last_name", ""),
                    "company_name": inv.get("company", ""),
                    "campaign": campaign_id,
                    "custom_variables": {
                        "subject_line": str(inv.get("subject_a", "")),
                        "email_body": str(inv.get("email_body", "")),
                    },
                },
                timeout=15,
            )
            if r.status_code == 200:
                lead_id = r.json().get("id", "")
                db.mark_contacted(inv["id"], "EMAIL", inv["subject_a"], inv["email_body"], lead_id)
                pushed += 1
        print(f"  Pushed: {pushed}")
    else:
        print(f"\n[7/8] SKIPPED — no campaign available")

    # ── STEP 8: Launch ────────────────────────────────────
    status_text = "READY"
    if campaign_id and pushed > 0 and INSTANTLY_API_KEY:
        print(f"\n[8/8] LAUNCHING CAMPAIGN...")
        r = requests.post(
            f"https://api.instantly.ai/api/v2/campaigns/{campaign_id}/activate",
            headers=headers,
            json={},
            timeout=15,
        )
        if r.status_code == 200:
            status_text = "LAUNCHED"
            print(f"  Campaign is LIVE")
        else:
            status_text = "DRAFT — launch manually in Instantly"
            print(f"  Auto-launch failed ({r.status_code}) — launch manually in Instantly")
    else:
        print(f"\n[8/8] SKIPPED")

    # ── FINAL SUMMARY ─────────────────────────────────────
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("ARIA LOAD COMPLETE")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  File:               {filename}")
    print(f"  Loaded:             {len(added_ids)}")
    print(f"  Duplicates skipped: {duplicates}")
    print(f"  Bad emails removed: {invalid_count}")
    print(f"  Emails written:     {written}")
    print(f"  Campaign created:   {campaign_name}")
    print(f"  Pushed to Instantly:{pushed}")
    print(f"  Status:             {status_text}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_load(csv_path: str):
    """Load CSV/Excel and run full pipeline — verify, score, write, send."""
    load_and_launch(csv_path)


def cmd_verify():
    """Run Millionverifier on unverified emails."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("EMAIL VERIFICATION")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    stats = verify_batch(limit=500)
    print(f"\n  Valid:   {stats['valid']}")
    print(f"  Invalid: {stats['invalid']}")
    print(f"  Unknown: {stats['unknown']}")
    print(f"  Checked: {stats['total_checked']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_score():
    """Score all unscored investors."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("SCORING INVESTORS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    unscored = db.get_unscored(limit=5000)
    tier_counts = {1: 0, 2: 0, 3: 0, 0: 0}

    for inv in unscored:
        scored = score_investor(inv)
        if scored["go"]:
            db.mark_scored(
                inv["id"], scored["tier"], scored["score"],
                scored["investor_type"], scored["channel"],
                scored["personalization_hook"],
            )
        else:
            db.update_investor(inv["id"], {"tier": 0, "score": scored.get("score", 0), "status": "SKIPPED"})
        tier_counts[scored.get("tier", 0)] = tier_counts.get(scored.get("tier", 0), 0) + 1

    print(f"  Scored: {len(unscored)}")
    print(f"  Tier 1 (Operator Angels):  {tier_counts.get(1, 0)}")
    print(f"  Tier 2 (SMB Operators):    {tier_counts.get(2, 0)}")
    print(f"  Tier 3 (AI/GTM Investors): {tier_counts.get(3, 0)}")
    print(f"  Skipped:                   {tier_counts.get(0, 0)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_research(n: int):
    """Research top N Tier 1+2 investors."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"RESEARCHING TOP {n} INVESTORS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    unresearched = db.get_unresearched(limit=n)
    high = medium = low = 0

    for inv in unresearched:
        result = research_investor(inv)
        conf = result.get("research_confidence", "LOW")
        db.mark_researched(
            inv["id"],
            result.get("research_hook") or "",
            conf,
            result.get("recent_activity") or "",
            result.get("portfolio_signal") or "",
        )
        if conf == "HIGH":
            high += 1
        elif conf == "MEDIUM":
            medium += 1
        else:
            low += 1

    print(f"\n  Researched: {len(unresearched)}")
    print(f"  HIGH confidence:   {high}")
    print(f"  MEDIUM confidence: {medium}")
    print(f"  LOW confidence:    {low}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_write(n: int):
    """Write emails for top N scored investors."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"WRITING EMAILS FOR TOP {n}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    unwritten = db.get_unwritten(limit=n)
    written = 0

    for inv in unwritten:
        name = f"{inv.get('first_name', '')} {inv.get('last_name', '')}"
        print(f"\n  Writing for {name}...")
        try:
            email = write_cold_email(inv)
            li_msg = None
            if inv.get("channel") in ("BOTH", "LINKEDIN"):
                li_msg = write_linkedin_message(inv)

            # Show preview
            print(f"  Subject A: {email['subject_a']}")
            print(f"  Subject B: {email['subject_b']}")
            print(f"  ──────────────────────────────────")
            print(f"  {email['body']}")
            print(f"  ──────────────────────────────────")

            choice = input("  Save? (y/n): ").strip().lower()
            if choice == "y":
                db.mark_written(
                    inv["id"],
                    email["subject_a"], email["subject_b"],
                    email["body"], li_msg,
                    email["predicted_reply_tier"],
                )
                written += 1
                print(f"  ✓ Saved")
            else:
                print(f"  Skipped")
        except Exception as e:
            print(f"  Error: {e}")

    print(f"\n  Written: {written}/{len(unwritten)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_send(dry_run: bool = False):
    """Push today's batch to Instantly."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if dry_run:
        print("SEND — DRY RUN (nothing will be sent)")
    else:
        print("SENDING TO INSTANTLY")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    ready = db.get_ready_to_contact(limit=25)
    if not ready:
        print("  No investors ready to send.")
        return

    print(f"  {len(ready)} investors ready\n")

    if dry_run:
        for i, inv in enumerate(ready, 1):
            tier_label = {1: "HOT", 2: "WARM", 3: "COLD"}.get(inv["tier"], "?")
            print(f"  [{i:2d}] {inv['first_name']:10s} {inv['last_name']:12s} | {inv['company']:20s} | T{inv['tier']} {tier_label} | {inv['score']}/10")
            print(f"       Subject: {inv.get('subject_a', 'N/A')}")
        print(f"\n  Would send {len(ready)} emails. Run without --dry-run to send.")
        return

    campaign_id = INSTANTLY_CAMPAIGN_ID or get_or_create_campaign()
    if not campaign_id:
        print("  Could not get/create campaign.")
        return

    sent = 0
    for inv in ready:
        lead_id = add_lead(campaign_id, inv)
        if lead_id:
            db.mark_contacted(inv["id"], "EMAIL", inv["subject_a"], inv["email_body"], lead_id)
            inv_fresh = db.get_investor(inv["id"])
            airtable_id = sync_investor(inv_fresh)
            if airtable_id:
                db.update_investor(inv["id"], {"airtable_id": airtable_id})
            sent += 1
            print(f"  ✓ {inv['email']}")

            # MemCollab: log trajectory for cross-agent learning
            if MEMCOLLAB_AVAILABLE:
                try:
                    defense = inv.get("defense_profile") or {}
                    traj = Trajectory(
                        agent="ARIA",
                        model_used="claude-haiku-4-5-20251001",
                        profile_text=f"{inv.get('first_name','')} {inv.get('last_name','')} {inv.get('company','')}",
                        defense_mode=defense.get("defense_mode", "MOTIVE_INFERENCE"),
                        pkm_confidence=defense.get("awareness_score", 5) / 10.0,
                        awareness_score=defense.get("awareness_score", 5),
                        bypass_strategy=defense.get("bypass_strategy", "PURE_DATA"),
                        channel="email",
                        message_text=inv.get("email_body", ""),
                        message_word_count=len(inv.get("email_body", "").split()),
                        outcome=Outcome.NO_REPLY,
                        vertical="vc",
                        icp_tier=str(inv.get("tier", "")),
                    )
                    mc_record(traj)
                except Exception:
                    pass
        else:
            print(f"  ✗ {inv['email']}")

    print(f"\n  Sent: {sent}/{len(ready)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_followup():
    """Process follow-ups for day 5-8 no-reply investors."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("FOLLOW-UPS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    candidates = db.get_followup_candidates()

    if not candidates:
        print("  No follow-up candidates right now.")
        return

    print(f"  {len(candidates)} candidates\n")
    campaign_id = INSTANTLY_CAMPAIGN_ID or get_or_create_campaign()
    sent = 0

    for inv in candidates:
        name = f"{inv['first_name']} {inv['last_name']}"
        print(f"  {name} | {inv['company']} | T{inv['tier']}")

        try:
            fu = write_followup(inv, followup_num=1)
            print(f"    Subject: {fu['subject']}")
            print(f"    {fu['body'][:100]}...")

            choice = input("    Send follow-up? (y/n): ").strip().lower()
            if choice == "y" and campaign_id:
                inv["subject_a"] = fu["subject"]
                inv["email_body"] = fu["body"]
                lead_id = add_lead(campaign_id, inv)
                if lead_id:
                    db.mark_contacted(inv["id"], "EMAIL", fu["subject"], fu["body"], lead_id)
                    sent += 1
                    print(f"    ✓ Sent")
        except Exception as e:
            print(f"    Error: {e}")

    print(f"\n  Follow-ups sent: {sent}/{len(candidates)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_replies():
    """Check Instantly for new replies."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("CHECKING REPLIES")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    stats = process_replies(INSTANTLY_CAMPAIGN_ID)
    print(f"\n  Processed:  {stats['processed']}")
    print(f"  Interested: {stats['interested']}")
    print(f"  Objections: {stats['objections']}")
    print(f"  Other:      {stats['other']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_linkedin():
    """Generate HeyReach CSV."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("LINKEDIN PREP")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    path = prep_heyreach_csv(limit=25)
    if path:
        print(f"  Output: {path}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_stats():
    """Detailed analytics."""
    stats = db.get_stats()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("ARIA ANALYTICS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Reply rate by tier
    conn = db._connect()
    c = conn.cursor()
    for tier in (1, 2, 3):
        c.execute("SELECT COUNT(*) FROM investors WHERE tier = ? AND status = 'CONTACTED'", (tier,))
        contacted = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM investors WHERE tier = ? AND replied = 1", (tier,))
        replied = c.fetchone()[0]
        total_t = contacted + replied
        rate = (replied / total_t * 100) if total_t > 0 else 0
        print(f"  Tier {tier}: {replied}/{total_t} replied ({rate:.1f}%)")

    # Reply rate by investor type
    print()
    c.execute("SELECT DISTINCT investor_type FROM investors WHERE investor_type IS NOT NULL")
    types = [r[0] for r in c.fetchall()]
    for itype in types:
        c.execute("SELECT COUNT(*) FROM investors WHERE investor_type = ? AND email_count > 0", (itype,))
        contacted = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM investors WHERE investor_type = ? AND replied = 1", (itype,))
        replied = c.fetchone()[0]
        rate = (replied / contacted * 100) if contacted > 0 else 0
        print(f"  {itype}: {replied}/{contacted} ({rate:.1f}%)")

    conn.close()

    # Projections
    if stats["contacted"] > 0:
        print(f"\n  Current reply rate: {stats['reply_rate']:.1f}%")
        projected_replies = int(2250 * stats["reply_rate"] / 100)
        projected_meetings = int(projected_replies * 0.25)
        print(f"  Projected replies (90 days): {projected_replies}")
        print(f"  Projected meetings (90 days): {projected_meetings}")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def main():
    parser = argparse.ArgumentParser(
        description="ARIA v1 — Autonomous Relationship Intelligence Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Full pipeline")
    p_run.add_argument("--auto", action="store_true", help="Skip email preview")
    p_run.add_argument("--per-query", type=int, default=50, help="Results per Apollo query")
    p_run.add_argument("--limit", type=int, default=25, help="Max emails to send")

    # status
    sub.add_parser("status", help="Pipeline dashboard")

    # load
    p_load = sub.add_parser("load", help="Import CSV")
    p_load.add_argument("path", help="Path to CSV file")

    # verify
    sub.add_parser("verify", help="Verify emails")

    # score
    sub.add_parser("score", help="Score investors")

    # research
    p_research = sub.add_parser("research", help="Research investors")
    p_research.add_argument("n", type=int, help="Number to research")

    # write
    p_write = sub.add_parser("write", help="Write emails")
    p_write.add_argument("n", type=int, help="Number to write")

    # send
    p_send = sub.add_parser("send", help="Send to Instantly")
    p_send.add_argument("--dry-run", action="store_true", help="Show what would be sent")

    # followup
    sub.add_parser("followup", help="Process follow-ups")

    # replies
    sub.add_parser("replies", help="Check for replies")

    # linkedin
    sub.add_parser("linkedin", help="Generate HeyReach CSV")

    # briefing
    sub.add_parser("briefing", help="Send daily briefing")

    # stats
    sub.add_parser("stats", help="Detailed analytics")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(auto=args.auto, per_query=args.per_query, send_limit=args.limit)
    elif args.command == "status":
        cmd_status()
    elif args.command == "load":
        cmd_load(args.path)
    elif args.command == "verify":
        cmd_verify()
    elif args.command == "score":
        cmd_score()
    elif args.command == "research":
        cmd_research(args.n)
    elif args.command == "write":
        cmd_write(args.n)
    elif args.command == "send":
        cmd_send(dry_run=args.dry_run)
    elif args.command == "followup":
        cmd_followup()
    elif args.command == "replies":
        cmd_replies()
    elif args.command == "linkedin":
        cmd_linkedin()
    elif args.command == "briefing":
        send_daily_briefing()
    elif args.command == "stats":
        cmd_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
