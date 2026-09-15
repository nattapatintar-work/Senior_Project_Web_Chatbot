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

## Current database state (as of Batch 12, committed)

- **287 recipes**, 182 savory / 105 dessert (63.4% / 36.6%)
- Target: **300 recipes at ~60/40** → still need roughly **+0–1 savory /
  +12–13 dessert** (300 at 60/40 = 180/120; savory is already essentially
  at target, dessert is the entire remaining gap). **Batch 13 should be
  dessert-only** unless a genuinely new savory angle turns up unprompted.
- 3 new ingredients added across all batches so far (`yanang`, `pla_ra`,
  `dried_shrimp`) — cap is 10 total
- Latest commits: Batch 12 (277→287, includes a th_165 data-integrity
  fix — see below), Batch 11 (269→277), Batch 10 (257→269)

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

## Batch 12 — DONE (10 dishes: th_281–th_290, 4 savory + 6 dessert, plus a th_165 data-integrity fix)

All 10 written, validated (`validate_recipe_draft.py` clean, `pytest
tests/` 88 passed, `compute_nutrition.py` 287 checked / 0 mismatched),
duplicate-re-checked against the full final file (no exact `name_th` +
`main_ingredients`-set duplicates anywhere in the DB), and committed.

**3 of the original 9 planned dessert dishes had to be dropped at write
time** (ลูกชุบ, ขนมวุ้นกะทิ, ซาหริ่ม) — all three turned out to use only
`coconut_milk`/coconut cream (seasoning-flagged, `yolo_class_id: None`),
never fresh grated `coconut` (`yolo_class_id: 92`), and their only other
non-seasoning ingredient was `mung_bean` (also non-YOLO). Two of the
three (ลูกชุบ, ซาหริ่ม) had literally zero YOLO-detectable main
ingredients; ขนมวุ้นกะทิ had no valid `main_ingredients` at all once
seasonings and a flavor-only pandan were excluded — a step beyond a YOLO
failure, a hard schema violation. **New standing check, added above:
verify a "coconut" main-ingredient claim survives contact with the real
source before finalizing, not just at the research-summary stage.**

**jicama/shallot/celery — resolved, not unreachable after all.** The
prior "likely permanently unreachable" note (below, now corrected) was
wrong: the user found real single-dish sources for all three on a first
personal search attempt, after 4 prior attempts (Batches 10, 11, and
twice in 12) had come up empty. Root cause, confirmed by tracing every
query used across all 4 attempts: search results **were** turning up
real single-recipe pages (e.g. the celery stir-fry sources appeared in
this session's own Batch-12 search output) but got filtered out by
judging the snippet instead of fetching the page — plus a narrower query
style (generic "recipe site:wongnai/cookpad" phrasing) that didn't think
to try lifestyle-blog platforms like Lemon8. See `Claude.md`'s Working
Style section for the standing rule this produced. Final dishes:
- **th_287** ยำหอมแดง — `{shallot, chili}` (chili as real co-main breaks
  a collision with th_174's `{shallot}` alone)
- **th_288** แกงกะทิไก่มันแกว — `{jicama, chicken}`, a genuinely new
  curry format for jicama
- **th_289** ผัดมันแกวน้ำมันหอย — `{jicama}` alone, correctly
  `excluded_for: [vegan, vegetarian]` despite no meat (oyster_sauce)
- **th_290** ขึ้นฉ่ายผัดหมูสับ — `{celery, minced_meat}`, a genuinely
  different dictionary key from th_170's `{pork, celery}` (whole-cut vs.
  minced); accepted despite a similar cooking technique to th_170, by
  explicit user decision (celery had already failed 5 real search
  attempts by that point)
- A candidate 3rd jicama dish (ผัดมันแกว, pork + duck egg) was skipped —
  same core technique as th_165, not judged distinct enough

**th_165 data-integrity fix (found while sourcing th_289).** th_165 and
th_289 turned out to cite the *exact same* source URL — but that URL
(re-fetched twice) is a pork-free jicama stir-fry, while th_165 claimed
`main_ingredients: {jicama, pork}`. Traced via `git log -S` to th_165's
origin commit (`a61650d`, "Isan batch 1", 2026-09-13) — the wrong URL was
there from the moment th_165 was created, a same-day fetch-skip in an
unrelated batch effort, not long-term data decay. Re-sourced from a
different, verified real page (jicama + pork + duck egg,
main_ingredients corrected to `{jicama, pork, egg}`, nutrition
recomputed from Thai FCD). Added `STD:1292` (duck egg) to
`data/thaifcd_cache.json` — confirmed fetched from the live
`tools/thaifcd.py get` output, not estimated.

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

- **Never dismiss a search result as unfit based on the snippet alone —
  fetch and check the actual page content before dropping a candidate.**
  jicama/shallot/celery were wrongly reported "unreachable" across
  Batches 10–12 (4 attempts): real single-dish source pages were sitting
  in the search results the whole time, filtered out by judging the
  snippet instead of opening the page. All 3 were resolved in Batch 12
  once fetched properly — see Batch 12's section below and `Claude.md`'s
  Working Style section for the full writeup. Also try lifestyle-blog
  platforms (Lemon8, etc), not just Wongnai/Cookpad — that was part of
  the gap too.
- **Verify a "coconut" main-ingredient claim survives contact with the
  real source.** Coconut *milk/cream* (`coconut_milk`, seasoning, no
  `yolo_class_id`) is a different dictionary key from fresh grated
  coconut (`coconut`, YOLO-detectable); a dish using only coconut milk
  doesn't get YOLO-detectability credit from "coconut" (Batch 12: 3 of 9
  planned dishes dropped for exactly this once re-fetched at write time).
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

