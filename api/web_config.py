"""
api/web_config.py
=================
Settings for the web chatbot backend (api/app.py).

Why this is not api/config.py: that file is LEGACY (LINE OA track) and raises
ConfigError at import unless LINE_CHANNEL_* credentials are set. The web app
has no LINE credentials, so it must never import that module.

Same pattern as api/config.py otherwise: .env is loaded once at import, real
environment variables win over the file, and nothing secret is ever printed.
"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)


# --- Secrets -----------------------------------------------------------------

# Empty string when unset. NOT fatal: /confirm falls back to the keyword stub
# in api/intent.py, so every other endpoint (and the tests) work without a key.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()


def anthropic_key_configured() -> bool:
    """True only for a real-looking value, not empty and not the .env.example placeholder."""
    key = ANTHROPIC_API_KEY
    if not key:
        return False
    return not (key.startswith("your_") and key.endswith("_here"))


def mask_secret(value: str) -> str:
    """
    Safe-to-log form of a secret: first 4 characters + ellipsis, or "<unset>".
    Same idea as api/main.py truncating the LINE user id / reply token
    (`user_id[:8]...`). Use this, never the raw value, in any log or error text.
    """
    if not value:
        return "<unset>"
    return f"{value[:4]}…"


# --- YOLO confidence threshold ---------------------------------------------------

THRESHOLDS_PATH = PROJECT_ROOT / "data" / "thresholds.yaml"


def _load_confidence_threshold() -> float:
    """
    Read "default" from data/thresholds.yaml (Person 1's file — read only).
    Same fallback as api/config.py: a missing file means 0.5, not a crash.
    """
    if not THRESHOLDS_PATH.exists():
        print(f"[web_config] {THRESHOLDS_PATH} not found, using default threshold 0.5", flush=True)
        return 0.5
    with open(THRESHOLDS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return float(data.get("default", 0.5))


CONFIDENCE_THRESHOLD = _load_confidence_threshold()


# --- Uploads -----------------------------------------------------------------

MAX_IMAGES_PER_REQUEST = 5
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


# --- Sessions ----------------------------------------------------------------

# In-memory store, single instance (demo deployment). Idle sessions are swept
# so the dict cannot grow without bound.
SESSION_TTL_SECONDS = float(os.getenv("SESSION_TTL_SECONDS", "3600"))


# --- HTTP layer ----------------------------------------------------------------

# Comma-separated origins allowed to call the API from a browser, e.g.
# "https://chat.example.com,http://localhost:8080". Empty = same-origin only.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# Behind an AWS ALB / proxy the socket peer is the proxy, which would put every
# user in ONE rate-limit bucket. Set TRUST_FORWARDED_FOR=1 there so the limiter
# keys on the first X-Forwarded-For hop. Off by default: locally the header is
# client-controlled and would let anyone dodge the limit.
TRUST_FORWARDED_FOR = os.getenv("TRUST_FORWARDED_FOR", "0") == "1"

# Per-IP limits (slowapi syntax). /detect is GPU-bound so it keeps the strict 5.
LIMIT_DETECT = "5/minute"
LIMIT_DEFAULT = "10/minute"
