# -*- coding: utf-8 -*-
"""
One-time script: builds the 10 dessert/coverage recipes (7 desserts + 3 savory
gap-fillers: chayote, spaghetti, hyacinth_bean) and appends them to
data/recipes.json. Nutrition macros are left at 0 -- tools/compute_nutrition.py
--fill computes and writes them from nutrition_ref / nutrition_basis, so no
macro is ever typed by hand. Every recipe_source_url was verified via a real
search/fetch this session.
"""
import json

recipes = json.load(open('data/recipes.json', encoding='utf-8'))
ZERO = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carb": 0.0}


def computed(name_th, main, opt, seas, tags, excl, cook, basis, refs, source_note, url, notes):
    serving_g = sum(basis.values())
    return {
        "name_th": name_th, "main_ingredients": main, "optional_ingredients": opt,
        "seasonings": seas, "health_tags": tags, "excluded_for": excl,
        "serving_g": serving_g, "cook_time_min": cook, "nutrition": dict(ZERO),
        "nutrition_method": "computed", "nutrition_basis": basis, "basis_refs": refs,
        "nutrition_source": source_note, "recipe_source_url": url, "notes": notes,
    }


def direct(name_th, main, opt, seas, tags, excl, serving_g, cook, ref, source_note, url, notes):
    return {
        "name_th": name_th, "main_ingredients": main, "optional_ingredients": opt,
        "seasonings": seas, "health_tags": tags, "excluded_for": excl,
        "serving_g": serving_g, "cook_time_min": cook, "nutrition": dict(ZERO),
        "nutrition_method": "direct", "nutrition_ref": ref,
        "nutrition_source": source_note, "recipe_source_url": url, "notes": notes,
    }


NEW = []

# 1. Rambutan in syrup -- covers rambutan
NEW.append(computed(
    "เงาะลอยแก้ว", ["rambutan"], [], ["sugar"], [], [], 15,
    {"rambutan": 150, "sugar": 30},
    {"rambutan": "STD:707", "sugar": "STD:1391"},
    "Thai FCD (INMU), computed from rambutan (STD:707), sugar (STD:1391)",
    "https://www.youtube.com/watch?v=yMs6uPBm0ik",
    "Coverage dish for rambutan (previously unused despite having real Thai FCD data). "
    "Salt (traditional, a pinch) omitted from nutrition_basis: no Thai FCD salt record, "
    "and table salt is genuinely ~0 kcal/protein/fat/carb."
))

# 2. Sweet tamarind snack -- covers tamarind
NEW.append(computed(
    "มะขามคลุก", ["tamarind", "chili"], [], ["sugar"], [], [], 10,
    {"tamarind": 100, "chili": 5, "sugar": 15},
    {"tamarind": "STD:750", "chili": "STD:545", "sugar": "STD:1391"},
    "Thai FCD (INMU), computed from sweet tamarind (STD:750), bird's eye chili (STD:545), sugar (STD:1391)",
    "https://foodof.com/Spicy%20and%20Sweet%20Tamarind%20-%20Cookery%20of%20Thailand",
    "Coverage dish for tamarind (previously unused -- the dictionary's tamarind_paste entry "
    "is a different product, the concentrated cooking paste, not the fresh sweet fruit). "
    "Salt (traditional) omitted from nutrition_basis: no Thai FCD record, genuinely ~0 macros."
))

# 3. Banana in syrup, no coconut milk -- reuses banana, adds variety
NEW.append(computed(
    "กล้วยเชื่อม", ["banana"], [], ["sugar"], [], [], 45,
    {"banana": 150, "sugar": 40},
    {"banana": "STD:696", "sugar": "STD:1391"},
    "Thai FCD (INMU), computed from ripe banana (STD:696), sugar (STD:1391)",
    "https://www.thaitable.com/thai/recipe/bananas-in-syrup",
    "Distinct from th_049 (กล้วยบวชชี) -- plain sugar syrup, no coconut milk, giving the "
    "database a banana dessert without coconut milk's fat/clean-tag implications."
))