## Batch 13 — NOT STARTED, dessert-only push

Target: roughly **+12–13 dessert, +0–1 savory** — savory is essentially
at the 60/40 target already (182 of a ~180 goal), so this batch should be
dessert almost exclusively unless a genuinely new savory angle turns up
unprompted. Dessert-relevant ingredients already at "saturated, don't
force another entry" territory (mango: 5 formats, coconut: 7+, durian: 4,
lychee: 4, jackfruit: 5, taro_root: 6, cassava: 4, rambutan: 3) should
stay deprioritized unless a genuinely new angle appears — don't retry a
technique-repeat search.

### Untouched / worth another pass

- **taro_root, pineapple** — Batch 11's first-choice new dessert formats
  for both were dropped (taro's เผือกเชื่อม judged too close to existing
  ฉาบ/ทอด entries; pineapple's grilled/butter-baked angle had no real
  recipe source, only a restaurant-menu listing). A *different* angle on
  either might land — not a retry of the same search.
- **banana** — still deliberately deprioritized (11 uses, most-used
  ingredient in the DB).
- jicama/shallot/celery are now resolved (Batch 12) — no need to revisit
  unless a specific new format is wanted beyond what's already there.

### Exact next steps to resume

1. Re-run the ingredient-usage distribution fresh (check git log first —
   this file's counts are current as of the Batch 12 commit, but verify
   nothing else has landed since).
2. Build a fresh low-usage ingredient list oriented at dessert formats
   not yet tried (different fruits/starches than Batches 10–12 covered),
   plus opportunistically retry taro_root/pineapple with new angles.
3. Apply the same duplicate-check-before-proposing discipline (exact
   `name_th` match AND `main_ingredients`-set match against the full
   existing list) that's caught real near-misses in every batch so far.
4. Verify every source URL is a real single-recipe page by actually
   fetching it (don't trust the search snippet, and don't stop at
   Wongnai/Cookpad — Batch 12 found real sources on Lemon8 too). Batch 10
   had one dead/paywalled source, Batch 11 had an ingredient-list
   correction, and Batch 12 had 3 dishes dropped for a coconut-milk-vs-
   fresh-coconut mixup — all caught only by re-fetching at write time,
   never by trusting the research-phase summary.
5. Report the consolidated dish list back to the user for approval before
   writing anything.
6. Once approved: source Thai FCD/external nutrition for all dishes
   (checking `external_nutrition.json` first per the standing rule), write
   into `data/recipes.json`, run `tools/compute_nutrition.py --fill`,
   `tools/derive_diet_tags.py --fix`, assign clean/keto tags, run
   `tools/validate_recipe_draft.py` + full `pytest tests/` +
   `tools/compute_nutrition.py` (verify), show the exact diff, get
   approval, commit.
