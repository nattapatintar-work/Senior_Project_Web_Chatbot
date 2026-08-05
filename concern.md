# ⚠️ Concerns

Things to watch on the Ingredient-to-Recipe Chatbot project. Unlike the dated files in
`Summarization/`, this is **not a snapshot** — it lives until every item is closed.

**How to read this:**

- Concerns are grouped by **the week they were raised**. New weeks get appended below.
- **Impacts** = the week it actually causes damage if nothing is done. The gap between
  when it was raised and when it bites is your window to fix it cheaply.
- **Severity** = how expensive if ignored, not how urgent right now. A 🔴 item may need
  no action this week and still be the worst thing on the list.
- Every concern has a **next action**. A worry with no action is just anxiety.
- IDs (`C1`, `C2`, …) are stable — use them when talking to Person 1.

---

# ------- Week 1 -------

- ~~**C1** — Dictionary can't hold seasonings/aromatics, and 4 tests forbid adding them~~ → ✅ **CLOSED 2026-08-05**
- **C2** — 20 classes ≈ 4,000 instances to label, not 3,000 → 🟡 **impacts Week 3–4**
- ~~**C3** — PyThaiNLP unverified on Python 3.13~~ → ✅ **CLOSED 2026-08-05**
- **C4** — Thai prefix collisions break naive matching → 🟡 **impacts Week 5** *(worse since Week 3: 40 new entries added more collisions)*
- ~~**C5** — No git repo; AGPL-3.0 obligation unmet~~ → ✅ **CLOSED 2026-08-05**
- **C6** — ปวยเล้ง synonym is my guess, not your decision → 🟢 **impacts Week 2**
- **C7** — `rapidfuzz` / `pyyaml` missing from requirements → 🟢 **impacts Week 5, 8**
- **C8** — cp874 encoding crash will recur on Person 1's PC → 🟢 **impacts anytime**

---

## ~~C1 — The dictionary has no room for ingredients YOLO can't see~~ ✅ CLOSED

> ✅ **Closed 2026-08-05 (Week 3)** — Option A implemented. Detail below kept because
> Weeks 11–12 need the reasoning.
>
> **Resolution:** the dictionary now has two tiers in one file. The 20 detectable
> ingredients keep `yolo_class_id` 0–19, completely unchanged; 40 text-only entries were
> added with `yolo_class_id: null` (proteins, herbs, staples, seasonings). Because no
> existing key moved and no existing ID changed, the joint lock with Person 1 holds.
>
> The four tests were relaxed as predicted, and **two new ones added** that guard the
> lock better than the originals did:
>
> - `test_the_detectable_tier_is_still_the_agreed_twenty` — checks identity *and order*
>   of the 20, so a rename or reorder fails even though a count would still look right
> - `test_seasonings_are_never_detectable` — no seasoning may carry a class ID
>
> Two fields were added to every entry while the file was open: `is_seasoning` (basic
> seasonings must not affect matching, `Claude.md:427`) and `is_animal_product`, which
> lets the vegan rule be **derived from the data** instead of remembered. That second one
> matters more than it looks — see the note at the end of this entry.
>
> ⚠️ **Still owed to Person 1:** they have not yet been told. The message is short —
> *IDs 0–19 and all 20 keys are untouched; only entries YOLO will never see were added.*
> Tell them before they next pull, not after.

**Original entry follows.**

> 🔴 **High** · **Impacts: Week 3–4** (recipe entry) · Owner: You + Person 1

`data/ingredients.json` contains exactly the 20 ingredients YOLO will be trained on. But
the 40-recipe database due in Weeks 3–4 needs ingredients a camera will *never* usefully
detect — holy basil, fish sauce, oyster sauce, soy sauce, sugar, rice, noodles, pork,
shrimp, beef.

This is not hypothetical. It is already inconsistent today:

```
recommender/recommend.py:88   "missing": ["holy_basil"]
data/ingredients.json         holy_basil  →  not present
```

