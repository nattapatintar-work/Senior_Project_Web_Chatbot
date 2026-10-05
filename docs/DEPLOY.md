# Deploying the web chatbot

Single-server setup: nginx serves the static page (`web/`) and proxies the API paths to one
uvicorn process (`api.app:app`) on `127.0.0.1:8000`. Everything below was written from the code;
nothing here has been run against the server.

## 1. Pre-deploy checklist

Tick every line before restarting the service.

**Code**
- [ ] The changes are committed and pushed (the server updates with `git pull`).
- [ ] Locally: `python -m pytest -q` and `node --test web/tests/*.test.js` both pass.

**Model files that are NOT in git** (copy by hand, see section 2)
- [ ] `models/bert_ner/model.safetensors` is on the server, same size as the local file.
- [ ] `models/best_phase1_n_ceiling1000_img640.pt` (YOLO weights) is on the server. Without it the app still boots, but `/detect` answers 503.

**Environment** (see `.env.example`, section 3)
- [ ] `ANTHROPIC_API_KEY` is set. Without it the app runs, but with no LLM: `/confirm` uses the keyword classifier and text the BERT model is unsure about uses the keyword extractor.
- [ ] `TRUST_FORWARDED_FOR=1`. Behind nginx every visitor otherwise shares one rate-limit bucket (10 requests/minute for everybody).
- [ ] Nothing else is required. The `LINE_*` and `DEBOUNCE_SECONDS` variables belong to the legacy LINE bot and are not needed.

**Model ids**
- [ ] `python tools/check_llm_models.py` prints `OK` for both ids (it makes exactly 2 real API calls). The extraction id defaults to `claude-sonnet-5`, which has not been verified against any account. If it fails, set `EXTRACTION_LLM_MODEL`. The intent id (`claude-haiku-4-5-20251001`) is hard-coded in `api/web_config.py`; if it fails, that file has to be edited.

**Config**
- [ ] `data/thresholds.yaml` `default:` is the real YOLO cutoff. It was `0.01` (marked TEMPORARY in the file) at the time of writing; Person 1 owns that value.

**nginx and systemd**
- [ ] The nginx location proxies all 8 routes, **including `/extract_bert`** (section 4).
- [ ] `proxy_read_timeout` is above 8 seconds (the LLM fallback can take that long) and `client_max_body_size` is at least 45m (5 photos of up to 8 MB).
- [ ] The service runs **one** uvicorn worker (section 5).

## 2. Files the server needs

### BERT NER model: `models/bert_ner/` (or wherever `BERT_NER_MODEL_PATH` points)

| File | Needed for | In git? |
|---|---|---|
| `config.json` | model architecture | yes |
| `label_config.json` | label map and the 0.8 confidence threshold | yes |
| `tokenizer.json` | tokenizer | yes |
| `tokenizer_config.json` | tokenizer | yes |
| `model.safetensors` (418,654,572 bytes locally; or `pytorch_model*.bin`) | the weights | **no** (`.gitignore`: `*.safetensors`, `*.bin`) |

After `git pull` only the weights are missing. Copy them from your machine:

```bash
scp -i <key.pem> models/bert_ner/model.safetensors ubuntu@<server-ip>:~/app/models/bert_ner/
# on the server, compare with the local file:
ls -l ~/app/models/bert_ner/ && sha256sum ~/app/models/bert_ner/model.safetensors
```

Loading is **lazy**: the model is read on the first `/extract_bert` call, not at startup. That first call is slow and holds a lock, so send one warm-up request after every restart (section 6). The web UI's default request timeout is 30 seconds.

What happens when something is missing (`bert` is the value in `GET /health`, from `bert_status()`):

