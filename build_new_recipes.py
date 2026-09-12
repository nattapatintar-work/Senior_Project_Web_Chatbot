# -*- coding: utf-8 -*-
"""
One-time script: builds the new coverage-driven recipes and merges them with
the 38 carried-forward recipes into the final data/recipes.json. Nutrition
macros are left at 0 here -- tools/compute_nutrition.py --fill computes and
writes them from nutrition_ref / nutrition_basis afterward, so no macro is
ever typed by hand. Sources for both nutrition (Thai FCD food codes) and
recipe/ingredient lists (recipe_source_url) were verified this session.
"""
import json

ZERO = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carb": 0.0}
FCD = "Thai FCD (INMU), computed from "


def computed(name_th, main, opt, seas, tags, excl, serving_g, cook, basis, refs,
             source_note, url, notes):
    return {
        "name_th": name_th, "main_ingredients": main, "optional_ingredients": opt,
        "seasonings": seas, "health_tags": tags, "excluded_for": excl,
        "serving_g": serving_g, "cook_time_min": cook, "nutrition": dict(ZERO),
        "nutrition_method": "computed", "nutrition_basis": basis, "basis_refs": refs,
        "nutrition_source": source_note, "recipe_source_url": url, "notes": notes,
    }


def direct(name_th, main, opt, seas, tags, excl, serving_g, cook, ref,
           source_note, url, notes):
    return {
        "name_th": name_th, "main_ingredients": main, "optional_ingredients": opt,
        "seasonings": seas, "health_tags": tags, "excluded_for": excl,
        "serving_g": serving_g, "cook_time_min": cook, "nutrition": dict(ZERO),
        "nutrition_method": "direct", "nutrition_ref": ref,
        "nutrition_source": source_note, "recipe_source_url": url, "notes": notes,
    }


NEW = []

NEW.append(computed(
    "ผัดผักบุ้งไฟแดง", ["water_spinach", "garlic", "chili"], [],
    ["oyster_sauce", "soy_sauce", "vegetable_oil"], ["clean", "keto"], ["vegetarian", "vegan"],
    150, 10,
    {"water_spinach": 150, "garlic": 6, "vegetable_oil": 10, "soy_sauce": 8, "oyster_sauce": 8},
    {"water_spinach": "STD:507", "garlic": "STD:226", "vegetable_oil": "STD:1368",
     "soy_sauce": "STD:273", "oyster_sauce": "STD:270"},
    FCD + "water spinach (STD:507), N2, K34, N136, N60",
    "https://learnthaiwithmod.com/2012/08/stir-fried-chinese-water-morning-glory-pad-pak-bung-fai-daeng-%E0%B8%9C%E0%B8%B1%E0%B8%94%E0%B8%9C%E0%B8%B1%E0%B8%81%E0%B8%9A%E0%B8%B8%E0%B9%89%E0%B8%87%E0%B9%84%E0%B8%9F%E0%B9%81%E0%B8%94%E0%B8%87/",
    "Coverage dish for water_spinach. The dish's name comes from the flare of fire under a hot wok, not from spiciness."
))

NEW.append(computed(
    "กุยช่ายผัดไข่", ["chives", "egg"], [],
    ["soy_sauce", "vegetable_oil", "oyster_sauce"], [], ["vegetarian", "vegan"],
    150, 10,
    {"chives": 100, "egg": 55, "vegetable_oil": 10, "soy_sauce": 6, "oyster_sauce": 6},
    {"chives": "STD:413", "egg": "STD:1274", "vegetable_oil": "STD:1368",
     "soy_sauce": "STD:273", "oyster_sauce": "STD:270"},
    FCD + "chives (STD:413), H19, K34, N136, N60",
    "https://redhousespice.com/chinese-chive-egg/",
    "Coverage dish for chives."
))

NEW.append(computed(
    "มะระผัดไข่", ["bitter_gourd", "egg"], [],
    ["fish_sauce", "vegetable_oil", "soy_sauce"], ["clean"], ["vegetarian", "vegan"],
    150, 12,
    {"bitter_gourd": 120, "egg": 55, "vegetable_oil": 10, "fish_sauce": 6, "soy_sauce": 5},
    {"bitter_gourd": "STD:585", "egg": "STD:1274", "vegetable_oil": "STD:1368",
     "fish_sauce": "STD:291", "soy_sauce": "STD:273"},
    FCD + "bitter gourd (STD:585), H19, K34, N71, N136",
    "https://www.pholfoodmafia.com/recipe/stir-fried-bitter-gourd-with-egg-%E0%B8%A1%E0%B8%B0%E0%B8%A3%E0%B8%B0%E0%B8%9C%E0%B8%B1%E0%B8%94%E0%B9%84%E0%B8%82%E0%B9%88/",
    "Coverage dish for bitter_gourd."
))

NEW.append(computed(
    "ผัดถั่วงอกหัวโตเต้าหู้", ["soybean_sprouts", "tofu"], ["green_onion"],
    ["soy_sauce", "vegetable_oil"], ["clean", "keto", "vegetarian", "vegan"], [],
    150, 8,
    {"soybean_sprouts": 120, "tofu": 60, "vegetable_oil": 8, "soy_sauce": 6},
    {"soybean_sprouts": "STD:447", "tofu": "STD:373", "vegetable_oil": "STD:1368", "soy_sauce": "STD:273"},
    FCD + "soybean sprout (STD:447), tofu (STD:373), K34, N136",
    "https://www.pholfoodmafia.com/recipe/stir-fried-yellow-garlic-chives-with-egg-tofu-%E0%B8%81%E0%B8%B8%E0%B8%A2%E0%B8%8A%E0%B9%88%E0%B8%B2%E0%B8%A2%E0%B8%82%E0%B8%B2%E0%B8%A7%E0%B8%9C%E0%B8%B1%E0%B8%94%E0%B9%80%E0%B8%95%E0%B9%89%E0%B8%B2%E0%B9%84%E0%B8%82%E0%B9%88/",
    "Coverage dish for soybean_sprouts (ถั่วงอกหัวโต -- a distinct, larger sprout from the plain bean sprout, which has no entry in this dictionary). Fully vegan: soy sauce only, no fish/oyster sauce."
))

