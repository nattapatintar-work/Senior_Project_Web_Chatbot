# 🍳 FoodFridgeGreen — Web Chatbot Track

> A static-web, ChatGPT-style chatbot (FastAPI backend) that recommends Thai recipes
> from ingredient photos + text. This is a **parallel track** to the LINE OA capstone,
> **not a replacement for it**. This repo does **not** target LINE (see the Legacy
> appendix at the bottom).

---

## 🛠️ Working Style

- **Show actual diffs/data, not prose summaries.** When reporting a change for
  review (a recipe edit, an ingredient field, a tag fix), show the exact
  before/after values or JSON — not a description of what changed. The user
  reviews the real data, not a paraphrase of it.
- **Every cut/rejected dish or ingredient needs a specific, named reason.**
  Never say "removed" or "adjusted" alone — say *why*: "no findable source,"
  "duplicate of th_0XX," "needs an out-of-scope ingredient," etc. This applies
  any time something proposed doesn't make it into the final data.
- **Never dismiss a search result as unfit based on the snippet alone —
  always fetch and check the actual page content before dropping a
  candidate.** Traced to a real miss: jicama/shallot/celery were reported
  "unreachable" across three recipe-database batches, but real single-dish
  sources for all three were sitting in the search results the whole time —
  filtered out by judging the snippet instead of opening the page. Applies
  to source-hunting of every kind, not just the recipe batches.

---

# PART A — WHAT THIS REPO IS

## 1. Scope

### 1.1 Problem
People open the fridge, see a pile of random ingredients, and don't know what to cook.
Ingredients expire and get thrown away — a convenience problem and a household
food-waste problem.

### 1.2 This track vs. the LINE OA capstone

| | Source |
|---|---|
| **Reused 100% from the LINE OA work** | NLP pipeline (dictionary + fuzzy matching + Trie + negation), TF-IDF recommender, `detect()` interface (YOLO/Gemini wrapper), recipe database |
| **Newly built here** | Frontend chat UI, backend REST API layer (replaces the LINE webhook), new session/state management (no LINE reply token / push API), AWS deployment |

### 1.3 Parent research context
The LINE OA capstone's research question — *when an LLM is already more accurate at
identifying ingredients, is training a dedicated YOLO model still worth it, and where
is the cost/speed/reliability break-even?* — is studied there. **This repo runs no
experiments** and does not carry the Test-A/Test-B sets, budget sweep, random
baseline, consistency or nutrition experiments. It is the product track.

---

## 2. Architecture

- **Frontend:** static HTML/CSS/JS, ChatGPT-style chat UI.
- **Backend:** FastAPI REST API running `detect()` (YOLO/Gemini), the NLP pipeline,
  the intent classifier and the recommender.
- **Transport:** plain HTTP. Images upload via multipart form directly — no webhook,
  no reply token, no push API, no 2-step Content API fetch.
- **Deploy:** AWS. YOLO inference needs a GPU instance (candidate: `g4dn.xlarge`),
  which is **not** covered by the free tier — cost is the main risk (see Open Items).

```
browser (static UI) ⇄ FastAPI ─┬─ detect()           YOLO11 → Gemini fallback
                               ├─ extract()          dictionary/fuzzy/Trie/negation
                               ├─ intent classifier  LLM (confirm / reject / correction)
                               └─ recommend()        TF-IDF + cosine + diet filter
```

---

## 3. User Flow

### 3.1 Seasoning tab (second tab, next to Chat)
- Checklist of seasoning ingredients; the user ticks what they have.
- Must be ticked **before** the chat starts — not editable mid-conversation (MVP).
- Ticked seasonings are passed to the recommender alongside the ingredient list.

### 3.2 Input
- Pasting image(s) shows preview thumbnails **inside the input box**; nothing is sent
  yet and the user can keep typing.
- Two patterns: (a) paste image(s), type text, press Enter once; (b) paste image(s),
  press Enter immediately with no text.
- **Processing starts only on Enter.** Ingredients detected across all pasted images
  are unioned into one set.

### 3.3 Processing
- No text → call `detect()` right away.
- Text → the NLP pipeline must extract **three things from one mixed sentence**:
  include ingredient, exclude ingredient, health tag
  (e.g. "have chicken and egg, no pork, want it clean").

### 3.4 Confirm loop
1. Show the full combined ingredient list (image + text) and ask the user to confirm
   — **free text only, no Quick Reply buttons.**
2. An LLM **intent classifier** reads the reply → `confirm` / `reject` /
   `confirm+correction` (e.g. "yeah that's right, but also add garlic").
