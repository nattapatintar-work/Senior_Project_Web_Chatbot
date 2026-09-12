# 🍳 Ingredient-to-Recipe Chatbot — Full Project Summary & Person 2 Roadmap

> Combined reference document: project overview + detailed 12-week roadmap for Person 2 (Language & System).

---

# PART A — PROJECT OVERVIEW

## 1. What This Project Is

### 1.1 The Starting Problem
People open the fridge, see a pile of random ingredients, and don't know what to cook. Ingredients expire and get thrown away — both a convenience problem and a household food-waste problem.

### 1.2 What We're Building
A **LINE chatbot** — users send a photo of ingredients, type a text message, or both, and the bot recommends recipes with nutrition info, filtered by health condition (clean / keto / vegetarian).

### 1.3 ⚠️ The Reframed Research Angle
Pilot testing found that **the LLM identifies ingredients with very high accuracy already.** This forced a reframe:

| | Old Frame | **New Frame** |
|---|---|---|
| Question | "Is our model more accurate?" | **"If the LLM is already more accurate, is training our own model still worth it — and at what point does it become worth it?"** |
| Problem with old frame | If the answer is "no," the project is uninteresting | **Can't be answered without experimentation**, and has genuine practical value |
| Thai herbs group | Would require training galangal/ginger/fingerroot | **Cut** — no usable images available, saves 10-12 hours |

> 📝 Reframing based on real pilot results looks more scientific than clinging to an original hypothesis the data doesn't support.

### 1.4 ✅ The Original Goal Is Still Fully Intact

| | Originally | Now |
|---|---|---|
| What problem does the system solve? | People with ingredients who don't know what to cook | **Same** |
| What is the deliverable of the project? | A chatbot that helps users | **Cost-effectiveness numbers comparing two approaches** |

> 📝 The chatbot shifted status from "the deliverable" to **"the context that makes the comparison meaningful"** — without it, the project becomes a floating benchmark that can't explain why 0.2s vs 5s latency actually matters.

---

## 2. Core Objective

### 2.1 Main Research Question
> For ingredient identification used to recommend recipes, **when a large language model is already more accurate, is it still worth training a dedicated detection model — and where is the break-even point** — when considering cost, speed, and reliability?

### 2.2 Four Objectives

| # | Objective |
|---|---|
| 1 | Develop an image-based ingredient detection model (YOLO11) and a Thai text extraction system (PyThaiNLP) |
| **2** | **Evaluate comparative cost-effectiveness between the specialized model and the LLM across 4 dimensions** ← core of the project |
| 3 | Design and evaluate a Hybrid Routing mechanism, finding the budget break-even point |
| 4 | Build a recipe recommendation system and chatbot to serve as **a real testing environment** |

**Details of Objective 4:**
1. Build a recipe database of 40 menus (main/optional ingredients + seasonings + health tags + reference nutrition)
2. Build a recommendation system (TF-IDF + cosine + health filter + partial match)
3. Build a chatbot that accepts multiple input types (image/text/both + session buffer + Quick Reply)
4. Apply Hybrid Routing from Objective 3 in practice (reading from `thresholds.yaml`)
5. Evaluate recommendation quality on 30-40 cases, measured with Precision@3, Recall@5

> ⚠️ Don't write Objective 4 as "for user convenience" — that's a weak justification. Write it as **"to serve as a real testing environment."**

### 2.3 Measuring 4 Dimensions

| Dimension | How Measured | Expected Result |
|---|---|---|
| Accuracy | Image-level F1 | LLM wins (expected 5-10%) |
| Cost | Baht per 1,000 calls | **YOLO wins decisively** (free after training) |
| Speed | Median + p95 latency | **YOLO wins decisively** (0.2s vs 3-8s) |
| Reliability | Consistency + nutrition accuracy | **Our system wins** |

**Expected headline finding:**
> "Even though the LLM is 8% more accurate, using a hybrid approach at a 30% budget cuts cost by 70% and average latency by 60%, at a cost of only 3% accuracy."

---

## 3. Component Breakdown

### 3.1 CV — YOLO11

