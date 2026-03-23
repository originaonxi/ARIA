"""
ARIA Investor Researcher — SerpAPI research for Tier 1 and 2 investors.
Finds recent activity, portfolio signals, and thesis statements.
"""

import requests

from config import SERP_API_KEY


def _search(query: str, num: int = 3) -> list:
    """Run a SerpAPI search and return simplified results."""
    if not SERP_API_KEY:
        print("  [research] No SerpAPI key — skipping")
        return []

    try:
        r = requests.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": SERP_API_KEY,
                "num": num,
                "gl": "us",
                "hl": "en",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        results = []
        for item in data.get("organic_results", []):
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
            })
        return results
    except Exception as e:
        print(f"    [research] Search error: {e}")
        return []


def _extract_signal(results: list, keywords: list) -> str:
    """Find the best matching snippet from search results."""
    for r in results:
        text = f"{r['title']} {r['snippet']}".lower()
        for kw in keywords:
            if kw in text:
                snippet = r["snippet"][:200] if r["snippet"] else r["title"][:200]
                return snippet.strip()
    return ""


ACTIVITY_KEYWORDS = [
    "invest", "backed", "angel", "portfolio",
    "wrote", "said", "tweet", "post", "interview",
    "podcast", "spoke", "announced", "launched",
    "blog", "article", "shared", "published",
]

PORTFOLIO_KEYWORDS = [
    "invested in", "backed", "portfolio", "led round",
    "angel round", "seed round", "pre-seed",
    "co-invested", "announced", "funding",
]

THESIS_KEYWORDS = [
    "thesis", "focused on", "passionate about",
    "investing in", "interested in", "looking for",
    "vertical", "saas", "smb", "automation",
    "ai", "revenue", "sales", "gtm",
]


def research_investor(investor: dict) -> dict:
    """
    3 SerpAPI searches for an investor.
    Returns investor dict + research fields.
    """
    first = investor.get("first_name", "")
    last = investor.get("last_name", "")
    name = f"{first} {last}".strip()
    company = investor.get("company", "")

    if not name:
        investor["research_hook"] = None
        investor["research_confidence"] = "LOW"
        investor["recent_activity"] = None
        investor["portfolio_signal"] = None
        return investor

    print(f"    Researching {name}...")

    # Search 1 — Recent activity
    print(f"      Checking recent activity...")
    q1 = f"{name} investor 2025 2026 AI startup"
    r1 = _search(q1)
    activity = _extract_signal(r1, ACTIVITY_KEYWORDS)

    # Search 2 — Portfolio signal
    print(f"      Checking portfolio...")
    q2 = f"{name} angel invested portfolio backed"
    r2 = _search(q2)
    portfolio = _extract_signal(r2, PORTFOLIO_KEYWORDS)

    # Search 3 — Thesis signal
    print(f"      Checking thesis...")
    q3 = f"{name} SMB automation revenue AI thesis"
    r3 = _search(q3)
    thesis = _extract_signal(r3, THESIS_KEYWORDS)

    # Determine confidence and build hook
    confidence = "LOW"
    hook = None

    if activity:
        confidence = "HIGH"
        # Extract topic from activity snippet
        topic = activity[:80].rstrip(".")
        hook = (
            f"Saw your recent post about {topic} — "
            f"that is exactly the problem we are solving at Aonxi."
        )
    elif portfolio:
        confidence = "MEDIUM"
        signal = portfolio[:60].rstrip(".")
        hook = (
            f"Given your investment activity ({signal}), I thought "
            f"what we are building will feel familiar."
        )
    elif thesis:
        confidence = "MEDIUM"
        focus = thesis[:60].rstrip(".")
        hook = (
            f"Given your focus ({focus}), "
            f"wanted to share what we are seeing at Aonxi."
        )
    else:
        confidence = "LOW"
        # Fall back to personalization hook if available
        hook = investor.get("personalization_hook")

    investor["research_hook"] = hook
    investor["research_confidence"] = confidence
    investor["recent_activity"] = activity or None
    investor["portfolio_signal"] = portfolio or None

    print(f"      Confidence: {confidence}")
    return investor


if __name__ == "__main__":
    test_investors = [
        {
            "first_name": "Jason",
            "last_name": "Lemkin",
            "company": "SaaStr",
            "personalization_hook": "Given your focus on SaaS, I thought Aonxi would be worth your time.",
        },
        {
            "first_name": "Elad",
            "last_name": "Gil",
            "company": "Color Health",
            "personalization_hook": "Given your operator background, I thought Aonxi would be worth your time.",
        },
    ]

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("RESEARCHER TEST — 2 PUBLIC INVESTORS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for inv in test_investors:
        result = research_investor(inv.copy())
        print(f"\n  {result['first_name']} {result['last_name']}")
        print(f"    Confidence: {result['research_confidence']}")
        print(f"    Hook: {result.get('research_hook', 'None')}")
        if result.get("recent_activity"):
            print(f"    Activity: {result['recent_activity'][:100]}...")
        if result.get("portfolio_signal"):
            print(f"    Portfolio: {result['portfolio_signal'][:100]}...")
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
