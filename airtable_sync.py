"""
Airtable CRM sync — visual layer on top of SQLite.
SQLite is the source of truth. Airtable is what you see on your phone.
"""

import requests

from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME

AIRTABLE_URL = "https://api.airtable.com/v0"


def _headers():
    return {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }


def sync_investor(investor: dict) -> str:
    """
    Push investor to Airtable. Returns airtable record_id.
    If investor already has airtable_id, update instead.
    """
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        print("  [airtable] No API key or base ID — skipping sync")
        return None

    first = investor.get("first_name", "")
    last = investor.get("last_name", "")
    name = f"{first} {last}".strip()

    fields = {
        "Name": name,
        "Email": investor.get("email") or "",
        "Company": investor.get("company") or "",
        "Tier": investor.get("tier") or 0,
        "Score": investor.get("score") or 0,
        "Status": investor.get("status") or "NEW",
        "Type": investor.get("investor_type") or "",
        "Reply Tier": investor.get("predicted_reply_tier") or "",
        "Research Hook": (investor.get("research_hook") or "")[:200],
    }

    if investor.get("first_contacted"):
        fields["First Contacted"] = investor["first_contacted"][:10]

    fields["Replied"] = bool(investor.get("replied"))
    fields["Meeting Booked"] = bool(investor.get("meeting_booked"))

    airtable_id = investor.get("airtable_id")

    try:
        if airtable_id:
            # Update existing record
            r = requests.patch(
                f"{AIRTABLE_URL}/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}/{airtable_id}",
                headers=_headers(),
                json={"fields": fields},
                timeout=15,
            )
        else:
            # Create new record
            r = requests.post(
                f"{AIRTABLE_URL}/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}",
                headers=_headers(),
                json={"fields": fields},
                timeout=15,
            )

        r.raise_for_status()
        data = r.json()
        record_id = data.get("id")
        return record_id

    except requests.exceptions.HTTPError as e:
        print(f"  [airtable] Error: {e.response.status_code} — {e.response.text[:200]}")
        return None
    except Exception as e:
        print(f"  [airtable] Error: {e}")
        return None


def update_status(record_id: str, status: str,
                  replied: bool = False, meeting: bool = False):
    """Update status on existing Airtable record."""
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not record_id:
        return

    fields = {"Status": status, "Replied": replied, "Meeting Booked": meeting}

    try:
        r = requests.patch(
            f"{AIRTABLE_URL}/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}/{record_id}",
            headers=_headers(),
            json={"fields": fields},
            timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  [airtable] Update error: {e}")


def print_setup_instructions():
    """Print Airtable base setup instructions."""
    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AIRTABLE SETUP INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Create a new Airtable base (or use existing)
2. Create a table named: Investors
3. Add these fields with correct types:

   Name              → Single line text
   Email             → Email
   Company           → Single line text
   Tier              → Number (integer)
   Score             → Number (integer)
   Status            → Single select
                       Options: NEW, VERIFIED, SCORED,
                       WRITTEN, CONTACTED, REPLIED,
                       MEETING, INVALID, DEAD
   Type              → Single line text
   Reply Tier        → Single line text
   Research Hook     → Long text
   First Contacted   → Date
   Replied           → Checkbox
   Meeting Booked    → Checkbox

4. Copy the Base ID from the URL:
   airtable.com/appXXXXXXXXXX/...
   The appXXX part is your AIRTABLE_BASE_ID

5. Create a Personal Access Token at:
   airtable.com/create/tokens
   Give it: data.records:read, data.records:write

6. Add to your .env:
   AIRTABLE_API_KEY=patXXXX
   AIRTABLE_BASE_ID=appXXXX
   AIRTABLE_TABLE_NAME=Investors

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


if __name__ == "__main__":
    print_setup_instructions()
