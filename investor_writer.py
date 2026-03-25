"""
ARIA Investor Writer — Claude writes 3-sentence cold emails.
Michael Seibel structure: traction, why this investor, the ask.
Model: claude-haiku-4-5-20251001
"""

import json
import sys
import os
import anthropic

from config import ANTHROPIC_API_KEY

# MemCollab — cross-agent shared memory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "memcollab"))
try:
    from memcollab import build_memory_injection
    MEMCOLLAB_AVAILABLE = True
except ImportError:
    MEMCOLLAB_AVAILABLE = False

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


# ── Defense Profiling ─────────────────────────────────────────────

GTM_COMPANIES = {
    "gong", "outreach", "salesloft", "hubspot", "salesforce", "apollo",
    "zoominfo", "chorus", "clari", "drift", "intercom", "sendoso",
    "6sense", "bombora", "demandbase", "seismic", "highspot", "clearbit",
}

DEFENSE_PROFILES = {
    "MOTIVE_INFERENCE": {
        "title_signals": {"partner", "vp", "director", "founder", "managing", "general partner", "gp"},
        "bypass_strategy": "PURE_DATA",
        "forbidden_phrases": [
            "excited", "reach out", "love to", "synergy", "opportunity",
            "quick call", "touching base", "circle back", "on your radar",
        ],
    },
    "TACTIC_RECOGNITION": {
        "title_signals": {"founder", "co-founder", "serial entrepreneur", "repeat founder"},
        "bypass_strategy": "SIGNAL_HOOK",
        "forbidden_phrases": [
            "I noticed you", "I came across", "relevant to your work",
            "fellow founder", "as a fellow", "I saw that you",
            "your impressive", "your amazing",
        ],
    },
    "OVERLOAD_AVOIDANCE": {
        "title_signals": {"ceo", "owner", "operator", "president", "managing director"},
        "bypass_strategy": "PURE_DATA",
        "forbidden_phrases": [
            "just wanted to", "hope this finds you", "I know you're busy",
            "when you get a chance", "at your convenience", "quick question",
        ],
    },
    "SOCIAL_PROOF_SKEPTICISM": {
        "title_signals": {"cto", "engineer", "vp engineering", "technical", "data", "architect"},
        "bypass_strategy": "CREDIBILITY_FIRST",
        "forbidden_phrases": [
            "industry-leading", "best-in-class", "proven", "trusted by",
            "world-class", "top-tier", "leading provider", "market leader",
        ],
    },
}

BYPASS_INSTRUCTIONS = {
    "PURE_DATA": "Open with a concrete number. Never open with 'I'. Lead with verifiable data. No persuasion language — let the numbers do the work.",
    "SIGNAL_HOOK": "Open by referencing something specific from the last 7 days — their post, their hire, their funding news. Prove you did real research, not a template merge.",
    "CREDIBILITY_FIRST": "Open with exact numbers and a public-verifiable proof point (GitHub link, public metric). No round numbers. No unverifiable claims.",
}


def _estimate_cold_email_volume(investor: dict) -> int:
    """Estimate how many cold emails this person gets per week."""
    title = (investor.get("investor_type") or investor.get("title") or "").lower()
    tier = investor.get("tier", 3)
    if tier == 1 or "partner" in title or "managing" in title:
        return 200
    elif tier == 2 or "founder" in title:
        return 100
    return 50


def _detect_defense_mode(investor: dict) -> str:
    """Detect primary defense mode from investor profile."""
    title = (investor.get("investor_type") or investor.get("title") or "").lower()
    company = (investor.get("company") or "").lower()

    # Check GTM/sales background → MOTIVE_INFERENCE
    if company in GTM_COMPANIES:
        return "MOTIVE_INFERENCE"

    # Check title signals in priority order
    for mode in ["SOCIAL_PROOF_SKEPTICISM", "MOTIVE_INFERENCE", "TACTIC_RECOGNITION", "OVERLOAD_AVOIDANCE"]:
        profile = DEFENSE_PROFILES[mode]
        for signal in profile["title_signals"]:
            if signal in title:
                return mode

    # Fallback: VCs and investors default to MOTIVE_INFERENCE
    if any(kw in title for kw in ("investor", "angel", "vc", "venture", "capital")):
        return "MOTIVE_INFERENCE"

    return "MOTIVE_INFERENCE"


