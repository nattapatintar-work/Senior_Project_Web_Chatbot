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
- ~~**C4** — Thai prefix collisions break naive matching~~ → ✅ **CLOSED 2026-08-08** (real cause was the tokenizer, not sort order — see closure note)
- ~~**C5** — No git repo; AGPL-3.0 obligation unmet~~ → ✅ **CLOSED 2026-08-05**
- **C6** — ปวยเล้ง synonym is my guess, not your decision → 🟢 **impacts Week 2**
- ~~**C7** — `rapidfuzz` / `pyyaml` missing from requirements~~ → ✅ **CLOSED 2026-08-08**
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
> **Count updated 2026-08-08 (session 5): the text-only tier has since grown to 49** (69
> total), picking up further additions made while filling `recipes.json` — e.g.
> `yellow_curry_paste` and `sour_curry_paste`, both called out by name in their triggering
> recipes' `notes` fields as "had to be added." The 20 detectable IDs are still untouched.
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
> ✅ **Told 2026-08-12 (session 8).** Message sent as planned — *IDs 0–19 and all 20 keys
> are untouched; only entries YOLO will never see were added.* Open since session 3, closed
> this session.

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

## ~~C4 — Thai prefix collisions will break naive matching~~ ✅ CLOSED

> ✅ **Closed 2026-08-08 (session 6, Week 5).** `nlp/extract.py::extract()` implemented for
> real. Detail below kept because Weeks 11–12 need the reasoning, and because this concern's
> "next action" turned out to name the wrong fix.
>
> **The root cause was not what this concern originally diagnosed.** The prescribed fix —
> sort synonyms by length descending, then first-match-wins — assumes matching happens
> against the raw string. It doesn't: `extract()` tokenizes with PyThaiNLP first, and
> **PyThaiNLP's default tokenizer destroys the evidence before any synonym list is ever
> consulted.** Confirmed directly: `word_tokenize("ไม่เอาน้ำมันหอย")` with no custom
> dictionary returns `['ไม่', 'เอา', 'น้ำมัน', 'หอย']` — "น้ำมันหอย" is already split into
> "น้ำมัน" + "หอย" by the tokenizer itself, so no amount of synonym-sorting downstream can
> recover it. The actual fix is a `pythainlp.util.Trie` built from every dictionary synonym,
> passed as `custom_dict` to `word_tokenize()`, so compounds survive as single tokens.
> Verified live before and after: `น้ำมันหอย` and `คลีน` (this project's own worked example,
> `Claude.md:122`, also silently breaks under the default tokenizer) both stay whole with
> the custom dict; nothing that was already correct (`พริกไทย`, `กุ้งแห้ง`, `น้ำปลา`) got
> disturbed.
>
> **A full audit found 56 collision pairs, not the 11 documented below** — including 18
> English pairs (`egg`/`eggplant`, `fish`/`fish sauce`, `onion`/`green onion`, …) this
> concern never considered, and several more Thai pairs from the curry-paste synonyms added
> while writing `recipes.json` (`พริกแกงเขียวหวาน`/`พริก`, `พริกแกงกะหรี่`/`พริก`, …). All 56
> resolve correctly under the tokenizer fix; representative cases from the audit are now
> pinned in `tests/test_extract.py`'s `COLLISION_CASES`, not just the four originally named
> here.
>
> **Four pairs this concern listed were never real collisions.** `มะเขือ-`, `ถั่ว-`,
> `มันฝรั่ง`/`มันเทศ`, and `หอมใหญ่`/`ต้นหอม` are *sibling* prefixes — neither is a substring
> of the other, since no bare `มะเขือ`/`ถั่ว`/`มัน`/`หอม` synonym exists in the dictionary.
> Longest-match-first was never going to break on these; they're a risk for *fuzzy*
> matching instead, where a loose similarity threshold could conflate look-alikes. They now
> have their own test category (`SIBLING_CASES`) rather than living inside the collision
> table, because they're a different bug with a different fix (the fuzzy cutoff, not
> tokenization).
>
> **New, smaller finding, flagged not fixed:** `sour_curry_paste`'s synonym list includes
> `พริกแกงเหลือง`/`น้ำพริกแกงเหลือง`, which in common Thai usage names the *yellow* curry
> paste, not sour — `yellow_curry_paste` separately claims `พริกแกงกะหรี่`. Possibly a
> mis-assignment from when the curry-paste entries were added while writing `recipes.json`.
> Left as-is per instruction — neither ingredient is camera-detectable, both are seasonings,
> and fixing `ingredients.json` mid-NLP-work would mix two unrelated changes in one commit.
> Worth a look before the report is written.

**Original entry follows.**

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