NEW.append(computed(
    "แกงเลียงกุ้ง", ["pumpkin", "shrimp", "maenglak"], ["chili"],
    ["fish_sauce", "shrimp_paste"], ["clean"], ["vegetarian", "vegan"],
    200, 20,
    {"pumpkin": 100, "shrimp": 60, "maenglak": 15, "fish_sauce": 10, "shrimp_paste": 5},
    {"pumpkin": "STD:561", "shrimp": "STD:895", "maenglak": "STD:248",
     "fish_sauce": "STD:291", "shrimp_paste": "STD:254"},
    FCD + "pumpkin (D108), shrimp (F25-equivalent), lemon basil (STD:248), N71, shrimp paste (STD:254)",
    "https://hot-thai-kitchen.com/kaeng-liang/",
    "Coverage dish for maenglak and shrimp_paste. No coconut milk, so it stays light -- kaeng liang predates the introduction of coconut milk to central Thai curries."
))

NEW.append(computed(
    "ไก่ผัดเม็ดมะม่วงหิมพานต์", ["chicken", "cashew", "onion"], ["bell_pepper"],
    ["oyster_sauce", "soy_sauce", "vegetable_oil", "sugar"], [], ["vegetarian", "vegan"],
    180, 15,
    {"chicken": 120, "cashew": 25, "onion": 40, "vegetable_oil": 10, "oyster_sauce": 10, "soy_sauce": 5, "sugar": 4},
    {"chicken": "STD:895", "cashew": "STD:363", "onion": "STD:622", "vegetable_oil": "STD:1368",
     "oyster_sauce": "STD:270", "soy_sauce": "STD:273", "sugar": "STD:1391"},
    FCD + "chicken (F25), cashew (STD:363), onion (STD:1287), K34, N60, N136, sugar",
    "https://hot-thai-kitchen.com/cashew-chicken/",
    "Coverage dish for cashew. A Thai-Chinese restaurant staple -- the Thai version is drier and more sauce-intense than the Chinese-American original."
))

NEW.append(computed(
    "ข้าวผัดสับปะรดกุ้ง", ["rice", "pineapple", "shrimp"], ["cashew", "bell_pepper"],
    ["yellow_curry_paste", "fish_sauce", "sugar", "vegetable_oil"], [], ["vegetarian", "vegan"],
    300, 15,
    {"rice": 200, "pineapple": 60, "shrimp": 60, "vegetable_oil": 10, "fish_sauce": 8,
     "sugar": 4, "yellow_curry_paste": 5},
    {"rice": "STD:1272", "pineapple": "STD:814", "shrimp": "STD:895", "vegetable_oil": "STD:1368",
     "fish_sauce": "STD:291", "sugar": "STD:1391", "yellow_curry_paste": "STD:294"},
    FCD + "cooked rice, pineapple (STD:814), shrimp (F25), K34, N71, sugar, curry powder (STD:264)",
    "https://www.recipetineats.com/pineapple-fried-rice-thai/",
    "Coverage dish for pineapple. Curry powder is what gives Thai pineapple fried rice its characteristic yellow tint and mild warmth; cashew is optional garnish here since th_006 already covers it as a main."
))

NEW.append(computed(
    "ยำส้มโอ", ["pomelo", "shrimp"], ["coconut", "peanuts", "lime", "chili"],
    ["chili_paste", "fish_sauce", "sugar"], [], ["vegetarian", "vegan"],
    150, 15,
    {"pomelo": 100, "shrimp": 40, "chili_paste": 10, "fish_sauce": 8, "sugar": 6},
    {"pomelo": "STD:812", "shrimp": "STD:895", "chili_paste": "STD:302",
     "fish_sauce": "STD:291", "sugar": "STD:1391"},
    FCD + "pomelo (STD:812), shrimp (F25), roasted chili paste (STD:1440), N71, sugar",
    "https://hot-thai-kitchen.com/yum-som-o/",
    "Coverage dish for pomelo. Toasted coconut and peanuts are traditional garnishes, listed optional since a user's photo/text rarely surfaces them."
))

NEW.append(computed(
    "ข้าวผัดอเมริกัน", ["rice", "sausage"], ["egg", "onion"],
    ["butter", "sugar", "salt"], [], ["vegetarian", "vegan"],
    300, 15,
    {"rice": 200, "sausage": 60, "butter": 10, "sugar": 5},
    {"rice": "STD:1272", "sausage": "STD:1011", "butter": "STD:1384", "sugar": "STD:1391"},
    FCD + "cooked rice, fried pork sausage (STD:1011), butter (STD:1384), sugar",
    "https://hot-thai-kitchen.com/american-fried-rice/",
    "Coverage dish for butter and sausage. Ketchup and raisins, part of the traditional dish, are not in the ingredient dictionary and are omitted rather than approximated. Salt is in the seasonings list but not the nutrition_basis: Thai FCD has no standalone salt record, and table salt is genuinely ~0 kcal/protein/fat/carb, so omitting it does not understate the macros this project tracks."
))