def profile_defenses(target: dict) -> dict:
    """
    Profile a target's psychological defenses against cold outreach.
    Returns awareness_score, defense_mode, bypass_strategy, forbidden_phrases.
    """
    title = (target.get("investor_type") or target.get("title") or "").lower()
    company = (target.get("company") or "").lower()
    tier = target.get("tier", 3)

    # Awareness score: 0-10
    score = 3  # baseline
    if tier == 1:
        score += 3
    elif tier == 2:
        score += 1
    if company in GTM_COMPANIES:
        score += 3
    if any(kw in title for kw in ("partner", "vp", "director", "managing")):
        score += 2
    if any(kw in title for kw in ("founder", "ceo", "cto")):
        score += 1
    estimated_volume = _estimate_cold_email_volume(target)
    if estimated_volume >= 200:
        score += 1
    score = min(score, 10)

    defense_mode = _detect_defense_mode(target)
    profile = DEFENSE_PROFILES[defense_mode]

    return {
        "awareness_score": score,
        "defense_mode": defense_mode,
        "bypass_strategy": profile["bypass_strategy"],
        "forbidden_phrases": profile["forbidden_phrases"],
        "estimated_weekly_cold_emails": estimated_volume,
    }


def _parse_json(raw: str) -> dict:
    """Parse JSON from Claude response, handling code fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    return json.loads(text)


def write_cold_email(investor: dict, use_defense_profiling: bool = True) -> dict:
    """
    Write a cold email for an investor.
    Uses best hook available based on research confidence.
    When use_defense_profiling=True, applies defense-aware bypass strategy.
    Returns: {subject_a, subject_b, body, predicted_reply_tier, defense_profile}
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

    # Defense profiling
    defense = profile_defenses(investor) if use_defense_profiling else None

    # Build system prompt with defense layer
    system = SYSTEM_PROMPT
    if defense:
        banned = ", ".join(f'"{p}"' for p in defense["forbidden_phrases"])
        bypass_instruction = BYPASS_INSTRUCTIONS[defense["bypass_strategy"]]
        system += f"""

DEFENSE PROFILE (awareness: {defense['awareness_score']}/10, mode: {defense['defense_mode']}):
BANNED WORDS — never use any of these phrases: {banned}
WRITING STRATEGY: {bypass_instruction}"""

    # MemCollab: inject cross-agent learned patterns
    if defense and MEMCOLLAB_AVAILABLE:
        memory_ctx = build_memory_injection(defense["defense_mode"], vertical="vc")
        if memory_ctx:
            system += memory_ctx

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
        system=system,
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
        "defense_profile": defense,
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
    print("DEFENSE PROFILING TEST — 3 INVESTORS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for inv in test_investors:
        name = f"{inv['first_name']} {inv['last_name']}"
        print(f"\n{'='*50}")
        print(f"  {name} | Tier {inv['tier']} | {inv['research_confidence']}")
        print(f"{'='*50}")

        # Defense profile
        defense = profile_defenses(inv)
        print(f"\n  DEFENSE PROFILE:")
        print(f"    Awareness Score:  {defense['awareness_score']}/10")
        print(f"    Defense Mode:     {defense['defense_mode']}")
        print(f"    Bypass Strategy:  {defense['bypass_strategy']}")
        print(f"    Est. Weekly Spam: ~{defense['estimated_weekly_cold_emails']} emails")
        print(f"    Forbidden:        {defense['forbidden_phrases']}")

        # Email WITHOUT defense profiling
        print(f"\n  ── EMAIL WITHOUT DEFENSE PROFILING ──")
        email_naive = write_cold_email(inv, use_defense_profiling=False)
        print(f"  SUBJECT A: {email_naive['subject_a']}")
        print(f"  SUBJECT B: {email_naive['subject_b']}")
        print(f"  ─────────────────────────────────")
        for line in email_naive["body"].split("\n"):
            print(f"  {line}")

        # Email WITH defense profiling
        print(f"\n  ── EMAIL WITH DEFENSE PROFILING ──")
        email_defense = write_cold_email(inv, use_defense_profiling=True)
        print(f"  SUBJECT A: {email_defense['subject_a']}")
        print(f"  SUBJECT B: {email_defense['subject_b']}")
        print(f"  REPLY TIER: {email_defense['predicted_reply_tier']}")
        print(f"  ─────────────────────────────────")
        for line in email_defense["body"].split("\n"):
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