# 4. Peanut brittle -- reuses peanuts, adds variety
NEW.append(computed(
    "ถั่วตัด", ["peanuts"], [], ["sugar"], [], [], 20,
    {"peanuts": 100, "sugar": 80},
    {"peanuts": "STD:345", "sugar": "STD:1391"},
    "Thai FCD (INMU), computed from roasted peanuts (STD:345), sugar (STD:1391)",
    "https://whattocooktoday.com/easy-sesame-peanut-brittle.html",
    "Coverage-variety dish. Sesame seeds, part of some versions, are not in the dictionary "
    "and are omitted -- this is the plain peanuts-and-sugar variant, which is also a "
    "recognized traditional form (Fah Sung Thong)."
))

# 5. Coconut-flavored roasted cashew -- reuses cashew, adds variety
NEW.append(computed(
    "เม็ดมะม่วงหิมพานต์อบกะทิ", ["cashew"], [], ["coconut_milk", "sugar"], [], [], 25,
    {"cashew": 100, "coconut_milk": 30, "sugar": 20},
    {"cashew": "STD:363", "coconut_milk": "STD:1348", "sugar": "STD:1391"},
    "Thai FCD (INMU), computed from raw cashew nut (STD:363), coconut milk (STD:1348), sugar (STD:1391)",
    "https://www.pholfoodmafia.com/recipe/coconut-flavoured-cashew-nut-%E0%B9%80%E0%B8%A1%E0%B9%87%E0%B8%94%E0%B8%A1%E0%B8%B0%E0%B8%A1%E0%B9%88%E0%B8%A7%E0%B8%87%E0%B8%AB%E0%B8%B4%E0%B8%A1%E0%B8%9E%E0%B8%B2%E0%B8%99%E0%B8%95%E0%B9%8C/",
    "Coverage-variety dish. Egg white, part of the source recipe's coating, is not priced "
    "separately here -- simplified to the three ingredients that carry the flavor and "
    "macros the dictionary already tracks."
))

# 6. Pumpkin egg custard -- reuses pumpkin, egg; DIRECT Thai FCD dish
NEW.append(direct(
    "สังขยาฟักทอง", ["pumpkin", "egg"], [], ["coconut_milk", "sugar"], [], ["vegan"], 150, 45,
    "STD:1654",
    "Thai FCD (INMU), food code T279 (สังขยาฟักทอง)",
    "https://rachelcooksthai.com/pumpkin-custard/",
    "Whole-dish direct lookup -- egg custard steamed inside a hollowed kabocha pumpkin. "
    "Excluded for vegan and vegetarian only via egg/coconut milk's dairy-adjacent status is "
    "not applicable here (coconut milk is plant-based); excluded_for vegan is driven by egg."
))

# 7. Golden egg-yolk drops -- reuses egg; DIRECT Thai FCD dish
NEW.append(direct(
    "ทองหยอด", ["egg"], [], ["sugar"], [], ["vegetarian", "vegan"], 50, 20,
    "STD:1634",
    "Thai FCD (INMU), food code T141 (ทองหยอด)",
    "https://en.wikipedia.org/wiki/Thong_yot",
    "Whole-dish direct lookup. One of the nine auspicious Thai desserts (introduced to the "
    "Ayutthaya court by Maria Guyomar de Pinha); egg yolk dropped into hot sugar syrup. "
    "Excluded for vegetarian and vegan: it is egg, essentially."
))

# 8. Chayote-shrimp stir-fry -- covers chayote (via USDA, Thai FCD has no usable record)
NEW.append(computed(
    "กุ้งผัดฟักแม้ว", ["chayote", "shrimp"], ["garlic"], ["oyster_sauce", "soy_sauce", "vegetable_oil"], [], ["vegetarian", "vegan"], 12,
    {"chayote": 130, "shrimp": 80, "garlic": 6, "vegetable_oil": 10, "oyster_sauce": 8, "soy_sauce": 5},
    {"chayote": "EXT:usda-chayote-raw", "shrimp": "STD:1042", "garlic": "STD:226",
     "vegetable_oil": "STD:1368", "oyster_sauce": "STD:270", "soy_sauce": "STD:273"},
    "Thai FCD (INMU) except chayote: USDA FoodData Central, \"Chayote, fruit, raw,\" 1 Apr. 2019 (FDC 170402) -- see data/external_nutrition.json",
    "https://rackoflam.com/shrimp-and-chayote-stir-fry/",
    "Coverage dish for chayote. Thai FCD's only chayote record (STD:586, young leaves/shoots) "
    "has all four macros null -- not analysed -- confirmed by direct lookup and a broader "
    "re-search this session, so the fruit itself is sourced externally. USDA's carbohydrate-"
    "by-difference (4.51g/100g) includes fiber (1.70g); stored here on Thai FCD's available-"
    "carbohydrate basis (2.81g) so it can be summed with the Thai FCD-sourced ingredients in "
    "this same recipe without overstating carbs -- same correction as th_040's broccoli."
))