NEW.append(computed(
    "แกงขนุนอ่อนใส่หมู", ["jackfruit", "pork"], ["chili"],
    ["shrimp_paste", "fish_sauce"], [], ["vegetarian", "vegan"],
    200, 40,
    {"jackfruit": 120, "pork": 80, "shrimp_paste": 6, "fish_sauce": 8},
    {"jackfruit": "STD:416", "pork": "STD:970", "shrimp_paste": "STD:254", "fish_sauce": "STD:291"},
    FCD + "young jackfruit (STD:416), raw minced pork (STD:970), shrimp paste, fish sauce",
    "https://hot-thai-kitchen.com/northern-jackfruit-curry/",
    "Coverage dish for jackfruit (young/unripe, ขนุนอ่อน -- a savoury vegetable use, distinct from the ripe fruit eaten as dessert). A water-based Northern Thai curry, no coconut milk."
))

NEW.append(direct(
    "กล้วยบวชชี", ["banana"], [], ["coconut_milk", "sugar", "salt"],
    ["vegetarian", "vegan"], [], 200, 20, "STD:1599",
    "Thai FCD (INMU), food code STD:1599 (กล้วยบวชชี)",
    "https://hungryinthailand.com/bananas-in-coconut-milk/",
    "Coverage dish for banana. A classic simple dessert -- bananas simmered in lightly sweetened, salted coconut milk."
))

NEW.append(computed(
    "ข้าวเหนียวมะม่วง", ["rice", "mango"], [], ["coconut_milk", "sugar", "salt"],
    ["vegetarian", "vegan"], [], 250, 30,
    {"rice": 150, "mango": 150, "coconut_milk": 60, "sugar": 20},
    {"rice": "STD:149", "mango": "STD:765", "coconut_milk": "STD:1348", "sugar": "STD:1391"},
    FCD + "steamed glutinous rice (STD:149), Nam Dok Mai mango (STD:765), coconut milk, sugar",
    "https://hot-thai-kitchen.com/mango-sticky-rice/",
    "Coverage dish for mango. \"rice\" here is glutinous/sticky rice (ข้าวเหนียว), nutritionally different from the dictionary's canonical steamed jasmine rice (ข้าวสวย) that the key otherwise represents -- flagged since compute_nutrition sources it from a dedicated sticky-rice record (STD:149), not the jasmine-rice one used elsewhere. Salt is seasoned to taste and omitted from nutrition_basis: no Thai FCD record exists, and salt is genuinely ~0 kcal/protein/fat/carb."
))

NEW.append(computed(
    "ข้าวเหนียวทุเรียน", ["rice", "durian"], [], ["coconut_milk", "sugar", "salt"],
    ["vegetarian", "vegan"], [], 250, 30,
    {"rice": 150, "durian": 100, "coconut_milk": 60, "sugar": 15},
    {"rice": "STD:149", "durian": "STD:736", "coconut_milk": "STD:1348",
     "sugar": "STD:1391"},
    FCD + "steamed glutinous rice (STD:149), Monthong durian (STD:736), coconut milk, sugar",
    "https://hot-thai-kitchen.com/durian-sticky-rice/",
    "Coverage dish for durian. Same 'rice' key here means glutinous sticky rice as in the mango version above. Salt omitted from nutrition_basis (no Thai FCD record; genuinely ~0 macros)."
))

NEW.append(computed(
    "มันสำปะหลังเชื่อม", ["cassava"], [], ["coconut_milk", "sugar"],
    ["vegetarian", "vegan"], [], 180, 90,
    {"cassava": 150, "coconut_milk": 30, "sugar": 30},
    {"cassava": "STD:1929", "coconut_milk": "STD:1348", "sugar": "STD:1391"},
    FCD + "raw cassava (STD:1929), coconut milk, sugar",
    "https://whattocooktoday.com/candied-cassava-coconut-milk.html",
    "Coverage dish for cassava. Long, slow simmer in syrup until translucent; coconut milk sauce poured over at serving, not cooked in."
))

NEW.append(computed(
    "แกงบวดเผือก", ["taro_root", "pumpkin"], [], ["coconut_milk", "sugar", "salt"],
    ["vegetarian", "vegan"], [], 220, 20,
    {"taro_root": 120, "pumpkin": 80, "coconut_milk": 60, "sugar": 20},
    {"taro_root": "STD:1922", "pumpkin": "STD:561", "coconut_milk": "STD:1348",
     "sugar": "STD:1391"},
    FCD + "steamed taro (STD:1922), pumpkin (D108), coconut milk, sugar",
    "https://www.templeofthai.com/recipes/coconut_pudding.php",
    "Coverage dish for taro_root. Thai FCD has no raw-taro record, only steamed (STD:1922) -- accepted as-is per the same convention used for sweet_potato's B9 record in the carried-forward dessert. Salt omitted from nutrition_basis (no Thai FCD record; genuinely ~0 macros)."
))

NEW.append(computed(
    "กล้วยลิ้นจี่กะทิ", ["banana", "lychee"], [], ["coconut_milk", "sugar", "salt"],
    ["vegetarian", "vegan"], [], 200, 10,
    {"banana": 100, "lychee": 80, "coconut_milk": 60, "sugar": 15},
    {"banana": "STD:696", "lychee": "STD:785", "coconut_milk": "STD:1348",
     "sugar": "STD:1391"},
    FCD + "ripe banana (STD:696), lychee (STD:785), coconut milk, sugar",
    "https://daboxcsa.org/blogs/recipes/thai-banana-lychee-dessert-in-coconut-milk",
    "Coverage dish for lychee. A simple mixed-fruit-in-coconut-milk dessert in the same family as กล้วยบวชชี. Salt omitted from nutrition_basis (no Thai FCD record; genuinely ~0 macros)."
))

