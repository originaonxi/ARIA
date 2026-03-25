"""
ARIA Reply Processor — classifies investor replies using Claude.
Updates SQLite + Airtable. Sends HOT alerts to owner.
"""

import json
import os
import sys
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText

import anthropic

from config import ANTHROPIC_API_KEY, OWNER_EMAIL, SMTP_USER, SMTP_PASS
from aria_db import get_investor_by_email, mark_replied, update_investor
from instantly_client import get_new_replies
from airtable_sync import update_status

# MemCollab — update trajectory outcomes on reply
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "memcollab"))
try:
    from memcollab import update_outcome as mc_update_outcome, Outcome
    MEMCOLLAB_AVAILABLE = True
except ImportError:
    MEMCOLLAB_AVAILABLE = False

# Map ARIA sentiment → MemCollab Outcome
SENTIMENT_TO_OUTCOME = {
    "INTERESTED": "HOT",
    "OBJECTION": "OBJECTION",
    "NOT_NOW": "NOT_NOW",
    "NEGATIVE": "UNSUBSCRIBE",
    "REFERRAL": "NOT_NOW",
    "AUTO_REPLY": None,  # skip — not a real response
    "UNKNOWN": None,
}

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

CLASSIFY_PROMPT = """Classify this investor reply into exactly one category.
Return JSON only:
{{"sentiment": "CATEGORY", "key_phrase": "most important phrase from the reply"}}

Categories:
INTERESTED: wants to learn more, asks questions, positive tone, wants to chat
OBJECTION: too early, wrong thesis, no budget, wrong stage
NOT_NOW: follow up later, wrong timing, maybe later
REFERRAL: suggests talking to someone else instead
NEGATIVE: not interested, remove me, harsh tone
AUTO_REPLY: out of office, auto-response, vacation

Reply text:
{reply_text}"""


def classify_reply(reply_text: str) -> dict:
    """
    Classify reply sentiment using Claude.
    Returns: {sentiment, key_phrase}
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        messages=[{
            "role": "user",
            "content": CLASSIFY_PROMPT.format(reply_text=reply_text),
        }],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {"sentiment": "UNKNOWN", "key_phrase": raw[:100]}


def send_hot_alert(investor: dict, reply_text: str, sentiment: str):
    """Send email alert to owner for HOT (INTERESTED) replies."""
    if not SMTP_USER or not SMTP_PASS or not OWNER_EMAIL:
        print("  [alert] SMTP not configured — printing alert instead")
        print(f"  🔥 HOT REPLY from {investor.get('first_name', '')} {investor.get('last_name', '')}!")
        print(f"     {reply_text[:200]}")
        return

    first = investor.get("first_name", "")
    last = investor.get("last_name", "")
    company = investor.get("company", "")
    tier = investor.get("tier", "?")
    score = investor.get("score", "?")
    inv_type = investor.get("investor_type", "")
    linkedin = investor.get("linkedin_url", "")

    subject = f"🔥 INVESTOR REPLY — {first} {last} {company}"

    body = f"""{first} {last} at {company} replied to ARIA.
Tier: {tier} | Score: {score}/10 | Type: {inv_type}

Their message:
"{reply_text}"

Book now:
calendar.app.google/gZ6V9ry93SQizZye8
"""

    if linkedin:
        body += f"\nTheir LinkedIn: {linkedin}\n"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = OWNER_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, OWNER_EMAIL, msg.as_string())
        print(f"  [alert] HOT alert sent to {OWNER_EMAIL}")
    except Exception as e:
        print(f"  [alert] Failed to send alert: {e}")


def process_replies(campaign_id: str = None) -> dict:
    """
    Fetch replies from Instantly. Classify each.
    Update DB + Airtable. Alert on HOT.
    Returns stats.
    """
    replies = get_new_replies(campaign_id)
    processed = 0
    interested = 0
    objections = 0
    other = 0

    if not replies:
        print("  No new replies found.")
        return {"processed": 0, "interested": 0, "objections": 0, "other": 0}

    for reply in replies:
        reply_email = reply.get("from_email") or reply.get("email") or ""
        reply_text = reply.get("body") or reply.get("text") or reply.get("snippet") or ""

        if not reply_email or not reply_text:
            continue

        # Find investor in DB
        investor = get_investor_by_email(reply_email)
        if not investor:
            print(f"  [reply] Unknown sender: {reply_email} — skipping")
            continue

        # Skip if already processed
        if investor.get("replied"):
            continue

        # Classify
        result = classify_reply(reply_text)
        sentiment = result.get("sentiment", "UNKNOWN")
        key_phrase = result.get("key_phrase", "")
        print(f"  {reply_email}: {sentiment} — \"{key_phrase}\"")

        # Update DB
        mark_replied(investor["id"], reply_text[:500], sentiment)

        # Update Airtable
        if investor.get("airtable_id"):
            update_status(
                investor["airtable_id"],
                "REPLIED",
                replied=True,
            )

        # MemCollab: update trajectory outcome
        if MEMCOLLAB_AVAILABLE:
            try:
                tid = investor.get("memcollab_tid") or ""
                if tid:
                    mc_outcome = SENTIMENT_TO_OUTCOME.get(sentiment)
                    if mc_outcome:
                        mc_update_outcome(
                            tid, mc_outcome,
                            reply_text=reply_text[:200],
                            latency_hours=0.0,
                        )
            except Exception:
                pass

        # Alert on INTERESTED
        if sentiment == "INTERESTED":
            interested += 1
            send_hot_alert(investor, reply_text, sentiment)
        elif sentiment == "OBJECTION":
            objections += 1
        else:
            other += 1

        processed += 1

    return {
        "processed": processed,
        "interested": interested,
        "objections": objections,
        "other": other,
    }


if __name__ == "__main__":
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("REPLY PROCESSOR TEST")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    test_replies = [
        "This sounds interesting! Can you share more about how the autonomous agent works? Happy to chat next week.",
        "Thanks for reaching out but we're not investing in pre-seed right now. Try us again in Q3.",
        "Out of office until March 30th. Will respond when I return.",
        "Please remove me from your list.",
        "You should talk to my partner Jake — he covers AI/automation deals. jake@firm.vc",
    ]
    for reply in test_replies:
        result = classify_reply(reply)
        print(f"\n  Reply: \"{reply[:60]}...\"")
        print(f"  → {result['sentiment']}: \"{result['key_phrase']}\"")
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
