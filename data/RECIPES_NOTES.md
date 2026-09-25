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

## 9. Convention: edible weight of shell-on shellfish, whole squid, whole fish and bone-in wings (rounds 3 and 6, decided 2026-09-20)

For the raw-weight amounts given in a source, decide what is actually edible:

- **Meat-labelled weights are counted as-is**: shucked or boiled meat (e.g. "หอยแมลงภู่แกะต้ม
  200 g" in th_342), canned clam meat (th_344), and already-cleaned/cut squid (th_339).
- **Shell-on bivalves (mussel, clam): about 30% edible.** e.g. th_345: 1 kg of clams in shell
  = 300 g meat; th_343: 12 shell-on clams assumed about 20 g each = 72 g meat.
- **Whole uncleaned squid: about 75% edible** (th_338: 400 g whole squid = 300 g).
- When a source does not say whether the weight is shell-on (e.g. th_341 หอยทอด, where the
  mussels are batter-fried), the assumption is stated in that recipe's `notes`.
- Crab keeps its own rule from round 2 (hard-shell about 50%, soft-shell about 100%,
  meat-labelled as-is).
- **Whole fish: about 45% edible** (fillet yield; decided in round 6). A source that says
  "2 whole tilapia" with no size is assumed to be about 400 g per fish and priced as
  360 g of meat in total (th_396 ปลาทับทิมนึ่งขิง); th_389 (แกงส้มผักบุ้งปลาน้ำดอกไม้)
  assumes 2 fish x about 250 g whole = 225 g of meat. A weight that is already labelled as
  fillet or meat is counted as-is.
- **Bone-in chicken wings: about 55% edible** (round 6). th_393 (ไก่ทอดตะไคร้): 1 kg of
  mid-wings is priced as 550 g of meat and skin. The general chicken record `STD:895`
  (12.4 g fat/100 g) already carries skin-level fat, so wings priced this way are not a
  lean-record-for-fatty-cut mismatch.
- These two percentages are round-6 assumptions, not measured yields. Each recipe that uses
  them states the fish/wing size it assumed in its `notes`.

## 10. Known Limitations

One place for everything that is known to be imperfect in the recipe database, written up
so it can be lifted into the report's limitations section. Entries are grouped by kind.
All are recorded deliberately and **not fixed** yet; each says what would resolve it.
(Limitations of the original 40-recipe database are in §3 keto tag, §4 assumed gram
amounts, §5 what the sources could not supply, and §6 coverage imbalance.)

### A. Edible-weight inconsistencies (which grams count as food)

- **Crab weight basis differs between th_240 and th_303.** th_240 (ปูผัดพริกไทยดำ) counts
  its crab grams directly as edible meat against `STD:1157` (meat-only record). th_303
  (ปูอบวุ้นเส้น) treats the source's 300 g of crab pieces as whole crab with shell and
  assumes about 50% edible (75 g meat per serving). The two recipes therefore apply
  different assumptions to the same kind of source figure. Reconcile to one convention
  later; neither recipe is changed now. (th_186, th_247 and th_304 also use crab; check
  them in the same pass.) The crab rule adopted in round 2 (hard-shell about 50%,
  soft-shell about 100%, meat-labelled as-is) governs all recipes written since.
- **Bivalve weights: th_056, th_057 and th_238 count grams as meat regardless of shell.**
  th_056 (หอยลายผัดพริกเผา), th_184, th_237 (clam) and th_057, th_187, th_238 (mussel) each
  price 150 g of shellfish directly against `STD:1176` / `STD:1173` (edible-meat records)
  without saying whether the source weight was shell-on. Since round 3 the rule in §9
  applies to new recipes; these six older recipes were NOT revisited. Reconcile in a future
  cleanup pass (same category of issue as th_240 vs th_303 for crab).
- **Older fish and bone-in recipes were not revisited for the round-6 whole-fish and wing
  rules (§9).** Earlier fish dishes such as th_171 (ปลากระพงผัดขึ้นฉ่าย, 150 g) and th_261
  (แกงเหลืองปลา, 150 g) price the source's fish weight directly against the fish record
  `STD:1084`, and the older recipes do not always say whether that weight was whole fish or
  fillet. Not audited; reconcile in a future cleanup pass if any of them start from a
  whole-fish weight.

### B. Nutrition record does not match the food

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
- **th_034 (ผัดผักโขมกระเทียม) nutrition uses the wrong Thai FCD record.** Its key is
  `spinach` but its nutrition is computed from `STD:489` (Amaranth, raw), not `STD:469`
  (Spinach, raw), which every other spinach recipe uses. Related to concern C6 (the
  ปวยเล้ง/ผักโขม spinach-vs-amaranth ambiguity). Needs a decision on whether the dish is
  really spinach or amaranth, then either a re-key or a nutrition recompute. Not fixed.
- **Lemongrass (`STD:237`) has kcal and carbohydrate but blank protein and fat.** The only
  Thai FCD lemongrass record was added to the cache in round 6 for th_392 (ยำตะไคร้), th_393
  (ไก่ทอดตะไคร้) and th_396 (ปลาทับทิมนึ่งขิง, as part of a galangal/lemongrass topping). The
  tool counts the blank fields as 0, so protein and fat from lemongrass are slightly
  understated in those three recipes (small: 5-22 g of lemongrass per serving). The older
  soups th_018/019/020 are not affected: their nutrition is `direct` (a whole-dish INMU
  record), so lemongrass is never priced separately there.
  Revisit if a fuller record (or a disclosed external one) turns up.
- **th_399 (ผัดยอดฟักแม้วไฟแดง) prices chayote SHOOTS with the chayote FRUIT record.** The
  dish uses ยอดฟักแม้ว (young shoots, 500 g), keyed as `chayote` because it is the same
  plant as the ฟักแม้ว fruit in th_097, th_218 and th_285. Thai FCD's only chayote record
  (`STD:586`, "young leaves") has all four macros blank, so nutrition comes from the USDA
  fruit record `EXT:usda-chayote-raw` (19 kcal, 0.82 g protein per 100 g), the same
  external record the fruit dishes use. Shoots are leafier than the fruit, so protein and
  fibre are understated for this recipe (kcal is probably a little low as well). Accepted
  as-is on 2026-09-20 with the disclosure already in its `notes`. Revisit if a shoots
  record turns up, or split the dictionary entry (fruit vs shoots) if the difference
  matters for recommendations.

### C. Coverage targets not met

- **quail_egg: landed at 5 after round 3 (target 6-9 not met) — RESOLVED in round 4,
  now 6.** Savory quail-egg dishes are genuinely scarce in Thai cuisine. Most search results
  for "ไข่นกกระทา" are the dessert ขนมไข่นกกระทา, which contains no quail egg at all and was
  rejected. Only two further verifiable savory dishes were found in round 3 (th_346
  green-curry fried quail eggs, th_347 mixed-vegetable oyster-sauce stir-fry), on top of the
  existing three (th_058, th_164, th_248). Decided 2026-09-20 to accept 5 and report the
  shortfall rather than pad with an unfit or borderline dish. Round 4 then found a sixth
  genuine dish while sourcing amaranth recipes — th_368 (ผัดผักโขมน้ำมันหอยและไข่นกกระทา,
  amaranth stir-fried with boiled quail eggs) — taking quail_egg to 6 main-ingredient recipes,
  so the 6-9 target is now met. Kept here as a record of why the count sat at 5 for a time; th_368's
  own quantities are all assumed (its source gives none), so it is a weak-quantity dish.
- **mussel landed at 5 main-ingredient recipes (target 6-9 not met).** The remaining
  verifiable mussel dishes were near-duplicates of stir-fries already in the database: a
  sixth candidate, ผัดโคตรหอยแมลงภู่ (onion + sweet basil), differs from th_342 (shallot +
  sweet basil) and the existing th_057 (holy basil) by little more than the aromatics, and
  a steamed-mussel-with-dip dish duplicated th_187. Decided 2026-09-20 to keep only
  หอยทอด (th_341) and the shallot stir-fry (th_342) and report 5, rather than add
  near-identical recipes that would inflate the count without adding coverage.
- **ivy_gourd landed at 3 main-ingredient recipes (target 4-5 not met, round 5).** The
  existing two are th_068 (with egg) and th_199 (with minced meat); round 5 added th_379
  (ตำลึงผัดน้ำมัน), a deliberately minimal two-ingredient dish (ivy gourd + oil, exactly as
  its source lists it). Every other ตำลึง dish found was rejected: ตำลึงผัดไข่ has the same
  main set as th_068; แกงจืดตำลึงหมูสับ has the same main set as th_199 (and one version uses
  egg tofu, not the dictionary tofu); แกงเลียง (all pages) is a near-duplicate of th_043
  แกงเลียงกุ้ง; one แกงเลียง page used ตำลึงหวาน, a term with no clear meaning here, which
  was not guessed at. Decided 2026-09-20 to report 3 rather than pad with duplicates.

### D. Audit backlog (documented in round 5, deliberately not fixed)

Two items found while building round 5. Each is written up so a future audit round can
find every affected recipe in one pass. Neither has been fixed and no existing recipe was
changed.

- **D1. Pork-bone dishes omit the bones' contribution to the broth.** Thai FCD has no
  bone or bone-broth record and the dictionary has no key for pork bones, so recipes whose
  only pork is bones/bone-broth carry NO pork macros. The bones are named in each recipe's
  `notes`, but kcal, protein and fat are understated (the bones' fat and gelatine dissolve
  into the soup; how much is not measurable from the sources). Affected: th_373
  (ต้มจับฉ่ายกระดูกหมู, 450 g bones omitted), th_378 (มะระต้มกระดูกหมู, 1 bone omitted),
  th_310 (แกงจืดปวยเล้งหมูสับ, 3 bones omitted, minced pork is priced) and th_295
  (ต้มจืดกะหล่ำม้วนหมูเด้ง, 3 cups pork-bone broth omitted, minced pork is priced). Related
  but different: th_196, th_166 and th_299 price pork RIBS as lean pork `STD:958` (th_299
  is listed under B; th_196 and th_166 are not yet), so they overstate lean meat rather
  than omit it. Vegan/vegetarian tags are not at risk in
  th_373 and th_378 because each also has a keyed animal ingredient (oyster sauce, fish
  sauce); this was checked deliberately after the round-4 standing rule on false tags.
  Resolve by finding a defensible record for bone broth (Thai FCD or a disclosed external
  one), or by adding a dictionary key and a per-recipe estimate. Other bone-in recipes not
  listed here have not been audited.
- **D2. พริกหยวก is a dictionary synonym of bell_pepper, but th_342 leaves it out.**
  `data/ingredients.json` lists พริกหยวก among bell_pepper's synonyms, and th_176
  (หมูผัดพริกหยวก) and th_270 (พริกหยวกยัดไส้ทอด) treat it as bell_pepper. th_342
  (หอยแมลงภู่ผัดพริกสด, round 3) lists พริกหยวก 2-3 pieces in its source but omitted it as
  "not พริกหวาน", so it is neither keyed nor priced (a small amount; the effect on its
  nutrition is minor). The two positions contradict each other. The underlying question
  is whether พริกหยวก (a mild, thin, pale-green Thai pepper) and พริกหวาน (sweet bell
  pepper) should be one dictionary key at all; they are different vegetables in cooking,
  and merging them also affects text matching in `nlp/`. Resolve by either splitting the
  dictionary entry or adding พริกหยวก to th_342 as bell_pepper, then re-running the round-3
  checks. Not touched now; `nlp/` and the dictionary were not changed.