NEW.append(computed(
    "ยำวุ้นเส้นทะเล", ["glass_noodle", "minced_meat", "shrimp"], ["onion", "tomato", "celery"],
    ["fish_sauce", "sugar"], ["keto"], ["vegetarian", "vegan"], 200, 15,
    {"glass_noodle": 40, "minced_meat": 60, "shrimp": 50, "onion": 30, "tomato": 40,
     "celery": 15, "fish_sauce": 10, "sugar": 5},
    {"glass_noodle": "STD:396", "minced_meat": "STD:970", "shrimp": "STD:895", "onion": "STD:622",
     "tomato": "STD:571", "celery": "STD:495", "fish_sauce": "STD:291", "sugar": "STD:1391"},
    FCD + "dried mung bean noodle (STD:396), minced pork (STD:970), shrimp, onion, tomato, celery (STD:495), N71, sugar",
    "https://hot-thai-kitchen.com/glass-noodle-salad-v2/",
    "Coverage dish for glass_noodle, minced_meat, and celery all at once. NOT tagged keto despite the arithmetic possibly allowing it -- glass_noodle is one of HEALTH_TAGS.md's explicit starch staples."
))

NEW.append(computed(
    "หอยลายผัดพริกเผา", ["clam", "holy_basil"], ["chili"],
    ["chili_paste", "fish_sauce", "vegetable_oil"], [], ["vegetarian", "vegan"], 150, 10,
    {"clam": 150, "vegetable_oil": 10, "chili_paste": 15, "fish_sauce": 6},
    {"clam": "STD:1176", "vegetable_oil": "STD:1368",
     "chili_paste": "STD:302", "fish_sauce": "STD:291"},
    FCD + "clam (STD:1176), K34, roasted chili paste (STD:302), N71",
    "https://www.pholfoodmafia.com/recipe/stir-fried-clams-with-chilli-paste-%E0%B8%AB%E0%B8%AD%E0%B8%A2%E0%B8%A5%E0%B8%B2%E0%B8%A2%E0%B8%9C%E0%B8%B1%E0%B8%94%E0%B8%9E%E0%B8%A3%E0%B8%B4%E0%B8%81%E0%B9%80%E0%B8%9C%E0%B8%B2/",
    "Coverage dish for clam. holy_basil is listed as a main ingredient (essential to the dish) but Thai FCD has no standalone raw holy basil leaf record, so it is not in nutrition_basis -- its likely contribution (a leafy herb, ~15g) is small and its omission is disclosed here rather than approximated from an unrelated record."
))

NEW.append(computed(
    "ผัดฉ่าหอยแมลงภู่", ["mussel", "holy_basil"], ["bell_pepper"],
    ["chili_paste", "fish_sauce", "sugar", "vegetable_oil"], [], ["vegetarian", "vegan"], 150, 12,
    {"mussel": 150, "vegetable_oil": 10, "chili_paste": 15, "fish_sauce": 6, "sugar": 4},
    {"mussel": "STD:1173", "vegetable_oil": "STD:1368",
     "chili_paste": "STD:302", "fish_sauce": "STD:291", "sugar": "STD:1391"},
    FCD + "mussel (STD:1173), K34, roasted chili paste (STD:302), N71, sugar",
    "https://rosasthai.com/recipes/mussels-chilli-basil",
    "Coverage dish for mussel. holy_basil is a main ingredient (essential to the dish) but has no standalone Thai FCD record, so it is excluded from nutrition_basis rather than approximated -- same disclosed gap as the clam dish above."
))

NEW.append(computed(
    "ไข่ลูกเขย", ["quail_egg", "shallot"], [],
    ["fish_sauce", "sugar", "tamarind_paste", "vegetable_oil"], [], ["vegetarian", "vegan"], 120, 20,
    {"quail_egg": 60, "shallot": 20, "vegetable_oil": 15, "fish_sauce": 8, "sugar": 10},
    {"quail_egg": "STD:1281", "shallot": "STD:251", "vegetable_oil": "STD:1368", "fish_sauce": "STD:291",
     "sugar": "STD:1391"},
    FCD + "quail egg (STD:1281), shallot (STD:251), K34, N71, sugar",
    "https://hot-thai-kitchen.com/son-in-law-eggs/",
    "Coverage dish for quail_egg and shallot together. Traditionally duck or hen eggs; quail eggs are a smaller, bite-size home variant that keeps the dish squarely inside the dictionary's protein tier. tamarind_paste is in the seasonings list but not nutrition_basis: Thai FCD has no tamarind-paste record (only whole-fruit forms, a poor proxy for the concentrated cooking paste), so it is disclosed as omitted rather than approximated."
))

NEW.append(computed(
    "ปูผัดผงกะหรี่", ["crab", "egg"], ["onion", "celery"],
    ["yellow_curry_paste", "milk", "sugar"], [], ["vegetarian", "vegan"], 180, 15,
    {"crab": 120, "egg": 55, "onion": 30, "celery": 10, "yellow_curry_paste": 10, "milk": 30, "sugar": 3},
    {"crab": "STD:1157", "egg": "STD:1274", "onion": "STD:622", "celery": "STD:495",
     "yellow_curry_paste": "STD:294", "milk": "STD:1335", "sugar": "STD:1391"},
    FCD + "crab meat (STD:1157), egg, onion, celery, curry powder (STD:264), milk (STD:1335), sugar",
    "https://hot-thai-kitchen.com/curry-crab/",
    "Coverage dish for crab and milk together. A Thai-Chinese restaurant dish (poo pad pong karee) -- evaporated or fresh milk softens the curry sauce into a custardy coating."
))