**Updated again 2026-08-08 (session 5): the dictionary is now 69 entries (20 detectable +
49 text-only), not 60.** The 9 added since (mostly seasonings pulled in while writing
`recipes.json`, e.g. `yellow_curry_paste`, `sour_curry_paste`) have **not** been audited
for new collisions the way the table below was. Whoever implements the Week 5 matcher
should re-run the collision check against the current 69, not against this table alone —
the longest-match-first fix covers unknown future collisions structurally, but the test
cases below were written against the 60-entry snapshot and may not be exhaustive anymore.

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

**Next action:** ~~In Week 5, sort synonyms by length descending before matching, so the
longest candidate is tried first. Add tests asserting "พริกหวาน" → bell_pepper,
"กะหล่ำดอก" → cauliflower, "พริกไทย" → pepper, and "น้ำมันหอย" → oyster_sauce. Write those
tests before the matcher.~~ Done, but the actual fix was a custom tokenizer dictionary, not
just sort order — see the closure note above.

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

## ~~C7 — `rapidfuzz` and `pyyaml` are missing from requirements.txt~~ ✅ CLOSED

> ✅ **Closed 2026-08-08 (session 5).** Both added to `requirements.txt`
> (`rapidfuzz>=3.0.0` under NLP, `pyyaml>=6.0` under a new "Chat system (Week 8)" block).
> `pip install -r requirements.txt` verified clean on this machine (rapidfuzz 3.14.5,
> pyyaml 6.0.2 resolved), and `pytest tests/ -q` still 53 passed afterward.
>
> **A related gap surfaced while closing this one, not fixed here:** `requests` is
> imported by `tools/thaifcd.py` but declared in neither `requirements.txt` nor
> `tools/requirements-dev.txt`. Filed as **C16** below rather than folded into this entry,
> since it's a different file and a different owner-facing risk (the nutrition tool, not
> the chatbot).

**Original entry follows.**

> 🟢 **Low** · **Impacts: Week 5 and Week 8** · Owner: You

- `rapidfuzz` — fuzzy matching for typos, required by Week 5 (`Claude.md:442`)
- `pyyaml` — needed to read `thresholds.yaml` from Person 1 in Week 8 (`Claude.md:523`)

Minor, but it means `pip install -r requirements.txt` on a fresh machine does not produce
a working environment — which matters when Person 1 clones the repo.

**Next action:** ~~Add both when you next touch `requirements.txt`. No rush, but do it
before Week 5.~~ Done.

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
- ~~**C15** — The keto tag is true of the dish and misleading about the meal~~ → ✅ **CLOSED 2026-09-15**

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

> **Update 2026-08-08:** 3 recipes spot-checked against the *live* Thai FCD site
> (`th_001`, `th_010`, `th_031` — all `direct`), not just the committed cache. All three
> scaled-to-serving values matched the recipe's `nutrition` block exactly, and matched the
> cached values in `data/thaifcd_cache.json` exactly — no drift between source, cache, and
> recipe. This verifies the `direct` two-thirds of the database; it says nothing about the
> `computed` third, where the concern below still applies in full — the gram amounts are
> still ours, not INMU's, no matter how faithfully the arithmetic runs.

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

## ~~C15 — The keto tag is true of the dish and misleading about the meal~~ ✅ CLOSED

> ✅ **Closed 2026-09-15.** Fixed in `api/main.py`'s `format_reply()`: when a dish is
> `keto`-tagged **and** the user's message specifically requested `keto`
> (`parsed["health_tags"]` from `extract()`, threaded through as `format_reply()`'s new
> `requested_health_tags` parameter), the reply now shows a `🏷️ คีโต (ไม่รวมข้าว)` line
> for that dish. If the user never asked for keto, no tag line is shown at all — a dish
> being incidentally keto isn't noise an unrelated user needs to see. `recommend()` and
> `HEALTH_TAGS.md`'s keto rule were deliberately left untouched, per the 2026-08-10
> decision below — the tagging logic is correct for what it measures; only the display
> layer needed the qualifier. Verified end-to-end: `"มีไข่ อยากกินคีโต"` shows the
> qualifier on all 3 resulting keto dishes; `"มีไข่"` alone (same ingredient, no keto
> request) shows none, even though the same dishes remain genuinely keto-tagged. All 88
> tests still pass — no test pinned `format_reply()`'s output text, so nothing else
> needed updating.

