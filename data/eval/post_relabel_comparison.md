# Post-relabel recommender baseline: comparison with the db8c153 baseline

- Old: `data/eval/baseline_rule_metrics.json`, `baseline_top3.json` (commit `db8c153`, 2-value category). Not modified.
- New: `data/eval/post_relabel_rule_metrics.{json,md}`, `post_relabel_top3.json` at HEAD `0618189`.
- Same 30 queries (`test_set_draft_v1.json`, unchanged), same `eval_dump_top3.build()` and `eval_rule_score.compute()`, same rubric constants. `recommend()` is called with the default `category=None` (all), `seasonings=[]`, `top_k=3`. The condiment exclusion is always on.

**Headline: every number is identical to four decimals, and the top-3 lists are identical for 30 of 30 queries. The relabel and the category picker had no effect on this evaluation.**

## 1. Old vs new, overall

| variant | pass line | P@3 old | P@3 new | Hit@3 old | Hit@3 new | mean total old | mean total new |
|---|---|---|---|---|---|---|---|
| total_capped | lenient | 0.767 | 0.767 | 0.867 | 0.867 | 3.733 | 3.733 |
| total_capped | strict | 0.700 | 0.700 | 0.833 | 0.833 | 3.733 | 3.733 |
| total_uncapped | lenient | 0.967 | 0.967 | 1.000 | 1.000 | 4.089 | 4.089 |
| total_uncapped | strict | 0.856 | 0.856 | 0.967 | 0.967 | 4.089 | 4.089 |
| total_system_violation_only | lenient | 0.789 | 0.789 | 0.867 | 0.867 | 3.833 | 3.833 |
| total_system_violation_only | strict | 0.722 | 0.722 | 0.833 | 0.833 | 3.833 | 3.833 |

| independent metric | old | new |
|---|---|---|
| catalog_coverage | 0.145 | 0.145 |
| dessert_share_pooled | 0.213 | 0.213 |
| dessert_share_mean_per_query | 0.211 | 0.211 |
| intra_list_diversity_mean | 0.628 | 0.628 |
| mean_system_score | 0.679 | 0.679 |
| distinct recipes / catalog | 58/400 | 58/400 |
| system rule violations in returned items | 0 | 0 |

## 2. Per group, total_capped

| group | queries | lenient P@3 old | new | lenient Hit@3 old | new | strict P@3 old | new | strict Hit@3 old | new |
|---|---|---|---|---|---|---|---|---|---|
| A | 6 | 0.889 | 0.889 | 1.000 | 1.000 | 0.833 | 0.833 | 1.000 | 1.000 |
| B | 8 | 0.917 | 0.917 | 1.000 | 1.000 | 0.875 | 0.875 | 1.000 | 1.000 |
| C | 6 | 0.722 | 0.722 | 0.833 | 0.833 | 0.667 | 0.667 | 0.833 | 0.833 |
| D | 4 | 0.833 | 0.833 | 1.000 | 1.000 | 0.833 | 0.833 | 1.000 | 1.000 |
| E | 6 | 0.445 | 0.445 | 0.500 | 0.500 | 0.278 | 0.278 | 0.333 | 0.333 |

## 3. Per-query top-3 diff

Queries whose top-3 ids changed: **0 of 30**. For all 30 queries the old and new id lists are equal and in the same order.

Recipes whose `category` changed between `db8c153` and HEAD: 25 ({'savory->snack': 8, 'dessert->snack': 10, 'savory->condiment': 4, 'dessert->drink': 3}). Of these, 0 appear in any top-3 of the 30 queries, so no returned item changed category either. Same category for every returned recipe, old vs new: True.

Changed recipes (id: old -> new): th_004: savory->snack, th_037: savory->snack, th_075: savory->snack, th_081: savory->snack, th_091: dessert->snack, th_104: dessert->snack, th_105: dessert->snack, th_106: dessert->snack, th_107: dessert->snack, th_112: dessert->snack, th_113: dessert->snack, th_114: dessert->snack, th_115: dessert->snack, th_173: savory->condiment, th_174: savory->condiment, th_221: savory->condiment, th_228: dessert->snack, th_242: dessert->drink, th_245: dessert->drink, th_263: savory->condiment, th_281: dessert->drink, th_355: savory->snack, th_384: savory->snack, th_400: savory->snack, th_403: savory->snack

