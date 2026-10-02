"""
tools/check_llm_models.py
=========================
Checks that the two Claude model ids the app uses are accepted by YOUR Anthropic account.

    python tools/check_llm_models.py

*** THIS SCRIPT MAKES EXACTLY 2 REAL API CALLS (about a fraction of a cent in total): one
tiny request (max_tokens=5) per model id. It is never run by pytest or by any other script.
***

Model ids come from the same config the app uses (api/web_config.py):
  - extraction fallback  EXTRACTION_LLM_MODEL  (env var, default claude-sonnet-5)
  - /confirm classifier  INTENT_MODEL          (claude-haiku-4-5-20251001, not env-configurable)

The API key
  Read from the ANTHROPIC_API_KEY environment variable (or .env, through api.web_config,
  exactly as the app does). It is never printed. Any error text is scrubbed of the key before
  it is shown. If the key is missing or still the .env.example placeholder, the script exits
  with a message and makes no call.

Exit code: 0 if both calls succeed, 1 if any call fails, 2 if the key is missing.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import anthropic

from api import web_config

TIMEOUT_SECONDS = 20.0
MAX_TOKENS = 5


def scrub(text: str) -> str:
    """Never let the key reach the terminal, even inside an error message."""
    key = web_config.ANTHROPIC_API_KEY
    return text.replace(key, "<redacted>") if key else text


def check(client: anthropic.Anthropic, label: str, model: str) -> bool:
    try:
        client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": "Reply with the single word: OK"}],
        )
    except Exception as exc:  # noqa: BLE001 - report any failure, whatever its class
        print(f"FAIL  {label}: {model}\n      {type(exc).__name__}: {scrub(str(exc))}")
        return False
    print(f"OK    {label}: {model}")
    return True


def main() -> None:
    if not web_config.anthropic_key_configured():
        sys.exit("ANTHROPIC_API_KEY is not set (or is still the .env.example placeholder): "
                 "no API calls were made.")

    client = anthropic.Anthropic(api_key=web_config.ANTHROPIC_API_KEY, timeout=TIMEOUT_SECONDS, max_retries=0)
    results = [
        check(client, "extraction model (EXTRACTION_LLM_MODEL)", web_config.EXTRACTION_LLM_MODEL),
        check(client, "intent model (INTENT_MODEL)", web_config.INTENT_MODEL),
    ]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
