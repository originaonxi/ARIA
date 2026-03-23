"""
Configuration loader — reads all secrets from .env file only.
Never hardcode API keys or credentials anywhere.
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv required. Run: pip install python-dotenv")
    sys.exit(1)

env_path = Path(__file__).parent / ".env"

if not env_path.exists():
    print("=" * 60)
    print("ERROR: .env file not found!")
    print()
    print("  1. Copy .env.example to .env:")
    print("     cp .env.example .env")
    print()
    print("  2. Edit .env and add your real API keys.")
    print("=" * 60)
    sys.exit(1)

load_dotenv(env_path)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY")
INSTANTLY_CAMPAIGN_ID = os.getenv("INSTANTLY_CAMPAIGN_ID")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Investors")
MILLIONVERIFIER_API_KEY = os.getenv("MILLIONVERIFIER_API_KEY")
OWNER_EMAIL = os.getenv("OWNER_EMAIL")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

DB_PATH = os.path.join(os.path.dirname(__file__), "aria.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

_required = {
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "OWNER_EMAIL": OWNER_EMAIL,
}

_missing = [k for k, v in _required.items() if not v]
if _missing:
    print(f"ERROR: Missing required env vars in .env: {', '.join(_missing)}")
    sys.exit(1)
