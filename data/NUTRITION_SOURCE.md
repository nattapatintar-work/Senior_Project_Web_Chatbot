# Nutrition Data Source

Every number in `data/recipes.json` comes from here. Nothing is estimated.

`Claude.md:430` is the reason this file exists: if nutrition values are guessed,
experiment 5.5② — asking the LLM 30 nutrition questions and comparing against a
reference table — has nothing real to compare against, and the finding
evaporates. A sourced number can be checked by a reader; an invented one cannot,
no matter how reasonable it looks.

---

## The source

**Online Thai Food Composition Database**, Institute of Nutrition, Mahidol
University (INMU) — the Regional Food Data Centre of INFOODS.

<https://inmu.mahidol.ac.th/thaifcd/>

**Citation** (as printed on every record retrieved):

> Kunchit Judprasong, Prapasri Puwastien, Nipa Rojroongwasinkul, Anadi
> Nitithamyong, Piyanut Sridonpai, Amnat Somjai. Institute of Nutrition,
> Mahidol University (2015). Thai Food Composition Database, Online version 2,
> September 2018, Thailand. Web site: http://www.inmu.mahidol.ac.th/thaifcd

**Terms:** non-commercial use is free, *provided INMU is acknowledged*. That
acknowledgement belongs in the report as well as here.

**Retrieved:** 2026-08-05.

> ⚠️ **Version discrepancy, worth a footnote in the report.** The website
> advertises "Online version 3, August 2025", but the citation block printed
> inside every retrieved record still reads "Online version 2, September 2018".
> This project cites what the retrieved document says, since that is what the
> numbers actually came from.

---

## Why this source and not an estimate

It is the national reference table. It was built from laboratory analyses run at
INMU between 1997 and 2025, it is the database behind INMUCAL-Nutrients, and it
was used for Thailand's National Food Consumption Surveys. INMUCAL itself is
desktop software requiring a licence; the online database exposes the same
underlying food composition data and is free to query, which is why it is the
one used here.

---

## How values were retrieved

The database publishes each food as a generated PDF — there is no JSON API and
no bulk download. `tools/thaifcd.py` fetches and parses those PDFs;
`tools/build_cache.py` runs every lookup once into `data/thaifcd_cache.json`,
which is committed. So each value is reproducible by re-running the script and
reviewable in a git diff.

Four macros are read, by their INFOODS tags:

| Field | Tag | Fallback |
|---|---|---|
| `kcal` | `ENERC` | `ENERCT` |
| `protein` | `PROTCNT` | — |
| `fat` | `FAT` | — |
| `carb` | `CHOAVLDF` | `CHOCDF` |

The fallbacks are not improvisation. Raw ingredients carry `ENERC` and
`CHOAVLDF`; composed dishes usually leave those blank and carry `ENERCT` and
`CHOCDF` instead, and the database says so in its own `ENERCT` row: *"If
CHOAVLDF was not available, CHOCDF was used."* The cache records which tag
supplied each number, so the substitution is never invisible.

**A nutrient the database did not determine is stored as `null`, never as 0.**
A zero would be a fabricated measurement, and it would look exactly like a real
one.

---

## Two derivation methods

All values are **per 100 g**, so every recipe records a `serving_g` and scales
from it.

### Method A — direct (preferred)

The dish exists in the database as a whole cooked dish, mostly in group **T,
"Mixed foods: ready-to-eat"**. One lookup, and the recipe cites its food code:

```
nutrition_source: "Thai FCD (INMU), food code T54"
```

### Method B — computed from ingredients

Used where the database has no entry for the dish. Per-ingredient values are
still fully sourced; what is *not* sourced is the gram amount of each
ingredient, which is a recipe-formulation choice made here. Those amounts are
recorded per recipe so a reader can disagree with them specifically:

```
nutrition_source: "Thai FCD (INMU), computed from food codes H12, D08, ... — see nutrition_basis"
```

> **The honest limitation:** Method B's *nutrient values* are reference data,
> but its *proportions* are this project's assumption, and cooking losses and
> oil absorption are not modelled. Method A carries no such assumption. Recipes
> using Method B should be identified as such in the report rather than
> presented as equivalent.

---

## The one non-Thai-FCD source: USDA, for broccoli

`broccoli` has no Thai FCD entry, so `th_040` (ไก่ผัดบรอกโคลี) draws on:

> "Broccoli, raw." FoodData Central, 30 Oct. 2020, U.S.D.A., Agricultural
> Research Service, fdc.nal.usda.gov. (SR Legacy 11090 / FDC 170379)
>
> Per 100 g: 34 kcal · 2.82 g protein · 0.37 g fat · 6.64 g carbohydrate by
> difference · 2.6 g dietary fibre

Kept in `data/external_nutrition.json`, deliberately **not** in the Thai FCD
cache — mixing a second source into a file labelled "what INMU published" would
make its provenance a lie.

> ⚠️ **The two databases do not define carbohydrate the same way.** USDA's
> "Carbohydrate, by difference" **includes** dietary fibre; Thai FCD's
> `CHOAVLDF` **excludes** it. Adding them together unmodified would overstate
> broccoli's carbohydrate by 2.6 g per 100 g — enough, in this recipe, to push
> the dish past the 10 g keto threshold and flip its health tag.
>
> Broccoli therefore enters on the Thai FCD basis: **6.64 − 2.6 = 4.04 g
> available carbohydrate.** Both raw figures are kept alongside it so the
> subtraction is checkable rather than merely asserted.

This is the kind of mismatch that produces a wrong number with no error
attached. Any future addition from a second database needs the same check
before its values are summed with INMU's.

---

## Known coverage gaps

Found while building the database, and worth stating plainly rather than
working around silently:

1. **Two of the 20 YOLO classes have no entry at all** — `broccoli` (บรอกโคลี)
   and `onion` (หอมใหญ่ / หัวหอม). Searches return nothing. Broccoli is
   resolved via USDA, above. Onion needed no external source: it appears only
   in Method A recipes, where the whole dish was analysed.

2. **Simple home stir-fries are largely absent.** The database is rich in
   curries, rice dishes, and noodle dishes, but has no entry for ผัดกะหล่ำปลี,
   ผัดคะน้า, ไก่ผัดขิง, ต้มจืด, or ผัดผักรวมมิตร. This is what forced Method B
   to exist, and it is why the detectable classes — mostly salad vegetables —
   line up poorly with what the national table actually covers.

3. **Cooked-dish entries are not always where you would expect.** ไข่เจียว is
   not in group T; it is filed under eggs as "ไข่ไก่, เจียว (เติมน้ำปลา)".
   A dish missing from group T is not necessarily missing from the database,
   so it is worth searching by ingredient name before concluding it is absent.