3. `reject` → show a checklist to tick off wrong ingredients + a text field to add
   missing ones; on submit, **loop back to step 1** with the new list.
4. `confirm` → the final list goes straight into the recommender.

### 3.5 Reply
Built from templates. The LLM never writes the reply text.

---

## 4. Components

### 4.1 `detect()` — YOLO11 + Gemini fallback
```
Input:  a photo of ingredients
Output: [{"ingredient":"egg","confidence":0.92}, {"ingredient":"tomato","confidence":0.88}, ...]
```
- **100** ingredients have a `yolo_class_id` in `data/ingredients.json`.
- Transfer learning: use `yolo11n.pt`, **not** `yolo11n.yaml` (the latter trains from scratch).
- **Routing rule (unchanged):**
```python
score = max(all confidences in the image)   # nothing detected = 0
if score < THRESHOLD:
    → call LLM (Gemini)
else:
    → use YOLO result (only items with conf >= 0.5)
```
  The rule looks at the image's *maximum* confidence, not per-item; low-confidence
  detections are discarded to avoid false positives. Values come from `thresholds.yaml`
  (defaults if absent).

### 4.2 NLP — `extract()`
```
Input:  "I have shrimp and egg, want clean, no pork"
Output: {"ingredients": ["shrimp","egg"], "health_tags": ["clean"], "excluded": ["pork"]}
```
Pipeline: dictionary lookup → fuzzy matching (**threshold 85**) → **Trie** (prefix
collisions) → negation detection. No trained NER model (labeling cost not worth it for
a fixed vocabulary). English typos are recovered reliably; Thai typo recovery is a
documented limitation (see `concern.md`).

### 4.3 Intent classifier (NEW)
- **Input:** the user's free-text reply to the confirm-ingredients prompt.
- **Output:** `confirm` / `reject` / `confirm+correction` (mixed in one sentence).
- **Why an LLM:** keyword matching can't parse mixed sentences.
- **STILL OPEN:** which LLM API (Gemini, already used for vision, or another), prompt
  design, and error handling when the interpretation is ambiguous.

### 4.4 Recommender
- TF-IDF + cosine similarity between the user's ingredient set and each recipe's
  ingredient profile (scales fine to 400 recipes). Scoring is partial — a user is
  never required to have every ingredient.
- **Diet filter first:** filter recipes by `excluded_for` *before* computing similarity.
  AND across requested tags. An excluded ingredient drops a dish only via
  `main_ingredients`/`seasonings`, never `optional_ingredients`.
- `missing` = main ingredients only; a missing optional is not a shopping-list item.
- **Seasoning — Option A (decided):** seasonings the user ticked are **optional/bonus
  only**. A recipe missing a wanted seasoning is still recommended, just scored lower
  than one that matches the seasonings too.
  > ⚠️ **Pending code change:** `recommender/recommend.py` (docstring ~line 35,
  > `_recipe_document` ~line 95) still strips seasonings from both the recipe document
  > and the user's list. That is the *old* rule and must be changed to implement
  > Option A. The seasoning **weight** relative to main ingredients is **not decided**
  > (open item).
- > 📝 **TODO, not yet implemented:** `recommend()`'s TF-IDF vectorizer treats every
  > ingredient key identically, regardless of whether it's photo-detectable
  > (`yolo_class_id` set) or text-only (`null`). The idea, never built: weight
  > non-YOLO ingredients lower, since a user is far less likely to have *typed* a
  > text-only ingredient (e.g. `pla_ra`, `yanang`) than to have it visible in a photo.
  > This would need a per-token weight vector multiplied against the TF-IDF matrix (or
  > a second `TfidfVectorizer` fit separately), not a change to `_recipe_document()`'s
  > main×2/optional×1 repetition scheme (that solves a different problem). A note for
  > a future session to pick up deliberately, not to guess into `recommend.py`.

### 4.5 LLM — Gemini Flash Lite
**Flash Lite tier only**, verified from real account limits:

| Model | RPM | RPD | Usable? |
|---|---|---|---|
| Gemini 3.5 Flash Lite | 15 | 500 | ✅ |
| Gemini 3.1 Flash Lite | 15 | 500 | ✅ backup |
| Gemini 3.6 / 3.5 / 2.5 Flash | 5 | 20 | ❌ too limited |
| Gemini Pro | 0 | 0 | ❌ no free-tier access |

**Roles here:** (1) `detect()` fallback when YOLO isn't confident, (2) confirm/reject
intent classifier (unless the open item picks a different provider).

