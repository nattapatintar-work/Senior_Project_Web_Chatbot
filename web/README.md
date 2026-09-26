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
  js/logic.js         pure decisions (chips, cards, error mapping, "show more") - unit-tested under Node
  js/api.js           fetch wrapper: timeouts, multipart, one normalised error shape
  js/images.js        photo prep: decode, downscale to <=1600 px JPEG, thumbnails
  js/app.js           state, rendering, the conversation flow
  tests/*.test.js     node --test (no dependencies)
```

## Run it locally

**Against a local backend (recommended for development)**

```bash
# terminal 1 - backend; CORS_ORIGINS lets the page on :8080 call it
CORS_ORIGINS=http://localhost:8080 python -m uvicorn api.app:app --port 8000
# terminal 2 - static files
cd web && python -m http.server 8080
```

Open <http://localhost:8080/?api=http://localhost:8000>. The `?api=` parameter overrides `API_BASE` for that page load,
so nothing needs editing. (PowerShell: `$env:CORS_ORIGINS="http://localhost:8080"` before starting uvicorn.)

**Against the deployed EC2 backend from your machine**

`API_BASE` already defaults to `http://15.135.217.132`. A page served from `localhost:8080` is a different origin from that
server, so the server must allow it: add `Environment=CORS_ORIGINS=http://localhost:8080` to
`/etc/systemd/system/foodfridgegreen-api.service`, then `sudo systemctl daemon-reload && sudo systemctl restart foodfridgegreen-api`.
(The `GET` method is now in the CORS allow-list too, so a browser can call `/health`.) Serving the page from the EC2 itself
(next section) avoids CORS altogether.

Don't open `index.html` by double-clicking (`file://`): the page's origin becomes `null`, which browsers block for API calls.

## Serve it from the same EC2 instance (existing nginx)

Same origin as the API, no CORS, and the page and API share one address.

1. **Backend first.** This frontend needs the enriched `/recommend` (adds `cook_time_min`, `recipe_source_url`,
   `main_ingredients`, `seasonings` per recipe):
   ```bash
   ssh -i <key.pem> ubuntu@15.135.217.132
   cd ~/app && git pull && sudo systemctl restart foodfridgegreen-api
   ```
2. **Copy the static files somewhere nginx can read.** `/home/ubuntu` is `drwxr-x---`, so nginx (`www-data`) cannot read `~/app/web`
   directly; publish a copy (repeat this after every `git pull` that changes `web/`):
   ```bash
   sudo mkdir -p /var/www/foodfridgegreen
   sudo cp -r ~/app/web/. /var/www/foodfridgegreen/
   sudo rm -rf /var/www/foodfridgegreen/tests /var/www/foodfridgegreen/README.md   # optional: not needed at runtime
   ```
3. **nginx** (`/etc/nginx/sites-available/foodfridgegreen`): serve the files at `/`, proxy only the API paths.
   ```nginx
   server {
       listen 80 default_server;
       listen [::]:80 default_server;
       server_name _;
       client_max_body_size 45m;               # photo uploads (5 x 8 MB)

       root /var/www/foodfridgegreen;
       index index.html;

       location / {
           try_files $uri $uri/ =404;
           add_header Cache-Control "no-cache";  # a redeploy shows up on the next refresh
       }

       location ~ ^/(health|detect|extract|confirm|correct|seasoning|recommend)$ {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $remote_addr;   # overwrite, so the rate limiter can't be spoofed
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_read_timeout 60s;
       }
   }
   ```
   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```
4. Open `http://15.135.217.132/`. Because the page and the API are now the same origin, you can set
   `API_BASE: ""` in `web/js/config.js` (same-origin, works if the IP changes); the default absolute IP also works.

Note: with this config the API is only reachable at those seven paths (FastAPI's `/docs` is no longer proxied).

**Separate hosting** (S3, Netlify, GitHub Pages, ...): set `API_BASE` to the API's address and add the page's origin to
`CORS_ORIGINS` on the server. An `https://` page cannot call this `http://` API (browsers block mixed content) until the API has TLS.

## What follows the design, and what is added

Ported from the design: the 390 px phone layout, Chat / Seasoning tabs with the lock icon, the 26-tile seasoning grid and its
confirm/pending/locked states, the gate ("ยืนยันเครื่องปรุงก่อนเริ่มแชท"), bubbles, typing indicator, ingredient chips
(plain / struck / +added), recipe cards (rank, minutes, kcal, tags, ดูสูตร, main-ingredient and seasoning have/miss chips), the
composer with thumbnails, and the design's scroll-anchoring rule.

Real behavior the mock only pretended: every step calls the backend (`/seasoning`, `/detect`, `/extract`, `/confirm`, `/correct`,
`/recommend`), the seasoning tab locks when the server locks it, "new chat" keeps your ticks (localStorage) but needs a re-confirm.

Additions the design does not show (built in the same visual language, marked `extension` in the CSS):

| Addition | Why |
|---|---|
| Correction checklist (tap wrong items, add text, "อัปเดตรายการ") | the backend's `reject` -> `/correct` loop has no design |
| "ไม่เอา" and "เงื่อนไข" chip groups | text-derived exclusions and health tags are central to the backend |
| A corrected/edited list is shown and confirmed again | real stage is `awaiting_confirm`; the mock jumped to results |
| Re-ask bubble for an `unclear` reply | the classifier's fourth intent |
| "ขอเพิ่ม"/"more" only when it is the whole message | the mock's `/เพิ่ม/` also matched "เพิ่มกระเทียม" |
| Up to 5 photos, paste-to-attach, downscale to <=1600 px JPEG | backend limit is 5 x 8 MB; phone photos are often bigger |
| Error bubbles with "ลองอีกครั้ง", session-expiry recovery, toast | network failure, 429, 404 session gone, 503, 413, 422 |
| Visible keyboard focus, `aria-live` chat log, reduced-motion respect | accessibility |

## Tests

```bash
node --test "web/tests/*.test.js"          # logic + API wrapper (34 tests, no dependencies)
python -m pytest tests/test_web_data.py    # data.js still matches data/ingredients.json
python tools/gen_web_data.py               # regenerate data.js after editing the ingredient dictionary
```

## Known limits

- Chat history lives in the page; a refresh starts a new chat (the seasoning ticks are remembered, the server session is not resumed).
- Server sessions expire after 1 hour idle; the UI rebuilds one silently and asks you to resend.
- Rate limits are per IP: `/detect` 5/min, everything else 10/min. The UI shows a "ส่งถี่เกินไป" bubble with retry.
- Text like "ไม่เอาหมู" typed into the checklist's add field is applied by the server, but `/correct` does not echo the exclusion list,
  so that bubble may not show a "ไม่เอา" chip for it. The recommendations still honor it.
- HEIC photos can't be decoded by desktop Chrome; the UI asks for a JPG. (iOS/Safari converts on pick.)
- Thai is the design language: negation detection on the server is Thai-only by design (`ไม่เอา…`).
- The font (Anuphan) loads from Google Fonts; offline it falls back to Noto Sans Thai / the system Thai font.
