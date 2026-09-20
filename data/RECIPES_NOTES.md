# Recipe Database — Conventions and Judgment Calls

`data/recipes.json` holds 40 recipes. Every nutrient value in it comes from a cited
source; **this file records the decisions that are mine rather than the source's**, so
they can be argued with individually.

Per-recipe reasoning lives in each recipe's `notes` field. What is here is the
cross-cutting stuff that would otherwise be repeated 40 times.

---

## 1. No macro was typed by hand

160 numbers means 160 chances to slip a decimal, and a slipped decimal in a nutrition
table does not look like an error — it looks like a slightly different dish.

So each recipe declares **where its numbers come from**, and `tools/compute_nutrition.py`
does the arithmetic:

| `nutrition_method` | Declares | Arithmetic |
|---|---|---|
| `direct` (32 recipes) | `nutrition_ref`, e.g. `"STD:1456"` | source per-100 g × `serving_g` / 100 |
| `computed` (8 recipes) | `nutrition_basis` + `basis_refs` | Σ (grams × per-100 g / 100) |

```
python tools/compute_nutrition.py          # verify — exits 1 on any mismatch
python tools/compute_nutrition.py --fill    # recompute and write back
```

Run the verify mode after editing any serving size or gram amount. It exists precisely
for the case where someone changes a portion and forgets to refresh the macros.

---

## 2. Serving sizes

Thai FCD publishes per 100 g, so `serving_g` is the multiplier. Get it wrong and **all
four macros scale together**, which is the nasty part — every number stays in a
believable ratio, so nothing looks off.

| Dish type | `serving_g` | Reasoning |
|---|---|---|
| Rice / noodle one-plate | 300 | a เมนูจานเดียว plate |
| Curry / soup | 200 | **the curry only** — rice is counted as its own dish |
| Stir-fry side | 150 | |
| Salad, yum | 120 | a shared side, not a main |
| Fried egg dish | 70 | about two eggs |
| Boiled egg | 50 | one egg |
| Computed recipes | Σ of `nutrition_basis` | so the portion and its parts cannot drift apart |

---

## 3. ⚠️ The keto tag is the weakest thing in this database

23 of 40 recipes carry `keto`, which is far more than you would expect from a Thai recipe
database. That number is not a bug — the rule in `HEALTH_TAGS.md` was applied exactly as
written — but it is misleading, and here is why:

**Curry servings are 200 g of curry, with the rice counted separately.** So
แกงเขียวหวานไก่ scores 6.1 g of carbohydrate and passes the ≤10 g test. Nobody eats green
curry without rice. Add a normal 200 g serving of rice and the real total is nearer 60 g.

The tag is therefore true about *the dish as measured* and misleading about *the meal as
eaten*. Two things follow:

- **Week 7:** the recommender must not present a curry as keto-friendly without saying
  "without rice". Tracked as concern **C15**.
- **The rule may need a third clause** — something like "not conventionally served with
  rice". That was not added here because changing a rule to get a nicer-looking answer,
  after seeing the answer, is how a definition stops meaning anything. Better to leave the
  rule honest and record that it is producing a bad result.

`clean` (17 of 40) is more trustworthy: it is mostly driven by the absence of sugar and
coconut milk, which is a property of the dish itself rather than of the portion.

---

## 4. Gram amounts in the 8 computed recipes

Thai FCD has **no entry for any simple home stir-fry** — no ผัดกะหล่ำปลี, no ไก่ผัดขิง, no
ผัดผักรวมมิตร. Those dishes had to be built from per-ingredient values.

The nutrient values stay sourced. **The gram amounts are mine** (concern C14). They are
one-person household portions, and two conventions are worth knowing:

- **Oil is always stated explicitly** — 10–12 g, about one tablespoon. It is the single
  biggest lever on the calorie count, so it is never folded into another number. If you
  think a Thai cook uses more oil than this, these calorie figures are low, and that is
  the first number to change.
- **Raw weights, not cooked.** Chicken is priced from the raw record (F25). Cooking loss
  and oil absorption are not modelled, so a real cooked portion weighs less and is a
  little more calorie-dense per gram than shown.

---

## 5. Two things the sources could not supply

**Fish sauce has no protein value.** Thai FCD record N71 leaves `PROTCNT` blank. It is
summed as zero, so th_034 and th_038 understate protein by roughly 0.4 g. It is *not*
stored as 0 in the cache — `null` means "not determined", 0 would mean "none", and those
are different claims. `compute_nutrition.py` prints a note for each affected recipe on
every run.

**Broccoli is not in Thai FCD at all** (concern C12), so th_040 uses USDA FoodData
Central. This needed a correction before the two could be added together:

> USDA "Carbohydrate, by difference" **includes** dietary fibre.
> Thai FCD `CHOAVLDF` **excludes** it.

Summing them raw would have overstated broccoli's carbs by 2.6 g per 100 g — enough to
push th_040 over the keto limit and flip its tag. Broccoli therefore enters as
6.64 − 2.6 = **4.04 g available carbohydrate**. Both raw figures are kept in
`data/external_nutrition.json` so the subtraction is checkable.

`onion` is also missing from Thai FCD but needed no external source, because it appears
only in `direct` recipes where the whole dish was analysed.

---

## 6. Coverage, and one honest imbalance