# 9. Drunken spaghetti -- covers spaghetti (Thai FCD has zero pasta entries)
NEW.append(computed(
    "สปาเกตตีผัดขี้เมา", ["spaghetti", "pork", "holy_basil", "chili"], [],
    ["oyster_sauce", "fish_sauce", "vegetable_oil"], [], ["vegetarian", "vegan"], 20,
    {"spaghetti": 150, "pork": 80, "chili": 5, "vegetable_oil": 10, "oyster_sauce": 10, "fish_sauce": 8},
    {"spaghetti": "EXT:usda-pasta-cooked", "pork": "STD:970", "chili": "STD:545",
     "vegetable_oil": "STD:1368", "oyster_sauce": "STD:270", "fish_sauce": "STD:291"},
    "Thai FCD (INMU) except spaghetti: USDA FoodData Central, \"Pasta, cooked, unenriched, without added salt,\" 1 Apr. 2019 (FDC 168928) -- see data/external_nutrition.json",
    "https://hungryinthailand.com/spaghetti-kee-mao-recipe/",
    "Coverage dish for spaghetti. Thai FCD has zero pasta/spaghetti entries under any spelling "
    "searched, confirmed this session and in the original 84-recipe rebuild. USDA's carb-by-"
    "difference (30.86g/100g) includes fiber (1.80g); stored on the available-carbohydrate "
    "basis (29.06g), same correction as chayote/broccoli above. holy_basil is a main "
    "ingredient (essential to the dish's identity) but has no standalone Thai FCD record -- "
    "excluded from nutrition_basis rather than approximated, same disclosed gap as th_056/057."
))

# 10. Hyacinth bean stir-fry -- covers hyacinth_bean (Thai FCD AND IFCT both lack a fresh-pod record)
NEW.append(computed(
    "ผัดถั่วแปบ", ["hyacinth_bean", "garlic"], [], ["oyster_sauce", "soy_sauce", "vegetable_oil"], [], ["vegetarian", "vegan"], 10,
    {"hyacinth_bean": 130, "garlic": 6, "vegetable_oil": 8, "oyster_sauce": 8, "soy_sauce": 5},
    {"hyacinth_bean": "EXT:usda-hyacinth-bean-immature-raw", "garlic": "STD:226",
     "vegetable_oil": "STD:1368", "oyster_sauce": "STD:270", "soy_sauce": "STD:273"},
    "Thai FCD (INMU) except hyacinth_bean: USDA FoodData Central, \"Hyacinth-beans, immature seeds, raw,\" 1 Apr. 2019 (FDC 169234) -- see data/external_nutrition.json",
    "https://food52.com/recipes/34054-hyacinth-beans-stir-fry",
    "Coverage dish for hyacinth_bean, the last of the 5 originally-flagged gaps. Thai FCD has "
    "zero entries. The official Indian Food Composition Tables (IFCT 2017, ICMR-NIN) were "
    "checked directly via the ifct2017/ifct2017 GitHub mirror and have only dried mature-seed "
    "'Field bean' varieties (B007/B008/B009), the same wrong food form as USDA's own "
    "mature-seed record (FDC 175210, not used). This USDA 'immature seeds, raw' record is "
    "the fresh-pod match the dictionary entry (category: vegetable) actually represents; its "
    "46 kcal/100g independently cross-checks against unrelated secondary sources quoting the "
    "same figure. Seasoned the same way as the other bean stir-fries in this database "
    "(winged_bean, green_bean, yardlong_bean) for consistency."
))

start_id = len(recipes) + 1
for i, r in enumerate(NEW, start=start_id):
    r['id'] = f"th_{i:03d}"

all_recipes = recipes + NEW
json.dump(all_recipes, open('data/recipes.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"total recipes now: {len(all_recipes)}")
for r in NEW:
    print(r['id'], r['name_th'])