The project doc has the same shape in its own recipe example (`Claude.md:403-405`), which
lists `holy_basil`, `fish_sauce`, `oyster_sauce`. And the canonical NLP example at
`Claude.md:122` — *"มีกุ้งกับไข่ อยากกินคลีน ไม่เอาหมู"* — uses กุ้ง (shrimp) and หมู (pork),
neither of which is in the locked 20. **The project's own worked examples cannot run
against the current dictionary.**

**Why this is a trap rather than an ordinary gap:** the contract tests actively prevent
the fix. Adding `"holy_basil": {"yolo_class_id": null, ...}` turns four green tests red:

| Test in `tests/test_contract.py` | Assertion | Why it fails |
|---|---|---|
| `test_ingredients_file_loads` | `len(data) == 20` | becomes 21 |
| `test_ingredients_are_the_agreed_twenty` | exact key list | unexpected extra key |
| `test_every_ingredient_has_the_required_fields` | `isinstance(id, int)` | `None` is not an `int` |
| `test_yolo_class_ids_are_sequential_from_zero` | `sorted(ids) == range(20)` | `TypeError` sorting `None` against `int` |

So whoever hits this in Week 3 gets four failing tests telling them they broke something,
when in fact the tests are what need to change. That is a genuinely confusing hour, and it
lands in your heaviest week.

**Two ways out:**

*Option A — two tiers in one file (recommended).* Keep `yolo_class_id` as `0–19` for
detectable ingredients, add `null` for text-only ones. Relax the tests to assert that
*non-null* IDs are contiguous from 0, and drop the hard `== 20` count.

- ✅ One dictionary, one lookup path, one place to resolve a Thai word
- ✅ The 20 locked YOLO classes and their IDs are **completely untouched** — Person 1's
  training is unaffected, so this does not reopen the locked agreement
- ⚠️ Requires editing 4 tests

*Option B — a separate `pantry.json`.* Leave `ingredients.json` frozen, keep
non-detectable items in a second file.

- ✅ Nothing existing changes at all
- ⚠️ Two files to keep in sync, and every lookup checks both — the exact "same ingredient,
  two names, no link" failure `Claude.md:364` warns about, just moved up a level

**Recommendation, not a decision:** Option A. Adding a nullable field changes no existing
ID, so the joint lock with Person 1 holds. But it *is* a schema change to a file you
agreed together — tell them before doing it, not after.

**Next action:** ~~Decide A or B with Person 1 before starting recipe entry in Week 3.~~
Done — Option A. Remaining action is only to **tell Person 1**, which has not happened yet.

> 💡 **Worth carrying forward:** the fix that closed this concern also removed a whole
> class of future bug. `is_animal_product` means the vegan rule lives in exactly one
> place — the dictionary — rather than being restated in the recipe file, the test file,
> and Week 7's health filter. The trade is that **a wrongly flagged ingredient is now
> wrong everywhere at once, and every test will cheerfully agree with it.** That flag is
> the one field in `ingredients.json` worth double-checking by hand.

---

## C2 — 20 classes means ~4,000 instances to label, not ~3,000

> 🟡 **Medium** · **Impacts: Week 3–4** · Owner: Person 1

`Claude.md:89` budgets 12–15 classes; you and Person 1 agreed on 20. At the recommended
200 instances per class (`Claude.md:104`) that is ~4,000 instances instead of ~3,000 —
roughly a third more labelling, landing in the same weeks as your recipe database.

Not your workload, but it is your risk: if Person 1 falls behind on dataset merging, the
Week 6 sync (`Claude.md:448`) explicitly anticipates work shifting onto you.

**Next action:** Confirm Person 1 has priced in 20 classes rather than 15. If it looks
tight, the fallback is dropping to 150 instances/class for the visually easiest classes
(carrot, egg) rather than cutting a class outright.

---