| Situation | At startup | `/health` `bert` | On `/extract_bert` |
|---|---|---|---|
| All files present | nothing | `pending`, then `loaded` after the first call | BERT, with the LLM fallback when it is unsure |
| Weights or `label_config.json` missing | nothing | `unavailable` | keyword extractor; one log line `[extract] BERT model unavailable (...)`; the folder is re-checked on every request, so copying the files in works without a restart |
| Files present but the load fails (corrupt file, `transformers`/`torch` missing, `config.json` or tokenizer files missing) | nothing | `pending`, then `unavailable` after the first call | keyword extractor; the same one log line; the failure is remembered until the service restarts |

The BERT model does **not** need `data/thresholds.yaml`. That file is only the YOLO confidence cutoff (`api/web_config.py`). It is committed; if it were missing the app would print `[web_config] ... not found, using default threshold 0.5` and use 0.5.

### YOLO weights
`models/best_phase1_n_ceiling1000_img640.pt` is loaded, verified against `data/ingredients.json` and warmed up when the service starts (`api/mock_cv.py`). If it is missing or the class mapping does not match, the log shows `[app] detector unavailable: ...`, `/health` reports `"detector": "unavailable"` and `/detect` answers 503. Nothing else is affected.

## 3. Environment variables

Read from the process environment, or from `.env` in the repo root (real environment variables win). Full template: `.env.example`.

| Name | Default | Required? | Without it / when wrong |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | empty | optional | no LLM anywhere: keyword `/confirm`, keyword extraction when BERT is unsure. A `your_..._here` placeholder counts as unset. |
| `EXTRACTION_LLM_MODEL` | `claude-sonnet-5` | optional | a rejected id falls back to the keyword extractor (logged as `[extract] LLM fallback failed (NotFoundError, status=404 ...)`). |
| `BERT_NER_MODEL_PATH` | `<repo>/models/bert_ner` | optional | see the table in section 2. |
| `SESSION_TTL_SECONDS` | `3600` | optional | idle sessions are dropped after this many seconds; a non-numeric value crashes the service at startup. |
| `CORS_ORIGINS` | empty | optional | only needed when the page is served from a different origin than the API. |
| `TRUST_FORWARDED_FOR` | `0` | **set to `1` behind nginx** | one shared rate-limit bucket for all visitors. |

Not configurable by env var (constants in `api/web_config.py`): the intent model id, the intent timeout (5 s), the extraction timeout (8 s), the rate limits (`/detect` 5/min, everything else 10/min per IP) and the upload limits.

## 4. nginx

All routes the web UI calls (`web/js/api.js`) plus `/extract`, the keyword route kept as a manual fallback:

| Route | Method | Called by the UI |
|---|---|---|
| `/health` | GET | yes |
| `/seasoning` | POST | yes |
| `/detect` | POST (multipart) | yes |
| `/extract_bert` | POST | yes (the live text extractor) |
| `/extract` | POST | no (kept for switching back) |
| `/confirm` | POST | yes |
| `/correct` | POST | yes |
| `/recommend` | POST | yes |

**Easy to miss:** `/extract` and `/extract_bert` share a prefix. An anchored regex such as `^/(...|extract|...)$` matches `/extract` only, so the older documented rule silently dropped `/extract_bert` and the UI got nginx's 404. List both names.

`/etc/nginx/sites-available/foodfridgegreen`:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 45m;                 # photo uploads: 5 x 8 MB

    root /var/www/foodfridgegreen;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
        add_header Cache-Control "no-cache";  # a redeploy shows up on the next refresh
    }

    location ~ ^/(health|seasoning|detect|extract|extract_bert|confirm|correct|recommend)$ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;   # overwrite, so the rate limiter cannot be spoofed
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts: /extract_bert can call the LLM fallback (up to ~8 s), the first call after a
        # restart also loads the BERT model, and /detect runs YOLO. nginx's default (60 s) is fine;
        # never set this below ~15 s.
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo mkdir -p /var/www/foodfridgegreen
sudo cp -r ~/app/web/. /var/www/foodfridgegreen/      # repeat after every git pull that changes web/
```

FastAPI's `/docs` and `/openapi.json` are intentionally not proxied.

## 5. systemd

The repo contains **no** service file. Before changing anything, look at the one already on the server and keep its Python path:

```bash
systemctl cat foodfridgegreen-api
```

The command it has to run (from `api/app.py`: `uvicorn api.app:app`), from the repo root:

```
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Reference unit (adjust `User`, paths and the interpreter to what is really on the server):