Top-3 per query for reference:

| query | group | top-3 ids | category old -> new |
|---|---|---|---|
| A1 | A | th_002, th_096, th_108 | savory->savory, dessert->dessert, dessert->dessert |
| A2 | A | th_011, th_007, th_014 | savory->savory, savory->savory, savory->savory |
| A3 | A | th_021, th_166, th_176 | savory->savory, savory->savory, savory->savory |
| A4 | A | th_022, th_296, th_157 | savory->savory, savory->savory, savory->savory |
| A5 | A | th_293, th_291, th_292 | savory->savory, savory->savory, savory->savory |
| A6 | A | th_298, th_168, th_290 | savory->savory, savory->savory, savory->savory |
| B1 | B | th_002, th_096, th_108 | savory->savory, dessert->dessert, dessert->dessert |
| B2 | B | th_029, th_203, th_011 | savory->savory, savory->savory, savory->savory |
| B3 | B | th_170, th_188, th_328 | savory->savory, savory->savory, savory->savory |
| B4 | B | th_019, th_020, th_018 | savory->savory, savory->savory, savory->savory |
| B5 | B | th_396, th_171, th_172 | savory->savory, savory->savory, savory->savory |
| B6 | B | th_235, th_336, th_269 | savory->savory, savory->savory, savory->savory |
| B7 | B | th_251, th_002, th_056 | savory->savory, savory->savory, savory->savory |
| B8 | B | th_294, th_297, th_031 | savory->savory, savory->savory, savory->savory |
| C1 | C | th_014, th_023, th_367 | savory->savory, savory->savory, savory->savory |
| C2 | C | th_002, th_001, th_003 | savory->savory, savory->savory, savory->savory |
| C3 | C | th_372, th_293, th_292 | savory->savory, savory->savory, savory->savory |
| C4 | C | th_297, th_233, th_215 | savory->savory, dessert->dessert, dessert->dessert |
| C5 | C | th_022, th_296, th_157 | savory->savory, savory->savory, savory->savory |
| C6 | C | th_101, th_232, th_053 | dessert->dessert, dessert->dessert, dessert->dessert |
| D1 | D | th_011, th_007, th_329 | savory->savory, savory->savory, savory->savory |
| D2 | D | th_021, th_176, th_170 | savory->savory, savory->savory, savory->savory |
| D3 | D | th_022, th_002, th_096 | savory->savory, savory->savory, dessert->dessert |
| D4 | D | th_029, th_203, th_011 | savory->savory, savory->savory, savory->savory |
| E1 | E | th_049, th_092, th_103 | dessert->dessert, dessert->dessert, dessert->dessert |
| E2 | E | th_101, th_095, th_214 | dessert->dessert, dessert->dessert, dessert->dessert |
| E3 | E | th_026, th_027 | savory->savory, savory->savory |
| E4 | E | th_297, th_021, th_003 | savory->savory, savory->savory, savory->savory |
| E5 | E | th_120, th_124, th_049 | dessert->dessert, dessert->dessert, dessert->dessert |
| E6 | E | th_372, th_293, th_042 | savory->savory, savory->savory, savory->savory |

## 4. Group E in detail (current data)

**E1** มีกล้วย | ingredients ['banana'] | tags [] | excluded [] | returned 3

| rank | id | name | category | A | B | C | total_capped | total_uncapped | system viol / with-optional viol |
|---|---|---|---|---|---|---|---|---|---|
| 1 | th_049 | กล้วยบวชชี | dessert | 2 | 2 | 0 | 2 | 4 | 0/0 |
| 2 | th_092 | กล้วยเชื่อม | dessert | 2 | 2 | 0 | 2 | 4 | 0/0 |
| 3 | th_103 | กล้วยปิ้ง | dessert | 2 | 2 | 0 | 2 | 4 | 0/0 |