NEW.append(computed(
    "ออส่วน", ["oyster", "egg"], ["soybean_sprouts"],
    ["soy_sauce", "vegetable_oil"], [], ["vegetarian", "vegan"], 200, 15,
    {"oyster": 100, "egg": 55, "vegetable_oil": 15, "soy_sauce": 6},
    {"oyster": "STD:1172", "egg": "STD:1274", "vegetable_oil": "STD:1368", "soy_sauce": "STD:273"},
    FCD + "oyster, stir-fried (STD:1172 -- the closest available Thai FCD record; the raw-oyster record STD:1171 exists but has no analysed macros), egg, K34, N136",
    "https://en.wikipedia.org/wiki/O-tao",
    "Coverage dish for oyster. Uses the stir-fried oyster record rather than raw, which happens to match how this dish is actually cooked -- the raw record (STD:1171) is present in Thai FCD but carries no analysed nutrient values at all."
))

NEW.append(computed(
    "แกงจืดฟักเขียวหมูสับ", ["winter_melon", "minced_meat"], [],
    ["salt", "pepper", "soy_sauce"], ["clean", "keto"], ["vegetarian", "vegan"], 200, 25,
    {"winter_melon": 150, "minced_meat": 60, "soy_sauce": 6, "pepper": 1},
    {"winter_melon": "STD:559", "minced_meat": "STD:970", "soy_sauce": "STD:273",
     "pepper": "STD:243"},
    FCD + "winter melon (STD:559), raw minced pork (STD:970), soy sauce, salt, pepper",
    "https://www.pholfoodmafia.com/recipe/winter-melon-soup-%E0%B9%81%E0%B8%81%E0%B8%87%E0%B8%88%E0%B8%B7%E0%B8%94%E0%B8%9F%E0%B8%B1%E0%B8%81/",
    "Coverage dish for winter_melon."
))

NEW.append(computed(
    "ยำถั่วพู", ["winged_bean", "shrimp"], ["shallot", "lime", "chili"],
    ["fish_sauce", "sugar"], ["clean", "keto"], ["vegetarian", "vegan"], 150, 12,
    {"winged_bean": 120, "shrimp": 50, "fish_sauce": 8, "sugar": 4},
    {"winged_bean": "STD:451", "shrimp": "STD:895", "fish_sauce": "STD:291", "sugar": "STD:1391"},
    FCD + "winged bean pod (STD:451), shrimp, N71, sugar",
    "https://hot-thai-kitchen.com/wing-bean-salad/",
    "Coverage dish for winged_bean. Named as a salad (ยำ), matching the actual recipe source, rather than a stir-fry."
))

NEW.append(computed(
    "ผัดมะรุมไข่", ["moringa", "egg"], ["garlic"],
    ["fish_sauce", "vegetable_oil"], ["clean"], ["vegetarian", "vegan"], 150, 10,
    {"moringa": 100, "egg": 55, "vegetable_oil": 10, "fish_sauce": 6},
    {"moringa": "STD:587", "egg": "STD:1274", "vegetable_oil": "STD:1368", "fish_sauce": "STD:291"},
    FCD + "moringa leaves (STD:587), egg, K34, N71",
    "https://phuketsouth.com/how-to-use-moringa-leaves-in-thai-cooking/",
    "Coverage dish for moringa."
))

NEW.append(computed(
    "แกงขี้เหล็ก", ["senna_siamea", "pork"], [],
    ["shrimp_paste", "fish_sauce"], [], ["vegetarian", "vegan"], 200, 60,
    {"senna_siamea": 100, "pork": 80, "shrimp_paste": 6, "fish_sauce": 8},
    {"senna_siamea": "STD:421", "pork": "STD:970", "shrimp_paste": "STD:254", "fish_sauce": "STD:291"},
    FCD + "senna siamea leaves and shoots (STD:421), raw minced pork, shrimp paste, fish sauce",
    "https://www.thaifoodheritage.com/en/recipe_list/detail/gaeng-khilek-thick-curry-with-siamese-senna",
    "Coverage dish for senna_siamea. Traditionally the leaves are boiled and drained at length first to remove bitterness -- a preparation step, not a nutrition change, since the raw-leaf record is what enters the food before that processing loss."
))

NEW.append(computed(
    "ผัดหน่อไม้ไข่", ["bamboo_shoots", "egg"], ["shrimp"],
    ["fish_sauce", "vegetable_oil"], ["clean"], ["vegetarian", "vegan"], 150, 10,
    {"bamboo_shoots": 100, "egg": 55, "vegetable_oil": 10, "fish_sauce": 6},
    {"bamboo_shoots": "STD:613", "egg": "STD:1274", "vegetable_oil": "STD:1368", "fish_sauce": "STD:291"},
    FCD + "bamboo shoot (STD:613), egg, K34, N71",
    "https://www.ezythaicooking.com/free_recipes/stir-fried-bamboo-shoots-with-egg.html",
    "Coverage dish for bamboo_shoots."
))

