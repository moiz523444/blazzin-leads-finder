"""
Settings loaded from environment variables or a local .env file (KEY=value per line).
All keys are optional - the app falls back to free keyless sources when one is missing.
"""
import os

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _load_env_file():
    if not os.path.exists(_ENV_FILE):
        return
    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

# Free: https://developer.tomtom.com (2,500 requests/day, no credit card)
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")
# Free: Google Cloud console -> enable "PageSpeed Insights API" -> create API key (25,000/day)
PAGESPEED_API_KEY = os.environ.get("PAGESPEED_API_KEY", "")
# Leads are kept on disk so contacted status and de-duplication survive restarts
DB_PATH = os.environ.get("LEADS_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db"))
