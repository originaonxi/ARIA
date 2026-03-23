"""
Instantly API v2 client — handles email sending, warming, sequences.
Replaces Gmail SMTP entirely.
"""

import requests

from config import INSTANTLY_API_KEY, INSTANTLY_CAMPAIGN_ID

BASE_URL = "https://api.instantly.ai/api/v2"


def _headers():
    return {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json",
    }


def _get(endpoint: str, params: dict = None) -> dict:
    """Make authenticated GET request."""
    try:
        r = requests.get(
            f"{BASE_URL}{endpoint}",
            headers=_headers(),
            params=params or {},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        print(f"  [instantly] GET {endpoint} error ({e.response.status_code}): {e.response.text[:200]}")
        return {}
    except Exception as e:
        print(f"  [instantly] GET {endpoint} error: {e}")
        return {}


def _post(endpoint: str, payload: dict) -> dict:
    """Make authenticated POST request."""
    try:
        r = requests.post(
            f"{BASE_URL}{endpoint}",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        print(f"  [instantly] POST {endpoint} error ({e.response.status_code}): {e.response.text[:200]}")
        return {}
    except Exception as e:
        print(f"  [instantly] POST {endpoint} error: {e}")
        return {}


def list_campaigns() -> list:
    """List all campaigns."""
    data = _get("/campaigns", {"limit": 100})
    return data.get("items", data.get("data", []))


def get_or_create_campaign(
    name: str = "ARIA Investor Outreach",
    daily_limit: int = 25,
) -> str:
    """
    Check if campaign exists by name. Return existing or create new.
    Returns campaign_id.
    """
    if not INSTANTLY_API_KEY:
        print("  [instantly] No API key — skipping")
        return None

    # Check existing campaigns
    campaigns = list_campaigns()
    for c in campaigns:
        if c.get("name") == name:
            cid = c.get("id")
            print(f"  [instantly] Found existing campaign: {cid}")
            return cid

    # Create new campaign
    payload = {
        "name": name,
        "daily_limit": daily_limit,
        "stop_on_reply": True,
        "email_gap": 10,
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
        "campaign_schedule": {
            "schedules": [{
                "timing": {"from": "09:00", "to": "11:00"},
                "days": {
                    "monday": True,
                    "tuesday": True,
                    "wednesday": True,
                    "thursday": True,
                },
                "timezone": "America/New_York",
            }],
        },
    }

    data = _post("/campaigns", payload)
    cid = data.get("id")
    if cid:
        print(f"  [instantly] Created campaign: {cid}")
    else:
        print(f"  [instantly] Failed to create campaign")
    return cid


def add_lead(campaign_id: str, investor: dict) -> str:
    """
    Add single lead with personalized variables.
    Returns instantly_lead_id or None.
    """
    if not campaign_id:
        return None

    email = investor.get("email", "")
    if not email or "@" not in email:
        print(f"  [instantly] No valid email for {investor.get('first_name', '?')}")
        return None

    payload = {
        "campaign_id": campaign_id,
        "email": email,
        "first_name": investor.get("first_name", ""),
        "last_name": investor.get("last_name", ""),
        "company_name": investor.get("company", ""),
        "custom_variables": {
            "subject_line": investor.get("subject_a", ""),
            "email_body": investor.get("email_body", ""),
        },
    }

    data = _post("/leads", payload)
    lead_id = data.get("id") or data.get("lead_id")
    return lead_id


def add_leads_batch(campaign_id: str, investors: list) -> dict:
    """Add up to 25 leads at once. Returns stats."""
    added = 0
    failed = 0
    lead_ids = []

    for inv in investors[:25]:
        lead_id = add_lead(campaign_id, inv)
        if lead_id:
            added += 1
            lead_ids.append(lead_id)
        else:
            failed += 1

    return {"added": added, "failed": failed, "lead_ids": lead_ids}


def get_campaign_stats(campaign_id: str) -> dict:
    """Get campaign analytics."""
    if not campaign_id:
        return {}
    return _get(f"/campaigns/{campaign_id}/analytics")


def get_new_replies(campaign_id: str = None, since_hours: int = 24) -> list:
    """Get reply emails from Instantly."""
    params = {"email_type": "received", "limit": 100}
    if campaign_id:
        params["campaign_id"] = campaign_id

    data = _get("/emails", params)
    return data.get("items", data.get("data", []))


def pause_campaign(campaign_id: str):
    """Pause a campaign."""
    return _post(f"/campaigns/{campaign_id}/pause", {})


def resume_campaign(campaign_id: str):
    """Resume a campaign."""
    return _post(f"/campaigns/{campaign_id}/resume", {})


if __name__ == "__main__":
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("INSTANTLY CLIENT TEST")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    campaigns = list_campaigns()
    print(f"  Existing campaigns: {len(campaigns)}")
    for c in campaigns[:5]:
        print(f"    - {c.get('name', '?')} ({c.get('id', '?')[:12]}...)")

    cid = get_or_create_campaign("ARIA Test Campaign")
    print(f"  Campaign ID: {cid}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
