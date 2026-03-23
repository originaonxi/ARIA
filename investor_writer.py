"""
ARIA Investor Writer — Claude writes 3-sentence cold emails.
Michael Seibel structure: traction, why this investor, the ask.
Model: claude-haiku-4-5-20251001
"""

import json
import anthropic

from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You write angel investor cold emails for Anmol Sam, CTO of Aonxi.

Michael Seibel's 3-sentence structure:
Sentence 1: What Aonxi does + traction proof — lead with the number
Sentence 2: Why THIS investor specifically — use their hook
Sentence 3: The ask — 20 minutes, no deck

AONXI REAL NUMBERS (never change, never add, never fabricate):
$650,458 ARR in 5 months from $0 raised
40 customers | fully autonomous | zero sales reps
AROS built in 1 day: $0.50/day vs Gong $100,000/year
3,016 prospects scored | $455K pipeline
Code is public: github.com/originaonxi/aros-agent

HARD RULES:
1. Under 100 words. Hard limit.
2. First sentence leads with money or first name.
3. Never use: revolutionary, game-changing, disrupting, disruptive, cutting-edge, world-class, transformative, innovative, groundbreaking, state-of-the-art.
4. Never fabricate any number or claim.
5. Sign off with:
   Anmol
   origin@aonxi.com
   calendar.app.google/gZ6V9ry93SQizZye8
6. Return valid JSON only:
   {"subject_a": "...", "subject_b": "...", "body": "..."}
7. No markdown, no code fences, just raw JSON."""

FOLLOWUP_SYSTEM = """You write follow-up emails for Anmol Sam, CTO of Aonxi.

RULES:
1. Under 75 words. Hard limit.
2. NEW data point — never repeat the first email.
3. No pleasantries. No "just following up." No "checking in."
4. Lead with something new — a milestone, a shipped feature, a new customer.
5. Same sign-off: Anmol, origin@aonxi.com, calendar.app.google/gZ6V9ry93SQizZye8
6. Return valid JSON only: {"subject": "...", "body": "..."}
7. No markdown, no code fences, just raw JSON.

AONXI REAL NUMBERS (never change):
$650,458 ARR | 5 months | $0 raised | 40 customers
AROS: $0.50/day vs Gong $100K/yr | Code is public"""

LINKEDIN_SYSTEM = """You write LinkedIn connection messages for Anmol Sam, CTO of Aonxi.

RULES:
1. MAX 300 characters. Hard limit.
2. Lead with traction. No links.
3. One sentence about why them. One sentence traction. Ask for 20 min.
4. No pleasantries. Get to it.
5. Return plain text only — no JSON, no quotes.

AONXI: $650K ARR, 5 months, $0 raised, 40 customers, fully autonomous."""


def _parse_json(raw: str) -> dict:
    """Parse JSON from Claude response, handling code fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    return json.loads(text)


def write_cold_email(investor: dict) -> dict:
    """
    Write a cold email for an investor.
    Uses best hook available based on research confidence.
    Returns: {subject_a, subject_b, body}
    """
    first = investor.get("first_name", "")
    last = investor.get("last_name", "")
    company = investor.get("company", "")
    tier = investor.get("tier", 3)
    investor_type = investor.get("investor_type", "")
    research_conf = investor.get("research_confidence", "LOW")
    research_hook = investor.get("research_hook") or ""
    pers_hook = investor.get("personalization_hook") or ""

    # Pick best hook
    if research_conf == "HIGH" and research_hook:
        hook = research_hook
    elif research_conf == "MEDIUM" and research_hook:
        hook = research_hook
    else:
        hook = pers_hook

    user_prompt = f"""Write a cold email to this angel investor:

Name: {first} {last}
Company: {company}
Tier: {tier} (1=operator angel, 2=SMB operator, 3=AI/GTM investor)
Type: {investor_type}
Research confidence: {research_conf}

WHY THIS INVESTOR (use this as sentence 2):
{hook}

Return JSON: {{"subject_a": "...", "subject_b": "...", "body": "..."}}

Subject A should be traction-focused (e.g. "$650K ARR, 5 months, $0 raised")
Subject B should be personal (e.g. "{first} — autonomous agent, Gong for $0.50")"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    data = _parse_json(response.content[0].text)

    # Determine reply tier
    if tier == 1 and research_conf in ("HIGH", "MEDIUM"):
        reply_tier = "HOT"
    elif tier == 1:
        reply_tier = "WARM"
    elif tier == 2:
        reply_tier = "WARM"
    else:
        reply_tier = "COLD"

    return {
        "subject_a": data.get("subject_a", ""),
        "subject_b": data.get("subject_b", ""),
        "body": data.get("body", ""),
        "predicted_reply_tier": reply_tier,
    }


def write_linkedin_message(investor: dict) -> str:
    """Write a LinkedIn connection message. MAX 300 chars."""
    first = investor.get("first_name", "")
    company = investor.get("company", "")
    hook = investor.get("personalization_hook") or investor.get("research_hook") or ""

    user_prompt = f"""Write a LinkedIn connection message to:
