"""
Millionverifier email verification.
Verify every email before sending. Bouncing investor emails is catastrophic.
"""

import requests

from config import MILLIONVERIFIER_API_KEY


def verify_email(email: str) -> tuple:
    """
    Returns (valid: bool, confidence: str).
    valid=True only if result='ok'.
    confidence: HIGH/MEDIUM/LOW.
    """
    if not MILLIONVERIFIER_API_KEY:
        print("  [verify] No Millionverifier API key — skipping")
        return (True, "UNVERIFIED")

    if not email or "@" not in email:
        return (False, "INVALID_FORMAT")

    try:
        r = requests.get(
            "https://api.millionverifier.com/api/v3/",
            params={
                "api": MILLIONVERIFIER_API_KEY,
                "email": email.strip().lower(),
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        result = data.get("result", "").lower()
        subresult = data.get("subresult", "").lower()

        if result == "ok":
            return (True, "HIGH")
        elif result == "unknown":
            # Unknown = risky but not definitively bad
            if subresult in ("mail_server_did_not_respond", "timeout"):
                return (False, "LOW")
            return (False, "MEDIUM")
        else:
            # result == "error" or other
            return (False, "HIGH")

    except Exception as e:
        print(f"  [verify] Error verifying {email}: {e}")
        return (True, "UNVERIFIED")


def verify_batch(limit: int = 100) -> dict:
    """
    Get unverified investors from DB. Verify up to limit.
    Update DB with results.
    Returns: {valid, invalid, unknown}
    """
    from aria_db import get_unverified, mark_verified

    investors = get_unverified(limit=limit)
    valid_count = 0
    invalid_count = 0
    unknown_count = 0

    for inv in investors:
        email = inv.get("email", "")
        if not email:
            continue

        valid, confidence = verify_email(email)
        mark_verified(inv["id"], valid)

        if valid and confidence != "UNVERIFIED":
            valid_count += 1
            print(f"    ✓ {email}")
        elif confidence == "UNVERIFIED":
            unknown_count += 1
            print(f"    ? {email} (unverified — no API key)")
        else:
            invalid_count += 1
            print(f"    ✗ {email} ({confidence})")

    return {
        "valid": valid_count,
        "invalid": invalid_count,
        "unknown": unknown_count,
        "total_checked": len(investors),
    }


if __name__ == "__main__":
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("MILLIONVERIFIER TEST")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    test_emails = ["test@gmail.com", "fake@notadomain99999.com"]
    for em in test_emails:
        valid, conf = verify_email(em)
        print(f"  {em}: valid={valid}, confidence={conf}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
