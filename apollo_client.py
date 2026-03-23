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


def bulk_match_linkedin(linkedin_urls: list) -> list:
    """
    Enrich up to 10 people at once via Apollo bulk_match.
    Uses reveal_personal_emails to get personal emails.
    Returns list of normalized investor dicts.
    """
    if not APOLLO_API_KEY or not linkedin_urls:
        return [None] * len(linkedin_urls)

    details = [{"linkedin_url": url} for url in linkedin_urls]

    try:
        r = requests.post(
            f"{BASE_URL}/people/bulk_match",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "x-api-key": APOLLO_API_KEY,
            },
            json={
                "details": details,
                "reveal_personal_emails": True,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        matches = data.get("matches", [])

        results = []
        for match in matches:
            if not match:
                results.append(None)
                continue

            normalized = normalize_apollo_result(match)

            # bulk_match puts emails in personal_emails, not email
            email = match.get("email") or ""
            personal = match.get("personal_emails") or []
            if not email and personal:
                email = personal[0]
            normalized["email"] = email
            results.append(normalized)

        # Pad if fewer matches returned than requested
        while len(results) < len(linkedin_urls):
            results.append(None)

        return results

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        if status == 429:
            print(f"    [apollo] Rate limited")
        else:
            print(f"    [apollo] Bulk match error ({status}): {e.response.text[:150]}")
        return [None] * len(linkedin_urls)
    except Exception as e:
        print(f"    [apollo] Bulk match error: {e}")
        return [None] * len(linkedin_urls)


def enrich_csv_batch(csv_path: str, limit: int = None, batch_size: int = 10) -> dict:
    """
    Read a LinkedIn-only CSV, enrich in batches via Apollo bulk_match,
    add to DB with dedup. Returns stats.
    """
    import time
    import pandas as pd
    from aria_db import add_investor

    df = pd.read_csv(csv_path)
    if limit:
        df = df.head(limit)
    total = len(df)

    found_email = 0
    no_email = 0
    added = 0
    duplicates = 0
    errors = 0
    processed = 0

    # Process in batches
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_df = df.iloc[batch_start:batch_end]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        # Collect LinkedIn URLs for this batch
        batch_rows = []
        linkedin_urls = []
        for _, row in batch_df.iterrows():
            linkedin = str(row.get("Profile URL", "")).strip()
            batch_rows.append(row)
            if linkedin and "linkedin.com" in linkedin:
                linkedin_urls.append(linkedin)
            else:
                linkedin_urls.append(None)

        # Bulk match only valid URLs
        valid_urls = [u for u in linkedin_urls if u]
        print(f"\n  Batch {batch_num}/{total_batches} [{batch_start+1}-{batch_end}] — enriching {len(valid_urls)} profiles...")

        if valid_urls:
            enriched_results = bulk_match_linkedin(valid_urls)
        else:
            enriched_results = []

        # Map results back — build a dict from url to result
        url_to_result = {}
        for url, result in zip(valid_urls, enriched_results):
            url_to_result[url] = result

        # Process each row
        for row, linkedin_url in zip(batch_rows, linkedin_urls):
            processed += 1
            first = str(row.get("First Name", "")).strip()
            last = str(row.get("Last Name", "")).strip()
            name = f"{first} {last}"

            enriched = url_to_result.get(linkedin_url) if linkedin_url else None

            if enriched:
                # Merge CSV data where Apollo is missing
                if not enriched.get("bio"):
                    headline = row.get("Headline")
                    if pd.notna(headline):
                        enriched["bio"] = str(headline)[:500]
                if not enriched.get("title"):
                    title = row.get("Job Title")
                    if pd.notna(title):
                        enriched["title"] = str(title).strip()
                if not enriched.get("linkedin_url") and linkedin_url:
                    enriched["linkedin_url"] = linkedin_url
                if not enriched.get("location"):
                    loc = row.get("Location")
                    if pd.notna(loc):
                        enriched["location"] = str(loc).strip()

                email = enriched.get("email", "")
                success, reason = add_investor(enriched)
                if success:
                    added += 1
                    if email and "@" in email:
                        found_email += 1
                        print(f"    ✓ {name} — {email}")
                    else:
                        no_email += 1
                        print(f"    ○ {name} — enriched, no email")
                elif "dup" in reason:
                    duplicates += 1
                else:
                    errors += 1
            else:
                # No Apollo match — add with CSV data only
                fallback = {
                    "first_name": first,
                    "last_name": last,
                    "title": str(row.get("Job Title", "")).strip() if pd.notna(row.get("Job Title")) else "",
                    "company": str(row.get("Company", "")).strip() if pd.notna(row.get("Company")) else "",
                    "linkedin_url": linkedin_url or "",
                    "bio": str(row.get("Headline", "")).strip()[:500] if pd.notna(row.get("Headline")) else "",
                    "location": str(row.get("Location", "")).strip() if pd.notna(row.get("Location")) else "",
                    "source": "csv_linkedin",
                }
                success, reason = add_investor(fallback)
                if success:
                    added += 1
                    no_email += 1
                    print(f"    ○ {name} — no Apollo match")
                elif "dup" in reason:
                    duplicates += 1
                else:
                    errors += 1

        # Rate limit between batches
        time.sleep(1)

    return {
        "total_processed": processed,
        "added": added,
        "found_email": found_email,
        "no_email": no_email,
        "duplicates": duplicates,
        "errors": errors,
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
