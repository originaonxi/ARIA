"""
LinkedIn outreach prep — generates HeyReach-ready CSVs.
Input: scored investors from DB with LinkedIn URLs.
Output: CSV with connection messages, sorted by score.
"""

import os
from datetime import datetime

import pandas as pd

from config import DATA_DIR
from aria_db import get_ready_to_contact
from investor_writer import write_linkedin_message


def prep_heyreach_csv(limit: int = 25) -> str:
    """
    Pull top LinkedIn-eligible investors from DB.
    Write personalized connection messages.
    Output HeyReach-ready CSV.
    Returns path to output CSV.
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    # Get investors with LinkedIn URLs
    investors = get_ready_to_contact(limit=limit * 2)  # Get extra, filter for LinkedIn
    linkedin_ready = [
        inv for inv in investors
        if inv.get("linkedin_url") and "linkedin.com" in str(inv.get("linkedin_url", ""))
    ][:limit]

    if not linkedin_ready:
        print("  No LinkedIn-ready investors in queue.")
        return None

    rows = []
    for inv in linkedin_ready:
        print(f"  Writing LinkedIn message for {inv['first_name']} {inv['last_name']}...")
        conn_msg = write_linkedin_message(inv)

        # Follow-up message (shorter version)
        followup_msg = (
            f"Hi {inv['first_name']}, following up — $650K ARR in 5 months, "
            f"zero sales reps. Worth 20 minutes?"
        )
        if len(followup_msg) > 300:
            followup_msg = followup_msg[:297] + "..."

        rows.append({
            "firstName": inv.get("first_name", ""),
            "lastName": inv.get("last_name", ""),
            "linkedinUrl": inv.get("linkedin_url", ""),
            "connectionMessage": conn_msg,
            "followUpMessage": followup_msg,
            "tier": inv.get("tier", 0),
            "score": inv.get("score", 0),
            "type": inv.get("investor_type", ""),
        })

    # Sort by score DESC
    rows.sort(key=lambda x: x["score"], reverse=True)

    # Output
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(DATA_DIR, f"heyreach_{date_str}.csv")
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)

    print(f"\n  Output: {out_path}")
    print(f"  Total: {len(rows)} investors")
    return out_path


if __name__ == "__main__":
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("LINKEDIN PREP — HeyReach CSV")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Show expected output structure
    print("\n  HeyReach CSV columns:")
    print("  firstName | lastName | linkedinUrl |")
    print("  connectionMessage | followUpMessage |")
    print("  tier | score | type")

    print("\n  Mock row:")
    print("  Sarah | Chen | linkedin.com/in/sarahchen |")
    print("  $650K ARR in 5 months, $0 raised... | ")
    print("  Hi Sarah, following up... |")
    print("  1 | 10 | OPERATOR_ANGEL")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