**What it does:**
```
Input:  a photo of ingredients
Output: [{"ingredient":"egg", "confidence":0.92},
         {"ingredient":"tomato", "confidence":0.88},
         {"ingredient":"onion", "confidence":0.31}]
```
> Confidence (0-1) decides when to call the LLM.

**Classes trained: 12-15 classes** — egg, chicken, pork, shrimp, tomato, onion, garlic, chili, carrot, cabbage, mushroom, lime, cucumber
**Data source:** Roboflow Universe + supplemental Google Images/Kaggle

**Training method:** Transfer Learning + Fine-tuning
```python
from ultralytics import YOLO
model = YOLO("yolo11n.pt")   # ← COCO weights = transfer learning
model.train(data="data.yaml", epochs=100, save_period=10)   # ← full fine-tuning
```
> ⚠️ Trap: must use `yolo11n.pt`, NOT `yolo11n.yaml` (the latter trains from scratch).

**Image count:**
| Level | instances/class | Expected mAP |
|---|---|---|
| Minimum | 100-150 | 0.5-0.65 |
| Recommended | 200-250 | 0.65-0.75 |

Target: 15 classes × 200 = ~3,000 instances ≈ 1,200-1,800 images (an instance ≠ an image — one image with 3 tomatoes = 3 instances)

> 💡 Diversity matters more than volume — 200 varied images beat 500 near-identical ones.

**Dataset composition recommended:**
| Type | Share | Reason |
|---|---|---|
| Single/multiple ingredients on table/cutting board | 60-70% | Matches real user behavior most closely + easy to label |
| In fridge / in bags / occluded | 20-30% | Trains the model to handle hard conditions |
| Plain stock photos | 10-20% | Helps learn basic per-class appearance |

**Why not shoot entirely inside the fridge:** most fridge items are packaged (model learns "box" instead of "egg"), heavy occlusion (only 20-30% of object visible), labeling 3-4x slower, and real users typically take items out onto the table to photograph rather than photographing the whole fridge.

### 3.2 NLP — PyThaiNLP + Dictionary

```
Input:  "I have shrimp and egg, want something clean, no pork"
Output: {"ingredients": ["shrimp","egg"], "health_tags": ["clean"], "excluded": ["pork"]}
```

**3 capabilities:**
| # | Capability | Example |
|---|---|---|
| 1 | Thai word segmentation (Thai has no spaces) | tokenize the sentence into words |
| 2 | Fuzzy matching | misspelled ingredient → corrected ingredient |
| 3 | Negation detection | "no pork" → exclude pork |

> 📝 We deliberately don't train our own NER model — labeling thousands of sentences would take 3-4 weeks, not worth it for just 15-20 vocabulary terms.

**Why NLP is essential — 3 reasons:**
1. Fills in items the image can't see (e.g. shrimp paste in a jar, not visible in photo)
2. Health conditions can only come from text, never from an image
3. Corrects misdetections ("that's not pork, it's chicken")

> This is what makes the system genuinely **multimodal**, not just CV and NLP placed side by side.

### 3.3 Recommender — Content-Based Filtering

```
Input:  ["chicken","garlic","chili"], health=["clean"]
Output: [{"name":"Pad Kra Pao Chicken", "score":0.87,
          "have":["chicken","garlic","chili"],
          "missing":["holy_basil"],
          "nutrition":{"kcal":450,...}}]
```

Menus are converted into vectors; user ingredients are converted the same way, then compared via cosine similarity. TF-IDF weighting ensures rare ingredients (like shrimp) matter more than ingredients present in every recipe (like oil). Scoring is partial — a user is never required to have every ingredient, since no one has a complete set at home.

**40-menu database** covers Thai household dishes plus international dishes commonly cooked by Thais (fried rice, pad see ew, spaghetti) — because detected ingredients are universal, restricting the menu database to authentic Thai food only would create unmatchable cases.

> ⚠️ Must reference real nutrition tables (Thai Food Composition Database / INMUCAL / Department of Health) — self-estimated nutrition data invalidates the nutrition experiment entirely.

### 3.4 LLM — Gemini 3.5 Flash Lite

**Must use the Flash Lite tier only**, verified from real account limits:

