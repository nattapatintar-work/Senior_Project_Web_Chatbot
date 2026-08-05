"""
nlp/extract.py
==============
Turns a Thai sentence typed by the user into structured data the rest of the
system can work with.

    "มีกุ้งกับไข่ อยากกินคลีน ไม่เอาหมู"
        |
        v
    {"ingredients": ["shrimp", "egg"], "health_tags": ["clean"], "excluded": ["pork"]}

STATUS: MOCK (Week 1-2 skeleton)
--------------------------------
Right now this returns hardcoded fake data. That is on purpose, and it is the
"Skeleton First" idea from the project doc: we lock the *shape* of the answer
now, so that in Week 5 we can fill in the real logic without anything else in
the project needing to change.

This function is Handoff #2 to Person 1 (due Week 5), so the signature below
should be treated as a promise. Changing the internals later is fine.
Changing the keys it returns is not.

Week 5 will replace the mock body with three real steps:
    1. Thai word segmentation  -> pythainlp.word_tokenize()
    2. Fuzzy matching          -> rapidfuzz, to survive typos
    3. Negation detection      -> spotting "ไม่เอา" / "ไม่ใส่" / "ไม่กิน"
"""

import json
from pathlib import Path

# Where the shared ingredient dictionary lives.
# __file__ is this file's own path, so this works no matter which folder you
# run python from. .parent goes up one level: nlp/ -> project root.
INGREDIENTS_PATH = Path(__file__).parent.parent / "data" / "ingredients.json"


def load_ingredients() -> dict:
    """
    Read data/ingredients.json off disk and hand it back as a Python dict.

    encoding="utf-8" is not optional here. The file is full of Thai text, and
    on Windows Python otherwise guesses a legacy encoding and throws
    UnicodeDecodeError.
    """
    with open(INGREDIENTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def extract(text: str) -> dict:
    """
    Pull ingredients, health tags, and exclusions out of a Thai sentence.

    Args:
        text: whatever the user typed, e.g. "มีไก่กับไข่ ไม่เอาพริก"

    Returns:
        A dict with exactly these three keys, each one a list of strings:
            {
                "ingredients": [...],   # canonical keys, e.g. ["chicken", "egg"]
                "health_tags": [...],   # e.g. ["clean", "keto"]
                "excluded":    [...],   # things the user said NO to
            }

        "Canonical key" means the English snake_case name used as the top-level
        key in ingredients.json ("green_onion", not "ต้นหอม" and not "spring
        onion"). Everything downstream expects that form, which is exactly what
        the shared dictionary is for.

    NOTE: mock implementation. Ignores `text` entirely and returns fixed data.
    """
    # TODO(Week 5): tokenize with pythainlp, match against the dictionary
    #               synonyms, and detect negation. See module docstring.
    return {
        "ingredients": ["chicken", "egg"],
        "health_tags": [],
        "excluded": [],
    }


# Running `python nlp/extract.py` directly executes this block, which is a
# quick way to eyeball the output. Importing the file does NOT run it.
if __name__ == "__main__":
    # A Thai-locale Windows console defaults to the cp874 codepage and prints
    # Thai text as garbage. Switching stdout to UTF-8 fixes the display. This
    # is a terminal quirk only — the strings themselves are always fine.
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    sample = "มีไก่กับไข่ อยากกินคลีน ไม่เอาพริก"
    print(f"input : {sample}")
    print(f"output: {extract(sample)}")
