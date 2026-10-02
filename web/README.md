# FoodFridgeGreen web frontend

A static, framework-free, build-step-free chat UI for the FastAPI backend in `api/`.
Plain HTML + CSS + vanilla JS; open it over HTTP and it works. The look comes from
`design_reference/Main.dc.EXACT.html` (colors, spacing, fonts and components ported value for value);
the behavior comes from the real backend, not the design's mock data.

```
web/
  index.html          shell: tabs, chat view, seasoning view, composer
  css/styles.css      the design's tokens/components (+ clearly marked "extension" rules)
  js/config.js        API_BASE (the one file you normally edit)
  js/data.js          GENERATED: 26 seasoning tiles + key -> Thai name map (from data/ingredients.json)
  js/logic.js         pure decisions (chips, cards, error mapping, "show more", confirm corrections) - unit-tested under Node
  js/api.js           fetch wrapper: timeouts, multipart, one normalised error shape
  js/images.js        photo prep: decode, downscale to <=1600 px JPEG, thumbnails
  js/app.js           state, rendering, the conversation flow
  tests/*.test.js     node --test (no dependencies)
```

## How it works

```
browser (this page) -> nginx -> FastAPI (api/app.py, one uvicorn worker)
```

| User does | Route | What the backend runs |
|---|---|---|
| Ticks seasonings, confirms | `POST /seasoning` | creates the session; locked once the chat starts |
| Sends photos | `POST /detect` | YOLO (`api/mock_cv.py`); the confidence cutoff is `data/thresholds.yaml` |
| Sends text | `POST /extract_bert` | **BERT NER first** (`nlp/extract_bert.py`). If BERT finds nothing or is unsure, **a Claude model** (default `claude-sonnet-5`, env `EXTRACTION_LLM_MODEL`) is asked instead. If the model folder is missing, or the LLM call fails or there is no API key, the **keyword extractor** (`nlp/extract.py`) answers. Words tagged as ingredients that the dictionary does not know come back in `unknown`. |
| Replies to "is this list right?" | `POST /confirm` | **Claude Haiku 4.5** classifies the reply (confirm / reject / confirm+correction / unclear); the keyword classifier answers when there is no key or the call fails. |
| Ticks wrong items / adds text after a reject | `POST /correct` | keyword `extract()` for the added text |
| Confirms the list | `POST /recommend` | TF-IDF + cosine with the diet filter (`recommender/recommend.py`); no LLM |
| (page load / monitoring) | `GET /health` | `{"status","detector","bert"}` |

`POST /extract` (the keyword extractor alone) is not called by the UI; it stays available as a manual fallback (switch the string in `js/api.js`).

Rules the UI mirrors from the backend:
- The LLM never writes the reply text and never picks the menu; replies are templates in `js/app.js`.
- Only typed "no X" (for example "ไม่เอาหมู") bans dishes, and only those appear under the "ไม่เอา" chip group. Taking an ingredient out at the confirm step, or ticking it in the checklist, just removes it from the list (shown as a struck-through chip) and does **not** ban dishes.
- Words the dictionary does not know are listed in a short note under the bubble; the confirm flow carries on.
- The category picker (ทั้งหมด / อาหารคาว / ขนมหวาน, shown with the ingredient list) is sent as `category` on `POST /recommend` (no new route): `savory` and `dessert` are hard filters, `all` applies no category filter (the data has only savory and dessert recipes, so it is their union), and the choice resets to `all` every round.

## Configuration

**Frontend:** `js/config.js` holds `API_BASE`. `""` means same origin (nginx serves the page and the API on one address), a URL points to another server. `?api=<url>` overrides it for one page load.

**Backend environment variables** (names only; defaults, meaning and what breaks without them are in `.env.example` and `docs/DEPLOY.md`):
`ANTHROPIC_API_KEY`, `EXTRACTION_LLM_MODEL`, `BERT_NER_MODEL_PATH`, `SESSION_TTL_SECONDS`, `CORS_ORIGINS`, `TRUST_FORWARDED_FOR`.
The app runs without any of them: with no API key it uses the keyword classifier/extractor, and without the BERT weights it uses the keyword extractor.

## Run it locally

**Against a local backend (recommended for development)**

```bash
# terminal 1 - backend, from the repo root; CORS_ORIGINS lets the page on :8080 call it
CORS_ORIGINS=http://localhost:8080 python -m uvicorn api.app:app --port 8000
# terminal 2 - static files
cd web && python -m http.server 8080
```

Open <http://localhost:8080/?api=http://localhost:8000>. (PowerShell: `$env:CORS_ORIGINS="http://localhost:8080"` before starting uvicorn.)