| | |
|---|---|
| Recipes | 40 |
| Photo-reachable (all `main_ingredients` detectable) | **22** — floor is 20 |
| Direct / computed | 32 / 8 |
| Detectable classes with at least one recipe | **20 of 20** |
| Energy range per serving | 39 kcal (สลัดผักสด) – 663 kcal (ผัดซีอิ๊วหมู) |

**Chicken appears in 16 of 40 recipes.** That is more than ideal, and it is structural
rather than careless: chicken and egg are the *only* proteins among the 20 detectable
classes, so almost any photo-reachable dish with meat in it has to be a chicken dish.
Chicken *curries* specifically are capped at 5.

The fix is not more recipes — it is a class list with more proteins in it. Worth raising
at the Week 6 sync, and worth a sentence in the report, since it is the same underlying
mismatch as concern C12: the detection classes were chosen around what a camera can see,
while Thai cooking data is organised around what people actually eat.

**สลัดผักสด at 39 kcal** is the one dish below the 40 kcal sanity floor. It is correct —
200 g of undressed raw vegetables really is that light. Its dressing is deliberately not
counted, and adding a typical 30 g of creamy dressing would roughly triple the figure.

---

## 7. Rules that the tests enforce, so you do not have to remember them

`tests/test_recipes.py` (21 tests) checks all of this on every run:

- Every ingredient key resolves against `ingredients.json` — no free-text names
- `seasonings` contains only `is_seasoning: true` items, and `main_ingredients` none
- Anything with `is_animal_product: true` excludes `vegan` — this is what catches fish
  sauce, oyster sauce, and shrimp paste, the trap `Claude.md:429` names
- Meat and seafood exclude `vegetarian`; excluding vegetarian implies excluding vegan
- `keto` requires ≤10 g carb **and** no starch staple in `main_ingredients`
- `clean` requires no sugar and no coconut milk
- ≥20 recipes reachable from a photo alone
- Every recipe cites a source, and computed ones show their gram amounts

The two `clean` rules that are *not* machine-checkable — "not deep-fried" and "no
processed meat" — stay human judgements, applied per `HEALTH_TAGS.md`. th_004
(มันฝรั่งทอด) and th_022 (ทอดมันกุ้ง) are the two dishes where deep-frying was the
deciding factor.

---

## 8. Convention: promoting a minor-by-weight ingredient to `main_ingredients`

Decided 2026-09-20 (user decision, round 1 of the coverage batch). Promoting an
ingredient that is minor by weight into `main_ingredients` is an **accepted, intentional
convention**, not a one-off judgement call, when it is done for a system reason:

- to avoid an **exact `main_ingredients`-set collision** with an existing recipe, or
- to satisfy a task's **required ingredient** (e.g. "carrot must be a main ingredient").

Conditions: the ingredient must really be in the source recipe, ideally one of its named
or defining components, and the promotion must be disclosed in the recipe's `notes`
(what was promoted, why, and its actual weight share).

Precedent examples:
- **th_299** (ต้มจืดหัวไชเท้าแครอท) — carrot is main although it is the minor vegetable
  by weight (about 40 g against 165 g of radish per serving); it is in the dish name and
  the task required carrot as a main.
- **th_308** (เนื้อผัดพริกไทยดำ) — onion promoted to main because `{beef}` alone would
  collide exactly with th_156 and th_235.

Earlier examples of the same pattern: th_265 (kaffir lime leaf), th_284, th_290.

## 9. Known inconsistencies / backlog for a future cleanup pass

Recorded, deliberately **not fixed** yet.

- **Crab weight basis differs between th_240 and th_303.** th_240 (ปูผัดพริกไทยดำ) counts
  its crab grams directly as edible meat against `STD:1157` (meat-only record). th_303
  (ปูอบวุ้นเส้น) treats the source's 300 g of crab pieces as whole crab with shell and
  assumes about 50% edible (75 g meat per serving). The two recipes therefore apply
  different assumptions to the same kind of source figure. Reconcile to one convention
  later; neither recipe is changed now. (th_186, th_247 and th_304 also use crab; check
  them in the same pass.)
- **th_034 (ผัดผักโขมกระเทียม) nutrition uses the wrong Thai FCD record.** Its key is
  `spinach` but its nutrition is computed from `STD:489` (Amaranth, raw), not `STD:469`
  (Spinach, raw), which every other spinach recipe uses. Related to concern C6 (the
  ปวยเล้ง/ผักโขม spinach-vs-amaranth ambiguity). Needs a decision on whether the dish is
  really spinach or amaranth, then either a re-key or a nutrition recompute. Not fixed.
- **Fatty pork cuts are priced as lean (known limitation, th_328).** Thai FCD has no
  pork-belly (or other high-fat pork) record, so th_328 (หมูย่างเกาหลีห่อผักสลัดคอส,
  100 g pork belly + 100 g pork shoulder per serving) is priced entirely with lean pork
  `STD:958`. Fat and kcal are therefore understated for that recipe, considerably so for
  the belly half. Accepted as-is with the disclosure already in its `notes` (2026-09-20).
  The same shortfall applies to any recipe that prices a fatty cut with a lean record,
  e.g. th_299 (pork ribs priced as `STD:958`); the same idea applies to beef "with fat"
  priced with plain beef meat `STD:936` in th_306 and th_335. No audit has been done for
  other affected recipes. Revisit if a better Thai FCD record (or a disclosed external
  one) turns up.
