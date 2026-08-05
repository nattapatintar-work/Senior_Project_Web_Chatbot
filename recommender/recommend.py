"""
recommender/recommend.py
========================
Given the ingredients a user has, suggest the Top-3 dishes they could cook.

    ["chicken", "garlic", "chili"] + health=["clean"]
        |
        v
    [{"name_th": "ผัดกะเพราไก่", "score": 0.87,
      "have": ["chicken", "garlic", "chili"], "missing": ["holy_basil"], ...}]

STATUS: MOCK (Week 1-2 skeleton)
--------------------------------
Returns hardcoded fake dishes for now. The real version lands in Week 7 and
needs data/recipes.json (the 40-dish database, Weeks 3-4) to exist first.

Week 7 replaces the mock body with standard Content-Based Filtering:
    1. Turn each dish into a vector of the ingredients it uses
    2. Weight those vectors with TF-IDF, so a rare ingredient counts for more
       than one that shows up in every single recipe
    3. Score with cosine similarity (0.0 = nothing in common, 1.0 = identical)
    4. Drop dishes the health filter rules out, keep the best 3

The doc is explicit that this is implementation, not research. TF-IDF and
cosine similarity are textbook methods and scikit-learn already provides both,
so nothing here needs inventing.

One rule worth remembering now: scoring is PARTIAL. A user is never required
to have every ingredient a dish calls for, because nobody has a full fridge.
Missing items get reported in "missing" as a shopping list, not used to
disqualify the dish.
"""


def recommend(
    ingredients: list[str],
    health_tags: list[str] | None = None,
    excluded: list[str] | None = None,
    top_k: int = 3,
) -> list[dict]:
    """
    Score every dish against what the user has, return the best `top_k`.

    Args:
        ingredients: canonical keys the user has, e.g. ["chicken", "egg"].
                     These come from YOLO (photo), extract() (text), or both
                     merged together.
        health_tags: diets to filter for, e.g. ["clean"]. None means no filter.
        excluded:    ingredients to avoid, e.g. ["pork"]. Any dish needing one
                     of these is dropped entirely.
        top_k:       how many dishes to return. Defaults to 3.

    Returns:
        A list of at most `top_k` dicts, best score first:
            {
                "id":        "th_001",              # matches recipes.json
                "name_th":   "ผัดกะเพราไก่",
                "score":     0.87,                  # always between 0.0 and 1.0
                "have":      ["chicken", ...],      # user already has these
                "missing":   ["holy_basil"],        # needs to buy these
                "nutrition": {"kcal": 450, "protein": 32, "fat": 18, "carb": 35},
            }

        Empty list is a valid answer — it means nothing matched, and the bot
        should say so rather than crash.

    Why `health_tags: list[str] | None = None` and not `= []`:
        A mutable default like [] is created once and shared by every call to
        the function, so if anything ever appends to it the change leaks into
        later calls. It is a classic Python bug. Using None and converting
        inside the function avoids it.

    NOTE: mock implementation. Ignores every argument and returns fixed data.
    """
    # Convert the None defaults into real empty lists. The mock does not use
    # these yet, but Week 7 will, and doing it here keeps the pattern visible.
    health_tags = health_tags or []
    excluded = excluded or []

    # TODO(Week 7): load data/recipes.json, build the TF-IDF matrix, score with
    #               cosine similarity, apply the health and excluded filters.
    mock_results = [
        {
            "id": "th_001",
            "name_th": "ผัดกะเพราไก่",
            "score": 0.87,
            "have": ["chicken", "garlic", "chili"],
            "missing": ["holy_basil"],
            "nutrition": {"kcal": 450, "protein": 32, "fat": 18, "carb": 35},
        },
        {
            "id": "th_002",
            "name_th": "ไข่เจียว",
            "score": 0.72,
            "have": ["egg", "green_onion"],
            "missing": [],
            "nutrition": {"kcal": 220, "protein": 14, "fat": 16, "carb": 2},
        },
        {
            "id": "th_003",
            "name_th": "ผัดผักรวมมิตร",
            "score": 0.65,
            "have": ["cabbage", "carrot", "garlic"],
            "missing": ["broccoli"],
            "nutrition": {"kcal": 180, "protein": 6, "fat": 9, "carb": 20},
        },
    ]

    # Slicing with [:top_k] is safe even when the list is shorter than top_k —
    # Python just returns everything it has instead of raising an error.
    return mock_results[:top_k]


if __name__ == "__main__":
    # A Thai-locale Windows console defaults to the cp874 codepage and prints
    # Thai text as garbage. Switching stdout to UTF-8 fixes the display. This
    # is a terminal quirk only — the strings themselves are always fine.
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    results = recommend(["chicken", "garlic", "chili"], health_tags=["clean"])
    for i, dish in enumerate(results, start=1):
        print(f"{i}. {dish['name_th']}  (score {dish['score']})")
        print(f"   have   : {dish['have']}")
        print(f"   missing: {dish['missing']}")