## ~~C3 — PyThaiNLP is unverified on Python 3.13~~ ✅ CLOSED

> ✅ **Closed 2026-08-05 (Week 2)** — verified working, no action needed.

PyThaiNLP **5.3.5** installs and runs correctly on Python 3.13.2:

```
>>> word_tokenize('มีไก่กับไข่')
['มี', 'ไก่', 'กับ', 'ไข่']
```

Correct segmentation — 4 tokens, word boundaries in the right places. No Python 3.11
fallback venv needed. Week 5 can proceed on the current interpreter.

*(The output first appeared as mojibake, which was C8's cp874 console issue, not a
PyThaiNLP problem. Worth remembering: an encoding-looking failure is usually the terminal,
not the library.)*

---

## C4 — Thai prefix collisions will break naive matching

> 🟡 **Medium** · **Impacts: Week 5** · Owner: You

Several names in the locked 20 are prefixes of others:

| Short | Longer | Risk |
|---|---|---|
| พริก (chili) | พริกหวาน (bell pepper) | "พริกหวาน" matches as **chili** |
| กะหล่ำ (cabbage) | กะหล่ำดอก (cauliflower) | "กะหล่ำดอก" matches as **cabbage** |
| มันฝรั่ง (potato) | มันเทศ (sweet potato) | both start มัน |
| หอมใหญ่ (onion) | ต้นหอม (green onion) | both contain หอม |

**Updated 2026-08-05 (Week 3): the 40 text-only entries made this materially worse.**
The dictionary went from 20 entries to 60, and the new ones collide with each other and
with the original 20:

| Short | Longer | Risk |
|---|---|---|
| พริก (chili) | พริกไทย (pepper) | "พริกไทย" matches as **chili** — a seasoning read as a main ingredient |
| กุ้ง (shrimp) | กุ้งแห้ง (dried shrimp) | wrong ingredient, and both are animal products so the vegan filter still holds |
| ซีอิ๊ว (soy sauce) | ซีอิ๊วดำ (dark soy sauce) | wrong seasoning |
| ข้าว (rice) | ข้าวคั่ว (roasted rice powder) | staple confused with a seasoning — flips a keto tag |
| มะเขือ- | มะเขือเทศ / มะเขือยาว | tomato vs eggplant, entirely different dishes |
| ถั่ว- | ถั่วงอก / ถั่วลิสง / ถั่วฝักยาว | bean sprout vs peanut vs long bean |
| น้ำมัน (oil) | น้ำมันหอย (oyster sauce) | **vegan-relevant** — oyster sauce is an animal product, oil is not |

A first-match-wins loop over the synonym lists gets these wrong, and the failure is silent
— the user asks for bell pepper and the bot recommends a chili dish. Nothing crashes, so
no test catches it unless one is written for it.

> ⚠️ The น้ำมัน / น้ำมันหอย pair is the one that actually hurts. A mismatch there does not
> just pick the wrong dish — it can let a dish containing oyster sauce pass a vegan
> filter, because the matcher recorded plain oil instead. A correctness bug wearing a
> ranking bug's clothes.

**Next action:** In Week 5, sort synonyms by length **descending** before matching, so the
longest candidate is tried first. Add tests asserting `"พริกหวาน" → bell_pepper`,
`"กะหล่ำดอก" → cauliflower`, `"พริกไทย" → pepper`, and `"น้ำมันหอย" → oyster_sauce`.
Write those tests *before* the matcher.

---

## ~~C5 — No git repo, and AGPL-3.0 is a real obligation~~ ✅ CLOSED