| Model | RPM | RPD | Usable? |
|---|---|---|---|
| Gemini 3.5 Flash Lite | 15 | 500 | ✅ |
| Gemini 3.1 Flash Lite | 15 | 500 | ✅ backup |
| Gemini 3.6 / 3.5 / 2.5 Flash | 5 | 20 | ❌ too limited |
| Gemini Pro | 0 | 0 | ❌ no free-tier access |

**3 roles:**
1. **Image comparison baseline ⭐** — run on every image in the experiment
2. Text comparison baseline — run on 60 sentences
3. Runtime fallback — when YOLO isn't confident

🚫 The LLM never selects the final menu (would make Recommender unmeasurable)
🚫 The LLM never composes the reply text (templates are faster and save reply-token lifespan)

**LLM testing rule:** every request must be independent — never ask within the same chat session, to avoid **context contamination** where the LLM sees prior context and "cheats" by inferring the topic, inflating results unrealistically.

> ⚠️ Never list candidate classes in the prompt (e.g. "is this galangal, ginger, or fingerroot") — that's over-helping the model and makes the comparison unfair.

---

## 4. Flow

### 4.1 Production Flow
```
User sends photo/text on LINE
        ↓
Webhook receives → respond HTTP 200 immediately
        ↓
Buffer into session + wait 2.5-3s (debounce)
        ↓
   ┌────┴────┐
[image]     [text]
YOLO11      PyThaiNLP
   ↓            ↓
max conf    extraction failed /
< threshold? negation detected?
   ↓            ↓
  LLM          LLM
   └────┬───────┘
        ↓
Merge ingredients + health conditions
        ↓
Recommender: TF-IDF + cosine + health filter
        ↓
Top-3 menus + have/missing + nutrition
        ↓
Template response → reply token (free)
```

**Accepts 3 input types:** image only / text only / both. Multiple images merge into one session, deduped by keeping highest confidence, capped at 5 images.

### 4.2 LLM Trigger Condition
```python
score = max(all confidences in the image)   # nothing detected = 0
if score < THRESHOLD:
    → call LLM
else:
    → use YOLO result (only items with conf >= 0.5)
```
> 💡 Rule looks at the image's maximum confidence, not per-item — if egg is high-confidence, don't call the LLM even if onion confidence is low; low-confidence detections get discarded to avoid false positives (shadows, stains mistaken for ingredients).

### 4.3 Research Flow — a Separate Concern
```
eval/run_experiment.py  → runs YOLO + LLM on 100% of images   (one-time run)
api/main.py              → production system, uses routing    (demo day)
```

---

## 5. Evaluation

### 5.1 ⚠️ mAP Cannot Be Compared Across Systems
YOLO produces bounding boxes; the LLM only produces a name list — mAP can't be computed for the LLM. **Image-level Precision/Recall/F1** is the main comparison metric across all 3 systems.

### 5.2 Test Sets
| Set | Size | Split |
|---|---|---|
| Test-A (from internet) | 60 images | val 20 / test 40 |
| Test-B (self-shot) ⭐ | 60 images | val 20 / test 40 |
| Text | 60 sentences | dev 20 / test 40 |
| Recommendations | 30-40 cases | ground truth from outsiders |

**Why both Test-A and Test-B matter:** the gap reveals **domain shift** — how much a model trained on public images degrades when it meets real-world conditions.

```
YOLO on Test-A: F1 ~0.80   ← same distribution as training data
YOLO on Test-B: F1 ~0.55   ← drops sharply
LLM  on Test-A: F1 ~0.85
LLM  on Test-B: F1 ~0.82   ← barely drops
```

🚨 The test set is opened exactly once, in Week 10 — never used to tune thresholds.
⚠️ Test-B must never be used for training — if accidentally mixed in, the entire experiment is invalidated.

### 5.3 Finding the Threshold via "Choose a Budget"
| Budget (% sent to LLM) | F1 | Cost/1000 | Avg latency |
|---|---|---|---|
| 0% (YOLO only) | 0.62 | 0 ฿ | 0.2s |
| **30%** ⭐ | **0.84** | 45 ฿ | 1.5s |
| 50% | 0.88 | 75 ฿ | 2.4s |
| 100% (LLM only) | 0.91 | 150 ฿ | 4.2s |

