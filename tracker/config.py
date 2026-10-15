"""Settings from environment variables (a local .env file is read if present)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def amazon():
    return {
        "credential_id": os.environ.get("AMAZON_CREDENTIAL_ID", ""),
        "credential_secret": os.environ.get("AMAZON_CREDENTIAL_SECRET", ""),
        # The credential version is shown next to your credentials in
        # Associates Central (Tools > Creators API).
        "version": os.environ.get("AMAZON_CREDENTIAL_VERSION", "2.2"),
        "partner_tag": os.environ.get("AMAZON_PARTNER_TAG", ""),
    }


def db_path():
    return os.environ.get("TRACKER_DB", str(ROOT / "data" / "tracker.db"))


def manual_max_age_hours():
    """A manually verified price older than this is shown as stale."""
    return float(os.environ.get("MANUAL_PRICE_MAX_AGE_HOURS", "24"))


def min_refresh_minutes():
    """Don't call the API again for a listing refreshed more recently than this."""
    return float(os.environ.get("MIN_REFRESH_MINUTES", "10"))
