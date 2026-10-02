# Post-2-category comparison: post_relabel (400 recipes, 5 categories) vs post_2cat (390 recipes, 2 categories)

- Old: `data/eval/post_relabel_rule_metrics.json`, `post_relabel_top3.json` (HEAD `0618189`, 400 recipes: savory 283, dessert 92, snack 18, condiment 4, drink 3). Not modified.
- New: `data/eval/post_2cat_rule_metrics.{json,md}`, `post_2cat_top3.json` (390 recipes: savory 292, dessert 98). Produced by calling `eval_dump_top3.build()` and `eval_rule_score.compute()` unchanged from a scratch runner.
- Same 30 queries (`test_set_draft_v1.json`), same rubric constants, `recommend()` default `category=None`, `seasonings=[]`, `top_k=3`.

## 1. Overall, old vs new

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
| catalog size | 400 | 390 |
| distinct recipes returned | 58 | 58 |
| catalog_coverage | 0.145 | 0.149 |
| dessert_share_pooled | 0.213 | 0.213 |
| dessert_share_mean_per_query | 0.211 | 0.211 |
| intra_list_diversity_mean | 0.628 | 0.628 |
| mean_system_score | 0.679 | 0.679 |
| system rule violations in returned items | 0 | 0 |

Catalog coverage differs only because the catalog shrank from 400 to 390 (58 distinct recipes in both).

## 2. Per group (A-E), P@3 and Hit@3

### total_capped

| group | lenient P@3 old | new | lenient Hit@3 old | new | strict P@3 old | new | strict Hit@3 old | new |
|---|---|---|---|---|---|---|---|---|
| A | 0.889 | 0.889 | 1.000 | 1.000 | 0.833 | 0.833 | 1.000 | 1.000 |
| B | 0.917 | 0.917 | 1.000 | 1.000 | 0.875 | 0.875 | 1.000 | 1.000 |
| C | 0.722 | 0.722 | 0.833 | 0.833 | 0.667 | 0.667 | 0.833 | 0.833 |
| D | 0.833 | 0.833 | 1.000 | 1.000 | 0.833 | 0.833 | 1.000 | 1.000 |
| E | 0.445 | 0.445 | 0.500 | 0.500 | 0.278 | 0.278 | 0.333 | 0.333 |

### total_uncapped

| group | lenient P@3 old | new | lenient Hit@3 old | new | strict P@3 old | new | strict Hit@3 old | new |
|---|---|---|---|---|---|---|---|---|
| A | 1.000 | 1.000 | 1.000 | 1.000 | 0.944 | 0.944 | 1.000 | 1.000 |
| B | 1.000 | 1.000 | 1.000 | 1.000 | 0.958 | 0.958 | 1.000 | 1.000 |
| C | 0.944 | 0.944 | 1.000 | 1.000 | 0.722 | 0.722 | 1.000 | 1.000 |
| D | 0.917 | 0.917 | 1.000 | 1.000 | 0.917 | 0.917 | 1.000 | 1.000 |
| E | 0.944 | 0.944 | 1.000 | 1.000 | 0.722 | 0.722 | 0.833 | 0.833 |

## 3. Queries whose top-3 ids changed

**1 of 30 queries changed.**

**C1** ingredients ['chicken'] | tags ['clean'] | excluded []

| rank | old id | old name | old cat | old score | new id | new name | new cat | new score |
|---|---|---|---|---|---|---|---|---|
| 1 | th_014 | ผัดเผ็ดไก่ | savory | 0.77 | th_014 | ผัดเผ็ดไก่ | savory | 0.77 |
| 2 | th_023 | ผัดพริกขิงไก่ใส่ถั่วฝักยาว | savory | 0.6 | th_023 | ผัดพริกขิงไก่ใส่ถั่วฝักยาว | savory | 0.6 |
| 3 | th_367 | ผักโขมผัดไก่ | savory | 0.55 | th_364 | ผัดกุยช่ายใส่ไก่ต้ม | savory | 0.54 |

The score shift is not caused by a deleted recipe being returned: no deleted id is in any old or new top-3. The TF-IDF vectorizer is fitted over all recipes at import (`recommender/recommend.py:135-137`), so deleting 10 recipes changes the IDF weights, which can reorder near-tied results.

## 4. Summary

- Headline P@3, Hit@3 and mean total are identical in all three variants (overall).
- Group results identical for every group: True.
- Queries with a changed top-3: 1.