NEW.append(computed(
    "ยำหัวปลีกุ้ง", ["banana_flower", "shrimp"], ["coconut", "lime"],
    ["fish_sauce", "sugar"], [], ["vegetarian", "vegan"], 150, 15,
    {"banana_flower": 100, "shrimp": 50, "fish_sauce": 8, "sugar": 5},
    {"banana_flower": "STD:623", "shrimp": "STD:895", "fish_sauce": "STD:291", "sugar": "STD:1391"},
    FCD + "banana flower (STD:623), shrimp, N71, sugar",
    "https://www.simplysuwanee.com/banana-blossom-salad/",
    "Coverage dish for banana_flower, with coconut listed as the traditional optional garnish."
))

NEW.append(computed(
    "ตำมะละกอกุ้งสด", ["green_papaya", "tomato", "yardlong_bean"], ["peanuts", "chili", "garlic", "lime"],
    ["fish_sauce", "sugar"], [], ["vegetarian", "vegan"], 150, 10,
    {"green_papaya": 100, "tomato": 40, "yardlong_bean": 30, "fish_sauce": 10, "sugar": 8},
    {"green_papaya": "STD:590", "tomato": "STD:571", "yardlong_bean": "STD:445",
     "fish_sauce": "STD:291", "sugar": "STD:1391"},
    FCD + "green papaya (STD:590), tomato, yardlong bean (using the green bean record STD:445 as the nearest raw-legume-pod proxy -- see notes), N71, sugar",
    "https://hot-thai-kitchen.com/papaya-salad-v3/",
    "Coverage dish for green_papaya. Built without dried shrimp, since that ingredient is absent from the dictionary -- fresh shrimp is used as a substitute source of protein/umami instead, which changes the flavour profile from the classic version but keeps every listed ingredient real and traceable."
))

NEW.append(computed(
    "ผัดตำลึงไข่", ["ivy_gourd", "egg"], ["garlic"],
    ["fish_sauce", "vegetable_oil"], ["clean"], ["vegetarian", "vegan"], 150, 10,
    {"ivy_gourd": 120, "egg": 55, "vegetable_oil": 10, "fish_sauce": 6},
    {"ivy_gourd": "STD:503", "egg": "STD:1274", "vegetable_oil": "STD:1368", "fish_sauce": "STD:291"},
    FCD + "ivy gourd (STD:503), egg, K34, N71",
    "https://recipe.sgethai.com/recipes/stir-fried-ivy-gourd-with-egg/",
    "Coverage dish for ivy_gourd."
))

NEW.append(computed(
    "ผักกาดขาวผัดหมูสับ", ["napa_cabbage", "minced_meat"], ["garlic"],
    ["oyster_sauce", "soy_sauce", "vegetable_oil"], [], ["vegetarian", "vegan"], 150, 10,
    {"napa_cabbage": 130, "minced_meat": 60, "vegetable_oil": 10, "oyster_sauce": 8, "soy_sauce": 5},
    {"napa_cabbage": "STD:478", "minced_meat": "STD:970", "vegetable_oil": "STD:1368",
     "oyster_sauce": "STD:270", "soy_sauce": "STD:273"},
    FCD + "napa cabbage (STD:478), raw minced pork, K34, N60, N136",
    "https://www.pholfoodmafia.com/recipe/stir-fried-napa-cabbage-with-minced-pork-%E0%B8%9C%E0%B8%B1%E0%B8%81%E0%B8%81%E0%B8%B2%E0%B8%94%E0%B8%82%E0%B8%B2%E0%B8%A7%E0%B8%9C%E0%B8%B1%E0%B8%94%E0%B8%AB%E0%B8%A1%E0%B8%B9%E0%B8%AA%E0%B8%B1/",
    "Coverage dish for napa_cabbage. Stir-fry rather than clear soup, matching the actual recipe source."
))

NEW.append(computed(
    "ผัดพริกขิงถั่วแขกกุ้ง", ["green_bean", "shrimp"], ["kaffir_lime_leaf"],
    ["red_curry_paste", "vegetable_oil", "fish_sauce"], ["clean", "keto"], ["vegetarian", "vegan"], 150, 15,
    {"green_bean": 120, "shrimp": 60, "vegetable_oil": 10, "red_curry_paste": 15, "fish_sauce": 6},
    {"green_bean": "STD:445", "shrimp": "STD:895", "vegetable_oil": "STD:1368",
     "red_curry_paste": "STD:296", "fish_sauce": "STD:291"},
    FCD + "green bean pod (STD:445), shrimp, K34, red curry paste, N71",
    "https://www.simplysuwanee.com/easy-red-curry-green-beans-with-shrimp/",
    "Coverage dish for green_bean. Same family as th_023 (ผัดพริกขิงไก่ใส่ถั่วฝักยาว) but with green_bean and shrimp instead of yardlong_bean and chicken."
))

NEW.append(computed(
    "ต้มจืดหัวไชเท้าหมูสับ", ["white_radish", "minced_meat"], ["coriander"],
    ["soy_sauce", "salt", "pepper"], ["clean", "keto"], ["vegetarian", "vegan"], 200, 25,
    {"white_radish": 150, "minced_meat": 60, "soy_sauce": 5, "pepper": 1},
    {"white_radish": "STD:624", "minced_meat": "STD:970", "soy_sauce": "STD:273",
     "pepper": "STD:243"},
    FCD + "white radish (STD:624), raw minced pork, soy sauce, salt, pepper",
    "https://www.cookingwithnart.com/daikon-soup-with-pork-ribs/",
    "Coverage dish for white_radish."
))

