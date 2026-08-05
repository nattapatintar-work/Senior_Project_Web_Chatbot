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

- **C1** — Dictionary can't hold seasonings/aromatics, and 4 tests forbid adding them → 🔴 **impacts Week 3–4**
- **C2** — 20 classes ≈ 4,000 instances to label, not 3,000 → 🟡 **impacts Week 3–4**
- ~~**C3** — PyThaiNLP unverified on Python 3.13~~ → ✅ **CLOSED 2026-08-05**
- **C4** — Thai prefix collisions break naive matching → 🟡 **impacts Week 5**
- **C5** — No git repo; AGPL-3.0 obligation unmet → 🟡 **impacts ongoing** *(partly addressed: `.gitignore` now exists)*
- **C6** — ปวยเล้ง synonym is my guess, not your decision → 🟢 **impacts Week 2**
- **C7** — `rapidfuzz` / `pyyaml` missing from requirements → 🟢 **impacts Week 5, 8**
- **C8** — cp874 encoding crash will recur on Person 1's PC → 🟢 **impacts anytime**

---

## C1 — The dictionary has no room for ingredients YOLO can't see

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

**Next action:** Decide A or B with Person 1 **before** starting recipe entry in Week 3.
Doing it after 40 recipes are written means editing all 40.

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

A first-match-wins loop over the synonym lists gets these wrong, and the failure is silent
— the user asks for bell pepper and the bot recommends a chili dish. Nothing crashes, so
no test catches it unless one is written for it.

**Next action:** In Week 5, sort synonyms by length **descending** before matching, so the
longest candidate is tried first. Add a test asserting `"พริกหวาน" → bell_pepper` and
`"กะหล่ำดอก" → cauliflower`. Write that test *before* the matcher.

---

## C5 — No git repo, and AGPL-3.0 is a real obligation

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

# Closed

Don't delete closed concerns — the reasoning is worth keeping, and Weeks 11–12 need it for
the report.

| ID | Raised | Closed | Resolution |
|---|---|---|---|
| C3 | Week 1 | 2026-08-05 (Week 2) | PyThaiNLP 5.3.5 verified working on Python 3.13.2; no fallback venv needed |

---

*Last updated: 2026-08-05, after Week 2 (LINE webhook).*