**E2** มีมะพร้าว ฟักทอง | ingredients ['coconut', 'pumpkin'] | tags [] | excluded [] | returned 3

| rank | id | name | category | A | B | C | total_capped | total_uncapped | system viol / with-optional viol |
|---|---|---|---|---|---|---|---|---|---|
| 1 | th_101 | แกงบวดฟักทอง | dessert | 2 | 2 | 0 | 2 | 4 | 0/0 |
| 2 | th_095 | สังขยาฟักทอง | dessert | 2 | 1 | 0 | 2 | 3 | 0/0 |
| 3 | th_214 | มะพร้าวแก้ว | dessert | 2 | 2 | 0 | 2 | 4 | 0/0 |

**E3** มีเส้นก๋วยเตี๋ยว(เส้นเล็ก) | ingredients ['rice_noodle'] | tags [] | excluded [] | returned 2

| rank | id | name | category | A | B | C | total_capped | total_uncapped | system viol / with-optional viol |
|---|---|---|---|---|---|---|---|---|---|
| 1 | th_026 | ก๋วยเตี๋ยวผัดขี้เมา | savory | 2 | 0 | 1 | 3 | 3 | 0/0 |
| 2 | th_027 | ก๋วยเตี๋ยวเส้นใหญ่ผัดซีอิ๊วหมู | savory | 2 | 0 | 1 | 3 | 3 | 0/0 |

**E4** มีไข่ ไก่ กุ้ง หมู ผักหลายอย่าง (5 อย่าง) | ingredients ['egg', 'chicken', 'shrimp', 'pork', 'carrot'] | tags [] | excluded [] | returned 3

| rank | id | name | category | A | B | C | total_capped | total_uncapped | system viol / with-optional viol |
|---|---|---|---|---|---|---|---|---|---|
| 1 | th_297 | แครอทไข่ | savory | 2 | 2 | 1 | 5 | 5 | 0/0 |
| 2 | th_021 | ต้มพะโล้ | savory | 2 | 2 | 1 | 5 | 5 | 0/0 |
| 3 | th_003 | ไข่ตุ๋น | savory | 2 | 2 | 1 | 5 | 5 | 0/0 |

**E5** มีข้าวเหนียว กล้วย | ingredients ['glutinous_rice', 'banana'] | tags [] | excluded [] | returned 3

| rank | id | name | category | A | B | C | total_capped | total_uncapped | system viol / with-optional viol |
|---|---|---|---|---|---|---|---|---|---|
| 1 | th_120 | ข้าวต้มมัด | dessert | 2 | 2 | 0 | 2 | 4 | 0/0 |
| 2 | th_124 | ข้าวเหนียวปิ้ง | dessert | 2 | 2 | 0 | 2 | 4 | 0/0 |
| 3 | th_049 | กล้วยบวชชี | dessert | 2 | 2 | 0 | 2 | 4 | 0/0 |

**E6** มีเต้าหู้ เห็ดหอม วีแกน ไม่เอาพริก | ingredients ['tofu', 'shiitake'] | tags ['vegan'] | excluded ['chili'] | returned 3

| rank | id | name | category | A | B | C | total_capped | total_uncapped | system viol / with-optional viol |
|---|---|---|---|---|---|---|---|---|---|
| 1 | th_372 | ผัดผักกวางตุ้งมังสวิรัติใส่เต้าหู้เห็ดหอม | savory | 2 | 1 | 1 | 4 | 4 | 0/0 |
| 2 | th_293 | เต้าหู้ทอดซอสมะขาม | savory | 2 | 2 | 1 | 0 | 0 | 0/1 |
| 3 | th_042 | ผัดถั่วงอกหัวโตเต้าหู้ | savory | 2 | 1 | 1 | 4 | 4 | 0/0 |

**Verdict: Group E stayed exactly the same.** Capped lenient P@3 0.445 -> 0.445, Hit@3 0.500 -> 0.500. It did not recover and did not get worse.

## 5. Group E diagnosis