NEW.append(computed(
    "ผัดกระเจี๊ยบเขียวไข่", ["okra", "egg"], ["garlic", "chili"],
    ["vegetable_oil", "soy_sauce"], ["clean"], ["vegetarian", "vegan"], 150, 10,
    {"okra": 120, "egg": 55, "vegetable_oil": 10, "soy_sauce": 5},
    {"okra": "STD:399", "egg": "STD:1274", "vegetable_oil": "STD:1368", "soy_sauce": "STD:273"},
    FCD + "okra pod (STD:399), egg, K34, N136",
    "https://krua.co/recipe/stir-fried-okra-with-egg",
    "Coverage dish for okra."
))

NEW.append(computed(
    "ผัดบวบใส่ไข่", ["sponge_gourd", "egg"], ["garlic"],
    ["fish_sauce", "vegetable_oil", "soy_sauce"], ["clean"], ["vegetarian", "vegan"], 150, 10,
    {"sponge_gourd": 130, "egg": 55, "vegetable_oil": 10, "fish_sauce": 5, "soy_sauce": 4},
    {"sponge_gourd": "STD:464", "egg": "STD:1274", "vegetable_oil": "STD:1368",
     "fish_sauce": "STD:291", "soy_sauce": "STD:273"},
    FCD + "angled sponge gourd (STD:464), egg, K34, N71, N136",
    "https://recipe.sgethai.com/recipes/stir-fried-angled-gourd-with-eggs/",
    "Coverage dish for sponge_gourd."
))

NEW.append(computed(
    "ยำมันแกว", ["jicama", "peanuts"], ["lime", "chili"],
    ["fish_sauce", "sugar"], [], ["vegetarian", "vegan"], 150, 10,
    {"jicama": 130, "peanuts": 15, "fish_sauce": 8, "sugar": 6},
    {"jicama": "STD:1923", "peanuts": "STD:345", "fish_sauce": "STD:291", "sugar": "STD:1391"},
    FCD + "jicama (STD:1923), peanuts, N71, sugar",
    "https://sunset.com/recipe/thai-style-jicama-salad",
    "Coverage dish for jicama."
))

NEW.append(computed(
    "ข้าวโพดคลุกเนย", ["corn"], [], ["butter", "milk", "sugar"],
    ["vegetarian"], ["vegan"], 150, 10,
    {"corn": 120, "butter": 10, "milk": 20, "sugar": 8},
    {"corn": "STD:143", "butter": "STD:1384", "milk": "STD:1335", "sugar": "STD:1391"},
    FCD + "sweet corn kernels (STD:143), butter, milk, sugar",
    "https://www.theworldofstreetfood.com/2023/08/thai-street-corn-or-khao-pod-klook-noey.html",
    "Coverage dish for corn. A Thai night-market street snack (khao pod klook noey), not plain boiled corn -- the milk-butter-sugar coating is the point of the dish."
))

NEW.append(computed(
    "ผัดผักปลังน้ำมันหอย", ["malabar_spinach", "garlic"], [],
    ["oyster_sauce", "vegetable_oil"], ["clean", "keto"], ["vegetarian", "vegan"], 150, 10,
    {"malabar_spinach": 150, "garlic": 6, "vegetable_oil": 10, "oyster_sauce": 8},
    {"malabar_spinach": "STD:511", "garlic": "STD:226", "vegetable_oil": "STD:1368", "oyster_sauce": "STD:270"},
    FCD + "Malabar spinach (STD:511), N2, K34, N60",
    "http://simplethaifood.com/thai-recipes/stir-fry/stir-fry-ceylon-spinach-with-oyster-sauce/",
    "Coverage dish for malabar_spinach."
))

NEW.append(computed(
    "ผัดมะเขือเปราะหมูสับ", ["thai_eggplant", "pork"], ["holy_basil"],
    ["soy_sauce", "vegetable_oil", "fish_sauce"], [], ["vegetarian", "vegan"], 150, 12,
    {"thai_eggplant": 130, "pork": 70, "vegetable_oil": 10, "soy_sauce": 6, "fish_sauce": 5},
    {"thai_eggplant": "STD:573", "pork": "STD:970", "vegetable_oil": "STD:1368",
     "soy_sauce": "STD:273", "fish_sauce": "STD:291"},
    FCD + "Thai eggplant (STD:573), raw minced pork, K34, N136, N71",
    "https://thatspicychick.com/thai-eggplant-stir-fry/",
    "Coverage dish for thai_eggplant."
))

NEW.append(computed(
    "ต้มยำเห็ดรวม", ["shiitake", "enoki", "king_oyster", "wood_ear", "button", "white_oyster"],
    ["lemongrass", "galangal", "kaffir_lime_leaf", "lime", "chili", "coriander"],
    ["fish_sauce", "chili_paste"], ["clean", "keto"], ["vegetarian", "vegan"], 200, 15,
    {"shiitake": 40, "enoki": 40, "king_oyster": 40, "wood_ear": 30, "button": 30, "white_oyster": 40,
     "fish_sauce": 10, "chili_paste": 10},
    {"shiitake": "STD:658", "enoki": "STD:627", "king_oyster": "STD:641", "wood_ear": "STD:662",
     "button": "STD:625", "white_oyster": "STD:640", "fish_sauce": "STD:291", "chili_paste": "STD:302"},
    FCD + "shiitake (STD:658), enoki (STD:627), king oyster (STD:641), wood ear (STD:662), button/champignon (STD:625), white oyster (STD:640), N71, roasted chili paste",
    "https://hot-thai-kitchen.com/mushroom-tom-yum/",
    "Coverage dish for all 6 remaining mushroom species at once. A vegetarian-friendly tom yum where mixed mushrooms substitute for meat/seafood entirely -- popular during vegetarian festivals."
))

