# My Side: Architecture Overview (Person 2 — Language & System)

> **What this document is.** A map of *my half* of the Ingredient-to-Recipe chatbot — every folder,
> every file, every function, and the method behind each one, written for someone new to coding
> and AI. Person 1's half (`cv/`, `llm/`, `eval/`, the training data, `config/thresholds.yaml`) is
> **deliberately not documented here**. Where my code touches theirs, I note that a dependency
> exists and stop there.
>
> Everything below was written by reading the actual source files, not by guessing from names.

---

## In-scope files and their one-line role

| Path | Role | Status |
|---|---|---|
| `nlp/extract.py` | Turns a free-text Thai sentence into structured `{ingredients, health_tags, excluded}` | ✅ Real (Week 5) |
| `recommender/recommend.py` | Scores the 40 recipes against what the user has, returns the Top-3 | ✅ Real (Week 7) |
| `api/main.py` | The LINE webhook: receives messages, runs the pipeline, sends the reply | ✅ Real plumbing |
| `api/session.py` | Groups messages sent in one burst into a single request (debounce) | ✅ Real |
| `api/config.py` | Loads LINE credentials from `.env` and refuses to start if they're missing | ✅ Real |
| `api/mock_cv.py` | Fake stand-in for Person 1's YOLO detector | 🚧 **STILL A MOCK** |
| `data/ingredients.json` | The central dictionary — 69 ingredients, their Thai synonyms and flags | ✅ Locked |
| `data/recipes.json` | The recipe database — 40 dishes with real sourced nutrition | ✅ Complete |
| `data/health_terms.json` | Vocabulary for detecting a diet from what the user *types* | ✅ Real |

### Two things the brief expected that do not exist yet

- **`data/test_b/batch_B/`** — there is no `data/test_b/` directory in the repo at all. The Week 2
  checklist item *"batch_B fully shot (30 images) + metadata logged"* is still unchecked in
  `Claude.md`. There is therefore no metadata schema to document. **Not yet created.**
- **`interface.md`** — no such file exists anywhere in the repo. The contract my functions must
  honour is enforced instead by **`tests/test_contract.py`**, which is the file I treat as the
  frozen agreement throughout this document.

---

## How my part fits into the whole pipeline

```
        User sends a photo and/or types a message on LINE
                              |
                              v
      ┌───────────────────────────────────────────────┐
      │  api/main.py  ::  POST /callback               │   ← MINE
      │  verify signature → return HTTP 200 instantly  │
      └───────────────────────────────────────────────┘
                              |
      ┌───────────────────────────────────────────────┐
      │  api/session.py — buffer + wait 2.5s           │   ← MINE
      │  (so a photo and its caption arrive together)  │
      └───────────────────────────────────────────────┘
                              |
              ┌───────────────┴───────────────┐
              |                               |
          [ photo ]                       [ text ]
              |                               |
   ╔══════════════════════╗        ┌────────────────────────┐
   ║ detect()             ║        │ nlp/extract.py         │  ← MINE
   ║ PERSON 1 — OUT OF    ║        │ Thai text → structure  │
   ║ SCOPE.               ║        └────────────────────────┘
   ║ Currently faked by   ║                    |
   ║ api/mock_cv.py 🚧    ║                    |
   ╚══════════════════════╝                    |
              |                                |
              └───────────────┬────────────────┘
                              v
      ┌───────────────────────────────────────────────┐
      │ api/main.py :: handle_user_input()             │  ← MINE
      │ merge photo ingredients + text ingredients     │
      └───────────────────────────────────────────────┘
                              |
      ┌───────────────────────────────────────────────┐
      │ recommender/recommend.py                       │  ← MINE
      │ TF-IDF + cosine + health filter → Top-3        │
      └───────────────────────────────────────────────┘
                              |
      ┌───────────────────────────────────────────────┐
      │ api/main.py :: format_reply() → send_reply()   │  ← MINE
      │ template text → LINE reply token (free)        │
      └───────────────────────────────────────────────┘
```

In one sentence: **I own everything except the box that looks at the picture.**

### ⚠️ Where my code depends on Person 1's

There is exactly **one** such point, and it is still faked:

| What | Where | State |
|---|---|---|
| `detect(image_path)` — find ingredients in a photo | called at `api/main.py:284` | 🚧 **Mocked** by `api/mock_cv.py`. Person 1 delivers the real one in Week 8 (Handoff #3). |
| `config/thresholds.yaml` — the confidence cutoff | **not read by my code at all yet** | The cutoff is currently the hardcoded constant `CONFIDENCE_THRESHOLD = 0.5` at `api/main.py:85`. Wiring the YAML in is still to do. |

The mock already returns the **agreed shape** — `[{"ingredient": str, "confidence": float}]` — so
Week 9 should be a one-line import swap, not a rewrite. That was the whole point of building the
mock instead of waiting.

---

# nlp/

## Role in the pipeline

Takes the raw sentence a person typed and turns it into three tidy lists the rest of the system
can act on. A photo can show that there is chicken on the counter, but it can never show that the
user wants *clean* food, and it cannot see the fish sauce inside a closed bottle. This folder is
what fills those gaps — it is the reason the system is genuinely **multimodal** rather than two
unrelated features bolted together.

```
"มีกุ้งกับไข่ อยากกินคลีน ไม่เอาหมู"
        ↓
{"ingredients": ["shrimp", "egg"], "health_tags": ["clean"], "excluded": ["pork"]}
```

Only one file lives here because the job is one job. Splitting a 300-line module into
`tokenize.py` + `match.py` + `negate.py` would spread a single linear procedure across three
files for no benefit.

## File: `nlp/extract.py`

### Module-level constants

| Constant | Value | What it's for |
|---|---|---|
| `INGREDIENTS_PATH` | `data/ingredients.json` | Built from `__file__`, so it works no matter which folder you run Python from |
| `HEALTH_TERMS_PATH` | `data/health_terms.json` | Same |
| `NEGATION_VERBS` | `{"เอา", "ใส่", "มี"}` | The verbs that, preceded by `ไม่`, mean "no X" |
| `MIN_FUZZY_TOKEN_LENGTH` | `4` | Tokens shorter than this never get fuzzy-matched |
| `FUZZY_SCORE_CUTOFF` | `85` | A typo guess below 85% similarity is thrown away |

Those last two numbers are not arbitrary. They were chosen so that `"chiken" → "chicken"` (92%)
passes while `"กระ" → "กระเพรา"` (60%) does not. Short Thai tokens are usually ordinary function
words like `มี` (have) or `กับ` (and), and a loose cutoff would match them to real ingredients by
accident.

### Import-time singletons (built once, not per message)

```python
_INGREDIENTS   = load_ingredients()
_HEALTH_TERMS  = load_health_terms()
_SYNONYM_INDEX = _build_synonym_index(_INGREDIENTS, _HEALTH_TERMS)
_ALL_SYNONYMS  = list(_SYNONYM_INDEX.keys())
_TRIE          = _build_trie(_SYNONYM_INDEX)
```

These run **once, when Python first imports the file** — not on every message. That matters
because `extract()` sits on the LINE reply-token path, and a reply token only lives about 30
seconds. Rebuilding a search tree out of 300+ synonyms for every incoming message would be a
wasteful place to spend that budget.

---

### function: `load_ingredients()`

- **Purpose:** Read `data/ingredients.json` off disk and return it as a Python dictionary.
- **Input/Output:** No arguments → `dict`. Keys are canonical names (`"chicken"`), values are the
  entry dicts described in the schema section below.
- **Method used:** Plain `json.load()` with `encoding="utf-8"` forced. The encoding is not
  optional — the file is full of Thai text, and on Windows Python otherwise guesses a legacy
  codepage and crashes with `UnicodeDecodeError`.
- **Called from:** At import time in this same file; also imported by
  `recommender/recommend.py:59` (it reuses this loader rather than writing a second one).
- **Depends on:** `data/ingredients.json`.

### function: `load_health_terms()`

- **Purpose:** Read `data/health_terms.json` — the Thai/English words people actually *type* to
  mean a diet.
- **Input/Output:** No arguments → `dict`, e.g. `{"keto": {"synonyms": ["คีโต", "โลว์คาร์บ", ...]}}`.
- **Method used:** Same UTF-8 `json.load()` as above.
- **Called from:** Import time in this file.
- **Depends on:** `data/health_terms.json`.
- **Why it's a separate file from `ingredients.json`:** these are two different kinds of
  vocabulary. `HEALTH_TAGS.md` defines the *recipe-side* rule (what makes a dish keto: carbs
  ≤ 10 g). `health_terms.json` is the *user-side* vocabulary (what a person types when they mean
  keto). Mixing them into one file would blur a real distinction.

### function: `_build_synonym_index(ingredients, health_terms)`

- **Purpose:** Flatten both dictionaries into one big lookup table mapping **every synonym string
  → the canonical key that owns it**.
- **Input/Output:**
  `(dict, dict)` → `dict[str, str]`. Example entries:
  `{"ไก่": "chicken", "อกไก่": "chicken", "คลีน": "health:clean"}`.
  Note the `health:` prefix — that's how one flat table can hold two different kinds of answer
  without needing two tables.
- **Method used:** A list comprehension builds `(synonym, key)` pairs, then they're sorted
  **longest synonym first** before being turned into a dict. Because later duplicates overwrite
  earlier ones in `dict()`, sorting long-first means a longer, more specific synonym wins over a
  shorter one. Entries in `health_terms.json` whose tag starts with `_` (comment fields) are
  skipped.
- **Called from:** Import time in this file.
- **Depends on:** The output of `load_ingredients()` and `load_health_terms()`.
- **Note:** In practice `tests/test_contract.py::test_no_synonym_is_shared_by_two_ingredients`
  already guarantees no synonym is claimed twice, so the ordering never actually decides anything
  today. It is kept as a safety net in case that guarantee is ever relaxed.

### function: `_build_trie(synonym_index)`

- **Purpose:** Build a **custom dictionary** so the Thai tokenizer keeps our ingredient names
  whole instead of chopping them up.
- **Input/Output:** `dict` → `pythainlp.util.Trie`.
- **Method used:** A **Trie** (say "try") is a tree-shaped structure for storing a big list of
  words so that "is this a real word?" can be answered very fast. PyThaiNLP's tokenizer uses one
  to decide where to cut a sentence. Here we hand it PyThaiNLP's own word list **plus** all ~300
  of our synonyms.
- **Called from:** Import time in this file.
- **Depends on:** `pythainlp.corpus.common.thai_words` and the synonym index.

> #### 🔑 Why this step exists at all — the tokenizer finding
>
> Thai is written **without spaces between words**, so before you can look anything up you have to
> guess where the word boundaries are. That guessing is called *tokenization*.
>
> PyThaiNLP's default tokenizer doesn't know this project's vocabulary, and it destroys exactly
> the words the system most needs:
>
> ```
> word_tokenize("ไม่เอาน้ำมันหอย")   →  ['ไม่', 'เอา', 'น้ำมัน', 'หอย']
> ```
>
> `น้ำมันหอย` is **oyster sauce**. Split like that, it becomes `น้ำมัน` (oil) + `หอย` (shellfish).
> A matcher would resolve the first half to `vegetable_oil` and silently drop the rest — meaning a
> dish containing oyster sauce could pass a vegan filter. That's a genuine correctness bug
> produced purely by tokenization, before any matching logic gets a chance to run.
>
> ```
> word_tokenize("อยากกินคลีน")       →  ['อยาก', 'กิน', 'คลี', 'น']
> ```
>
> The project's own canonical example doesn't survive either — `คลีน` ("clean") becomes `คลี` +
> `น`, neither of which is a usable lookup key.
>
> Passing the Trie as `custom_dict` fixes both. Verified live: `น้ำมันหอย` and `คลีน` now survive
> as single tokens, and compounds that were already correct (`พริกไทย`, `กุ้งแห้ง`, `น้ำปลา`) are
> undisturbed.

### function: `_resolve_token(token)`

- **Purpose:** Look up one word and decide what, if anything, it refers to.
- **Input/Output:** `str` → `str | None`. Returns a canonical ingredient key (`"chicken"`), a
  health tag with its prefix (`"health:clean"`), or `None`.
- **Method used:** Two stages.
  1. **Exact match** against `_SYNONYM_INDEX` — fast and always trusted.
  2. **Fuzzy matching** as a fallback, via `rapidfuzz.process.extractOne` with `fuzz.ratio`.
     *Fuzzy matching* means comparing two words that aren't spelled identically and scoring how
     similar they are, 0–100. `"chiken"` vs `"chicken"` scores 92. Anything under
     `FUZZY_SCORE_CUTOFF` (85) is rejected, and tokens shorter than 4 characters skip this stage
     entirely.
- **Called from:** `extract()`, once per token.
- **Depends on:** `_SYNONYM_INDEX`, `_ALL_SYNONYMS`.
- **Worth knowing:** returning `None` is the *normal* outcome. Most words in a sentence are
  function words, not ingredients.

> #### ⚠️ Documented limitation: Thai typo recovery is weak
>
> This was **measured, not overlooked.** English typos recover reliably. Thai typos usually do
> not, and the reason is the tokenizer again: a misspelled Thai word isn't in the custom
> dictionary, so the segmenter shatters it into syllable fragments rather than leaving it as one
> unknown chunk.
>
> ```
> word_tokenize("มีมะเขือเทดด้วย")   →  ['มี', 'มะเขือ', 'เท', 'ด', 'ด้วย']
> ```
>
> By the time rapidfuzz sees `มะเขือ`, its similarity to the full `มะเขือเทศ` (tomato) is only
> 80% — under the 85 cutoff. Lowering the cutoff was tried during planning and **rejected**: at
> 60%, unrelated short words started matching real ingredients by accident. A false positive
> silently corrupts an answer, whereas a missed typo merely fails to improve one. The trade was
> made knowingly. See `concern.md`.

### function: `extract(text)` ⭐ *the public contract*

- **Purpose:** The one function the rest of the system (and Person 1) calls. Pull ingredients,
  diets and exclusions out of a sentence.
- **Input/Output:**
  ```python
  extract("มีไก่กับไข่ อยากกินคลีน ไม่เอาพริก")
  # → {"ingredients": ["chicken", "egg"],
  #    "health_tags": ["clean"],
  #    "excluded":    ["chili"]}
  ```
  Always exactly those three keys, always lists of strings, even for empty or junk input.
  "Canonical key" means the English snake_case name used in `ingredients.json` — `"green_onion"`,
  never `"ต้นหอม"` and never `"spring onion"`.
- **Method used:** A single left-to-right walk over the tokens, carrying one `negated` flag:
  - A **blank token** (whitespace) resets `negated` to `False`. This is what stops a "no X" at the
    end of a sentence from leaking backwards onto ingredients mentioned earlier.
  - **Negation detection:** the cue is *two tokens*, not one — `ไม่` immediately followed by one
    of `เอา`/`ใส่`/`มี`. The tokenizer always splits `ไม่เอา` this way even with the custom dict,
    so the code consumes both tokens and sets `negated = True`.
  - Each remaining token goes through `_resolve_token()` and lands in `health_tags`, `excluded`
    (if negated), or `ingredients`. Duplicates are skipped by an `in` check, which preserves
    order — order is stable and predictable, which makes tests readable.
  - **Final rule:** anything in `excluded` is stripped out of `ingredients`. A key is never
    allowed in both lists. Excluded wins, because "ไม่เอา X" is a stronger, more specific signal
    than an earlier unqualified mention of X.
- **Called from:** `api/main.py:446` inside `handle_user_input()`. Also
  `tests/test_extract.py`, `tests/test_contract.py`.
- **Depends on:** `pythainlp.word_tokenize`, `_TRIE`, `_resolve_token`, and both JSON dictionaries.
- **Contract note:** This is **Handoff #2 to Person 1** (due Week 5, delivered). The three keys and
  their types are a promise that cannot change. Everything inside the function is free to change.

### `if __name__ == "__main__":` block

Running `python nlp/extract.py` directly prints one worked example. Importing the file does *not*
run it. It reconfigures stdout to UTF-8 first, because a Thai-locale Windows console defaults to
the cp874 codepage and prints Thai as garbage — a display quirk only, the strings themselves are
always fine.

---

# recommender/

## Role in the pipeline

Given the ingredients a user has, decide which of the 40 dishes they should cook. This is the
heart of my side of the project.

```
["chicken", "garlic", "chili"] + health=["clean"]
        ↓
[{"name_th": "ผัดกะเพราไก่", "score": 0.87,
  "have": ["chicken","garlic","chili"], "missing": ["holy_basil"], ...}]
```

The project docs are explicit that this is **implementation, not research** — scikit-learn already
provides both TF-IDF and cosine similarity, so nothing here needed inventing.

## File: `recommender/recommend.py`

### Import-time singletons

```python
_RECIPES           = load_recipes()
_KNOWN_INGREDIENTS = load_ingredients()          # reused from nlp/extract.py
_VECTORIZER        = TfidfVectorizer(analyzer=lambda doc: doc)
_RECIPE_MATRIX     = _VECTORIZER.fit_transform([...])
```

Same reasoning as `nlp/`: the TF-IDF matrix over 40 recipes is built **once at import**, not per
message, because this runs on the ~30-second reply-token clock.

`analyzer=lambda doc: doc` is worth explaining. Normally `TfidfVectorizer` expects English prose
and does its own splitting and lowercasing. Our "documents" are already lists of clean canonical
keys like `["chicken", "garlic"]`, so this tells scikit-learn *"don't process these, use them
exactly as given."*

The file also does `sys.path.insert(0, ...)` at the top so it can import `nlp.extract` whether
it's launched by pytest, imported by `api/main.py`, or run directly.

---

### function: `load_recipes()`

- **Purpose:** Read `data/recipes.json` and return it as a list of dicts.
- **Input/Output:** No arguments → `list[dict]`, 40 entries long.
- **Method used:** UTF-8 `json.load()`, same reasoning as `load_ingredients()`.
- **Called from:** Import time in this file.
- **Depends on:** `data/recipes.json`.

### function: `_recipe_document(recipe)`

- **Purpose:** Turn one recipe into the list of tokens the vectorizer will see.
- **Input/Output:** `dict` → `list[str]`, e.g.
  `["chicken","garlic","chicken","garlic","egg"]`.
- **Method used:** `main_ingredients * 2 + optional_ingredients` — mains are **listed twice**,
  optionals once. Repetition is how you say "mains matter more" using TF-IDF's own term-frequency
  counting, instead of bolting a separate weighting scheme on top. Simple, and easy to explain in
  a report.
  **`seasonings` are never included.** Everyone has fish sauce and sugar at home, so they must not
  affect which dish wins.
- **Called from:** Import time, once per recipe, to build `_RECIPE_MATRIX`.
- **Depends on:** the recipe dict's shape.

### function: `_is_seasoning(key, known)`

- **Purpose:** One-line helper — is this ingredient a basic seasoning?
- **Input/Output:** `(str, dict)` → `bool`. Safe on unknown keys: `.get(key, {}).get(...)` returns
  `False` rather than raising.
- **Method used:** Straight lookup of the `is_seasoning` flag in `ingredients.json`.
- **Called from:** `recommend()`.
- **Depends on:** `data/ingredients.json`.

### function: `_passes_health_filter(recipe, health_tags)`

- **Purpose:** Keep a recipe only if it suits **every** diet the user asked for.
- **Input/Output:** `(dict, list[str])` → `bool`.
- **Method used:** A loop with two checks per requested tag: the tag must be present in the
  recipe's `health_tags`, **and** absent from its `excluded_for`. Multiple tags are combined with
  **AND, not OR** — someone asking for both "vegan" and "keto" wants dishes that are both at once,
  not either one.
- **Called from:** `recommend()`.
- **Depends on:** the recipe's `health_tags` / `excluded_for` fields.
- **Note:** the `excluded_for` half is technically redundant — `tests/test_recipes.py` proves a
  recipe never claims and excludes the same tag. It's checked anyway rather than trusting an
  invariant silently.

### function: `_passes_excluded_filter(recipe, excluded)`

- **Purpose:** Drop dishes that need something the user said no to.
- **Input/Output:** `(dict, list[str])` → `bool`.
- **Method used:** Builds a set of the recipe's `main_ingredients | seasonings` and returns
  `False` if it overlaps the excluded list. **`optional_ingredients` are deliberately not
  checked** — an optional is omittable by definition, so the dish is still cookable without it. It
  simply never shows up in that recipe's `have`/`missing`.
- **Called from:** `recommend()`.
- **Depends on:** the recipe's `main_ingredients` / `seasonings` fields.

### function: `recommend(ingredients, health_tags=None, excluded=None, top_k=3)` ⭐ *the public contract*

- **Purpose:** The final deliverable of my side. Score every dish and return the best `top_k`.
- **Input/Output:**
  ```python
  recommend(["chicken","garlic","chili"], health_tags=["clean"])
  # → [{"id": "th_001",
  #     "name_th": "ผัดกะเพราไก่",
  #     "score": 0.87,                                      # always 0.0–1.0
  #     "have": ["chicken","garlic","chili"],
  #     "missing": ["holy_basil"],                          # MAIN ingredients only
  #     "nutrition": {"kcal":450,"protein":32,"fat":18,"carb":35},
  #     "health_tags": ["clean"]}]
  ```
  An **empty list is a valid answer** — it means nothing matched, and the bot says so rather than
  crashing.
- **Method used:** Five steps.
  1. **Strip seasonings from the user's own list.** Typing "fish_sauce" must not boost any score.
     (Seasonings are already excluded from the recipe side too — both halves are enforced.)
  2. **Filter before scoring.** Health filter and excluded filter run first, so the vector maths
     never runs on dishes that could not be returned anyway. Returns `[]` early if nothing
     survives, or if the user's ingredient list is empty.
  3. **TF-IDF.** *Term Frequency–Inverse Document Frequency* is a way of weighting words so that
     rare ones count for more. Garlic appears in nearly every Thai recipe, so it barely
     distinguishes anything; shrimp appears in a handful, so having shrimp is strong evidence. The
     weighting does that automatically — nobody hand-tunes it.
  4. **Cosine similarity.** Each recipe and the user's basket become arrows (vectors) in a space
     with one axis per ingredient. Cosine similarity measures the **angle** between two arrows and
     reports 0.0 (nothing in common) to 1.0 (identical). Using the angle rather than the distance
     means a user with 3 ingredients and a recipe with 8 can still score well — which is exactly
     the *partial scoring* the project requires, because nobody has a full fridge.
  5. **Assemble and sort.** Scores of 0 are skipped entirely ("nothing in common" is not a
     recommendation). `have` is everything the user owns from mains **and** optionals; `missing`
     is mains-only, because a missing optional is not a shopping-list item. Results are sorted
     best-first and cut to `top_k`.
- **Called from:** `api/main.py:452` inside `handle_user_input()`. Also
  `tests/test_recommend.py`, `tests/test_contract.py`, `tools/run_recommender_dev_set.py`.
- **Depends on:** `_RECIPE_MATRIX`, `_VECTORIZER`, `data/recipes.json`, and
  `nlp.extract.load_ingredients` for the seasoning flags.
- **Two small details that matter:**
  - The score is **clamped and rounded**: `round(min(1.0, max(0.0, score)), 2)`. Cosine similarity
    can return `1.0000000000000002` because of floating-point rounding inside the dot product,
    which would fail the "between 0 and 1" contract test.
  - Defaults are `None`, not `[]`. A mutable default like `[]` is created **once** and shared by
    every call to the function, so anything appending to it would leak into later calls. It's a
    classic Python bug and the `None` pattern avoids it.

---

# api/

## Role in the pipeline

Everything between "a person taps send on LINE" and "a reply appears on their phone." This folder
handles the messaging platform, groups messages that belong together, runs the pipeline, and
writes the final text. It is split into four files by *reason to change*: credentials
(`config.py`), message grouping (`session.py`), the fake detector (`mock_cv.py`), and the webhook
itself (`main.py`).

> **The LINE SDK version trap.** This project uses **line-bot-sdk v3**. Almost every LINE tutorial
> online is written for **v2**, and v2 code does not run on v3 — the imports, class names and the
> reply call are all different. Notably `TextMessage` means *incoming* in v2 and *outgoing* in v3.
> If a copied snippet raises `ImportError`, that's why.

---

## File: `api/config.py`

Loads the LINE credentials from a `.env` file at the project root and validates them **at import
time** — so a bad config stops the server immediately instead of producing a confusing 500 error
the first time a real user messages the bot.

Secrets live in `.env` (which `.gitignore` blocks) rather than in code because this repo has to be
public — YOLO is AGPL-3.0 licensed, which requires the whole codebase to be open source.

### class: `ConfigError(RuntimeError)`

- **Purpose:** A distinct exception type meaning "a required setting is missing or still a
  placeholder."
- **Method used:** A plain subclass of `RuntimeError` — no custom behaviour, it exists so callers
  and readers can tell a config problem apart from any other crash.

### function: `_require(name)`

- **Purpose:** Fetch one required environment variable, or explain clearly how to fix it.
- **Input/Output:** `str` (variable name) → `str` (its value). Raises `ConfigError` otherwise.
- **Method used:** Reads `os.getenv`, then applies **two** checks: empty/missing, and *still the
  placeholder from `.env.example`* (detected by the `your_..._here` pattern). The second check
  catches an easy mistake — copying the template and forgetting to paste real values — which would
  otherwise surface as a baffling 401 from LINE rather than anything pointing at `.env`. The error
  message is a numbered three-step fix.
- **Called from:** Twice at module level in this file.
- **Depends on:** `python-dotenv`, and a `.env` file at the project root.

### Module constants

| Constant | Source | Meaning |
|---|---|---|
| `PROJECT_ROOT`, `ENV_PATH` | derived from `__file__` | Work regardless of the current directory |
| `CHANNEL_ACCESS_TOKEN` | `_require(...)` | Proves we're allowed to send messages **out** |
| `CHANNEL_SECRET` | `_require(...)` | Proves messages coming **in** are genuinely from LINE |
| `DEBOUNCE_SECONDS` | env, default `2.5` | How long to wait after the last message |
| `MAX_IMAGES_PER_SESSION` | `5` | Cap on photos merged into one request |
| `INCOMING_DIR` | `data/incoming` | Where downloaded photos are saved (git-ignored: user data) |

Two credentials for two different jobs — that distinction trips people up constantly. The
**secret** verifies incoming requests; the **access token** authorises outgoing ones.

---

## File: `api/session.py`

### The problem this file solves

People don't send one tidy message. They send a photo, then a caption two seconds later:

```
11:04:01  [photo of chicken and egg]
11:04:03  "อยากกินคลีน"
```

Without buffering that's two separate webhooks, so the bot replies twice — once knowing only the
photo, once knowing only the text. Neither reply has the whole picture and the user gets spammed.

### The fix: **debounce**

*Debounce* means "wait a moment before acting, in case more input is coming."

```
photo arrives  →  buffer it, start a 2.5s timer
text arrives   →  buffer it, CANCEL the old timer, start a fresh 2.5s timer
(silence)      →  timer fires → process photo + text together → reply once
```

### Why this file imports nothing from the project

No `import api.config`, no `import api.main`. Two concrete reasons:

- `config.py` deliberately crashes if `.env` is missing. If this file imported it,
  `tests/test_session.py` couldn't run without real LINE credentials.
- `main.py` imports *this* file. If this file imported `main.py` back, Python would hit a
  **circular import** and fail to start.

Instead `main.py` pushes its settings in via `configure()` and its worker function in via
`set_flush_handler()`. That pattern is called **dependency injection**, and it's what keeps this
module pure Python and independently testable.

### class: `Session` (a `@dataclass`)

Everything one user has sent during the current debounce window.

| Field | Type | Purpose |
|---|---|---|
| `user_id` | `str` | Who this belongs to |
| `texts` | `list[str]` | Every text message in this burst |
| `image_ids` | `list[str]` | LINE message IDs of photos — **not** the photos themselves |
| `reply_token` | `str` | The token from the *most recent* message |
| `dropped_images` | `int` | How many photos went over the cap, so the reply can mention them |
| `timer` | `threading.Timer \| None` | The pending countdown; `None` = nothing scheduled |
| `first_seen` / `last_seen` | `float` | `time.monotonic()` timestamps |

Two details worth understanding:

- `field(default_factory=list)` rather than `= []`. A plain `= []` would be created **once** and
  shared by every `Session`, so all users would append into the same list. Same trap as the
  mutable-default one in `recommend()`.
- `time.monotonic()` rather than `time.time()`. Wall-clock time can jump (NTP sync, DST, manual
  clock changes), which would make an elapsed-time measurement lie. `first_seen` is what lets
  `main.py` log how much of the ~30-second reply-token lifetime was used up before the reply
  actually fired.

### Module state

`_sessions: dict[str, Session]` is **in memory only** — everything is lost on restart. That's
acceptable: a session lives ~2.5 seconds, and losing one costs the user a single repeated message.

`_lock = threading.Lock()` guards it. Timers fire on their own threads and Flask handles requests
on more threads; without a lock, two threads could modify the dict simultaneously and corrupt it.
The rule the file follows: **keep locked blocks short, never do network calls while holding it**,
or every other user waits.

### function: `configure(debounce_seconds=None, max_images=None)`

- **Purpose:** Override the module defaults.
- **Input/Output:** Two optional numbers → `None`. Only non-`None` arguments take effect.
- **Called from:** `api/main.py:501` at startup, and from `tests/test_session.py`.

### function: `set_flush_handler(handler)`

- **Purpose:** Register the function to call when a debounce window closes.
- **Input/Output:** A callable taking one `Session` → `None`.
- **Method used:** Dependency injection (see above). `None` means "not wired up yet," which is the
  normal state during tests.
- **Called from:** `api/main.py:505`, passing `process_session`.

### function: `add_text(user_id, text, reply_token)`

- **Purpose:** Buffer a text message and restart the user's countdown.
- **Input/Output:** three `str` → `None`.
- **Method used:** Under the lock: get-or-create the session, append the text, update `last_seen`,
  **overwrite** `reply_token` with the newest one, restart the timer.
- **Called from:** `api/main.py:214` in `on_text()`.
- **Why overwrite the token:** every incoming message carries its own reply token, each is
  single-use and expires in ~30 seconds. When three messages merge into one session we can only
  reply once — so we keep the *freshest* token, which has the most life left when the timer fires.

### function: `add_image(user_id, message_id, reply_token)`

- **Purpose:** Buffer a reference to a photo and restart the countdown.
- **Input/Output:** three `str` → `None`.
- **Method used:** Same as `add_text`, plus the cap: if `image_ids` is already at `_max_images`
  (5), increment `dropped_images` instead of appending. Counting rather than silently discarding
  is what lets the reply tell the user what happened.
- **Called from:** `api/main.py:230` in `on_image()`.
- **Note:** only the `message_id` is stored, never the picture. Downloading is slow and this runs
  inside the webhook request.

### function: `_get_or_create(user_id)`

- **Purpose:** Fetch a user's session, creating one if it doesn't exist.
- **Input/Output:** `str` → `Session`.
- **Called from:** `add_text`, `add_image`. Caller must already hold `_lock`.

### function: `_restart_timer(session)`

- **Purpose:** Cancel any pending countdown and start a fresh one. **This cancel-then-restart
  *is* the debounce.**
- **Input/Output:** `Session` → `None`.
- **Method used:** `threading.Timer(_debounce_seconds, _flush, args=(user_id,))`, with
  `daemon = True` set before starting. Daemon threads let Python exit even with timers pending —
  without it, Ctrl+C would hang until every countdown finished. Calling `.cancel()` on an
  already-fired timer is harmless.
- **Called from:** `add_text`, `add_image`. Caller holds `_lock`.

### function: `_flush(user_id)`

- **Purpose:** Runs on the timer's thread once the user has gone quiet; hands the session to the
  registered worker.
- **Input/Output:** `str` → `None`.
- **Method used:** A deliberate **two-step structure**:
  1. **Pop the session out of the dict while holding the lock.** This hands the thread sole
     ownership, so a message arriving at that exact moment starts a clean new session rather than
     mutating one already being processed. Skipping this produces a race-condition bug that
     appears once in a few hundred messages and is nearly impossible to reproduce on purpose.
  2. **Release the lock, then do the slow work.** Downloading images takes seconds; holding the
     lock that long would freeze every other user.

  It then handles three cases explicitly — session already popped, no handler registered, and
  handler raised — each with its own log line. That last one matters: an exception on a timer
  thread vanishes silently by default (no request to return a 500 to, no console output), so the
  bot would just stop replying with no clue why.
- **Called from:** the `threading.Timer` created in `_restart_timer`.

### function: `active_count()` / `function: reset()`

- `active_count()` → `int`, how many users currently have an open window. For tests and debugging.
- `reset()` cancels every pending timer and clears all sessions, so one test's leftover state
  can't leak into the next.

---

## File: `api/mock_cv.py` — 🚧 **STILL A MOCK**

**This file is fake and is meant to be deleted, not maintained.** Person 1 delivers the real
`detect()` plus `best.pt` in Week 8 (Handoff #3). Until then this returns plausible fixed results
so the rest of the chatbot can be built and tested end-to-end without waiting on anyone.

It lives in `api/` because `api/` is my folder. Person 1's real detector will live in theirs — this
file gets **deleted** at that point, not edited.

### function: `detect(image_path)` 🚧

- **Purpose:** Pretend to find ingredients in a photo.
- **Input/Output:** `str` (path) → `list[dict]`:
  ```python
  [{"ingredient": "tomato", "confidence": 0.91},
   {"ingredient": "egg",    "confidence": 0.88}]
  ```
  Confidence runs 0.0–1.0. The shape is copied exactly from the project doc so the real swap
  changes nothing else.
- **Method used:** `random.sample()` picks 2–5 entries from a hardcoded list of five, then sorts
  them highest-confidence first (matching what real YOLO returns). `image_path` is **ignored** —
  but callers must still pass it correctly, or Week 9 becomes a rewrite instead of a one-line swap.
- **Called from:** `api/main.py:284` inside `process_session()`.
- **Depends on:** nothing. That's the point.
- **Deliberate detail:** one fake entry (`garlic`, 0.42) sits **below** the 0.5 cutoff on purpose,
  so the confidence filter in `main.py` is actually exercised rather than merely assumed to work.
- **Outstanding:** `# TODO(Week 8): delete this file; import Person 1's real detect() instead.`

---

## File: `api/main.py`

The webhook itself. **Status: real LINE plumbing, one mocked brain.** Signature verification,
session buffering, image download and replies are all real and working; `detect()` is not.

### function: `_log(msg)`

- **Purpose:** One print helper for the whole webhook→reply path, tagged `[bot]` so the full chain
  for a single message is one `grep` away.
- **Input/Output:** `str` → `None`. Uses `flush=True` so output appears immediately.
- **Why it exists:** before it, the happy path for a text-only message printed **nothing** — the
  only `print()` in the file sat inside `_download_image()`, which a text-only message never
  reaches. That made a silent success and several silent early-return bugs look identical: "200,
  no reply, no log" either way. Every step now logs, success included.

### route: `GET /health` → `function: health()`

- **Purpose:** Liveness check. Open it in a browser to confirm the server is up.
- **Input/Output:** No arguments → `({"status": "ok"}, 200)`.
- **Why it's useful:** the LINE console only reports "webhook failed" without saying whether your
  *server* is down, your *tunnel* is down, or the *signature check* is rejecting. This isolates
  the first of those three.

### route: `POST /callback` → `function: callback()`

- **Purpose:** The webhook LINE calls whenever someone messages the bot.
- **Input/Output:** Reads the Flask request → returns `("OK", 200)`, or aborts with 400 on a bad
  signature.
- **Method used — two ideas, both important:**

  **1. Signature verification.** Your webhook URL is public, so anyone who finds it can POST to
  it. LINE proves a request is genuine by *signing* it: it hashes the request body together with
  your channel secret and puts the result in the `X-Line-Signature` header. `handler.handle()`
  recomputes that hash and compares. Only someone holding your secret could produce a matching
  value. The code reads `request.get_data(as_text=True)` — the **exact raw body** — because the
  signature was computed over exactly those bytes; using `request.json` would re-serialise the
  text and break verification.

  **2. Answer fast.** `handler.handle()` dispatches synchronously, so this HTTP response waits for
  the handlers to finish. That's why those handlers only drop the message into a buffer and
  return. **LINE retries a webhook that is slow to answer**, which would make the bot reply twice
  to one message. The real work happens later on the timer thread.

  The function also pre-parses the body just to log what event types arrived, which separates
  "no handler registered for this event type" (a sticker, a follow event, a postback) from every
  other silent path.
- **Depends on:** `handler` (built from `config.CHANNEL_SECRET`).

### handler: `on_text(event)`

- **Purpose:** Someone sent text. Buffer it and let the debounce timer do the rest.
- **Input/Output:** A LINE `MessageEvent` → `None`.
- **Method used:** Get the user ID, log, call `session.add_text()`. **No slow work here** — this is
  holding up the HTTP response.
- **Called from:** the LINE SDK, via the `@handler.add(MessageEvent, message=TextMessageContent)`
  decorator.

### handler: `on_image(event)`

- **Purpose:** Someone sent a photo. Buffer **only its ID**.
- **Input/Output:** A LINE `MessageEvent` → `None`.
- **Method used:** Same as `on_text` but calls `session.add_image()`. The picture is deliberately
  **not** downloaded here — that's a network round trip. Downloading happens in the flush handler
  once the window closes.

### function: `_user_id_of(event)`

- **Purpose:** Pull the user ID out of an event, safely.
- **Input/Output:** `MessageEvent` → `str | None`.
- **Method used:** `getattr(event.source, "user_id", None)` — messages can arrive from groups and
  chat rooms where there may be no user ID, and `getattr` returns `None` instead of raising. Logs
  the source type when it happens, so this case is distinguishable from a successful-but-unreplied
  flush.
- **Called from:** `on_text`, `on_image`.

### function: `process_session(sess)` ⭐ *the flush worker*

- **Purpose:** Handle one complete request — everything the user sent in one burst.
- **Input/Output:** `session.Session` → `None` (its output is a sent LINE message).
- **Method used:** Five steps, wrapped in a `try/except` that must never let an exception escape:
  1. **Download every buffered photo.** Each download is individually wrapped — one bad download
     shouldn't sink the whole reply, so it's skipped and the rest continues.
  2. **Run detection on each photo** via `mock_cv.detect()` 🚧, keeping only items at or above
     `CONFIDENCE_THRESHOLD` (0.5). Then deduplicate with `dict.fromkeys()`, which preserves order
     where `set()` would not — the same ingredient can appear in several photos.
  3. **Join the separate texts** into one string, so `extract()` sees the whole request at once.
  4. **Run the pipeline** via `handle_user_input()`.
  5. **Mention anything dropped** — if `sess.dropped_images > 0`, append a Thai note saying only
     the first N photos were used.

  Then `send_reply()`.
- **Called from:** `api/session.py:_flush()`, wired up by `session.set_flush_handler()` at the
  bottom of this file. It runs on the **debounce timer's thread**, so it may take as long as it
  needs without blocking the webhook.
- **Depends on:** `_download_image`, 🚧 `mock_cv.detect`, `handle_user_input`, `send_reply`.
- **Why the confidence cutoff exists:** low-confidence boxes are usually shadows, reflections or
  stains that YOLO mistook for food. Acting on them is *worse* than missing an ingredient — the
  bot would confidently recommend a dish based on something that was never there.

### function: `_download_image(message_id, user_id)`

- **Purpose:** Fetch one photo from LINE and save it, returning the saved path.
- **Input/Output:** two `str` → `str` (the path on disk).
- **Method used:** `MessagingApiBlob.get_message_content()` inside an `ApiClient` context manager,
  then `path.write_bytes()`. The filename is `{user_id[:8]}_{message_id}.jpg` — `message_id` is
  unique so collisions are impossible, and the user prefix just makes the folder readable while
  debugging.
- **Called from:** `process_session()`.
- **Depends on:** `config.INCOMING_DIR`, `line_config`.
- **Why save a copy:** image content on LINE **expires**. Saving means the file is still there in
  Week 8 when YOLO can finally read it — and it doubles as real test data.

### function: `send_reply(user_id, reply_token, text, first_seen=None)`

- **Purpose:** Send the reply. Try **Reply** first, fall back to **Push** only if that fails.
- **Input/Output:** three `str` + optional `float` → `None`.
- **Method used — the reply-token strategy. This is a budget decision, not a technical one:**

  | | Counts against monthly quota? |
  |---|---|
  | **Reply** message (answers a specific incoming message) | ❌ Free |
  | **Push** message (sent unprompted) | ✅ Costs quota |

  The Thai free LINE OA plan caps messages per month and has **no way to buy more**. Once the
  quota is gone the bot goes silent until the month rolls over — which mid-demo would be
  unrecoverable. So Push is strictly an emergency path. It only triggers when the reply token has
  already failed, which in practice means it expired: a token lasts ~30 seconds, and 2.5 s of
  debounce plus several image downloads can occasionally exceed that.

  Other details: text over `MAX_MESSAGE_LENGTH` (5000, LINE's hard limit) is truncated with an
  ellipsis. `_request_timeout=(5, 10)` is passed explicitly because the SDK's default is `None` —
  *no timeout at all* — so a stalled HTTPS call would block the daemon timer thread forever while
  printing nothing. `ApiException` is caught separately from generic exceptions because LINE's
  real reason (`"Invalid reply token"`, `"The reply token is already used"`) lives in `exc.body`,
  not in `str(exc)`.

  `first_seen` is logged as elapsed time before the call — this is the reply-token-expiry
  measurement. Without that number, a hang and a slow-but-successful call look identical in
  hindsight.
- **Called from:** `process_session()`.

### function: `handle_user_input(text="", detected_ingredients=None)` ⭐ *the pipeline*

- **Purpose:** Run one full turn of the conversation: raw input in, reply text out.
- **Input/Output:** `(str, list[str] | None)` → `str` (the reply, ready for LINE).
- **Method used:** Four steps, and it's short because each component does its own job:
  1. `parsed = extract(text)` — pull structure out of the typed message.
  2. Merge the photo's ingredients with the text's, deduplicating via `dict.fromkeys()` (order
     preserved, photo results first).
  3. `recommend(...)` with the merged ingredients plus the text's `health_tags` and `excluded`.
  4. `format_reply(results)`.
- **Called from:** `process_session()`; also directly by tests.
- **Depends on:** `nlp.extract.extract`, `recommender.recommend.recommend`.
- **Why one function handles both modalities:** this is what makes the system genuinely
  multimodal rather than two separate features. A photo can show ไก่ on the counter but can never
  show that the user wants something clean, and it cannot see the fish sauce inside a closed
  bottle. Text fills both gaps. Notice that health tags and exclusions come **only** from text —
  by construction there is no other source.

### function: `format_reply(results)`

- **Purpose:** Turn recommender output into the message the user actually reads.
- **Input/Output:** `list[dict]` → `str`. Empty input produces a polite Thai "no matching menu
  found, try sending more ingredients" message.
- **Method used:** Plain string assembly into a list of lines, then `"\n".join()`. Each dish gets
  a numbered heading, a ✅ *have* line, a 🛒 *need to buy* line (each shown only if non-empty),
  and a 📊 nutrition line with kcal/protein/fat/carb.
- **Called from:** `handle_user_input()`.
- **Why it's a template and not an LLM call:** templates are instant, and the LINE reply token
  expires in 10–30 seconds. A slow LLM round trip risks missing that window entirely and losing
  the reply. The project rules also state the LLM must never compose the reply text.

### Startup wiring

```python
session.configure(debounce_seconds=..., max_images=...)
session.set_flush_handler(process_session)
```

Done **here** rather than by `session.py` importing `main.py`, which would be a circular import.

The `if __name__ == "__main__":` block sets stdout to UTF-8 with `line_buffering=True` (without
the latter, redirecting output to a file makes Python hold `print()` in a buffer, so your log
looks empty while the server is running), enables `logging.basicConfig(level=logging.INFO)` so the
SDK's "No handler of \<EventType\>" messages are visible, and starts Flask.

> **`use_reloader=False` is required, not a preference.** Flask's auto-reloader runs the app in
> **two processes**. Both would hold their own session buffers and their own timers, so every
> message would be processed twice and the bot would reply twice. That looks exactly like the
> "LINE retried my webhook" bug, so it's very easy to spend an afternoon debugging the wrong
> thing. The cost is that code changes need a manual restart.

---

# `data/ingredients.json` & `data/recipes.json` — Schema Summary

## `data/ingredients.json` — the central dictionary

**69 entries.** A JSON object whose *keys* are the canonical English snake_case names used
everywhere else in the system.

```json
"chicken": {
  "name_th": "ไก่",
  "yolo_class_id": 0,
  "is_seasoning": false,
  "is_animal_product": true,
  "synonyms": ["ไก่", "เนื้อไก่", "อกไก่", "สะโพกไก่", "น่องไก่", "ไก่สด", "chicken"]
}
```

| Field | Type | What it means |
|---|---|---|
| *(the key)* | `str` | The **canonical name**. The single form every component agrees on. |
| `name_th` | `str` | Thai display name, for showing to users |
| `yolo_class_id` | `int \| null` | The class number Person 1's detector uses, or `null` if this ingredient is text-only and never detected from a photo |
| `is_seasoning` | `bool` | If true, this never influences recipe matching — everyone has it at home |
| `is_animal_product` | `bool` | The single source of truth for deriving vegetarian/vegan |
| `synonyms` | `list[str]` | Every Thai and English spelling a user might type |

### Locked design decisions visible in the data

- **Two tiers of ingredient.** Exactly **20** entries have a `yolo_class_id`, numbered **0–19 with
  no gaps** (enforced by `test_yolo_class_ids_are_sequential_from_zero`). The other **49** have
  `yolo_class_id: null` — these are things a camera realistically can't identify, like fish sauce
  inside a bottle, and can only ever arrive via text.
- **Seasonings are never detectable.** 22 entries have `is_seasoning: true`, and
  `test_seasonings_are_never_detectable` enforces that a seasoning never gets a YOLO class ID.
- **`is_animal_product` (15 entries) is a *flag*, not a hardcoded rule.** Vegan and vegetarian
  status is derived from this field rather than restated in code, so the definition lives in one
  place and shows up in a diff when it changes.
- **Every ingredient lists its own Thai name as a synonym**
  (`test_ingredient_includes_its_own_thai_name_as_a_synonym`), and **no synonym is claimed by two
  ingredients** (`test_no_synonym_is_shared_by_two_ingredients`). That second guarantee is what
  makes the flat synonym lookup in `nlp/extract.py` unambiguous.
- **Deliberate near-miss spellings are included.** e.g. `cabbage` lists both `กะหล่ำปลี` and the
  common misspelling `กระหล่ำปลี`. Since Thai fuzzy matching is weak (see the `nlp/` limitation),
  known misspellings are handled by putting them in the dictionary instead.

## `data/recipes.json` — the recipe database

**40 recipes**, `th_001` through `th_040`. A JSON array of objects.

| Field | Type | What it means |
|---|---|---|
| `id` | `str` | `"th_001"` … `"th_040"` |
| `name_th` | `str` | Thai dish name — what the user sees |
| `main_ingredients` | `list[str]` | Canonical keys. Counted **twice** in the TF-IDF document; a missing one appears in `missing` |
| `optional_ingredients` | `list[str]` | Counted once; never blocks a dish, never appears in `missing` |
| `seasonings` | `list[str]` | **Never** part of matching — but *are* checked by the excluded filter |
| `health_tags` | `list[str]` | Diets this dish actively suits: `clean` / `keto` / `vegetarian` / `vegan` |
| `excluded_for` | `list[str]` | Diets this dish is unsuitable for |
| `serving_g` | `int` | Grams the nutrition figures describe |
| `cook_time_min` | `int` | Cooking time |
| `nutrition` | `dict` | `{kcal, protein, fat, carb}` — the four macros |
| `nutrition_method` | `str` | `"direct"` or `"computed"` — see below |
| `nutrition_ref` | `str` | *(direct only)* the source record, e.g. `"STD:1270"` |
| `nutrition_basis` | `dict` | *(computed only)* gram amount assumed per ingredient |
| `basis_refs` | `dict` | *(computed only)* the source code for each ingredient |
| `nutrition_source` | `str` | Human-readable citation, e.g. `"Thai FCD (INMU), food code H4"` |
| `notes` | `str` | Why decisions were made — reasoning kept next to the data |

### Locked design decisions visible in the data

- **Nutrition is sourced, never estimated.** All 40 entries cite the Thai Food Composition
  Database (INMU). Self-estimated nutrition would invalidate the project's nutrition experiment
  entirely. Two methods are used:
  - **32 recipes are `"direct"`** — one INMU record covers the whole dish, cited via
    `nutrition_ref`.
  - **8 recipes are `"computed"`** — no single record exists, so the dish is built up from
    per-ingredient records. These carry the extra `nutrition_basis` (grams assumed) and
    `basis_refs` (source code per ingredient), so the arithmetic is fully auditable. The `notes`
    field is honest that the *gram amounts* are the author's judgement, not INMU's.
- **The vegan trap is handled, and visible in the data.** `th_001` ไข่เจียว (Thai omelette) is
  `excluded_for: ["vegetarian", "vegan"]` — **because of the fish sauce**, not the egg. Likewise
  `th_033` ผัดผักรวมมิตร is a stir-fried *vegetable* dish, yet excluded for both, because of the
  **oyster sauce**. This is the most commonly missed detail in the whole project, and it's enforced
  by the data rather than by anyone remembering.
- **Health tags are applied conservatively, from measurable rules.** Current distribution:
  keto 23, clean 17, vegetarian 5, vegan 4. `th_001` is *not* tagged clean because its source
  record shows 32.9 g fat per 100 g — evidence that a Thai omelette is shallow-fried in a lot of
  oil. The rule decided the tag, not intuition.
- **A recipe never both claims and excludes the same tag** — enforced by
  `tests/test_recipes.py::test_a_tag_is_never_both_claimed_and_excluded`.

## `data/health_terms.json` — the user-utterance vocabulary

A small fourth file, same shape as `ingredients.json` (`{tag: {"synonyms": [...]}}`) on purpose.

It holds what a person **types** to mean a diet — `คีโต`, `โลว์คาร์บ`, `low carb` → `keto` — as
opposed to `HEALTH_TAGS.md`, which defines what makes a *dish* keto (carbs ≤ 10 g). Two genuinely
different things, kept in two files.

Two documented approximations, both recorded in `_comment` fields inside the file itself:

- **`โลว์คาร์บ` (low-carb) → keto** is not strictly accurate — keto is a stricter subset of
  low-carb — but it's what people commonly type when they mean keto.
- **`กินเจ` → vegan, not vegetarian.** The Thai Buddhist *เจ* diet forbids all animal products
  including fish sauce and shrimp paste, matching this project's vegan definition. It's a slight
  over-match in the other direction, since *เจ* also forbids garlic and onion, which this
  project's vegan tag does not.
- **A bare `เจ` is deliberately excluded** from the synonym list: it's a substring of ordinary
  words like *เจอ* (to meet) and *เจ็ด* (seven), so matching it alone would fire on sentences with
  nothing to do with diet.

---

# Methodology Summary

| Method | What it is, in one line | Where it's used |
|---|---|---|
| **Thai word segmentation** | Thai has no spaces, so a tokenizer has to guess where words begin and end | `nlp/extract.py::extract` (`pythainlp.word_tokenize`) |
| **Custom Trie dictionary** | A tree of known words handed to the tokenizer so our compounds survive intact | `nlp/extract.py::_build_trie` — **required**, not an optimisation |
| **Synonym index** | One flat lookup table mapping every spelling → one canonical name | `nlp/extract.py::_build_synonym_index` |
| **Fuzzy matching** | Score how similar two differently-spelled words are, 0–100; accept above 85 | `nlp/extract.py::_resolve_token` (rapidfuzz) |
| **Negation detection** | Spot "no X" and move X to a separate exclusion list; scope resets at whitespace | `nlp/extract.py::extract` |
| **TF-IDF** | Weight ingredients so rare ones (shrimp) count more than ubiquitous ones (garlic) | `recommender/recommend.py::_VECTORIZER` (scikit-learn) |
| **Term-frequency weighting by repetition** | List main ingredients twice so TF-IDF itself makes them matter more | `recommender/recommend.py::_recipe_document` |
| **Cosine similarity** | Measure the *angle* between two ingredient vectors → a 0–1 similarity score | `recommender/recommend.py::recommend` |
| **Filter-before-score** | Rule dishes out first so vector maths never runs on impossible candidates | `recommender/recommend.py::recommend` |
| **Partial scoring** | Never require a full ingredient match — nobody has a complete fridge | `recommender/recommend.py::recommend` |
| **Webhook signature verification** | Hash the request body with a shared secret to prove it really came from LINE | `api/main.py::callback` |
| **Debounce** | Wait 2.5 s after the last message, restarting the clock each time, then act once | `api/session.py::_restart_timer` |
| **Thread lock + pop-under-lock** | Prevent two threads corrupting shared state; hand a session to one owner | `api/session.py::_flush` |
| **Dependency injection** | Pass functions/settings *in* instead of importing, to avoid circular imports | `api/session.py::set_flush_handler` |
| **Reply-token strategy** | Use free Reply first; Push (which costs quota) only after Reply has failed | `api/main.py::send_reply` |
| **Confidence thresholding** | Discard detections below 0.5 — a false ingredient is worse than a missed one | `api/main.py::process_session` |
| **Order-preserving dedup** | `dict.fromkeys()` instead of `set()` so merged results stay in a stable order | `api/main.py::process_session`, `handle_user_input` |
| **Template response** | Build the reply by string assembly, never by calling an LLM — speed and token life | `api/main.py::format_reply` |

---

# Status & Open Items

## ✅ Done and real

- `nlp/extract.py` — Week 5 complete. Measured on a 22-sentence dev set (`data/nlp_dev_set.json`),
  100% passing.
- `recommender/recommend.py` — Week 7 complete. Measured on `data/recommender_dev_set.json`
  (8 cases, all passing, via `tools/run_recommender_dev_set.py`).
- `data/ingredients.json` — 69 entries, locked. Handoff #1 to Person 1 delivered.
- `data/recipes.json` — all 40 recipes filled with sourced nutrition.
- `api/config.py`, `api/session.py` — complete.
- `api/main.py` — real webhook, real signature verification, real session buffering, real image
  download, real reply/push logic, real observability logging.

## 🚧 Still mocked or not yet built

| Item | State |
|---|---|
| `api/mock_cv.py::detect()` | **Mocked.** Waiting on Person 1's Handoff #3 (`best.pt` + real `detect()`), Week 8. Return shape already agreed, so the swap should be one line. |
| `config/thresholds.yaml` | **Not read by my code at all.** Verified by grep — no reference to `thresholds` anywhere in `api/`, `nlp/`, or `recommender/`. The cutoff is the hardcoded `CONFIDENCE_THRESHOLD = 0.5` at `api/main.py:85`. Handoff #4, Week 8. |
| **Quick Reply** buttons | **Not implemented.** Verified by grep — no `QuickReply` import or usage anywhere in `api/`. This is an open Week 8 checklist item ("Detected onion? [Yes] [No]"). |
| `data/test_b/batch_B/` | **Does not exist.** No `data/test_b/` directory in the repo. The 30-image shoot and its metadata log are still an unchecked Week 2 item. The metadata field list is therefore **not certain / needs verification** — it hasn't been created yet. |
| Cross-check labelling of 10 of Person 1's images | Unchecked Week 2 item. |

## Deliberate, documented limitations (not bugs)

- **Thai typo recovery is weak.** Measured during Week 5, and the trade-off was taken knowingly:
  lowering the fuzzy cutoff enough to catch Thai fragment-typos also manufactures false positives
  on ordinary short words. False positives corrupt an answer silently; missed typos merely fail to
  improve one. Mitigated by listing known misspellings directly in `ingredients.json`.
- **Sessions live in memory only.** Everything is lost on server restart. A session lives ~2.5
  seconds, so the worst case is one user resending one message.
- **`โลว์คาร์บ → keto` and `กินเจ → vegan`** are approximations, each documented in
  `data/health_terms.json` itself.
