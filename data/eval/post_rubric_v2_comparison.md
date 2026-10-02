# Rubric v2 comparison: post_2cat (rubric v1) vs post_rubric_v2

- Old: `data/eval/post_2cat_rule_metrics.json`, `post_2cat_top3.json` (390 recipes, rubric v1). Not modified.
- New: `data/eval/post_rubric_v2_metrics.{json,md}`, `post_rubric_v2_top3.json` (same data, same 30 queries, `RUBRIC_VERSION = "v2"`).
- Only the rubric changed: under v2 an excluded ingredient that is only optional no longer zeroes `total_capped` / `total_uncapped` (it never dropped a dish in `recommend()`; `recommender/recommend.py:162-169`). Main or seasoning matches and health-tag problems still zero an item. All other constants are unchanged.
- Top-3 recipe ids identical in all 30 queries (only scoring changed): **True**.
- Reproducibility check: recomputing `post_2cat_top3.json` under `rubric_version="v1"` reproduces the stored `post_2cat_rule_metrics.json` exactly (overall, groups, queries, differing_violations).

## 1. Overall, v1 vs v2

| variant | pass line | P@3 v1 | P@3 v2 | Hit@3 v1 | Hit@3 v2 | mean total v1 | mean total v2 |
|---|---|---|---|---|---|---|---|
| total_capped | lenient | 0.767 | 0.789 | 0.867 | 0.867 | 3.733 | 3.833 |
| total_capped | strict | 0.700 | 0.722 | 0.833 | 0.833 | 3.733 | 3.833 |
| total_uncapped | lenient | 0.967 | 0.989 | 1.000 | 1.000 | 4.089 | 4.189 |
| total_uncapped | strict | 0.856 | 0.878 | 0.967 | 0.967 | 4.089 | 4.189 |
| total_system_violation_only | lenient | 0.789 | 0.789 | 0.867 | 0.867 | 3.833 | 3.833 |
| total_system_violation_only | strict | 0.722 | 0.722 | 0.833 | 0.833 | 3.833 | 3.833 |

| independent metric | v1 | v2 |
|---|---|---|
| catalog_coverage | 0.149 | 0.149 |
| dessert_share_pooled | 0.213 | 0.213 |
| dessert_share_mean_per_query | 0.211 | 0.211 |
| intra_list_diversity_mean | 0.628 | 0.628 |
| mean_system_score | 0.679 | 0.679 |
| system rule violations in returned items | 0 | 0 |

Under v2 `total_system_violation_only` is identical to `total_capped` (both are zeroed only by the system rule), so the third variant is now redundant.

## 2. Per group, P@3 and Hit@3

### total_capped

| group | lenient P@3 v1 | v2 | lenient Hit@3 v1 | v2 | strict P@3 v1 | v2 | strict Hit@3 v1 | v2 |
|---|---|---|---|---|---|---|---|---|
| A | 0.889 | 0.889 | 1.000 | 1.000 | 0.833 | 0.833 | 1.000 | 1.000 |
| B | 0.917 | 0.917 | 1.000 | 1.000 | 0.875 | 0.875 | 1.000 | 1.000 |
| C | 0.722 | 0.722 | 0.833 | 0.833 | 0.667 | 0.667 | 0.833 | 0.833 |
| D | 0.833 | 0.917 | 1.000 | 1.000 | 0.833 | 0.917 | 1.000 | 1.000 |
| E | 0.445 | 0.500 | 0.500 | 0.500 | 0.278 | 0.333 | 0.333 | 0.333 |

### total_uncapped

| group | lenient P@3 v1 | v2 | lenient Hit@3 v1 | v2 | strict P@3 v1 | v2 | strict Hit@3 v1 | v2 |
|---|---|---|---|---|---|---|---|---|
| A | 1.000 | 1.000 | 1.000 | 1.000 | 0.944 | 0.944 | 1.000 | 1.000 |
| B | 1.000 | 1.000 | 1.000 | 1.000 | 0.958 | 0.958 | 1.000 | 1.000 |
| C | 0.944 | 0.944 | 1.000 | 1.000 | 0.722 | 0.722 | 1.000 | 1.000 |
| D | 0.917 | 1.000 | 1.000 | 1.000 | 0.917 | 1.000 | 1.000 | 1.000 |
| E | 0.944 | 1.000 | 1.000 | 1.000 | 0.722 | 0.778 | 0.833 | 0.833 |

## 3. Items whose scores changed

**2 item(s) changed** (the expectation was D2/th_170 and E6/th_293 only).

| query | rank | recipe | name | category | A/B/C | violation system / with optional | total_capped v1 -> v2 | total_uncapped v1 -> v2 | total_system_violation_only v1 -> v2 |
|---|---|---|---|---|---|---|---|---|---|
| D2 | 3 | th_170 | หมูผัดขึ้นฉ่าย | savory | 2/1/1 | 0/1 | 0 -> 4 | 0 -> 4 | 4 -> 4 |
| E6 | 2 | th_293 | เต้าหู้ทอดซอสมะขาม | savory | 2/2/1 | 0/1 | 0 -> 5 | 0 -> 5 | 5 -> 5 |

Per-query consequence for the changed items:

- D2 total_capped totals [4, 4, 0] -> [4, 4, 4]; lenient P@3 0.667 -> 1.000, strict P@3 0.667 -> 1.000, Hit@3 (lenient) 1 -> 1
- E6 total_capped totals [4, 0, 4] -> [4, 5, 4]; lenient P@3 0.667 -> 1.000, strict P@3 0.667 -> 1.000, Hit@3 (lenient) 1 -> 1