> ✅ **Closed 2026-08-05 (Week 3).**
>
> - `git init` on branch `main`, three commits so far. Baseline was committed *before*
>   the `ingredients.json` schema change, so the riskiest edit of the week is the first
>   thing that can be undone.
> - `.env` confirmed absent from the staged file list before the first commit — checked,
>   not assumed.
> - `LICENSE` added: verbatim AGPL-3.0 text (34,523 bytes) from gnu.org.
>
> **Not yet done:** the repo is local only. Pushing it public is still required for AGPL
> compliance and still needs a README. Tracked separately rather than reopening this.
>
> One thing to know before pushing: git is normalising LF → CRLF on checkout on this
> machine. Harmless locally, but if Person 1's machine is configured differently it will
> produce whole-file diffs that hide the real changes. A one-line `.gitattributes`
> (`* text=auto eol=lf`) fixes it, and is cheapest to add before anyone else clones.

**Original entry follows.**

> 🟡 **Medium** · **Impacts: ongoing**, hard deadline at submission · Owner: You + Person 1

`D:\Senior_Project` is not a git repository. Two separate problems:

1. **No version control.** No history, no undo, no way to see what changed. A bad edit to
   `ingredients.json` is unrecoverable.
2. **Licensing.** YOLO is AGPL-3.0 (`Claude.md:330`). That licence is viral: it requires
   the *entire* codebase, including your custom-trained weights, to be open-sourced. This
   is a legal obligation, not a preference. The free fix is a public GitHub repo with an
   AGPL-3.0 `LICENSE` file — which also helps the report, since reproducibility can be
   cited.

**Next action:** `git init`, add a `.gitignore` (`.venv`, `__pycache__`, `.env`, `*.pt`),
commit the current state. Add the AGPL-3.0 LICENSE before the repo goes public. Do the
`.gitignore` **first** — committing a `.env` with LINE credentials to a public repo lets
anyone post as your bot.

---

## C6 — ปวยเล้ง under `spinach` is my judgement call, not yours

> 🟢 **Low** · **Impacts: Week 2** (photo labelling) · Owner: You + Person 1

You specified `spinach (ผักโขม)`. I added ปวยเล้ง and ผักปวยเล้ง as synonyms on my own
initiative, because Thai speakers commonly use them interchangeably. Botanically they are
different plants, and they look different.

If Person 1 labels training images strictly as ผักโขม, then a user typing ปวยเล้ง gets
matched to a class trained on a plant that does not look like what they have.

**Next action:** Show Person 1 the `spinach` entry and decide together. Removing the two
synonyms is a 10-second edit if you want to play it safe.

---

## C7 — `rapidfuzz` and `pyyaml` are missing from requirements.txt

> 🟢 **Low** · **Impacts: Week 5 and Week 8** · Owner: You

- `rapidfuzz` — fuzzy matching for typos, required by Week 5 (`Claude.md:442`)
- `pyyaml` — needed to read `thresholds.yaml` from Person 1 in Week 8 (`Claude.md:523`)

Minor, but it means `pip install -r requirements.txt` on a fresh machine does not produce
a working environment — which matters when Person 1 clones the repo.

**Next action:** Add both when you next touch `requirements.txt`. No rush, but do it before
Week 5.

---

## C8 — The cp874 encoding crash will recur on Person 1's machine

> 🟢 **Low** · **Impacts: anytime** someone else runs the code · Owner: You

A Thai-locale Windows console defaults to the **cp874** codepage, which cannot encode
emoji. Printing 🍳 raises `UnicodeEncodeError`; Thai text prints as mojibake.

Already fixed in all three modules with `sys.stdout.reconfigure(encoding="utf-8")`, but the
fix is per-file, in each `__main__` block. Any *new* file that prints Thai will hit it
again, and Person 1 will hit it the first time they run your code.

Worth remembering: this is a **terminal-display issue only**. The strings are valid and
LINE is UTF-8 throughout, so the bot itself was never affected. Don't let it send you
hunting for an encoding bug in the wrong place.

**Next action:** Nothing now. When the Week 2 Flask app lands, put the `reconfigure` call
once at application startup instead of repeating it per file. Mention it to Person 1 so
they don't lose an hour to it.

---