*(illustrative numbers)* — this is the project's main result.

### 5.4 Random Baseline — Must Not Be Cut
| Method of choosing which images go to LLM (30% budget) | F1 |
|---|---|
| Random | 0.72 |
| Confidence-based | **0.84** |

> This is the most important test — "is hybrid better than pure YOLO" is trivially true. The real question is whether the improvement comes from **smart routing** or just from calling the LLM more.

### 5.5 Two Additional Experiments — Now Core, Not Optional

**① Consistency test (~1hr):** send the same image through the system 5 times, measure variance. YOLO should answer identically every time; the LLM may vary 1-2 times out of 5 — an architectural limitation of LLMs, not something that goes away with newer versions.

**② Nutrition experiment (~2hr):** ask the LLM 30 nutrition questions, compare against real reference tables. Must be asked separately from menu recommendation, or you can't isolate whether an error is a nutrition error or a wrong-menu error.

### 5.6 Error Analysis
| Image condition | YOLO F1 | LLM F1 |
|---|---|---|
| On table | 0.78 | 0.85 |
| In fridge (heavy occlusion) | 0.45 | 0.79 |

> The widening gap under hard conditions is a strong finding — the specialized model degrades much faster under occlusion, which is the realistic household scenario.

---

## 6. Answering "Why Not Just Use ChatGPT?"

**Layer 1 — Concede first:** "For a casual user who's just curious, ChatGPT is perfectly sufficient. This project doesn't claim to be more convenient or more accurate at reading images."

**Layer 2 — "Free for the user" ≠ "free for whoever builds the service":** 1,000 users × 3 calls/day = 90,000 calls/month; the free tier caps at 500/day — it simply cannot support that. The real question isn't "what should one user use" but "how should whoever builds this service invest."

**Layer 3 — Dimensions where our system genuinely wins (measurable):**
| Aspect | Asking ChatGPT | Our system |
|---|---|---|
| Steps | Open app → photo → type prompt → read | Send photo on LINE → done |
| Health conditions | Retype every time | Remembered in profile |
| Recipes | Freshly generated, may hallucinate | Verified database |
| Nutrition | Model's guess | Real sourced data |
| Speed | 3-8s | 0.2s |
| Consistency | Repeat query, different answer | 100% consistent |
| Output | Free text | Structured JSON, usable by other systems |

**Layer 4 — Wins that can't be measured in this project (used in discussion):** works offline (relevant for smart fridges/IoT), privacy (kitchen photos are personal; free-tier LLMs may train on them), full control and improvability (fix a misdetection by adding training images; version doesn't silently change).

**Short answer:**
> "This project doesn't claim to be better than ChatGPT. It answers: if you were building a real service with many users, how much could training your own model reduce cost, at what accuracy trade-off, and where's the right cutoff point?"

---

## 7. Budget

| Item | Cost |
|---|---|
| Colab Pro × 2 months | 700-850 ฿ |
| LLM API | 0 ฿ (free tier sufficient) or 70-150 ฿ if comparing 2 tiers |
| Ingredients for test shooting (normal groceries) | 150-250 ฿ |
| **Total** | **850-1,250 ฿ → ~425-625 ฿ per person** |