Rules:
- 🚫 The LLM never selects the final menu (would make the Recommender unmeasurable).
- 🚫 The LLM never composes the reply text (templates).
- Every request must be independent — never reuse a chat session, to avoid context
  contamination.
- Never list candidate classes in the prompt (e.g. "is this galangal, ginger, or
  fingerroot") — over-helping the model.
- Free-tier RPD (500) is a hard ceiling for a public web app — keep it in mind for the
  classifier, which adds an LLM call per confirm turn.

---

## 5. Data Schema (verified against the real files)

**`data/ingredients.json` — 142 entries** (116 regular ingredients + 26 seasonings).
Fields: `is_seasoning` (bool), `is_animal_product` (bool), `yolo_class_id`
(100 non-null; `null` = text-only), `synonyms[]`, `confusable_with[]`, plus `name_th`.

**`data/recipes.json` — 400 recipes**, IDs `th_001`–`th_403` with **gaps at th_059,
th_060, th_073** (IDs are never reused). Fields: `main_ingredients[]`,
`optional_ingredients[]`, `seasonings[]`, `health_tags[]`, `excluded_for[]`, nutrition
data (+ `nutrition_source`, `cook_time_min`, `recipe_source_url`).

**Health tags in use:** `clean`, `keto`, `vegetarian`, `vegan`.

**Diet filter source of truth:** `excluded_for` (single field read). Verified 100%
consistent with the `is_animal_product` derivation across all 400 recipes, zero
mismatches. **Keep `is_animal_product` as a validator** for future recipe additions to
catch human error.

---

## 6. Recipe DB Rules

- Nutrition must come from a **real, fetchable source** (Thai Food Composition
  Database / INMUCAL / Department of Health) — never self-estimated.
- Every recipe needs a real `recipe_source_url`; main/optional ingredients must come
  from the current ingredient dictionary.
- Basic seasonings live in `seasonings`, not in main/optional ingredients. (How they
  score is governed by §4.4 Option A.)
- **"Vegan" must exclude fish sauce and shrimp paste** — the most commonly missed detail.
- Health tags must be verifiable (clean / keto / vegetarian / vegan).
- Dessert/sweet dishes are allowed, not just savory. Same rules apply.
- The recipe DB must **not be split** between people — differing standards create the
  hardest-to-find bug. One owner, start to finish.
- Menu mix: authentic Thai + international dishes commonly cooked by Thais (fried rice,
  spaghetti), because detected ingredients are universal.

---

## 7. Codebase Map

| Path | Status |
|---|---|
| `data/ingredients.json`, `data/recipes.json` | **Reused as-is** |
| `nlp/extract.py` | **Reused as-is** |
| `recommender/recommend.py` | **Reused**, except the seasoning change in §4.4 |
| `api/main.py` | **Legacy — LINE webhook; to be replaced** by the FastAPI REST layer |
| `api/session.py` | **Legacy — 2.5s debounce buffer; to be replaced** (processing is now Enter-triggered) |
| `api/confirmation.py` | **Legacy — Quick Reply "anything else?" state; to be replaced** by the free-text intent-classifier loop |
| `api/mock_cv.py` | Mock `detect()` — keep until the real `detect()` is swapped in |
| `api/config.py` | Review during API rewrite |
| `tests/` | Existing tests for extract/recommend/recipes stay; `test_session.py` / `test_confirmation.py` go with their legacy modules |

**File ownership:** `data/`, `nlp/`, `recommender/`, `api/` and the web frontend are
mine. `detect()` / `best.pt` / `thresholds.yaml` belong to Person 1 — **report bugs,
don't fix them yourself.**

---

# PART B — WEB TRACK MILESTONES

- [ ] FastAPI endpoints (image upload multipart, chat turn, seasoning list)
- [ ] Frontend chat UI with image paste → thumbnails in input box, Enter-to-send
- [ ] Seasoning tab (tick before chat, locked mid-conversation)
- [ ] Intent classifier (LLM) + ambiguity handling
- [ ] Confirm/reject loop UI (checklist + add-text field → re-confirm)
- [ ] Seasoning Option A implemented in `recommend.py` (+ weight decided)
- [ ] Per-conversation state machine (extract → confirm → reject-edit → recommend)
- [ ] Swap `mock_cv` for real `detect()` + `thresholds.yaml`
- [ ] AWS deploy (instance chosen, cost checked)
- [ ] End-to-end test: real photo → detect/NLP → confirm loop → recommender → reply

(No dates set yet.)

---

## Open Items / Risks

1. **Which LLM** for the confirm/reject classifier + prompt design + ambiguity handling.
2. **AWS instance type** for YOLO inference (GPU cost control; not free tier).
3. **Seasoning weight** in the TF-IDF vector relative to main ingredients.
4. **Scope sign-off:** confirm with the academic advisor/team that this standalone web
   track running in parallel with the LINE OA track is within agreed project scope.
5. **Gemini 500 RPD quota:** the intent classifier and the `detect()` YOLO→Gemini
   fallback draw from the same 500 requests/day Flash Lite budget (15 RPM). The
   classifier fires on every confirm turn, and each `reject` loop (§3.4) triggers
   another call, so one conversation can spend several requests. Load per user is
   unmeasured; decide a mitigation (e.g. cap loop iterations, cheap keyword
   short-circuit for plain "yes"/"no", separate key/model for the classifier) before
   any public demo.

---

## License
YOLO is **AGPL-3.0**, which requires the entire codebase (including custom-trained
models) to be open source. Fix: keep the GitHub repo public with an AGPL-3.0 `LICENSE`
file (already present).

## Glossary

| Term | Meaning |
|---|---|
| PyThaiNLP | Python library for Thai text processing (word segmentation) |
| Fuzzy matching | Matching words that are close but not identical |
| Trie | Prefix tree; resolves ingredient names that are prefixes of others |
| TF-IDF | Weighting where rarer ingredients count more |
| Cosine similarity | 0–1 similarity between two vectors |
| Intent classifier | LLM step that labels a free-text reply confirm / reject / confirm+correction |
| Multipart form | HTTP upload format used to send images directly to the API |

---

# APPENDIX — Legacy: LINE OA Track (NOT targeted by this repo)

> Kept as historical reference only. Nothing below describes what this repo builds.

### L1. LINE production flow
```
User sends photo/text on LINE → Webhook receives → respond HTTP 200 immediately
→ buffer into session + wait 2.5-3s (debounce) → [image] YOLO11 / [text] PyThaiNLP
→ low conf / negation → LLM → merge → Recommender → Top-3 + have/missing + nutrition
→ template response → reply token (free)
```
Accepted image only / text only / both; multiple images merged into one session, deduped
by highest confidence, capped at 5.

### L2. LINE-specific mechanics
- **Reply token:** free, single-use, expires in 10-30s. Reply is primary; push is fallback only.
- **Quick Reply:** confirm low-confidence ingredients ("Detected onion? [Yes] [No]").
- **Biggest risk — LINE quota:** the Thai free OA plan has a limited monthly message
  quota, no top-up; reply messages don't count, push/broadcast/multicast do. Mitigation:
  Reply as primary, debounce 2.5-3s, templates, 2 OA accounts (dev/demo), daily check of
  `GET /v2/bot/message/quota/consumption` in weeks 8-10.
- **Deployment:** laptop + Cloudflare Tunnel, chosen because cloud cold starts (20-60s)
  can exceed the reply token lifespan; demo day always ran locally.

### L3. Old budget (LINE capstone)
Colab Pro ×2 months 700-850 ฿; LLM API 0 ฿ (or 70-150 ฿ for two tiers); test groceries
150-250 ฿. Total 850-1,250 ฿ (~425-625 ฿ per person).

### L4. "Why not just use ChatGPT?" (capstone framing)
Concede first (casual users are fine with ChatGPT); "free for the user" ≠ "free for
whoever builds the service" (1,000 users × 3 calls/day = 90,000/month vs. a 500/day free
cap); measurable wins: fewer steps, remembered health profile, verified recipe database,
sourced nutrition, speed (0.2s vs 3-8s), 100% consistency, structured JSON output;
unmeasured wins: offline use, privacy, full control over versioning.

### L5. Original 40-recipe / 12-15 class scale
The capstone began with a 40-menu DB and 12-15 YOLO classes; both are superseded by the
numbers in §5 above.

### L6. Old Person 2 roadmap and handoffs
The 12-week Person 2 roadmap (Weeks 1-12) and the four cross-handoffs
(`ingredients.json` → P1 wk 1, `extract()` → P1 wk 5, `best.pt`+`detect()` ← P1 wk 8,
`thresholds.yaml` ← P1 wk 8) live in the LINE OA repo and in the git history of this file.
Test-B photo shoot, Test-A/B splits and the experiment tables belong to that repo too.

---

*Rewritten for the standalone web chatbot track. Full prior version: `git show HEAD:Claude.md`.*