> **Update 2026-10-05 — the fix was lost in `1c8af19` and has been restored in the web layer.**
> The 2026-09-15 fix lived in `api/main.py`'s `format_reply()`, which is the LINE reply path.
> Commit `1c8af19` (2026-09-26, LINE code removal) replaced `format_reply()` and dropped the logic
> (no `requested_health_tags` and no "ไม่รวมข้าว" in `api/main.py` at that commit or at HEAD), and the
> web app never used `format_reply()`. So for the web app C15 was open again: a keto-tagged card showed a
> plain "keto" even when the user never asked for keto. Restored in the web UI: `web/js/logic.js`
> (`shouldShowKetoCaveat()`, `KETO_CAVEAT_LABEL`, `buildCard(..., requestedTags)` -> `ketoCaveat`),
> `web/js/app.js` (`renderCard()` shows "คีโต (ไม่รวมข้าว)" in place of "keto" on that card only;
> `recommendPage()` passes the server's `resp.used.health_tags`) and `web/tests/logic.test.js`. Same rule
> as 2026-09-15: the qualifier appears only when the dish is `keto`-tagged AND keto is among the health tags
> the user currently wants. `recommend()`, `nlp/extract.py` and the tagging rules are untouched.
> Related client/server mismatch, deliberately not changed here: the client accumulates health tags
> (`L.unionInOrder` at `web/js/app.js:643` and `:758`) while the server replaces them
> (`api/state.py`, `SessionState.apply_text_result`), so after "keto" then "vegan" the "เงื่อนไข" chips can
> still list keto although recommend() filtered on vegan only. The caveat reads the server's
> `used.health_tags` (`api/app.py` `/recommend`), so it is not affected.
> **Update 2026-10-05 (later) — the client/server health-tag mismatch above is resolved.**
> `web/js/logic.js` now has `nextHealthTags(current, incoming)`, which applies the server's rule (replace
> with the latest parse that mentions a tag, otherwise keep). `web/js/app.js` uses it where `/extract` and
> `/extract_bert` answers are merged (only that message's tags come back), and takes `/correct`'s answer
> as it is (that response carries the session's current tags). `L.unionInOrder` is unchanged and still
> used for ingredients. Tests: `web/tests/logic.test.js` ("nextHealthTags: ..."). Remaining difference, not
> changed because resets were left alone: after a finished round the server clears the tags on the next
> input (`start_new_round()`), while the client clears `S.healthTags` only on "start over", so a tag-less
> message in a new round can still show the previous round's chip.

**Original entry follows.**

> **Update 2026-08-10 (Week 7 session):** Decided — deferred to Week 8, not handled in
> `recommend()`. The recommender passes `health_tags` through on every result unchanged
> (a new, additive field on the frozen interface — `tests/test_contract.py`'s
> `issubset` check stays valid), so Week 8's `format_reply()` has what it needs to render
> "keto (ไม่รวมข้าว)" without re-reading `recipes.json`. `recommend()` itself does not
> qualify, reweight, or otherwise treat keto specially — display wording belongs in the
> template, not the scorer. Still open until Week 8 actually writes that wording; tracked
> there now, not here.

> **Update 2026-09-15 (recommender verification pass):** Confirmed still open, checked
> directly against the real code — `api/main.py`'s `format_reply()` never reads
> `dish["health_tags"]` anywhere (grepped the whole file). No "(ไม่รวมข้าว)" wording, no
> keto qualification, nothing. **This is a required Week 8 deliverable, not optional
> polish or a nice-to-have wording tweak** — until it's implemented, the bot will tell a
> user a dish is "keto" while it's actually served with ~60g of carbohydrate from rice,
> a health claim about the meal that is false as delivered even though the underlying
> per-dish number is correct. That gap is exactly what this concern exists to prevent
> shipping silently.

> 🟡 **Medium** · **Impacts: Week 8 (format_reply, required not optional), Weeks 11–12
> (report)** · Owner: You

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

**Next action:** already decided (2026-08-10 update above) — qualify the tag in Week 8's
`format_reply()` reply template (e.g. "keto (ไม่รวมข้าว)"), not by retagging
`recipes.json`. `recommend()` and `HEALTH_TAGS.md`'s keto rule stay as-is; this is
display-layer work only, and it's part of Week 8's checklist, not a separate optional
task. It needs a sentence in the report either way. The underlying point is a good one to
make regardless: a health tag is meaningless without a stated portion, and portion
conventions are exactly where a nutrition database quietly encodes an assumption.

---

# Closed

Don't delete closed concerns — the reasoning is worth keeping, and Weeks 11–12 need it for
the report.

| ID | Raised | Closed | Resolution |
|---|---|---|---|
| C3 | Week 1 | 2026-08-05 (Week 2) | PyThaiNLP 5.3.5 verified working on Python 3.13.2; no fallback venv needed |
| C1 | Week 1 | 2026-08-05 (Week 3) | Two-tier dictionary (Option A): originally 40 text-only entries with `yolo_class_id: null` (now 49 — grew during recipe-DB work, see C4), 20 detectable untouched. 4 tests relaxed, 2 stricter ones added. **Person 1 not yet told** |
| C5 | Week 1 | 2026-08-05 (Week 3) | `git init` + 3 commits + verbatim AGPL-3.0 `LICENSE`. `.env` verified excluded before first commit. Public push + README still outstanding |
| C12 | Week 3 | 2026-08-05 (Week 3) | broccoli via USDA FDC 170379 in `data/external_nutrition.json`, converted onto Thai FCD's available-carbohydrate basis; onion needed no source, appearing only in direct recipes |
| C13 | Week 3 | 2026-08-05 (Week 3) | `data/recipes.json` written; 53 tests passing |
| C7 | Week 1 | 2026-08-08 (session 5) | `rapidfuzz` and `pyyaml` added to `requirements.txt`; both installed and verified clean |
| C4 | Week 1 | 2026-08-08 (session 6) | Real fix was a `pythainlp.util.Trie` custom dictionary, not sort order — the tokenizer was destroying compounds before matching ever ran. Full 56-pair audit in `tests/test_extract.py`; 4 originally-listed "collisions" reclassified as non-colliding siblings |

---

# ------- Week 4 (session 4, 2026-08-08) -------

Nothing new opened. One verification note added to C14 above (live spot-check of 3
`direct` recipes against the Thai FCD site — all exact). No concerns closed; C14 and C15
still stand as written, since the spot-check only covers the `direct` two-thirds.

Also worth a line even though it isn't a project concern: `Claude.md`'s working copy had
picked up an accidental full duplication of its own content (552 → 1656 lines, no new
information) sometime between session 3 and this one. Discarded with `git checkout --
Claude.md`; nothing was lost, since the committed version was the correct, non-duplicated
one throughout.

---

# ------- Week 5 prep (session 5, 2026-08-08) -------

A readiness check for Week 5 (NLP extraction) surfaced three things worth fixing before
the real build starts, none of them the NLP work itself:

- **C7 closed** — see the closed table above.
- **New: C16** — `requests` is imported by `tools/thaifcd.py` but declared in neither
  `requirements.txt` nor `tools/requirements-dev.txt`. It only works locally because it
  happens to already be installed.
- **Count drift fixed** — `data/ingredients.json` had grown from the documented 60 entries
  to 69 (49 text-only, not 40) without concern.md being updated; C1's and C4's entries
  above now say so. The extra 9 are legitimate additions made while writing
  `recipes.json` (e.g. `yellow_curry_paste`, `sour_curry_paste`), not corruption, but the
  Week 5 collision audit in C4 needs re-running against the real 69, not the stale 60.

**Confirmed still not ready to start the actual Week 5 build:** `nlp/extract.py::extract()`
remains a pure mock (`STATUS: MOCK (Week 1-2 skeleton)` in its own docstring) that ignores
its input entirely — zero tokenization, matching, or negation logic exists yet. That is
expected; it *is* the Week 5 task, not a gap in it.

## C16 — `requests` is used by a tool script but declared nowhere

> 🟢 **Low** · **Impacts: anytime someone else re-runs `tools/thaifcd.py`** · Owner: You

`tools/thaifcd.py` does `import requests` unconditionally, but neither `requirements.txt`
nor `tools/requirements-dev.txt` lists it — only `pypdf` is declared there. It has worked
on this machine throughout because `requests` happens to already be installed (it's a
transitive dependency of `line-bot-sdk`), so the gap has been invisible.

Low severity because the chatbot itself never imports `tools/`, so this can't break the
bot. It would only bite someone following `tools/requirements-dev.txt`'s own header
instruction (`pip install -r tools/requirements-dev.txt`) on a machine where nothing else
happened to pull `requests` in first — most plausibly Person 1, if they ever needed to
re-run or extend the nutrition tool.

**Next action:** add `requests>=2.32.0` to `tools/requirements-dev.txt` next time that
file is touched. Not urgent enough to justify a solo edit for one line.

---

# ------- Week 5 (session 6, 2026-08-08) -------

`nlp/extract.py::extract()` implemented for real — no longer the mock. **C4 closed** (see
above; the real fix was a tokenizer-level custom dictionary, not the sort-order fix this
concern originally prescribed). New files: `tests/test_extract.py` (correctness tests,
separate from `test_contract.py`'s shape tests), `data/health_terms.json` (Thai/English
diet-tag vocabulary — did not exist anywhere before this session), `data/nlp_dev_set.json`
(22 sentences, mine to tune, Person 1's test set untouched). `recommender/` and `api/` not
touched. All 53 prior tests plus 16 new ones pass (69 total).

> ⚠️ **Correction, same session:** this section originally said "85 total" — an
> arithmetic error caught while writing up the session (69 prior + 16 new was miscounted
> as 69+16; the real prior count was 53, not 69). Confirmed by re-running
> `python -m pytest tests/ -q`, which prints 69. The commit message for `09f210e` repeats
> the same wrong number and was not amended — new commits are preferred over rewriting
> history here, and the number is corrected in the places anyone will actually read next
> (this file, the Summarization entry).

**Two design decisions made this session, both driven by evidence gathered during
planning, not by preference:**

- **เจ → `vegan`**, accepted only inside the compound phrases `กินเจ`/`อาหารเจ`, never as a
  bare `เจ` synonym — `เจ` alone is a substring of ordinary words (`เจอ`, `เจ็ด`) and would
  false-positive constantly. Both compounds already tokenize as single tokens under
  PyThaiNLP's own default dictionary, confirmed directly, so no custom-dict entry was even
  needed for them specifically. เจ excludes alliums where this project's `vegan` tag does
  not, so the mapping is a deliberate slight over-match, documented inline in
  `health_terms.json`.
- **Thai typo recovery via rapidfuzz is a documented gap, not a solved problem.** English
  typos recover reliably (`"chiken"` → `"chicken"`, 92% similarity). Thai typos mostly do
  not, because a misspelled Thai word is rarely in the custom dictionary, so the tokenizer
  shatters it into syllable fragments *before* rapidfuzz ever sees it — confirmed directly:
  `"มะเขือเทดด้วย"` (typo of `มะเขือเทศ`) tokenizes to `['มี', 'มะเขือ', 'เท', 'ด', 'ด้วย']`,
  and the surviving `มะเขือ` fragment scores only 80% against the correct synonym — below
  the 85% cutoff `extract.py` uses. A looser cutoff was tried during planning and rejected:
  at 60%, unrelated short tokens started matching real synonyms by accident (`กระ` →
  `กระเพรา` at 60%). Missing a Thai typo is an acceptable, tested-for outcome
  (`tests/test_extract.py::test_thai_typo_recovery_is_a_known_gap_not_a_silent_wrong_answer`);
  inventing a wrong ingredient from an unrelated token is not, and the test suite protects
  the boundary between the two rather than the accuracy number.

**Also found and flagged, not fixed** (per instruction — a data-file edit deserves its own
commit, not one bundled into NLP work): `sour_curry_paste` in `ingredients.json` likely
carries a curry-paste name (`พริกแกงเหลือง`) that actually names yellow curry paste, not
sour. See C4's closure note for detail.

---

*Last updated: 2026-08-08 (session 6). Week 5's real task — `nlp/extract.py::extract()` —
is now implemented and tested (69 tests passing). C4 closed. Still outstanding: Week 2
photo shoot (batch_B), telling Person 1 about the C1 schema change, the suspected
`sour_curry_paste`/`พริกแกงเหลือง` mis-assignment, and everything from Week 6 on.*

---

# ------- Week 7 (session 7, 2026-08-10) -------

`recommender/recommend.py::recommend()` implemented for real — no longer the Week 1–2
mock. TF-IDF + cosine similarity via scikit-learn over `data/recipes.json`'s 40 recipes,
health-tag and excluded-ingredient filtering applied *before* scoring. New files:
`tests/test_recommend.py` (15 correctness tests), `data/recommender_dev_set.json` (8 cases,
own dev set — Person 1's Week 10 test set untouched), `tools/run_recommender_dev_set.py`
(pass/fail runner, deliberately not a Precision@3 claim — see that file's own docstring for
why). `nlp/`, `data/ingredients.json`, `data/recipes.json` untouched.

**Readiness check confirmed all three prerequisites clean before starting:** every
ingredient key referenced by all 40 recipes resolves against `ingredients.json` (0 unknown
keys); `main_ingredients`/`optional_ingredients` contain zero `is_seasoning: true` entries
and `seasonings` contains only them; `extract()`'s three keys need no adapter and were
already wired straight through by `api/main.py:344`.

**Three design decisions made this session, confirmed with you before coding (not solo
judgement calls):**

- **C15 (keto/rice) deferred to Week 8**, not handled here. See C15's own update above.
  `recommend()` passes `health_tags` through unchanged as a new field on every result.
- **An excluded ingredient only drops a dish via `main_ingredients` or `seasonings`.** An
  excluded ingredient sitting only in `optional_ingredients` does not disqualify the dish —
  an optional is omittable by definition. Verified against real data: excluding
  `green_onion` (optional-only in `th_001`, absent entirely from `th_002`) keeps both
  dishes in the results, and neither falsely reports having an ingredient the user didn't
  supply.
- **Pure TF-IDF cosine, no blended coverage term.** Exactly `Claude.md:451-474`'s spec —
  no invented weighting to defend in the report.

### Two implementation details worth recording

**Seasonings are stripped twice, not once.** `Claude.md:427` says basic seasonings must not
affect matching. This is enforced on both sides of the scoring: a recipe's `seasonings`
list is never part of its TF-IDF document (so a recipe doesn't get "more fish sauce" credit
for restating it), and the *user's* ingredient list has seasonings stripped before
vectorising (so typing "fish_sauce" cannot itself inflate a score). Tested directly —
`recommend(["chicken","garlic"])` and `recommend(["chicken","garlic","fish_sauce"])` return
identical ids and identical scores, not just an identical ranking.

**A float-epsilon guard was needed that wasn't anticipated in the plan.** `cosine_similarity`
can return values like `1.0000000000000002` from floating-point rounding in the dot
product, which would fail `test_score_is_a_number_between_zero_and_one`'s `0.0 <= score
<= 1.0` — a real, if rare, way for the frozen contract to break on data-dependent floating
point noise rather than logic. Scores are clamped into `[0.0, 1.0]` before rounding to 2dp.

### Two test-writing mistakes caught before commit, not after

Both were bugs in the *test*, not the code — same discipline as session 6's C4 finding
("verify the fixture assumption directly, don't assume it"):

1. `test_health_tags_are_ANDed_not_ORed` originally assumed no recipe in the database is
   tagged both `vegan` and `keto`, and asserted `recommend(["chicken"], health_tags=
   ["vegan","keto"]) == []` on that basis. False — `th_036` and `th_037` are tagged both.
   The assertion passed anyway by coincidence (no vegan dish contains chicken regardless of
   the keto filter), which would have hidden a real OR-instead-of-AND bug. Rewritten to
   isolate the AND behaviour directly: `th_004` is vegan but not keto (potato is a starch
   staple, disqualified per `HEALTH_TAGS.md` regardless of its carb count), so querying
   `vegan` alone must surface it and `vegan`+`keto` together must not.
2. `test_excluded_for_is_respected_even_if_health_tags_were_mistagged` looped over *every*
   recipe using its own `excluded_for` as the query, including recipes whose `excluded_for`
   is `[]` — an empty filter list applies no filter at all, so it trivially "passed" for
   those without testing anything. Restricted to recipes with a non-empty `excluded_for`.

### Verification

```
$ python -m pytest tests/ -q
................................................................................ [100%]
84 passed in 4.59s
```
53 (Week 3) + 16 (Week 5, `test_extract.py`) + 15 (Week 7, `test_recommend.py`) = 84 —
re-derived from a fresh run at write time, not carried over from mid-session, per session
6's own corrective note above.

```
$ python tools/run_recommender_dev_set.py
...
8/8 dev cases passed
```

```
$ python -c "from api.main import handle_user_input; print(handle_user_input('มีไก่กับไข่ อยากกินคลีน ไม่เอาพริก'))"
🍳 เมนูแนะนำสำหรับคุณ
1. ไข่ต้ม     ✅ มีแล้ว: egg          📊 69.0 kcal | ...
2. ไข่ตุ๋น     ✅ มีแล้ว: egg          📊 92.0 kcal | ...
3. ผัดเผ็ดไก่  ✅ มีแล้ว: chicken     📊 200.0 kcal | ...
```
Full path — `extract()` → `recommend()` → `format_reply()` — with zero mocks anywhere,
correctly excluding chili-containing dishes per the sentence's own negation.

### Not fixed, not new — carried forward unchanged

Person 1 still not told about the C1 two-tier dictionary schema change (open since session
3), the suspected `sour_curry_paste`/`พริกแกงเหลือง` mis-assignment (C4's closure note), and
the Week 2 batch_B photo shoot (still not started, five sessions overdue). None of these
block Week 7 or Week 8.

**Priority for next session:** the same handoff note that's been ready for four sessions
now, then Week 8 (session buffer + debounce + reply-token strategy + Quick Reply +
`format_reply()`'s C15 keto/rice wording).

---

# ------- Week 8 prep (session 8, 2026-08-12) -------

## ~~Webhook silent-failure investigation — LINE OA received messages but sent no replies~~ ✅ CLOSED

> ✅ **Closed 2026-08-12 (session 8).** Root cause was **not application code** — a LINE OA
> platform setting.

The bot appeared completely silent: LINE OA showed messages as received, `POST /callback`
returned `200`, but no reply ever reached the user. Before any instrumentation existed,
this looked exactly like it could have been anywhere — Weeks 1–7 logic, the Flask app, the
LINE SDK, or the platform itself.

**Investigation order, cheapest-to-rule-out first:**

1. Added full observability instrumentation to `api/main.py` / `api/session.py` (no
   behavior change, committed separately as `1a836fe`): a `_log()` helper at every stage of
   callback → session → reply, explicit `_request_timeout=(5, 10)` on `reply_message`/
   `push_message` (the SDK's own default is no timeout at all), `first_seen`/`last_seen` on
   `Session`, and `logging.basicConfig` to surface the SDK's own log lines, not just this
   project's.
2. A signed dry-run confirmed `extract()` → `recommend()` → `format_reply()` was already
   correct **in-process**, before the instrumentation was even used to look at the live
   path — this ruled out five sessions of NLP/recommender work as the cause up front,
   rather than re-auditing it mid-investigation.
3. With logging enabled, the real signature appeared: `"callback: 0 event(s): []"`. The
   webhook *was* being hit (LINE always pings it, hence the `200`), but the events list
   was empty — the message itself never arrived in the payload.
4. Root cause: `manager.line.biz` → Response settings had **"Chat" response mode enabled**
   alongside "Webhook." "Chat" mode intercepts incoming user messages at the platform level
   and answers them through LINE's own auto-reply interface *before* they are ever
   forwarded to the registered webhook — so the app was never wrong, and never even saw
   the message.

**Fix:** disabled "Chat" in Response settings, confirmed "Webhook" stayed enabled. Zero
code changes.

**Confirmed live, real LINE app, zero mocks:** sent `"มีไก่กับไข่"` from a real phone,
server log reached `send_reply: reply OK`, LINE app received correct egg-based
recommendations with real nutrition data — same shape as session 7's in-process worked
example, this time over the actual production request path.

**Worth carrying forward:** this is a genuine "looked like a bug, wasn't" case for the
Weeks 11–12 report — the instrumentation that solved it stays committed (`1a836fe`)
because it's exactly what will make C11's slow-reply-token failure mode visible if it ever
fires for real, not a one-off debugging aid to strip out later.

---

# ------- Week 5 revisit (session 13, 2026-09-15) -------

## C17 — `confusable_with` field is documentation-only, not read by any code → ✅ noted, no fix needed

> A Week 5 NLP maintenance audit (dictionary grew 69 → 142 entries since Week 5; this
> pass checked whether `nlp/extract.py` and `data/nlp_dev_set.json` still held up)
> surfaced this while checking whether `lime`/`kaffir_lime_leaf` had a fuzzy-match risk
> flagged via `confusable_with`.

**Finding:** `data/ingredients.json`'s `confusable_with` field (added session 9,
alongside `category`) is **never read anywhere in the codebase** — grepped `nlp/`,
`tests/`, `tools/`, `recommender/`, `api/`, zero hits outside the data file itself. Its
original documented purpose (session 9's summary) was a *visual/naming-similarity
annotation*, likely intended for whoever labels YOLO training images (Person 1's side),
not an NLP fuzzy-match signal. It is currently populated for exactly one pair
(`eggplant`/`thai_eggplant`, mutual) plus one one-directional entry
(`amaranth`→`spinach`), and left empty (`[]`) everywhere else, including
`lime`/`kaffir_lime_leaf`.

**Why this matters:** a future session could reasonably assume setting
`confusable_with` on a pair would make `extract()` (or anything else) treat them more
cautiously. It would not — the field is inert. If that behavior is ever wanted, it needs
to be wired into `nlp/extract.py`'s resolution logic first (e.g. as an additional
fuzzy-match guard), not just populated in the data.

**Checked separately, the actual question that prompted this:** is there a real
fuzzy-match collision risk between `lime` and `kaffir_lime_leaf`? No —
`fuzz.ratio('มะนาว', 'มะกรูด')` = 36.4, `fuzz.ratio('lime', 'kaffir lime leaf')` = 40.0,
both far below the module's 85 cutoff. This holds regardless of `confusable_with`.

**Severity:** 🟢 Low. **Impacts:** anytime a future session touches `category`/
`confusable_with` or adds a new ingredient. **Next action:** none required — this entry
exists so nobody spends time wiring up or debugging a field that was never meant to be
functional yet, and either builds it out deliberately (extract.py + tests) or drops it,
rather than assuming it already does something.

## Same audit, everything else — confirmed clean, no new concerns raised

- **Stale dev-set keys**: none. All 22 pre-existing `nlp_dev_set.json` cases still pass
  against the current 142-entry dictionary.
- **New collision risk** (17 prefix-collision groups spanning ถั่ว/เห็ด/ผัก/ใบ/มะ/เนื้อ/มัน/
  มะเขือ/หอย/หอม/กะ/ปลา-ปลาหมึก/ฟัก/หัว/พริก/หน่อไม้/กระ/ไข่ไก่, including the two
  HIGH RISK shapes — พริก vs พริกหวาน, matching the original C4 bug's exact shape, and
  ไข่ไก่ must-not-split-into-ไข่+ไก่): all verified live via `extract()`, isolated and
  combined. **Zero collisions found.** The Trie-based longest-match tokenization (C4's
  fix) is handling all of it correctly.
- **Coverage gap**: real — 80 of 83 ingredients added since Week 5 had zero dev-set
  coverage. Closed for the 7 highest-risk ones (`pla_ra`, `yanang`, `sour_curry_paste`,
  `yellow_curry_paste`, `quail_egg`, `king_oyster`, `white_oyster`) by adding 5 new cases
  to `data/nlp_dev_set.json` this session (22 → 27), each verified against live
  `extract()` before being added. 73 newer ingredients remain uncovered — not addressed
  this session, no urgency identified.
- **Thai typo recovery**: still weak, confirmed still reproducible
  (`"มีมะเขือเทดด้วย"` still fails to recover มะเขือเทศ/tomato) — unchanged documented
  limitation, not touched.
- **เจ → vegan over-matching**: still doesn't exclude alliums (garlic/onion), confirmed
  live — unchanged documented limitation, already self-disclosed in
  `data/health_terms.json`, not touched.

`nlp/extract.py` itself was not modified — no bug was found in it.

---

# ------- Week 8 revisit (session 14, 2026-09-16) -------

## C18 — process_session()'s confirmation-flow wiring has zero automated test coverage

> Raised during a sanity check of the confirm-before-recommending flow (shipped earlier
> this session, `53392a5`). The check itself confirmed the flow is complete and correct
> (free-text additions work, all three PendingConfirmation fields merge correctly, and
> button-tap/typed-confirm/timeout/prompt-cap-hit all four converge on `_finalize()` with
> the fully merged data) — this is the one gap it found, not a bug.

**Finding:** `api/confirmation.py` itself is well-covered — 23 tests in
`tests/test_confirmation.py`, exercising `merge`/`resolve`/timeout/the resolve-timeout
race/multi-user isolation, all in isolation from Flask/LINE. But **`api/main.py`'s own
wiring has no automated tests at all** — grepped `tests/` directly, nothing references
`process_session`, `_finalize`, `_confirmation_prompt`, or `_on_confirmation_timeout`.
The three-way branch in `process_session()` (fresh request / user confirmed / user added
more), the "new photos override a coincidental confirmation-phrase text match" tie-break,
and the connection from `confirmation`'s resolved state into the actual
`recommend()`/`format_reply()` calls were verified only once, by hand, in a throwaway
terminal script during implementation — never captured as a permanent test.

**Why this matters:** a future change to this branching logic — most likely the deferred
low-confidence-verification feature ("is this really onion?"), which will almost
certainly need to touch `process_session()`'s same branch structure — could silently
break the confirm/merge/finalize wiring, and `pytest tests/` would still show fully green.
This is exactly the kind of regression this project's testing discipline elsewhere is
built to catch (see `tests/test_session.py`'s equivalent coverage of `session.py`'s own
debounce/flush wiring) — `api/main.py`'s confirmation branching is the one piece of this
subsystem that doesn't yet have that safety net.

**Next action:** write `tests/test_main.py` (or similar) covering `process_session()`'s
three branches end-to-end with a fake/stubbed `send_reply()` (mirroring how
`test_session.py`'s `collect_flushes()` and `test_confirmation.py`'s `collect_timeouts()`
substitute a recording function for the real side-effecting one), before or alongside
whatever change next touches this code — not deferred indefinitely. Not written now, by
explicit instruction; this entry exists so it isn't forgotten.

> 🟡 **Medium** · **Impacts: next time `process_session()` is touched (likely the deferred
> low-confidence-verification feature)** · Owner: You

---

# ------- Recipe DB round 4 (2026-09-20) -------

## C19 — No dictionary key distinguishes vegetarian/vegan (เจ) curry pastes from regular ones

> Found while sourcing round-4 recipes: แกงเหลืองถั่วงอกหัวโต เจ (a vegetarian yellow curry
> with giant bean sprouts, Cookpad 15637807) had to be dropped because of this. Logged here,
> not in `data/RECIPES_NOTES.md`, because it is a **dictionary schema gap**, not a per-recipe
> judgement call. A future-improvement note only — nothing was changed.

**Finding:** `data/ingredients.json` has exactly one key per curry paste, and every one of
them is flagged `is_animal_product: true` (they normally contain shrimp paste):
`green_curry_paste`, `red_curry_paste`, `yellow_curry_paste`, `massaman_curry_paste`,
`sour_curry_paste`, and also `chili_paste` (น้ำพริกเผา). There is no separate key (or field)
for the vegetarian/vegan (เจ / มังสวิรัติ) versions of these pastes, which are widely sold and
cooked in Thailand.

**Why it matters:** the vegetarian/vegan rules are derived mechanically from
`is_animal_product` (`tools/derive_diet_tags.py`, `tests/test_recipes.py`). So a genuinely
vegetarian/vegan curry that uses one of these pastes is automatically tagged
`excluded_for: [vegetarian, vegan]` — a **false-negative exclusion**: a vegetarian user asking
for such a dish will never be offered it. The mechanical tests also *forbid* correcting it by
hand (`test_no_animal_products_means_vegan_is_not_excluded` runs the other way, and the
forward tests demand the exclusion whenever an animal-flagged key is present).

**The opposite-direction gap is related:** an animal ingredient with NO dictionary key (a
chicken stock cube, bouillon) produces a *false-positive* vegan tag. Round 4 handled that
case by dropping the dish (ซุปถั่วงอกหัวโต), by explicit decision: a mechanically-honest but
actually-wrong vegan tag is not acceptable. The curry-paste gap is the mirror image and has no
such workaround, since the paste key exists but is the wrong one.

**Possible fixes (not chosen, for a future session):**
- add vegetarian-variant keys (e.g. `red_curry_paste_vegetarian`, `is_animal_product: false`)
  with matching Thai synonyms (พริกแกงเจ, พริกแกงมังสวิรัติ) so `extract()` can route to them;
- or add an optional `vegetarian_variant` field to the paste entries that recipes can select;
- either way `HEALTH_TAGS.md` and the two tag tests would need to allow the variant.

**Severity:** 🟢 Low for the current 369-recipe database (no shipped recipe is affected; the
one known case was dropped) · **Impacts: any future vegetarian/vegan curry recipe, and NLP
matching of เจ paste terms** · Owner: You
