"""
api/mock_cv.py
===============
STATUS: REAL — Week 8/9 handoff #3 from Person 1
--------------------------------------------------
Wraps Person 1's delivered YOLO model
(models/best_phase1_n_ceiling1000_img640.pt) to find ingredients in a photo.
No longer a mock — the filename stays `mock_cv.py` for now (every existing
import, `from api import mock_cv` / `mock_cv.detect(path)`, keeps working
unchanged), but the body below is real. Renaming to `api/cv.py` is a
reasonable follow-up, not done here.

The return shape is unchanged from the mock this replaces, on purpose:

    [{"ingredient": "egg",    "confidence": 0.92},
     {"ingredient": "tomato", "confidence": 0.88},
     {"ingredient": "onion",  "confidence": 0.31}]

CLASS-MAPPING VERIFICATION (done before this file was written, not assumed)
-----------------------------------------------------------------------------
The model's 100 classes were diffed programmatically against every
`yolo_class_id` in data/ingredients.json before any of this code was
written: 0 mismatches, id 0 == "chicken", id 99 == "peanuts", exactly as
the dictionary claims. The _verify_class_mapping() check below repeats
that same diff at every import, not just once by hand, so a future retrain
that silently reorders classes fails loudly at startup instead of quietly
mislabeling every detection forever — the worst kind of bug, because
nothing would look broken.

DEVICE SELECTION — MEASURED, NOT ASSUMED
-------------------------------------------
A bare `YOLO(path).predict(...)` does NOT automatically move computation to
a GPU even when one is present — confirmed directly on this machine
(an RTX 4050 Laptop GPU, CUDA available): omitting `device=` left inference
running on CPU. `device=0` must be passed explicitly to use the GPU. Real
measurements taken on this machine before writing this file:

    First call (cold, pays model-warmup cost)   CPU: 5.7s   GPU: 2.0s
    Steady-state (warm)                         CPU: 81ms  GPU: 29ms

The cold-start cost is real and would blow a chunk of the ~30s reply-token
budget if paid on a live user's first request. _warm_up() below pays it
once at import time instead, on a throwaway synthetic image, before the
Flask server ever starts accepting requests.
"""

from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

from nlp.extract import load_ingredients

MODEL_PATH = Path(__file__).parent.parent / "models" / "best_phase1_n_ceiling1000_img640.pt"

# device=0 (first CUDA GPU) if one is available, else plain "cpu" — decided
# once at import time, reused for every call. See the module docstring for
# why this can't be left to ultralytics' own default.
_DEVICE = 0 if torch.cuda.is_available() else "cpu"


def _verify_class_mapping(model: YOLO) -> None:
    """
    Diff the model's own class list against data/ingredients.json's
    yolo_class_id mapping. Raises loudly on any mismatch rather than letting
    detect() silently return wrong ingredient names forever — see the module
    docstring's CLASS-MAPPING VERIFICATION section.
    """
    ingredients = load_ingredients()
    expected = {
        entry["yolo_class_id"]: key
        for key, entry in ingredients.items()
        if entry.get("yolo_class_id") is not None
    }

    mismatches = {
        class_id: (model.names.get(class_id), expected.get(class_id))
        for class_id in set(model.names) | set(expected)
        if model.names.get(class_id) != expected.get(class_id)
    }
    if mismatches:
        raise RuntimeError(
            f"YOLO model class mapping does not match data/ingredients.json! "
            f"{len(mismatches)} mismatch(es): {mismatches}. "
            f"Model: {MODEL_PATH}"
        )


def _warm_up(model: YOLO) -> None:
    """
    Pay the first-inference cold-start cost (measured up to ~5.7s CPU / ~2.0s
    GPU on this machine) once, at import time, on a throwaway synthetic
    image — so the first real user's request never eats it. Result is
    discarded; only the side effect (warmed-up model) matters.
    """
    dummy_image = np.zeros((640, 640, 3), dtype=np.uint8)
    model.predict(dummy_image, verbose=False, device=_DEVICE)


# Loaded once at import time, not per request — same principle as
# nlp/extract.py's Trie and recommender/recommend.py's TF-IDF matrix: this
# runs on the ~30s reply-token path, so paying model-load-and-warmup cost per
# message would be wasteful, and on this machine's numbers, would blow the
# budget outright on a cold CPU run.
_MODEL = YOLO(str(MODEL_PATH))
_verify_class_mapping(_MODEL)
print(
    "[mock_cv] class mapping verified against data/ingredients.json (100 classes)",
    flush=True,
)
_warm_up(_MODEL)
print(f"[mock_cv] model loaded and warmed up on device={_DEVICE!r}", flush=True)


def detect(image_path: str) -> list[dict]:
    """
    Find ingredients in a photo using the real YOLO model.

    Args:
        image_path: path to a saved image.

    Returns:
        A list of {"ingredient": str, "confidence": float} dicts, sorted
        highest-confidence first — the exact shape the mock this replaces
        always returned, so api/main.py's confidence filter and everything
        downstream needs nothing else to change.
    """
    results = _MODEL.predict(image_path, verbose=False, device=_DEVICE)[0]

    # box.cls / box.conf are single-element torch.Tensors in Ultralytics'
    # Boxes API — int()/float() casts get plain Python values, since
    # downstream code (the confidence-filter comparison, and this list
    # eventually being JSON-shaped) expects plain types, not tensors.
    detections = [
        {
            "ingredient": _MODEL.names[int(box.cls)],
            "confidence": float(box.conf),
        }
        for box in results.boxes
    ]
    return sorted(detections, key=lambda d: d["confidence"], reverse=True)