# ------- Week 2 -------

- **C9** — Sessions live in memory; a restart loses them → 🟢 **impacts Week 9–10 testing, demo day**
- **C10** — `flask run --debug` makes the bot reply twice → 🟡 **impacts anytime you restart the server**
- **C11** — Slow image downloads can outlive the reply token, forcing quota-costing push → 🟡 **impacts Week 8–10**

---

## C9 — Sessions are in memory and vanish on restart

> 🟢 **Low** · **Impacts: Week 9–10 testing, demo day** · Owner: You

`api/session.py` keeps buffers in a module-level dict. Restarting the server drops every
open session, so a user mid-conversation gets no reply and must resend.

This is the right trade-off for now — a session lives ~2.5 seconds, so the window for loss
is tiny, and a database would be a lot of machinery for very little gain. Recording it
because it is a deliberate choice, not an oversight, and it belongs in the report's
limitations section (Weeks 11–12).

**Next action:** None. Just don't restart the server mid-demo.

---

## C10 — Flask's auto-reloader makes the bot reply twice

> 🟡 **Medium** · **Impacts: any time you restart the server** · Owner: You

`flask run --debug`, or `app.run(debug=True)` without `use_reloader=False`, runs the app in
**two processes**. Each gets its own session buffer and its own timers, so every message is
processed twice and the user receives two identical replies.

`api/main.py` already passes `use_reloader=False`, so the committed code is safe. The risk
is running the server a different way — `flask run --debug` is the command most tutorials
give.

The reason this is worth writing down: the symptom is identical to "LINE retried my
webhook because I answered too slowly." You could easily spend an afternoon optimising the
webhook when the actual cause is the reloader.

**Next action:** Always start it with `python api/main.py`. If you ever see doubled
replies, check for two Python processes **before** investigating anything else.

---

## C11 — Slow image downloads can outlive the reply token

> 🟡 **Medium** · **Impacts: Week 8–10** · Owner: You

A LINE reply token is single-use and lives ~30 seconds. The current path spends 2.5s on
debounce, then downloads up to 5 images one at a time, and from Week 8 also runs YOLO on
each. On a slow connection that can approach the limit.

When the token expires, `send_reply()` falls back to **push** — which costs monthly quota
that the Thai free plan cannot top up (`Claude.md:326`). So the failure is not a crash; it
is a quiet, cumulative drain on the thing you can least afford to run out of.

**Next action:** Watch for `[main] reply failed ...; falling back to push` in the server
log during Week 8–10 testing. If it shows up regularly, download images in parallel with
threads rather than one after another. Also check quota with
`GET /v2/bot/message/quota/consumption` during those weeks, as the doc advises.

---

# ------- Week 3 -------

- ~~**C12** — `broccoli` and `onion` have no nutrition data anywhere~~ → ✅ **CLOSED 2026-08-05**
- ~~**C13** — Test suite is red~~ → ✅ **CLOSED 2026-08-05** (53 passing)
- **C14** — Computed recipes' gram amounts are our assumption, not reference data → 🟡 **impacts Weeks 11–12**
- **C15** — The keto tag is true of the dish and misleading about the meal → 🟡 **impacts Week 7**

---

## ~~C12 — Two of the 20 detectable classes have no nutrition data at all~~ ✅ CLOSED