```ini
[Unit]
Description=FoodFridgeGreen API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/app
# The app also reads /home/ubuntu/app/.env itself; use this line instead of (or as well as) that file.
Environment=TRUST_FORWARDED_FOR=1
ExecStart=/home/ubuntu/app/.venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=3
# Startup imports torch/ultralytics, verifies and warms up the YOLO model; allow time.
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now foodfridgegreen-api
```

**Use exactly one worker.** Chat sessions (`api/state.py`) and the rate-limit counters (slowapi) live in the memory of one process. With `--workers 2` a request that lands on the other worker gets `404 unknown session` (the UI shows its "session expired" bubble and restarts the list) and the rate limits are per worker. Each worker would also load its own copy of the YOLO and BERT models. A restart also drops every session.

## 6. After deploying: commands to run on the server

```bash
BASE=http://127.0.0.1          # through nginx: exercises the proxy rules
API=http://127.0.0.1:8000      # straight to uvicorn: use this to tell an app problem from an nginx problem
sudo systemctl status foodfridgegreen-api --no-pager
```

### 6.1 Health

```bash
curl -s $BASE/health
# {"status":"ok","detector":"loaded","bert":"pending"}
```

| `detector` | Meaning / action |
|---|---|
| `loaded` | YOLO is ready. |
| `unavailable` | YOLO weights missing or class mapping mismatch; `/detect` returns 503. Check the journal for `[app] detector unavailable:`. Copy the `.pt` file and restart. |

| `bert` | Meaning / action |
|---|---|
| `loaded` | The model is in memory. Nothing to do. |
| `pending` | Weights are on disk and load on the first `/extract_bert` call. Send the warm-up (6.3) and check again; it should become `loaded`. |
| `unavailable` | Weights or `label_config.json` are missing, or a load already failed. Text still works through the keyword extractor. Copy the missing files into `models/bert_ner/` (or fix `BERT_NER_MODEL_PATH`), read the reason in the journal (`[extract] BERT model unavailable (...)`), then restart the service. |

### 6.2 Are all routes proxied? (one request each, nothing is stored)

```bash
curl -s -o /dev/null -w '/health   %{http_code}\n' $BASE/health
for p in seasoning extract extract_bert confirm correct recommend; do
  printf '/%-12s ' "$p"
  curl -s -o /dev/null -w '%{http_code}\n' -X POST $BASE/$p -H 'Content-Type: application/json' -d '{}'
done
curl -s -o /dev/null -w '/detect    %{http_code}\n' -X POST $BASE/detect -H 'Content-Type: application/json' -d '{}'
```

Expected: `/health` 200, `/seasoning` 200 (an empty body is a read-only call), then 422 for `extract`, `extract_bert`, `confirm`, `correct`, `recommend` and `detect` (the app rejected the empty body, so the request reached it). **A `404` on any of them means nginx is not proxying that route.** This loop uses 6 of the 10 requests per minute; wait a minute before 6.3.

### 6.3 One full pass (expected status per route)