### H1: the old 2-value labels caused wrong category scores. NOT SUPPORTED

- 25 recipes were relabeled (10 dessert->snack, 8 savory->snack, 4 savory->condiment, 3 dessert->drink), but none of them is in any top-3 of the 30 queries, before or after.
- Top-3 ids are identical for 30/30 queries and all metrics are identical to four decimals, in every variant and group.
- Group E's results are 9 dessert items (E1, E2, E5) and 8 savory items (E3, E4, E6). Their categories are the same in both label sets.

### H2: the dessert cap limits the score, so low Group E is a rubric artifact. SUPPORTED

- `DESSERT_TOTAL_CAP = 2` is lower than `PASS_LENIENT = 3` (`tools/eval_rule_score.py:53-54`). A dessert can therefore never pass either pass line in the capped variants, whatever its ingredient match.
- All 9 dessert items in Group E have A=2 and B>=1 (B=2 for 8 of them, B=1 for th_095), so they score 3-4 uncapped, which is a pass, and exactly 2 capped, which is a fail.
- Uncapped, Group E lenient P@3 is 0.944 and Hit@3 1.000, against 0.445 / 0.500 capped. The whole gap comes from the cap.
- Group E has three all-dessert queries (E1, E2, E5), and each scores 0 under the capped variants. Hit@3 is 0.5 only because E3, E4 and E6 are savory.

### H3: the recommender genuinely returns poor matches for dessert-heavy sets. NOT SUPPORTED (with caveats)

Eligible recipes in the 400-recipe catalog (condiments excluded, tags and exclusions applied), counting recipes where the user's ingredient is a main:

| query | user ingredients | eligible dessert (main) | eligible savory (main) | returned |
|---|---|---|---|---|
| E1 | banana | 10 | 0 (snack 1) | 3 dessert, A=2, B=2 |
| E2 | coconut, pumpkin | 12 | 4 | 3 dessert, A=2, B=2/1/2 |
| E5 | glutinous rice, banana | 19 | 0 (snack 1) | 3 dessert, A=2, B=2 |

- For all three dessert queries the catalog has 10-19 matching dessert recipes, and the system returned dishes that hold every main ingredient (B=2) or most of them (B=1). Too few dessert recipes is not the cause.
- The rubric measures ingredient overlap only. Whether these are the best desserts for the query is **INCONCLUSIVE**, because there are no human labels.
- Real weaknesses outside the dessert issue:
  - **E3** (rice noodle only) returns 2 items, not 3, because only 2 recipes in the catalog have it as a main or optional. Both have B=0 (over half the mains missing), so they pass lenient only through A=2 and C=1.
  - **E6** th_293 scores 0 because `violation_with_optional` fires: the excluded `chili` is in its optional list. `recommend()` does not drop a dish for an excluded optional by design (Claude.md 4.4), so this is a rubric/system definition mismatch. The `total_system_violation_only` variant scores it 4.

## 6. Rubric issues noticed (not changed)

1. `DESSERT_TOTAL_CAP (2) < PASS_LENIENT (3)`: dessert items cannot pass in the capped variants, so the capped numbers say nothing about dessert match quality. Group E's score is set by the rubric.
2. `points_c` treats only `category == "dessert"` as 0. Snack, drink and condiment get 1 point and are never capped. The 13 recipes relabeled from dessert to snack or drink now escape the dessert penalty and cap. None is returned in this test set, so there is no effect yet.
3. `violation_with_optional` zero-scores a dish the system returns on purpose (excluded ingredient only in optional). It affects E6 here.
4. `eval_rule_score.py` and `eval_dump_top3.py` write only to hard-coded old-baseline paths, so a plain re-run overwrites the old baseline. The new files were produced by calling their functions from a scratch runner outside the repo.
5. `to_markdown()` text is fixed: the title says "Baseline" and cites `baseline_top3.json`. The new `.md` has a header saying it is the post-relabel run.
6. The queries never pass `category` and never tick seasonings, so the category picker (`0618189`) and the seasoning bonus are not exercised by this evaluation.