> ✅ **Closed 2026-08-05 (Week 3).**
>
> - **broccoli** → USDA FoodData Central, "Broccoli, raw", 30 Oct 2020 (FDC 170379), in
>   `data/external_nutrition.json`, used by `th_040`. Cited in that recipe's
>   `nutrition_source` rather than silently blended into the Thai FCD numbers.
> - **onion** → no external source needed after all. It appears only in *direct* recipes
>   (`th_008`, `th_009`, `th_010`, `th_013`), where INMU analysed the whole dish, so its
>   contribution is already inside a measured value.
>
> **The part worth remembering** is not the gap but what closing it exposed: USDA
> "Carbohydrate, by difference" *includes* dietary fibre and Thai FCD `CHOAVLDF` *excludes*
> it. Summing the two as-published would have overstated broccoli's carbohydrate by 2.6 g
> per 100 g — enough to push `th_040` over the keto threshold and flip a health tag, with
> no error and nothing to notice. Broccoli is stored as 6.64 − 2.6 = 4.04 g on the Thai FCD
> basis, with both raw figures kept so the subtraction is checkable.
>
> ⚠️ **Any future second-database addition needs the same check before its values are
> summed with INMU's.** Two tables can both be correct and still not be addable.

**Original entry follows.**

> 🟡 **Medium** · **Impacts: Weeks 3–4 (recipe entry), Week 7 (recommender)** · Owner: You

Thai FCD has **no entry** for `broccoli` (บรอกโคลี) or `onion` (หอมใหญ่ / หัวหอม).
Searches return nothing — not a near-miss, not a differently-named variant, nothing.

Both are in the locked 20 that Person 1 is training on. So the detector will be able to
see them, users will type them, and the recipe database will have nothing sourced to say
about them.

Why this is awkward rather than fatal: a recipe can still *list* broccoli as an
ingredient, and matching works fine — the dictionary is what matching reads, not the
nutrition table. What breaks is only Method B (computing a dish's macros by summing its
ingredients), where an unaccounted ingredient means part of the dish's weight contributes
nothing to the total. The result is a plausible-looking underestimate.

**Next action:** avoid leaning on broccoli or onion as *significant* ingredients in
computed recipes — use them where they are garnish-scale, or prefer a direct-lookup dish.
Where that is not possible, state the omission in the recipe's `nutrition_basis` rather
than quietly dropping it. Revisit in Week 7 if these two turn out to be common in real
photos.

---

## ~~C13 — The test suite is red, and that is a slower problem than it looks~~ ✅ CLOSED

> ✅ **Closed 2026-08-05 (Week 3)** — `53 passed` (20 contract + 12 session + 21 recipe).
> `data/recipes.json` exists, so the 21 recipe tests have data to check.
>
> The habit the entry was really about still stands: green is the completion criterion for
> a piece of work, not a follow-up task.

**Original entry follows.**

> 🟡 **Medium** · **Impacts: now** · Owner: You

```
21 failed, 32 passed in 3.22s
```

All 21 failures are `tests/test_recipes.py` hitting `FileNotFoundError` on a
`data/recipes.json` that does not exist yet. The validator was written before the data on
purpose — it defines what the data must satisfy — so this is expected.

The concern is not the failure. It is the habit. A suite that is *known* to be red stops
being read, and the moment it stops being read it stops catching the thing it was written
to catch. Between now and the moment `recipes.json` lands, a real regression in the 32
passing tests would be invisible, because the summary line is already red.

**Next action:** treat green as the completion criterion for Weeks 3–4, not an optional
follow-up. Until then, run `pytest tests/test_contract.py tests/test_session.py` to get a
signal that still means something. Do not commit `recipes.json` in a partially-filled
state that leaves the suite red overnight.

---

## C14 — Half the recipes rest on gram amounts we invented

> 🟡 **Medium** · **Impacts: Weeks 11–12 (report)** · Owner: You

`Claude.md:430` forbids estimated nutrition, and this project honours that for **nutrient
values** — every one comes from Thai FCD. But roughly a third of the 40 recipes have no
composed-dish entry in the database, so their macros are summed from per-ingredient
values, and the **gram amount of each ingredient is a choice made by this project**.

That is a legitimate method — it is how recipe formulation normally works — but it is not
the same epistemic status as a laboratory-analysed dish, and the two must not be presented
as if they were. Cooking losses and oil absorption are not modelled either.

