"""
Apollo API client — finds investors automatically.
No manual CSV exports needed. Runs 3 queries daily.
"""

import requests

from config import APOLLO_API_KEY

BASE_URL = "https://api.apollo.io/api/v1"

QUERY_CONFIGS = {
    "angels": {
        "person_titles": [
            "angel investor", "angel", "investor",
            "pre-seed investor", "seed investor",
        ],
        "person_locations": ["United States"],
    },
    "gtm": {
        "person_titles": [
            "founder", "co-founder", "cto",
            "vp sales", "vp revenue", "chief revenue officer",
        ],
        "q_organization_keyword_tags": ["SaaS", "CRM", "Sales Software"],
        "person_locations": ["United States"],
    },
    "smb": {
        "person_titles": [
            "ceo", "founder", "owner", "operator",
        ],
        "q_organization_keyword_tags": [
            "home care", "franchise", "healthcare services", "cleaning",
        ],
        "person_locations": ["United States"],
    },
}


def search_investors(query_type: str, page: int = 1, per_page: int = 50) -> list:
    """
    Run Apollo people search.
    query_type: 'angels' | 'gtm' | 'smb'
    Returns list of raw investor dicts.
    """
    if not APOLLO_API_KEY:
        print("  [apollo] No API key configured — skipping search")
        return []

    config = QUERY_CONFIGS.get(query_type)
    if not config:
        print(f"  [apollo] Unknown query type: {query_type}")
        return []

    payload = {
        **config,
        "page": page,
        "per_page": per_page,
    }

    try:
        r = requests.post(
            f"{BASE_URL}/mixed_people/search",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "x-api-key": APOLLO_API_KEY,
            },
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("people", [])
    except requests.exceptions.HTTPError as e:
        print(f"  [apollo] API error ({e.response.status_code}): {e}")
        return []
    except Exception as e:
        print(f"  [apollo] Search error: {e}")
        return []


def normalize_apollo_result(raw: dict) -> dict:
    """Map Apollo fields to ARIA investor fields."""
    # Extract past companies from employment history
    past = []
    for job in (raw.get("employment_history") or []):
        org = job.get("organization_name") or ""
        if org:
            past.append(org)

    # Build location
    city = raw.get("city") or ""
    state = raw.get("state") or ""
    country = raw.get("country") or ""
    loc_parts = [p for p in [city, state, country] if p]

    # Bio from headline
    bio = raw.get("headline") or ""

    return {
        "apollo_id": raw.get("id") or "",
        "first_name": raw.get("first_name") or "",
        "last_name": raw.get("last_name") or "",
        "title": raw.get("title") or "",
        "company": (raw.get("organization", {}) or {}).get("name") or "",
        "past_companies": ", ".join(past[:10]),
        "location": ", ".join(loc_parts),
        "linkedin_url": raw.get("linkedin_url") or "",
        "email": raw.get("email") or "",
        "bio": bio,
        "source": "apollo",
    }


def daily_prospect_harvest(per_query: int = 50) -> dict:
    """
    Run all 3 queries. Normalize. Add to DB with dedup.
    Returns: {found, added, duplicates}
    """
    from aria_db import add_investor

    found = 0
    added = 0
    duplicates = 0

    for qtype in ("angels", "gtm", "smb"):
        print(f"  Searching Apollo: {qtype}...")
        results = search_investors(qtype, page=1, per_page=per_query)
        found += len(results)
        print(f"    Found {len(results)} results")

        for raw in results:
            investor = normalize_apollo_result(raw)

            # Skip if no email and no linkedin
            if not investor.get("email") and not investor.get("linkedin_url"):
                continue

            success, reason = add_investor(investor)
            if success:
                added += 1
            elif "dup" in reason:
                duplicates += 1

    return {"found": found, "added": added, "duplicates": duplicates}


if __name__ == "__main__":
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("APOLLO CLIENT TEST — small harvest")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    stats = daily_prospect_harvest(per_query=5)
    print(f"\n  Found: {stats['found']}")
    print(f"  Added: {stats['added']}")
    print(f"  Duplicates: {stats['duplicates']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