```bash
J='Content-Type: application/json'
SID=$(curl -s -X POST $BASE/seasoning -H "$J" -d '{"seasonings":[]}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["session_id"])')
echo "session: $SID"

# 200. Also the BERT warm-up: the FIRST call after a restart is slow. Look for include containing chicken and egg.
curl -s -X POST $BASE/extract_bert -H "$J" -d "{\"text\":\"มีไข่กับไก่\",\"session_id\":\"$SID\"}"; echo

# 200 (keyword route, same session)
curl -s -o /dev/null -w '/extract      %{http_code}\n' -X POST $BASE/extract -H "$J" -d "{\"text\":\"มีไข่กับไก่\",\"session_id\":\"$SID\"}"

# 409: /recommend before the list is confirmed (proves the route and the state guard)
curl -s -o /dev/null -w '/recommend    %{http_code}  (expect 409)\n' -X POST $BASE/recommend -H "$J" -d "{\"session_id\":\"$SID\",\"top_n\":3}"

# 200 (422 "not in the current ingredient list" would mean egg was not extracted)
curl -s -o /dev/null -w '/correct      %{http_code}\n' -X POST $BASE/correct -H "$J" -d "{\"session_id\":\"$SID\",\"exclude\":[\"egg\"]}"

# 200, "intent":"confirm","stage":"confirmed" (with an API key this calls Claude Haiku)
curl -s -X POST $BASE/confirm -H "$J" -d "{\"session_id\":\"$SID\",\"reply\":\"ใช่\"}"; echo

# 200, count >= 1
curl -s -o /dev/null -w '/recommend    %{http_code}\n' -X POST $BASE/recommend -H "$J" -d "{\"session_id\":\"$SID\",\"top_n\":3}"

# 200 with a real photo (503 = detector unavailable; 422 = the file was not a usable image)
curl -s -o /dev/null -w '/detect       %{http_code}\n' -X POST $BASE/detect -F "images=@/path/to/photo.jpg;type=image/jpeg"

curl -s $BASE/health      # "bert" should now read "loaded"
```

Rate limits are 10 requests/minute per client address (5/minute for `/detect`). This pass makes 7 default-limit requests, so do not run it twice within a minute; a 429 is the limiter, not a fault.

Finally open `http://<server-ip>/` in a browser and send one text message.

### 6.4 Logs

```bash
journalctl -u foodfridgegreen-api -n 100 --no-pager       # last 100 lines
journalctl -u foodfridgegreen-api -f                      # follow live
journalctl -u foodfridgegreen-api --since "10 min ago" --no-pager
sudo tail -n 50 /var/log/nginx/error.log                  # proxy problems (502/504)
```

Lines to look for (none contains the API key or the user's text):

| Line | Meaning |
|---|---|
| `[mock_cv] model loaded and warmed up on device=...` | YOLO started fine. |
| `[app] detector unavailable: ...` | YOLO did not load; `/detect` will 503. |
| `[intent] ANTHROPIC_API_KEY not configured: /confirm uses the keyword classifier` | no key: `/confirm` runs without the LLM. |
| `[extract] ANTHROPIC_API_KEY not configured: ...` | no key: BERT-unsure text uses the keyword extractor. |
| `[extract] BERT model unavailable (...)` | see the table in section 2. |
| `[extract] LLM fallback failed (Type, status=..., request_id=..., Nms) -> keyword extract()` | the extraction LLM call failed; `NotFoundError` / 404 means the model id is wrong. |
| `[intent] LLM classifier failed (...) -> keyword stub` | the `/confirm` LLM call failed. |
| `[web_config] ... thresholds.yaml not found ...` | `data/thresholds.yaml` is missing. |

## 7. Rollback

Only tracked code is affected; `.env`, the model weights and the systemd/nginx files stay as they are.

```bash
cd ~/app
git log --oneline -5                 # find the last good commit
git checkout <good-sha>              # a detached HEAD is fine for a rollback
# if requirements.txt differed between the two commits: pip install -r requirements.txt
sudo systemctl restart foodfridgegreen-api
sudo cp -r web/. /var/www/foodfridgegreen/
curl -s $BASE/health
```

When the fix is ready: `git checkout main && git pull`, then repeat the checklist. If the old version predates `/extract_bert`, the UI files you copied back must be from the same commit (the `web/` copy above does that).