NEW.append(computed(
    "ผัดผักกวางตุ้งน้ำมันหอย", ["bok_choy", "garlic"], [],
    ["oyster_sauce", "vegetable_oil", "sugar"], ["keto"], ["vegetarian", "vegan"], 150, 10,
    {"bok_choy": 150, "garlic": 6, "vegetable_oil": 10, "oyster_sauce": 8, "sugar": 3},
    {"bok_choy": "STD:474", "garlic": "STD:226", "vegetable_oil": "STD:1368",
     "oyster_sauce": "STD:270", "sugar": "STD:1391"},
    FCD + "bok choy (STD:474), N2, K34, N60, sugar",
    "https://vickypham.com/blog/bok-choy-oyster-sauce/",
    "Coverage dish for bok_choy. Not tagged clean: a pinch of sugar in the sauce is traditional for this exact preparation."
))

NEW.append(computed(
    "ต้มยำปลาใส่ผักชีลาว", ["fish", "dill"], ["lemongrass", "chili", "lime"],
    ["fish_sauce"], ["clean", "keto"], ["vegetarian", "vegan"], 200, 20,
    {"fish": 150, "dill": 15, "fish_sauce": 10},
    {"fish": "STD:1084", "dill": "STD:501", "fish_sauce": "STD:291"},
    FCD + "snakehead fish (STD:1084), dill (STD:501), N71",
    "https://hot-thai-kitchen.com/tom-yum-fish/",
    "Coverage dish for dill. Dill (ผักชีลาว) in a sour fish soup is a distinctly Isaan/Northeastern variation on the central Thai tom yum base cited here."
))

NEW.append(computed(
    "เมี่ยงคำ", ["piper_lolot", "peanuts"], ["ginger", "shallot", "lime", "coconut"],
    ["shrimp_paste", "sugar"], [], ["vegetarian", "vegan"], 150, 20,
    {"piper_lolot": 60, "peanuts": 20, "shrimp_paste": 8, "sugar": 15},
    {"piper_lolot": "STD:432", "peanuts": "STD:345", "shrimp_paste": "STD:254", "sugar": "STD:1391"},
    FCD + "piper lolot leaf (STD:432), peanuts, shrimp paste, sugar",
    "https://hot-thai-kitchen.com/miang-kham/",
    "Coverage dish for piper_lolot. Built without dried shrimp, which the classic topping list includes but which is absent from the dictionary -- ginger, shallot, lime and coconut cover the rest of the traditional toppings as optional."
))

NEW.append(computed(
    "ไก่ห่อใบเตยทอด", ["chicken", "pandan_leaf"], ["garlic", "coriander"],
    ["soy_sauce", "oyster_sauce", "sugar", "vegetable_oil"], [], ["vegetarian", "vegan"], 150, 20,
    {"chicken": 120, "vegetable_oil": 15, "soy_sauce": 8, "oyster_sauce": 6, "sugar": 4},
    {"chicken": "STD:895", "vegetable_oil": "STD:1368", "soy_sauce": "STD:273",
     "oyster_sauce": "STD:270", "sugar": "STD:1391"},
    FCD + "chicken (F25), K34, N136, N60, sugar -- pandan leaf itself is a discarded wrapper, not eaten, so it contributes no macros (same convention as th_037's uncounted dressing)",
    "https://rachelcooksthai.com/pandan-chicken-bites/",
    "Coverage dish for pandan_leaf. The leaf wraps and perfumes the chicken during frying but is not eaten, so it is listed as a main ingredient (it is essential to the dish) with zero nutrition_basis weight -- consistent with how th_037 excludes its uncounted dressing."
))

NEW.append(computed(
    "ไก่ทอดขมิ้น", ["chicken", "turmeric", "garlic"], [],
    ["fish_sauce", "vegetable_oil", "pepper"], [], ["vegetarian", "vegan"], 150, 20,
    {"chicken": 120, "turmeric": 10, "vegetable_oil": 15, "fish_sauce": 6, "pepper": 1},
    {"chicken": "STD:895", "turmeric": "STD:231", "vegetable_oil": "STD:1368",
     "fish_sauce": "STD:291", "pepper": "STD:243"},
    FCD + "chicken (F25), turmeric (STD:231), K34, N71, pepper",
    "https://krua.co/recipe/turmeric-fried-chicken",
    "Coverage dish for turmeric. Southern Thai fried chicken, marinated with fresh turmeric root rather than curry powder."
))

NEW.append(computed(
    "สลัดมันฝรั่ง", ["potato", "egg"], ["carrot", "onion"],
    ["mayonnaise", "salt", "pepper"], ["vegetarian"], ["vegan"], 180, 25,
    {"potato": 150, "egg": 55, "mayonnaise": 30, "pepper": 1},
    {"potato": "STD:1928", "egg": "STD:1274", "mayonnaise": "STD:1389",
     "pepper": "STD:243"},
    FCD + "raw potato (STD:1928, boiled before serving -- cooking loss not modelled), egg, mayonnaise (STD:1389), pepper",
    "https://www.pholfoodmafia.com/recipe/potato-salad-%E0%B8%AA%E0%B8%A5%E0%B8%B1%E0%B8%94%E0%B8%A1%E0%B8%B1%E0%B8%99%E0%B8%9D%E0%B8%A3%E0%B8%B1%E0%B9%88%E0%B8%87/",
    "Coverage dish for mayonnaise. A Western-influenced side dish that is genuinely common in Thai home cooking and at Thai buffets, per Claude.md's allowance for international dishes Thais actually cook. Salt omitted from nutrition_basis (no Thai FCD record; genuinely ~0 macros)."
))

json.dump(NEW, open("_new_recipes.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"built {len(NEW)} new recipes")
