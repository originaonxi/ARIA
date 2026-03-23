"""
ARIA Daily Briefing — 7am email to owner with full pipeline status.
"""

import smtplib
from datetime import datetime
from email.mime.text import MIMEText

from config import OWNER_EMAIL, SMTP_USER, SMTP_PASS, INSTANTLY_CAMPAIGN_ID
from aria_db import get_stats, get_followup_candidates
from instantly_client import get_campaign_stats


def build_briefing() -> str:
    """Build the daily briefing text."""
    stats = get_stats()
    today = datetime.now().strftime("%B %d, %Y")

    # Try to get Instantly stats
    instantly = {}
    if INSTANTLY_CAMPAIGN_ID:
        instantly = get_campaign_stats(INSTANTLY_CAMPAIGN_ID)

    sent_total = instantly.get("sent", 0)
    opens = instantly.get("opens", 0)
    open_rate = instantly.get("open_rate", 0)
    reply_count = instantly.get("replies", 0)
    reply_rate_inst = instantly.get("reply_rate", 0)
    bounces = instantly.get("bounces", 0)

    followups = get_followup_candidates()

    # Hot replies from last 24 hours
    from aria_db import _connect
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """SELECT first_name, last_name, company, reply_text, reply_sentiment
        FROM investors
        WHERE replied = 1 AND reply_sentiment = 'INTERESTED'
        AND updated_at >= datetime('now', '-1 day')
        ORDER BY updated_at DESC LIMIT 5"""
    )
    hot_replies = [dict(r) for r in c.fetchall()]
    conn.close()

    lines = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"ARIA DAILY — {today}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("PIPELINE")
    lines.append(f"  Investors in DB: {stats['total']} (verified: {stats['verified']})")
    lines.append(f"  Tier 1: {stats['by_tier'].get(1, 0)} | Tier 2: {stats['by_tier'].get(2, 0)} | Tier 3: {stats['by_tier'].get(3, 0)}")
    lines.append(f"  Total contacted: {stats['contacted']}")
    lines.append(f"  Replied: {stats['replied']} (reply rate: {stats['reply_rate']:.1f}%)")
    lines.append(f"  Meetings booked: {stats['meetings']}")
    lines.append("")
    lines.append("TODAY")
    lines.append(f"  Ready to send: {stats['ready_today']}")
    lines.append(f"  Follow-ups due: {len(followups)}")
    lines.append("")

    if sent_total or INSTANTLY_CAMPAIGN_ID:
        lines.append("INSTANTLY STATS")
        lines.append(f"  Sent (all time): {sent_total}")
        lines.append(f"  Opens: {opens} ({open_rate}%) | Replies: {reply_count} ({reply_rate_inst}%)")
        lines.append(f"  Bounces: {bounces}")
        lines.append("")

    lines.append("HOT REPLIES (last 24hrs)")
    if hot_replies:
        for hr in hot_replies:
            name = f"{hr.get('first_name', '')} {hr.get('last_name', '')}"
            company = hr.get("company", "")
            preview = (hr.get("reply_text") or "")[:80]
            lines.append(f"  {name} | {company} | \"{preview}\"")
    else:
        lines.append("  No new HOT replies. Keep sending.")
    lines.append("")

    lines.append("YOUR ACTION:")
    lines.append("  Run: python aria.py run")
    lines.append("  Finds → Verifies → Scores → Researches → Writes → Sends")
    lines.append("  All automatic. 25 investors today.")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def send_daily_briefing():
    """Build and send the daily briefing email."""
    briefing = build_briefing()

    # Always print to console
    print(briefing)

    # Send via email if configured
    if not SMTP_USER or not SMTP_PASS or not OWNER_EMAIL:
        print("\n  [briefing] SMTP not configured — printed to console only")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    stats = get_stats()
    subject = f"ARIA Daily — {today} — {stats['contacted']} sent {stats['replied']} replies"

    msg = MIMEText(briefing)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = OWNER_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, OWNER_EMAIL, msg.as_string())
        print(f"\n  [briefing] Sent to {OWNER_EMAIL}")
    except Exception as e:
        print(f"\n  [briefing] Email failed: {e}")
        print("  Briefing printed to console above.")


if __name__ == "__main__":
    send_daily_briefing()
