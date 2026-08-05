"""
tools/build_cache.py
====================
Fetches every Thai FCD food the recipe database needs, once, into
data/thaifcd_cache.json.

WHY A CACHE
-----------
The Thai FCD server is an academic host, not an API. During enumeration it
reset the connection twice and timed out once. Re-fetching every time a recipe
is edited would be slow, rude, and -- because a failed fetch is easy to miss --
a way for a wrong number to creep in unnoticed.

So the network is touched exactly once per food. The cache is committed, which
means every nutrient value in data/recipes.json is reviewable in a git diff and
reproducible by re-running this script.

Run with:
    python tools/build_cache.py

Already-cached foods are skipped, so re-running it is cheap and safe.

HOW THE IDS BELOW WERE CHOSEN
-----------------------------
By searching the database and reading the candidate names. That step is not
automated on purpose: "ฟักทอง" alone returns seven entries -- flower, shoot,
peeled raw, peeled boiled, unpeeled raw -- and picking the right one is a
judgement call about what a person actually cooks with, not something a
substring match should decide silently.
"""

import sys

from thaifcd import get_cached, load_cache, save_cache

# ---------------------------------------------------------------------------
# Composed dishes -- Thai FCD group T, "Mixed foods: ready-to-eat".
# These give a whole dish's macros in one lookup, per 100 g of the dish.
# ---------------------------------------------------------------------------
DISHES = {
    "1456": "แกงเขียวหวาน, ไก่",
    "1459": "แกงเขียวหวานหมู",
    "1464": "แกงเผ็ด, ไก่",
    "1467": "แกงพะแนง, ไก่/หมู",
    "1468": "แกงมัสมั่น, ไก่",
    "1451": "แกงกะหรี่, ไก่",
    "1475": "แกงเหลืองไก่",
    "1471": "แกงส้มผักรวม",
    "1463": "แกงป่าฟักทองใส่หมู",
    "1460": "แกงซุปไก่",
    "1489": "ต้มข่าไก่",
    "1491": "ต้มยำ, กุ้ง",
    "1492": "ต้มยำ, ไก่",
    "1490": "ต้มพะโล้, รวม",
    "1502": "ผัดเปรี้ยวหวานไก่",
    "1503": "ผัดเผ็ดไก่",
    "1505": "ผัดพริกขิงไก่ใส่ถั่วฝักยาว",
    "1561": "ข้าวราดไก่ผัดใบกะเพรา",
    "1552": "ข้าวผัดทั่วไป",
    "1553": "ข้าวผัดผัก",
    "1554": "ข้าวผัดหมู",
    "1525": "ก๋วยเตี๋ยว, ผัดไทย",
    "1529": "ก๋วยเตี๋ยวเส้นใหญ่, ผัดซีอิ๊ว, หมู",
    "1524": "ก๋วยเตี๋ยว, ผัดขี้เมา",
    "1513": "ส้มตำ, ไทย",
    "1508": "ลาบอีสาน",
    "1506": "ยำรวมมิตรทะเล",
    "1569": "โจ๊ก, หมู",
    "1555": "ข้าวมัน, ไก่ต้ม",
    "1550": "ข้าวซอยไก่",
    "1551": "ข้าวต้มหมู",
    "1567": "ข้าวหมูแดง",
    "1481": "ไก่อบซอส",
    "1484": "ซุปมะเขือ",
    "1439": "มันฝรั่งทอด",
    "1494": "ทอดมัน, กุ้ง",
    # Cooked egg dishes. Filed under the egg group rather than group T, which
    # is why an earlier search for "ไข่เจียว" found nothing -- the entry is
    # named "ไข่ไก่, เจียว (เติมน้ำปลา)". Worth remembering: a dish missing
    # from group T is not necessarily missing from the database.
    "1270": "ไข่ไก่, เจียว (เติมน้ำปลา)",
    "1272": "ไข่ไก่, ตุ๋น (เติมน้ำและน้ำปลา)",
    "1271": "ไข่ไก่, ต้ม, 10 นาที",
}

# ---------------------------------------------------------------------------
# Raw ingredients, for the dishes Thai FCD has no composed entry for.
# Values are per 100 g, so a recipe using these must record its gram amounts.
# ---------------------------------------------------------------------------
INGREDIENTS = {
    "1274": "ไข่ไก่, ทั้งฟอง, ดิบ",
    "895": "ไก่, เนื้อ, ดิบ",
    "436": "ต้นหอม",
    "429": "แครอท, ดิบ",
    "571": "มะเขือเทศ, สุก",
    "409": "กะหล่ำปลี, ดิบ",
    "408": "กะหล่ำดอก, ดิบ",
    "226": "กระเทียม, สด",
    "489": "ผักโขมใหญ่, ดิบ",
    "484": "ผักกาดหอม, ดิบ",
    "441": "แตงกวา, ดิบ",
    "561": "ฟักทอง, เนื้อ, ปอกเปลือก, ดิบ",
    "562": "ฟักทอง, เนื้อ, ปอกเปลือก, ต้ม",
    "1926": "มันเทศ, เนื้อสีเหลือง, นึ่ง",
    "1928": "มันฝรั่ง, ดิบ",
    "576": "มะเขือยาว, ดิบ",
    "233": "ขิง, แก่",
    "545": "พริกขี้หนู",
    "1368": "น้ำมันปาล์มโอเลอิน",
    "291": "น้ำปลาแท้",
    "273": "ซีอิ้วขาว",
    "270": "ซอสหอยนางรม",
    "1391": "น้ำตาลทรายแดง",
}

# Two of the 20 YOLO classes have NO entry in Thai FCD at all: broccoli
# (บรอกโคลี) and onion (หอมใหญ่/หัวหอม). Searches for both return nothing.
# Any computed recipe therefore has to avoid them as significant ingredients,
# or accept that part of its weight is unaccounted for. Recorded here rather
# than discovered again later.
MISSING_FROM_DATABASE = ["broccoli", "onion"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    cache = load_cache()
    started_with = len(cache)
    failures = []

    for food_id, label in {**DISHES, **INGREDIENTS}.items():
        key = f"STD:{food_id}"
        if key in cache:
            continue
        try:
            record = get_cached("STD", food_id, cache)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED {food_id} {label}: {exc}")
            failures.append(food_id)
            continue
        macros = " ".join(
            f"{field}={record[field]}" for field in ("kcal", "protein", "fat", "carb")
        )
        flag = "" if None not in [record[f] for f in ("kcal", "protein", "fat", "carb")] else "  <-- INCOMPLETE"
        print(f"  {record['food_code']:>6}  {label[:32]:<34} {macros}{flag}")

    save_cache(cache)
    print(f"\ncached {len(cache)} foods (+{len(cache) - started_with} new)")
    if failures:
        print(f"FAILED: {failures} -- re-run to retry just these")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