- Put a real `ANTHROPIC_API_KEY` in `.env` (copy `.env.example`) to use the LLM paths; leave it out to run on the keyword paths.
- `models/bert_ner/model.safetensors` and the YOLO `.pt` file are git-ignored. Without the first, text goes through the keyword extractor; without the second, `/detect` answers 503 (`GET /health` shows both states).
- Use a single uvicorn worker: chat sessions and rate limits live in that process's memory.
- Don't open `index.html` by double-clicking (`file://`): the page's origin becomes `null`, which browsers block for API calls.

**Deploying** (nginx, systemd, model files, environment, smoke tests, rollback): see `docs/DEPLOY.md`. The nginx rule must list every route above, including `/extract_bert`.

## What follows the design, and what is added

Ported from the design: the 390 px phone layout, Chat / Seasoning tabs with the lock icon, the 26-tile seasoning grid and its
confirm/pending/locked states, the gate ("ยืนยันเครื่องปรุงก่อนเริ่มแชท"), bubbles, typing indicator, ingredient chips
(plain / struck / +added), recipe cards (rank, minutes, kcal, tags, ดูสูตร, main-ingredient and seasoning have/miss chips), the
composer with thumbnails, and the design's scroll-anchoring rule.

Real behavior the mock only pretended: every step calls the backend (`/seasoning`, `/detect`, `/extract_bert`, `/confirm`, `/correct`,
`/recommend`), the seasoning tab locks when the server locks it, "new chat" keeps your ticks (localStorage) but needs a re-confirm.

Additions the design does not show (built in the same visual language, marked `extension` in the CSS):

| Addition | Why |
|---|---|
| Correction checklist (tap wrong items, add text, "อัปเดตรายการ") | the backend's `reject` -> `/correct` loop has no design |
| "ไม่เอา" and "เงื่อนไข" chip groups | typed exclusions and health tags are central to the backend |
| A corrected/edited list is shown and confirmed again | real stage is `awaiting_confirm`; the mock jumped to results |
| Re-ask bubble for an `unclear` reply | the classifier's fourth intent |
| Note for ingredient words the dictionary does not know | `ExtractResponse.unknown` |
| "ขอเพิ่ม"/"more" only when it is the whole message | the mock's `/เพิ่ม/` also matched "เพิ่มกระเทียม" |
| Up to 5 photos, paste-to-attach, downscale to <=1600 px JPEG | backend limit is 5 x 8 MB; phone photos are often bigger |
| Error bubbles with "ลองอีกครั้ง", session-expiry recovery, toast | network failure, 429, 404 session gone, 503, 413, 422 |
| Visible keyboard focus, `aria-live` chat log, reduced-motion respect | accessibility |

## Tests

```bash
node --test web/tests/*.test.js              # logic + API wrapper, no dependencies (list the files: a bare directory fails on Node 24)
python -m pytest -q                          # whole backend suite (no real API calls: tests/conftest.py blocks them)
python -m pytest tests/test_web_api.py tests/test_web_data.py   # the web API contract and data.js sync
python tools/gen_web_data.py                 # regenerate data.js after editing the ingredient dictionary
```

## Known limits

- Chat history lives in the page; a refresh starts a new chat (the seasoning ticks are remembered, the server session is not resumed).
- Server sessions expire after 1 hour idle and are lost on a restart; the UI rebuilds one silently and asks you to resend.
- Rate limits are per client address: `/detect` 5/min, everything else 10/min. The UI shows a "ส่งถี่เกินไป" bubble with retry. Behind nginx `TRUST_FORWARDED_FOR=1` is required, otherwise all visitors share one bucket.
- The first text message after a server restart is slow (the BERT model is loaded then).
- Text like "ไม่เอาหมู" typed into the checklist's add field is applied and banned by the server, but `/correct` does not echo the exclusion list, so that bubble does not show a "ไม่เอา" chip for it. The recommendations still honor it.
- The "ไม่เอา" chips only grow within a chat; the server clears its exclusions when a finished round restarts (and un-bans an item the user later adds again), so a stale chip can remain until "new chat".
- Ingredient words typed into `/confirm` replies or the checklist that the dictionary does not know are dropped without a note (the `unknown` note only covers the main text box).
- HEIC photos can't be decoded by desktop Chrome; the UI asks for a JPG. (iOS/Safari converts on pick.)
- Thai is the design language: negation detection on the server is Thai-only by design (`ไม่เอา…`).
- The font (Anuphan) loads from Google Fonts; offline it falls back to Noto Sans Thai / the system Thai font.