**Colab Pro:** ~100 compute units/month, T4 uses ~2 CU/hr; estimate 15-20 training runs × 2-3hrs = 80-100 CU. No background execution on Pro (that's Pro+ only) — must keep the tab open. Use `save_period=10` to checkpoint to Drive, and Kaggle as backup (30 free GPU hrs/week).

**Biggest risk — LINE quota:** the Thai free LINE OA plan allows a limited number of messages/month with no top-up option; exceeding it silences the bot until next month. Reply messages don't count toward quota; push/broadcast/multicast do. Mitigation: rely on Reply as primary, push as fallback only; debounce 2.5-3s; use templates instead of re-calling the LLM on the slow path; create 2 LINE OA accounts (dev/demo) to double the free quota; check quota daily via `GET /v2/bot/message/quota/consumption` during weeks 8-10.

**Deployment — laptop + Cloudflare Tunnel:** chosen because cloud cold starts (20-60s) can exceed the reply token's lifespan (10-30s). No cold start, 100% free HTTPS, easiest debugging, `.pt` weights work directly without ONNX conversion. Demo day must run on the local machine — never risk the cloud on presentation day.

**License:** YOLO uses **AGPL-3.0** (a strict license requiring the entire codebase, including custom-trained models, to be open source). Free fix: make the GitHub repo public with an AGPL-3.0 LICENSE file — also good for the project (reproducibility, can be linked in the report).

---

# PART B — PERSON 2 ROADMAP (Language & System)

> Final deliverable: `recommend(ingredients, health_tags, excluded) → Top-3 menus`

## Overview

Your work splits into 4 major chunks:
1. **NLP** — turn Thai text into structured data the system can use (PyThaiNLP)
2. **Recipe DB + Recommender** — the menu database and the matching/scoring system
3. **LINE Bot / System** — receive user input, reply, manage sessions
4. **Test-B photo shoot** — help Person 1 with image data collection (Week 2 only)

Principles to hold onto throughout:
- **Skeleton First** → write every function's skeleton by Week 2 (fake internals are fine at first), then upgrade later
- **Never edit Person 1's files** — report bugs, don't fix them yourself
- **dev/test are separate** — you can tune your dictionary/recommender on the dev set anytime, but the test set is off-limits (Person 1 holds it, opened only in Week 10)

## Week 1 — Laying the Foundation

**Main task: `ingredients.json` + synonyms**
Build the "central dictionary" that connects CV (YOLO), NLP, and Recommender.
```json
{
  "egg": {
    "name_th": "ไข่ไก่",
    "yolo_class_id": 0,
    "synonyms": ["ไข่", "ไข่ไก่", "ไข่เป็ด", "egg"]
  }
}
```
> This is the single most common failure point — if CV says "chicken egg" and NLP says "egg" with no synonym link, the recommender can't recognize them as the same ingredient.

**Checklist:**
- [x] Draft a list of 12-15 ingredients (coordinate with Person 1 to match what they'll train YOLO on)
- [x] Day 4: 🔒 **Lock the ingredient list jointly with Person 1** (should not change easily after this)
- [x] Days 5-7: write the skeleton for all files + understand Person 1's contract tests
- [x] 📤 **Deliverable:** hand `ingredients.json` to Person 1 this week (if late, Person 1 can't merge the dataset)

> 💡 **Beginner note — what's a contract test?** A test suite that checks whether your function returns data in the agreed shape (does it have the right keys, is confidence between 0-1, etc). If it fails, you're blocked from pushing to main. It's a checkpoint that prevents things from breaking later when everyone's code comes together.

## Week 2 — Skeleton + Photo Shoot

**Task 1: LINE Bot skeleton (mock)**
Make the LINE Bot actually receive messages/photos and actually reply — using fake (mock) values for now.
```python
# nlp/extract.py — example mock
def extract(text):
    return {"ingredients": ["shrimp"], "health_tags": [], "excluded": []}
```
Goal by end of Week 2: send a message to the LINE Bot and get a real reply back (even if the reply comes from mock data) + contract tests passing.

**Task 2: Shoot + label batch_B (30 images)**
- Shoot per the recommended split: single/multiple items on table ~70%, in-fridge/occluded ~20-30%
- Don't shoot it all in one day — spread across 2-3 days at different times for lighting variety
- Agree on the labeling guideline with Person 1 before shooting: does >70% occlusion count? does an item cut off at the frame edge count? etc.

**Checklist:**
- [x] LINE Bot replies successfully with mock data
- [x] Contract tests pass
- [ ] batch_B fully shot (30 images) + metadata logged (filename, ingredients, lighting, scene_type, occlusion)
- [ ] Cross-check: label 10 of Person 1's images to align standards

## Weeks 3-4 — Recipe DB (Your Heaviest Task)

**Main task: 40-recipe database**
```json
{
  "id": "th_001",
  "name_th": "ผัดกะเพราไก่",
  "main_ingredients": ["chicken", "garlic", "chili", "holy_basil"],
  "optional_ingredients": ["egg", "onion"],
  "seasonings": ["fish_sauce", "oyster_sauce", "sugar"],
  "health_tags": ["clean"],
  "excluded_for": ["vegetarian", "vegan"],
  "nutrition": {"kcal": 450, "protein": 32, "fat": 18, "carb": 35},
  "nutrition_source": "INMUCAL",
  "cook_time_min": 15
}
```

⚠️ **Critical cautions:**
- Must reference real nutrition data (Thai Food Composition Database / INMUCAL / Department of Health) — never estimate; otherwise the nutrition experiment is invalid
- Basic seasonings (fish sauce, sugar, etc.) don't count toward ingredient matching — everyone has them at home
- **The definition of "vegan" must include fish sauce and shrimp paste** ← the most commonly missed detail
- The Recipe DB must **not be split with anyone else** — differing standards (one person considers Pad Kra Pao "clean," the other doesn't) creates the hardest-to-find bug of all. Do it solo, start to finish.
- **Note: dessert/sweet dishes are allowed in the recipe database, not just savory dishes** — this was clarified after an earlier session assumed savory-only. Same rules apply: main/optional ingredients from the current dictionary, real fetchable nutrition source, real recipe_source_url.

**Checklist:**
- [x] Find a reliable nutrition source before you start filling data
- [x] Fill in all 40 menus (mix of authentic Thai + international dishes commonly cooked by Thais, e.g. fried rice, spaghetti)
- [x] Define health tags so they're verifiable (clean/keto/vegetarian/vegan)
- [x] Wait for the 🔒 canonical ingredient list window to close (Day 4 of Week 1) before you start filling — never fill before it's locked

## Week 5 — NLP Comes Alive

**Main task: NLP extraction + fuzzy matching**
```
Input:  "I have shrimp and egg, want clean, no pork"
Output: {"ingredients": ["shrimp","egg"], "health_tags": ["clean"], "excluded": ["pork"]}
```
Three capabilities required:
1. **Thai word segmentation** (PyThaiNLP) — Thai has no spaces, so you need a tokenizer first
2. **Fuzzy matching** — catch near-miss misspellings
3. **Negation detection** (also this week) — detect "no," "without," etc.

> 💡 Don't train your own NER model (a model that learns to find ingredient names in a sentence) — that would need thousands of labeled sentences, not worth it for just 15-20 vocabulary terms. Dictionary + fuzzy matching is enough.

**Checklist:**
- [x] Thai word segmentation via PyThaiNLP working
- [x] Fuzzy matching catches misspellings *(English typos reliably; Thai typo recovery is a documented limitation — see concern.md, Week 5 session log)*
- [x] Negation detection catches "no X," "without X," etc.
- [x] **Measure on your own dev set** (20 sentences) — no need to send this to anyone yet, tune freely *(22 sentences, 100% pass, `data/nlp_dev_set.json`)*

## Week 6 — Check In + Be Ready for Extra Work

- 10-minute sync with Person 1: who's more overloaded? If Person 1 is stuck on dataset merging (Weeks 3-4), some work may get shifted to you — e.g. writing the 60 test sentences, entering more nutrition data, or helping with the literature review.
- Prepare mentally for this possibility — it's not abnormal.

## Week 7 — Recommender (The Heart of Your Side)

**Main task: Recommender via Content-Based Filtering**
```
Input:  ["chicken","garlic","chili"], health=["clean"]
Output: [{"name":"Pad Kra Pao Chicken", "score":0.87,
          "have":["chicken","garlic","chili"],
          "missing":["holy_basil"],
          "nutrition":{"kcal":450,...}}]
```
**How it works:**
- Convert each menu into a vector representing which ingredients it uses
- Apply TF-IDF weighting — rare ingredients (like shrimp) carry more weight than ingredients present in every recipe (like oil)
- Measure similarity via cosine similarity (0-1, closer to 1 = more similar)
- Scoring is partial — don't require a complete ingredient match, since no one has a full fridge

> 💡 **Beginner note:** Don't worry about this needing to be "cutting-edge research" — the project docs explicitly say this is **implementation, not research**. TF-IDF + cosine is a standard, well-established method — nothing new needs to be invented here.

**Checklist:**
- [x] Convert menus into vectors
- [x] Compute TF-IDF + cosine similarity
- [x] Filter by health tags (excluded_for) *(AND across requested tags; excluded ingredients drop a dish only via `main_ingredients`/`seasonings`, never `optional_ingredients` — see `concern.md` session log)*
- [x] Display "have" vs "need to buy" clearly separated *(`missing` is main-ingredients-only; a missing optional is not a shopping-list item)*
- [x] Measure on your dev set first *(`data/recommender_dev_set.json`, 8 cases, all passing — `tools/run_recommender_dev_set.py`)*

## Week 8 — Complete the Chat System

Several tasks converge this week:

| Task | Details |
|---|---|
| Session + debounce | merge photo+text that arrive at different times; wait 2.5-3s before processing |
| Reply token strategy | use **Reply** as primary (free, doesn't count toward quota); push only as fallback |
| Quick Reply | confirm low-confidence ingredients, e.g. "Detected onion? [Yes] [No]" |
| Template response | assemble replies via template (not LLM — faster and preserves reply-token lifespan) |

⚠️ Thai free LINE OA plan has a limited monthly message quota with no top-up option. Reply messages don't count toward quota; Push/Broadcast do — so design to rely on Reply as much as possible.

📤 **Receiving from Person 1 this week:** `best.pt` + `detect()`, and `thresholds.yaml` — **not blocking**; if Person 1 isn't ready, keep using mocks, no need to wait.

**Checklist:**
- [ ] Session buffer + debounce working correctly (test sending photo+text out of order)
- [ ] Reply token used as primary, with push fallback
- [ ] Quick Reply working for low-confidence cases
- [ ] Template response complete: menu + have/missing + nutrition

## Week 9 — Swap Mocks for the Real Thing

- Replace all mock functions with the real components from Person 1 (`detect()`, `thresholds.yaml`)
- Test end-to-end: real photo → YOLO/LLM → NLP → Recommender → reply
- Because Skeleton First was followed from the start, **this step should require no "re-merging."** If problems appear, it means the interface had an unclear agreement somewhere from the beginning.

## Week 10 — Test Set Opens (Once)

- Person 1 opens the test set to measure real results (you don't touch this test set)
- Your side: **fix bugs** found during end-to-end testing
- Careful: if you find a bug in Person 1's code, **report it, don't fix it yourself**

## Weeks 11-12 — Analysis + Report Writing

**Chapters you're responsible for writing:**
- Background + literature review
- Methodology: NLP + Recommender + System
- Conclusion + limitations (half, then you merge with Person 1's half)

## 📤 4 Cross-Handoff Points (Critical — Don't Miss These)

| # | From→To | What | Week | If You're Late |
|---|---|---|---|---|
| 1 | **You → Person 1** | `ingredients.json` | 1 | Person 1 can't merge the dataset |
| 2 | **You → Person 1** | `extract()` | 5 | Person 1 can't build the LLM text baseline |
| 3 | Person 1 → You | `best.pt` + `detect()` | 8 | Not blocking — keep using mocks |
| 4 | Person 1 → You | `thresholds.yaml` | 8 | Not blocking — use default values |

> Notice that the first two handoffs (Weeks 1 and 5, both from you) block Person 1's progress — these deserve extra priority.

## 📁 Files You Own (No One Else Edits These)
```
data/ingredients.json
data/recipes.json
data/test_b/batch_B/          (photos you shot)
nlp/
recommender/
api/
```

## 🧠 Key Technical Terms (Beginner-Friendly Glossary)

| Term | Plain-English Meaning |
|---|---|
| PyThaiNLP | A Python library for processing Thai text, e.g. word segmentation |
| Fuzzy matching | Matching words that are close but not exactly spelled the same |
| TF-IDF | A weighting method — rarer terms/ingredients get more weight, more importance |
| Cosine similarity | A 0-1 number showing how similar two things are |
| Debounce | Waiting briefly before processing, in case more data arrives (prevents duplicate firing) |
| Reply token | A free reply code from LINE, usable only once, expires fast (10-30s) |
| Contract test | A test suite checking whether your code returns data in the agreed format |
| Overfitting | When a model/dictionary is tuned so well to data it's seen that it fails on new data |

---

*Source: senior_project_summary.md — full project summary document*
