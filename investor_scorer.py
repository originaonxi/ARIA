"""
ARIA Investor Scorer — scores investors by thesis fit to Aonxi.
Tier 1: Operator angels from GTM/sales-tech companies.
Tier 2: SMB operators who know the pain.
Tier 3: AI/GTM investors by thesis.
"""


# ── TIER 1: Operator Angels — past companies ─────────────────
TIER1_COMPANIES = [
    "gong", "hubspot", "salesforce", "outreach", "apollo",
    "clay", "zoominfo", "instantly", "salesloft", "drift",
    "chorus", "clearbit", "mixmax", "lemlist", "ringcentral",
    "dialpad", "mailshake", "smartlead", "pipedrive",
    "close.io", "close", "intercom", "zendesk", "freshworks",
    "revenue.io", "yesware", "seamless", "lusha",
]

INVESTOR_SIGNALS = [
    "angel", "investor", "backed", "invested", "portfolio",
    "advisor", "scout", "pre-seed", "seed", "early stage",
    "emerging fund", "syndicate", "operator",
]

# ── TIER 2: SMB Operators ────────────────────────────────────
TIER2_INDUSTRIES = [
    "home care", "homecare", "home health", "senior care",
    "caregiver", "franchise", "cleaning", "janitorial",
    "property management", "healthcare services",
    "staffing", "personal care", "assisted living",
]

TIER2_TITLES = [
    "ceo", "founder", "owner", "operator", "president",
    "co-founder", "managing partner",
]

# ── TIER 3: AI/GTM Investors ────────────────────────────────
TIER3_KEYWORDS = [
    "pre-seed", "seed", "ai", "automation", "agents",
    "vertical saas", "smb", "small business",
    "future of work", "revenue", "gtm", "b2b saas",
    "operator", "revenue intelligence", "sales tech",
    "early stage", "emerging", "syndicate",
]

# ── SKIP signals ─────────────────────────────────────────────
SKIP_TITLES = [
    "recruiter", "recruiting", "talent acquisition",
    "designer", "graphic design", "ux design",
    "developer", "engineer", "software engineer",
]


def _match_any(text: str, keywords: list) -> list:
    """Return all matching keywords found in text."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw in text_lower]


def score_investor(row: dict) -> dict:
    """
    Score an investor by thesis fit.
    Returns row + tier, score, investor_type, channel,
    personalization_hook, go (bool).
    """
    title = str(row.get("title") or "").lower()
    company = str(row.get("company") or "")
    past = str(row.get("past_companies") or "").lower()
    bio = str(row.get("bio") or "").lower()
    linkedin = str(row.get("linkedin_url") or "")
    email = str(row.get("email") or "")
    combined = f"{title} {bio} {past}"

    tier = 3
    score = 3
    investor_type = "UNKNOWN"
    hook = ""

    # ── Check SKIP first ─────────────────────────────
    skip_matches = _match_any(title, SKIP_TITLES)
    investor_matches = _match_any(combined, INVESTOR_SIGNALS)
    if skip_matches and not investor_matches:
        row["tier"] = 0
        row["score"] = 1
        row["investor_type"] = "SKIP"
        row["channel"] = "NONE"
        row["personalization_hook"] = ""
        row["go"] = False
        return row

    # ── TIER 1: Operator Angels ──────────────────────
    company_matches = _match_any(past, TIER1_COMPANIES)
    if not company_matches:
        company_matches = _match_any(company.lower(), TIER1_COMPANIES)

    if company_matches:
        matched_company = company_matches[0].title()
        tier = 1
        score = 8
        investor_type = "OPERATOR_ANGEL"
        hook = (
            f"Given your time at {matched_company}, you have "
            f"seen exactly what enterprise GTM costs."
        )

        # Bonus for investor signals
        bonus = min(len(investor_matches) * 2, 4)
        score = min(score + bonus, 10)

    # ── TIER 2: SMB Operators ────────────────────────
    elif _match_any(f"{company.lower()} {bio}", TIER2_INDUSTRIES) and _match_any(title, TIER2_TITLES):
        tier = 2
        score = 6
        investor_type = "SMB_OPERATOR"
        hook = (
            f"As someone running {company}, you know "
            f"the client acquisition problem personally."
        )
        if investor_matches:
            score = 7

    # ── TIER 3: AI/GTM Investors ─────────────────────
    elif _match_any(combined, TIER3_KEYWORDS):
        kw_matches = _match_any(combined, TIER3_KEYWORDS)
        best_kw = kw_matches[0]
        tier = 3
        score = 4
        investor_type = "AI_GTM_INVESTOR"
        hook = (
            f"Given your focus on {best_kw}, "
            f"I thought Aonxi would be worth your time."
        )
        if len(kw_matches) >= 3:
            score = 5

    # ── CHANNEL logic ────────────────────────────────
    has_linkedin = bool(linkedin and "linkedin.com" in linkedin)
    has_email = bool(email and "@" in email)

    if has_linkedin and has_email:
        channel = "BOTH"
    elif has_email:
        channel = "EMAIL"
    elif has_linkedin:
        channel = "LINKEDIN"
    else:
        channel = "NONE"

    row["tier"] = tier
    row["score"] = score
    row["investor_type"] = investor_type
    row["channel"] = channel
    row["personalization_hook"] = hook
    row["go"] = tier in (1, 2, 3) and score >= 4 and channel != "NONE"

    return row


if __name__ == "__main__":
    test_cases = [
        {
            "first_name": "Sarah", "last_name": "Chen",
            "title": "Angel Investor, ex-VP Sales",
            "company": "Chen Ventures",
            "past_companies": "Gong, Salesforce",
            "bio": "Angel investor focused on AI and sales tech",
            "email": "sarah@example.com",
            "linkedin_url": "https://linkedin.com/in/sarahchen",
        },
        {
            "first_name": "Marcus", "last_name": "Williams",
            "title": "CEO",
            "company": "HomeWell Senior Care",
            "past_companies": "",
            "bio": "Running a home care franchise in Dallas",
            "email": "marcus@homewell.com",
            "linkedin_url": "",
        },
        {
            "first_name": "Priya", "last_name": "Kumar",
            "title": "Partner",
            "company": "AI Seed Fund",
            "past_companies": "",
            "bio": "Pre-seed investor in AI automation and vertical SaaS",
            "email": "priya@aifund.vc",
            "linkedin_url": "https://linkedin.com/in/priyakumar",
        },
        {
            "first_name": "John", "last_name": "Smith",
            "title": "Senior UX Designer",
            "company": "TechCorp",
            "past_companies": "",
            "bio": "Designing delightful user experiences",
            "email": "john@techcorp.com",
            "linkedin_url": "",
        },
        {
            "first_name": "Lisa", "last_name": "Park",
            "title": "Angel, ex-Head of Revenue",
            "company": "Park Capital",
            "past_companies": "Outreach, HubSpot",
            "bio": "Operator angel. Backed 12 startups in GTM space.",
            "email": "lisa@parkcapital.com",
            "linkedin_url": "https://linkedin.com/in/lisapark",
        },
    ]

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("INVESTOR SCORER TEST — 5 PROFILES")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for tc in test_cases:
        result = score_investor(tc.copy())
        print(f"\n  {result['first_name']} {result['last_name']} | {result['company']}")
        print(f"    Tier: {result['tier']} | Score: {result['score']}/10 | Type: {result['investor_type']}")
        print(f"    Channel: {result['channel']} | GO: {result['go']}")
        if result['personalization_hook']:
            print(f"    Hook: \"{result['personalization_hook']}\"")
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