Name: {first}
Company: {company}
Hook: {hook}

MAX 300 characters. Plain text only."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        system=LINKEDIN_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    msg = response.content[0].text.strip().strip('"')
    # Enforce 300 char limit
    if len(msg) > 300:
        msg = msg[:297] + "..."
    return msg


def write_followup(investor: dict, followup_num: int = 1) -> dict:
    """
    Write a follow-up email. Under 75 words. New data point.
    Returns: {subject, body}
    """
    first = investor.get("first_name", "")
    company = investor.get("company", "")

    options = [
        "AROS went live — sent its first real emails to home care owners in New York yesterday. Everything is public: github.com/originaonxi/aros-agent",
        "Quick update — new customer closed this week. ARR climbing past $650K. Would love 20 minutes.",
        "Shipped v1 to v5 roadmap yesterday. Vision: $499/mo replacing $305K/yr GTM stack for 400M SMBs. Worth 20 minutes?",
    ]
    data_point = options[(followup_num - 1) % len(options)]

    user_prompt = f"""Write follow-up #{followup_num} to:
Name: {first}
Company: {company}

Use this NEW data point (do not copy verbatim, rephrase naturally):
{data_point}

Under 75 words. Return JSON: {{"subject": "...", "body": "..."}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=FOLLOWUP_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return _parse_json(response.content[0].text)


if __name__ == "__main__":
    test_investors = [
        {
            "first_name": "Sarah", "last_name": "Chen",
            "company": "Chen Ventures", "tier": 1,
            "investor_type": "OPERATOR_ANGEL",
            "research_confidence": "HIGH",
            "research_hook": "Saw your recent post about the death of cold calling — that is exactly the problem we are solving at Aonxi.",
            "personalization_hook": "Given your time at Gong, you have seen exactly what enterprise GTM costs.",
        },
        {
            "first_name": "Marcus", "last_name": "Williams",
            "company": "HomeWell Senior Care", "tier": 2,
            "investor_type": "SMB_OPERATOR",
            "research_confidence": "MEDIUM",
            "research_hook": "Given your franchise expansion (3 new locations in 2025), what we are building will feel familiar.",
            "personalization_hook": "As someone running HomeWell Senior Care, you know the client acquisition problem personally.",
        },
        {
            "first_name": "Priya", "last_name": "Kumar",
            "company": "AI Seed Fund", "tier": 3,
            "investor_type": "AI_GTM_INVESTOR",
            "research_confidence": "LOW",
            "research_hook": None,
            "personalization_hook": "Given your focus on AI automation, I thought Aonxi would be worth your time.",
        },
    ]

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("WRITER TEST — 3 INVESTOR PROFILES")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for inv in test_investors:
        name = f"{inv['first_name']} {inv['last_name']}"
        print(f"\n  {name} | Tier {inv['tier']} | {inv['research_confidence']}")

        # Cold email
        email = write_cold_email(inv)
        print(f"\n  SUBJECT A: {email['subject_a']}")
        print(f"  SUBJECT B: {email['subject_b']}")
        print(f"  REPLY TIER: {email['predicted_reply_tier']}")
        print(f"  ─────────────────────────────────")
        for line in email["body"].split("\n"):
            print(f"  {line}")
        print(f"  ─────────────────────────────────")

        # LinkedIn
        li_msg = write_linkedin_message(inv)
        print(f"\n  LINKEDIN ({len(li_msg)} chars):")
        print(f"  {li_msg}")

        # Follow-up
        fu = write_followup(inv, followup_num=1)
        print(f"\n  FOLLOW-UP:")
        print(f"  Subject: {fu['subject']}")
        print(f"  ─────────────────────────────────")
        for line in fu["body"].split("\n"):
            print(f"  {line}")
        print(f"  ─────────────────────────────────")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
