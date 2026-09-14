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

## Current database state (as of Batch 11, committed)

- **277 recipes**, 176 savory / 101 dessert (63.5% / 36.5%)
- Target: **300 recipes at ~60/40** → still need roughly **+3–4 savory /
  +19 dessert**. Batch 11 moved the ratio the right direction (34.6% →
  36.5% dessert) but landed 0 of the savory portion — **Batch 12 should
  keep pushing dessert** and only pick up savory (jicama/shallot/celery
  or a fresh ingredient) opportunistically if a real source turns up.
- 3 new ingredients added across all batches so far (`yanang`, `pla_ra`,
  `dried_shrimp`) — cap is 10 total
- Latest commits: Batch 11 (269→277), Batch 10 (257→269), `547f0b1`
  (Batch 9, 249→257)

## Known, accepted: same `name_th` with different `main_ingredients`

`th_039`/`th_198` (ผัดผักบุ้งไฟแดง) and `th_099`/`th_220` (ผัดถั่วแปบ) share an
exact dish name but have different `main_ingredients` sets — **not a bug,
left as-is by user decision**. Generic Thai dish names legitimately cover
multiple ingredient variants in real usage; renaming one would misrepresent
what people actually call the dish. The duplicate-check rule (name_th
match AND main_ingredients-set match) correctly does not flag these,
since only the name half matches. The recommender keys off
`main_ingredients`, not `name_th`, so there's no functional impact. Don't
re-flag this pattern in future batches unless a *new* pair also matches on
`main_ingredients`.

## Batch 11 — DONE (8 dishes, th_273–th_280, all dessert)

All 8 written, validated (`validate_recipe_draft.py` clean, `pytest
tests/` 88 passed, `compute_nutrition.py` 277 checked / 0 mismatched),
duplicate-re-checked against the full final file, and committed. No new
dictionary ingredients, no new external nutrition sources (reused
`EXT:usda-baking-powder` from an earlier batch).

- **th_280** (ขนมมันทอด, cassava) — pre-approval assumed a tapioca-starch
  coating; re-fetching the source directly showed it's actually
  `rice_flour`. Corrected before writing, disclosed in `notes`, confirmed
  not a duplicate of th_105 (sweet potato — same `name_th` substring
  "มันทอด", different ingredient entirely).
- Savory research this batch (jicama/shallot/celery, genuinely new angles
  each) came up empty — every search surfaced only listing/collection
  pages, no single fetchable recipe page for any of the three. Dropped
  rather than citing a listing page, per user instruction to keep
  dropping until a real source turns up (no Wikipedia/encyclopedia
  fallback allowed).

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

## Batch 12 — NOT STARTED, keep pushing dessert

Target: roughly **+3–4 savory / +19 dessert** to close the rest of the
gap toward 60/40 by 300. Batch 11's dessert-relevant ingredients that hit
"saturated, don't force another entry" territory (mango: 5 formats,
coconut: 7) should stay deprioritized unless a genuinely new angle
appears — don't retry the same technique-repeat search.

### Untouched / worth another pass

- **taro_root, pineapple** — Batch 11's first-choice new dessert formats
  for both were dropped (taro's เผือกเชื่อม judged too close to existing
  ฉาบ/ทอด entries; pineapple's grilled/butter-baked angle had no real
  recipe source, only a restaurant-menu listing). A *different* angle on
  either might land — not a retry of the same search.
- **jicama, shallot, celery** — dropped again in Batch 11 with genuinely
  new angles each (ต้มจืดมันแกว/นึ่ง for jicama, ยำหอมแดง for shallot,
  ต้มจืดขึ้นฉ่าย/ไข่เจียวขึ้นฉ่าย for celery) — same result as Batch 10, no
  single fetchable recipe page for any of them. **No Wikipedia/
  encyclopedia fallback allowed** (explicit user decision) — keep
  dropping until a real single-recipe page turns up, or treat these as
  likely permanently unreachable for this DB's sourcing standard.
- **banana** — still deliberately deprioritized (11 uses, most-used
  ingredient in the DB).

### Exact next steps to resume

1. Re-run the ingredient-usage distribution fresh (check git log first —
   this file's counts are current as of the Batch 11 commit, but verify
   nothing else has landed since).
2. Build a fresh low-usage ingredient list oriented at dessert formats
   not yet tried (different fruits/starches than Batches 10–11 covered),
   plus opportunistically retry taro_root/pineapple with new angles.
3. Apply the same duplicate-check-before-proposing discipline (exact
   `name_th` match AND `main_ingredients`-set match against the full
   existing list) that's caught real near-misses in every batch so far.
4. Verify every source URL is a real single-recipe page (open and read
   it, don't trust the search snippet) — Batch 10 had one dead/paywalled
   source and Batch 11 had one ingredient-list correction slip through
   the research phase, both caught only by re-fetching at write time.
5. Report the consolidated dish list back to the user for approval before
   writing anything.
6. Once approved: source Thai FCD/external nutrition for all dishes
   (checking `external_nutrition.json` first per the standing rule), write
   into `data/recipes.json`, run `tools/compute_nutrition.py --fill`,
   `tools/derive_diet_tags.py --fix`, assign clean/keto tags, run
   `tools/validate_recipe_draft.py` + full `pytest tests/` +
   `tools/compute_nutrition.py` (verify), show the exact diff, get
   approval, commit.
