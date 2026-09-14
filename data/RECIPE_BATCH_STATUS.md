# Recipe database batch-expansion status

> **What this file is.** Continuity notes for the ongoing `data/recipes.json`
> expansion (40 → 300 recipes), written so a new session can resume a batch
> without re-deriving the research that's already been done. Updated at the
> end of each batch, or mid-batch when a session ends with work still
> in-flight (like this one).
>
> This is a working log, not a permanent design doc — once the database
> hits 300 and the expansion project is done, this file's job is done too.

---

## Current database state (as of Batch 10, committed)

- **269 recipes**, 176 savory / 93 dessert (65.4% / 34.6%)
- Target: **300 recipes at ~60/40** → still need roughly **+4 savory / +27
  dessert**. The savory/dessert gap widened this batch (Batch 10's
  untouched-ingredient list was all vegetables, which don't naturally
  yield dessert candidates) — **Batch 11 must go heavily dessert-focused**
  to recover toward 60/40 by 300.
- 3 new ingredients added across all batches so far (`yanang`, `pla_ra`,
  `dried_shrimp`) — cap is 10 total
- Latest commits: Batch 10 (257→269, this session), `547f0b1` (Batch 9,
  249→257)

## Batch 10 — DONE (12 dishes: th_261–th_272, 11 savory + 1 dessert)

All 12 written, validated (`validate_recipe_draft.py` clean,
`pytest tests/` 88 passed, `compute_nutrition.py` 269 checked / 0
mismatched), duplicate-re-checked against the full final file, and
committed. Two notable resolutions, both judged legitimate rather than
workarounds:

- **th_261** (แกงเหลืองปลา) — the originally-approved `thaifoodmaster`
  source turned out to be a paywalled landing page with no actual recipe
  content. Swapped to a working single-recipe Wongnai source for the same
  dish (southern yellow/sour fish curry); disclosed in `notes`.
- **th_265** (แกงเขียวหวานหมูมะเขือเปราะ) — its base `main_ingredients` set
  (`{pork, thai_eggplant}`) was an exact collision with existing th_077 and
  th_194. Resolved by promoting `kaffir_lime_leaf` from optional to main —
  the source uses 5–10 whole leaves (a defining quantity), with direct
  precedent at th_166/th_167 for counting it as a main ingredient at
  similar gram amounts.

New nutrition sources added (both disclosed, cited): `EXT:usda-vinegar-
distilled` (Thai FCD has no vinegar record at all — confirmed by repeated
search, plain and under the Thai term) and `EXT:usda-baking-powder`.

## Standing rules for every batch (from `Claude.md` + accumulated lessons)

- Real `recipe_source_url` — an exact single-recipe page, never a
  search/listing page
- Real nutrition: Thai FCD (INMU) first via `tools/thaifcd.py` /
  `data/thaifcd_cache.json`; a disclosed external (USDA) fallback via
  `data/external_nutrition.json` only when Thai FCD has no usable record
- **Before treating any ingredient as needing a fresh Thai-FCD "closest
  available" workaround, check `data/external_nutrition.json` first** — the
  th_218 (chayote) / th_220 (hyacinth_bean) / th_242 (lime) lesson from
  Batch 8: a correct external record already existed in two of those three
  cases and was never looked up
- Health tags (`clean`/`keto`) computed only *after* real nutrition exists,
  never guessed upfront — see `data/HEALTH_TAGS.md` for the exact rules
- `vegetarian`/`vegan` via `tools/derive_diet_tags.py --fix`, merged into
  existing `health_tags` (`sorted(set(existing) | set(new))`), never
  overwritten
- ≥1 YOLO-detectable ingredient (has a non-null `yolo_class_id` in
  `data/ingredients.json`) in `main_ingredients`
- Validate with `tools/validate_recipe_draft.py` before finalizing (catches
  `is_seasoning` misplacement — has caught real bugs almost every batch)
- **Duplicate-check every candidate dish before writing**: exact `name_th`
  match AND `main_ingredients`-set match against the full existing list.
  Two real catches this session alone:
  - Batch 9: a planned mushroom tom-yum dish turned out to already exist
    as th_078, mischaracterized earlier as a stir-fry without actually
    opening its record
  - Batch 10 (this session): a planned "crispy fried oyster" dish would
    have set-collided with th_239 (`main_ingredients: ['oyster']`), and its
    real ingredient list was too close to th_185's ออส่วน anyway — dropped
- Never pad dish counts to hit the ~12-15 target if genuine sources can't
  be found — drop honestly with a specific reason, same as every prior
  batch
- Show exact JSON diffs (not prose summaries) before every commit
- New ingredients only if clearly justified, hard cap 10 total (3 used)

## Batch 11 — NOT STARTED, must be heavily dessert-focused

Target: roughly **+4 savory / +27 dessert** to recover toward 60/40 by 300.
Most of Batch 10's untouched vegetable-ingredient list won't help with
this — dessert candidates need their own ingredient-usage pass (fruits,
coconut milk, rice flour, etc.), not a continuation of the vegetable list
below.

### Leftover from Batch 10's savory list — still untouched

jicama, shallot, celery — not reached in Batch 10 (ran out of turn
budget). All three were dropped once already in Batch 10 with reasons
above the fold in git history — see the Batch 10 commit message / this
file's prior version if picking one back up; needs a genuinely new angle,
not a retry of the same search.

Also explicitly deprioritized in Batch 10 because they already have two
distinct formats in the DB: malabar_spinach, amaranth, senna_siamea,
clove_basil, maenglak, spinach, bottle_gourd, banana_flower, green_peas.

### Exact next steps to resume

1. Re-run the ingredient-usage distribution fresh (check git log first —
   this file's counts are current as of the Batch 10 commit, but verify
   nothing else has landed since).
2. For the dessert push: pull the list of dessert-relevant ingredients at
   low use-counts (fruits, glutinous rice flour, coconut milk formats,
   etc.) the same way the savory list was built, and prioritize those —
   this is a different ingredient set than Batch 10 worked through.
3. Apply the same duplicate-check-before-proposing discipline (exact
   `name_th` match AND `main_ingredients`-set match against the full
   existing list) that's caught real near-misses in every batch so far.
4. Report the consolidated dish list back to the user for approval before
   writing anything.
5. Once approved: source Thai FCD/external nutrition for all dishes
   (checking `external_nutrition.json` first per the standing rule), write
   into `data/recipes.json`, run `tools/compute_nutrition.py --fill`,
   `tools/derive_diet_tags.py --fix`, assign clean/keto tags, run
   `tools/validate_recipe_draft.py` + full `pytest tests/` +
   `tools/compute_nutrition.py` (verify), show the exact diff, get
   approval, commit.
