"""
api/mock_cv.py
==============
A stand-in for Person 1's YOLO detector.

STATUS: MOCK — replaced in Week 8/9
-----------------------------------
Person 1 delivers the real `detect()` plus `best.pt` in Week 8 (Handoff #3).
Until then this returns fixed fake results so the rest of the chatbot can be
built and tested end to end without waiting.

The return shape is copied exactly from the project doc so that swapping in the
real detector changes nothing else:

    [{"ingredient": "egg",    "confidence": 0.92},
     {"ingredient": "tomato", "confidence": 0.88},
     {"ingredient": "onion",  "confidence": 0.31}]

This file lives in api/ because api/ belongs to Person 2. Person 1's real
detector will live in their own folder — this mock gets deleted then, not
edited.
"""

import random

# Pulled from data/ingredients.json. Deliberately a small subset: the mock
# should look like a plausible detection, not like the whole dictionary.
_FAKE_DETECTIONS = [
    {"ingredient": "tomato", "confidence": 0.91},
    {"ingredient": "egg", "confidence": 0.88},
    {"ingredient": "onion", "confidence": 0.76},
    {"ingredient": "carrot", "confidence": 0.64},
    {"ingredient": "garlic", "confidence": 0.42},  # below the 0.5 cutoff on purpose
]


def detect(image_path: str) -> list[dict]:
    """
    Pretend to find ingredients in a photo.

    Args:
        image_path: path to a saved image. IGNORED by the mock — but the real
                    detector needs it, so callers must pass it correctly now.
                    If they don't, Week 9 turns into a rewrite instead of a
                    one-line swap.

    Returns:
        A list of {"ingredient": str, "confidence": float} dicts.
        Confidence runs 0.0-1.0 and decides whether the LLM gets called later.

    One entry is deliberately below 0.5 so the confidence filter in
    api/session.py is actually exercised rather than just assumed to work.
    """
    # TODO(Week 8): delete this file; import Person 1's real detect() instead.
    _ = image_path  # unused until the real detector lands

    # Vary the count a little so testing doesn't always look identical.
    # random.sample picks without replacement, so no ingredient repeats.
    count = random.randint(2, len(_FAKE_DETECTIONS))
    picked = random.sample(_FAKE_DETECTIONS, count)

    # Sort highest-confidence first, matching what YOLO returns.
    return sorted(picked, key=lambda d: d["confidence"], reverse=True)
