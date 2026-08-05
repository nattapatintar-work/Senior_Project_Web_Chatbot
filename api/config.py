"""
api/config.py
=============
Loads the LINE credentials from the .env file and checks they are actually
there.

Why secrets live in .env instead of in the code:
    A channel access token is a password. Anything written directly into a .py
    file gets committed to git, and this repo has to be public (YOLO is
    AGPL-3.0). Keeping secrets in .env — which .gitignore blocks — means the
    code can be shared while the credentials stay private.

Why this file fails loudly at import time:
    If a missing token only caused an error when the first real message
    arrived, the server would appear to start perfectly and then throw a 500
    at LINE, which retries, which produces confusing duplicate errors. Far
    better to refuse to start at all, with a message that says exactly what is
    missing and how to fix it.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root — this file is api/config.py, so .parent.parent is one level
# above api/. Building the path this way means it does not matter which folder
# you run python from.
PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# Read .env and copy its contents into environment variables.
# Real environment variables win over the file, which is what you want on a
# deployment server where secrets are injected rather than written to disk.
load_dotenv(ENV_PATH)


class ConfigError(RuntimeError):
    """Raised when a required setting is missing or still a placeholder."""


def _require(name: str) -> str:
    """
    Fetch one required environment variable, or explain clearly what to do.

    Also rejects the placeholder values from .env.example. Copying the template
    and forgetting to paste the real values is an easy mistake, and the error
    it would otherwise produce is a confusing 401 from LINE rather than
    anything pointing at .env.
    """
    value = os.getenv(name, "").strip()

    if not value:
        raise ConfigError(
            f"\n\n  Missing required setting: {name}\n"
            f"\n  Fix it in three steps:\n"
            f"    1. Copy .env.example  ->  .env\n"
            f"    2. Open .env and paste your real value for {name}\n"
            f"    3. Start the server again\n"
            f"\n  Expected .env location: {ENV_PATH}\n"
            f"  Get the value from:     https://developers.line.biz/console/\n"
        )

    if value.startswith("your_") and value.endswith("_here"):
        raise ConfigError(
            f"\n\n  {name} is still the placeholder from .env.example.\n"
            f"\n  Current value: {value}\n"
            f"  Open {ENV_PATH} and replace it with the real value from\n"
            f"  https://developers.line.biz/console/\n"
        )

    return value


# Read at import time, so a bad config stops the server immediately.
CHANNEL_ACCESS_TOKEN = _require("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = _require("LINE_CHANNEL_SECRET")

# How long to wait after the last message before processing. The project doc
# recommends 2.5-3 seconds: long enough to catch a photo and its caption sent
# moments apart, short enough that the reply still feels immediate.
DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "2.5"))

# Maximum photos merged into one request. Beyond this the extras are ignored,
# because each one costs a download and (later) a YOLO pass.
MAX_IMAGES_PER_SESSION = 5

# Where downloaded photos are saved. Git-ignored: they are user data, not code.
INCOMING_DIR = PROJECT_ROOT / "data" / "incoming"