Concretely: `แกงเขียวหวานไก่` at 101 kcal/100 g is a measurement. `ไข่เจียว` computed from
egg + oil + fish sauce is a model, and its accuracy depends entirely on whether the
assumed oil quantity resembles what a real cook uses — and oil is the single biggest lever
on the calorie count.

**Next action:** every recipe already records `nutrition_method` as `direct` or `computed`,
and computed ones must fill `nutrition_basis` with their gram amounts —
`tests/test_recipes.py` enforces this. In the report, state the split (how many of each)
and name the limitation explicitly rather than letting the reader assume all 40 are
equally sourced. This is a limitation to *declare*, not to hide; declaring it costs
nothing and finding it undeclared costs credibility.

**Updated 2026-08-05 — the split is now known: 32 `direct`, 8 `computed`.** So four fifths
of the database is fully measured and one fifth carries assumed proportions. Two
conventions were used in the computed eight, both stated in `data/RECIPES_NOTES.md`:
oil is always listed explicitly at 10–12 g (it is the largest single lever on the calorie
count), and ingredients are priced at **raw** weight, so cooking loss and oil absorption
are not modelled.

---

## C15 — The keto tag is true of the dish and misleading about the meal

> 🟡 **Medium** · **Impacts: Week 7 (recommender), Weeks 11–12 (report)** · Owner: You

23 of the 40 recipes carry `keto`. That is far more than a Thai recipe database should
plausibly produce, and the cause is a portion convention rather than a bug.

Curry servings are **200 g of curry, with rice counted as a separate dish**. So
แกงเขียวหวานไก่ comes to 6.1 g of carbohydrate and passes the ≤10 g rule in
`HEALTH_TAGS.md` cleanly. But nobody eats green curry without rice, and adding a normal
200 g serving of rice puts the real meal nearer 60 g.

The tag is therefore **accurate about what was measured and misleading about what gets
eaten** — which is the more dangerous kind of wrong, because every individual number
checks out.

**Why the rule was not simply changed:** the tagging was done by applying
`HEALTH_TAGS.md` exactly as written. Rewriting a definition *after* seeing that it
produced an unflattering answer is how a definition stops meaning anything. The honest
move is to leave the rule intact and record that it is producing a bad result.

**Next action:** in Week 7, either

- have the recommender qualify the tag in the reply template — "keto, without rice" — or
- add a third clause to the keto rule ("not conventionally served with rice") and retag,
  documenting that the rule changed and why.

Either way it needs a sentence in the report. The underlying point is a good one to make:
a health tag is meaningless without a stated portion, and portion conventions are exactly
where a nutrition database quietly encodes an assumption.

---

# Closed

Don't delete closed concerns — the reasoning is worth keeping, and Weeks 11–12 need it for
the report.

| ID | Raised | Closed | Resolution |
|---|---|---|---|
| C3 | Week 1 | 2026-08-05 (Week 2) | PyThaiNLP 5.3.5 verified working on Python 3.13.2; no fallback venv needed |
| C1 | Week 1 | 2026-08-05 (Week 3) | Two-tier dictionary (Option A): 40 text-only entries with `yolo_class_id: null`, 20 detectable untouched. 4 tests relaxed, 2 stricter ones added. **Person 1 not yet told** |
| C5 | Week 1 | 2026-08-05 (Week 3) | `git init` + 3 commits + verbatim AGPL-3.0 `LICENSE`. `.env` verified excluded before first commit. Public push + README still outstanding |
| C12 | Week 3 | 2026-08-05 (Week 3) | broccoli via USDA FDC 170379 in `data/external_nutrition.json`, converted onto Thai FCD's available-carbohydrate basis; onion needed no source, appearing only in direct recipes |
| C13 | Week 3 | 2026-08-05 (Week 3) | `data/recipes.json` written; 53 tests passing |

---

*Last updated: 2026-08-05, after Week 3 (40-recipe database written and verified; Weeks
3–4 deliverable complete, Week 2 photo shoot still outstanding).*
