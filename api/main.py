"""
api/main.py
===========
The LINE chatbot webhook.

STATUS: Week 2 — real webhook, mock brains
------------------------------------------
The LINE plumbing here is real: signature verification, session buffering,
image download, replies. What it says is still fake — extract(), recommend()
and detect() are all mocks until Weeks 5, 7 and 8.

That split is deliberate. Week 2's goal is simply "send a message to the bot
and get a real reply back" (project doc, Week 2).

    User sends photo/text on LINE
            |
    POST /callback -> verify signature -> respond HTTP 200 IMMEDIATELY
            |
    Buffer into session + wait 2.5s (debounce)      <- api/session.py
            |
        photo -> detect()        text -> extract()
            |                            |
            +--------------+-------------+
                           |
            Merge ingredients + health conditions
                           |
            recommend(): TF-IDF + cosine + health filter
                           |
            Top-3 dishes + have/missing + nutrition
                           |
            Template response -> reply token (free)

⚠️ THE LINE SDK VERSION TRAP
----------------------------
This uses **line-bot-sdk v3**. Nearly every LINE bot tutorial you will find by
searching is written for **v2**, and v2 code does not run on v3 — the imports,
the class names and the reply call are all different.

    v2 (most tutorials)                  v3 (this file)
    from linebot import LineBotApi       from linebot.v3.messaging import MessagingApi
    TextMessage                          TextMessageContent  (for INCOMING)
    TextSendMessage                      TextMessage         (for OUTGOING)
    line_bot_api.reply_message(tok, msg) MessagingApi(client).reply_message(ReplyMessageRequest(...))

If you copy a snippet from a blog and get ImportError, that is why. Check the
official v3 docs instead:
https://github.com/line/line-bot-sdk-python
"""

# sys.path setup so `python api/main.py` can find the nlp/ and recommender/
# folders. Without it Python only looks inside api/ and raises ImportError.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, abort, request

# --- line-bot-sdk v3 imports (NOT v2 — see the warning above) ---------------
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent

from api import config, mock_cv, session
from nlp.extract import extract
from recommender.recommend import recommend

# Detections below this confidence are thrown away.
#
# Low-confidence boxes are usually shadows, reflections or stains that YOLO has
# mistaken for food. Acting on them is worse than missing an ingredient: the
# bot confidently recommends a dish based on something that was never there.
CONFIDENCE_THRESHOLD = 0.5

# LINE rejects a text message longer than 5000 characters.
MAX_MESSAGE_LENGTH = 5000

app = Flask(__name__)

# WebhookHandler verifies signatures. It needs the CHANNEL SECRET
# (Basic settings tab) — not the access token (Messaging API tab).
handler = WebhookHandler(config.CHANNEL_SECRET)

# Configuration carries the ACCESS TOKEN, used for sending. Two different
# credentials for two different jobs: the secret proves messages coming IN are
# genuine, the token proves we are allowed to send messages OUT.
line_config = Configuration(access_token=config.CHANNEL_ACCESS_TOKEN)


# ===========================================================================
# Routes
# ===========================================================================

@app.route("/health", methods=["GET"])
def health():
    """
    Liveness check. Open this in a browser to confirm the server is up.

    Useful because the LINE console only reports "webhook failed" without
    saying whether your server is down, your tunnel is down, or the signature
    check is rejecting. This isolates the first of those three.
    """
    return {"status": "ok"}, 200


@app.route("/callback", methods=["POST"])
def callback():
    """
    The webhook LINE calls whenever someone messages the bot.

    STEP 1 — VERIFY THE SIGNATURE
    Your webhook URL is public, so anyone who finds it can POST to it. LINE
    proves a request is genuine by signing it: it takes the request body, hashes
    it with your channel secret, and puts the result in the X-Line-Signature
    header. handler.handle() recomputes that hash and compares.

    Only someone holding your channel secret can produce a matching signature,
    so a valid signature means the request really came from LINE. Skipping this
    check would let anyone send fake events to your bot.

    STEP 2 — ANSWER FAST
    handler.handle() dispatches to the @handler.add functions below, and it does
    so synchronously — this HTTP response waits for them to finish. That is why
    those functions only drop the message into a buffer and return immediately.

    It matters because LINE retries a webhook that is slow to answer. A slow
    handler would therefore make the bot reply twice to one message. The real
    work happens later on the debounce timer's thread, so this route can return
    200 in milliseconds.
    """
    # The exact raw body, as text. It must be byte-for-byte what LINE sent,
    # because the signature was computed over exactly these bytes. Do not use
    # request.json here — parsing and re-serialising would change the text and
    # break verification.
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        # Wrong or missing signature. Either the request is not from LINE, or
        # LINE_CHANNEL_SECRET in .env does not match the channel.
        app.logger.warning("Rejected a webhook with an invalid signature")
        abort(400)

    return "OK", 200


# ===========================================================================
# Event handlers — these ONLY buffer. No slow work here.
# ===========================================================================

@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event: MessageEvent) -> None:
    """Someone sent text. Buffer it and let the debounce timer do the rest."""
    user_id = _user_id_of(event)
    if user_id is None:
        return
    session.add_text(user_id, event.message.text, event.reply_token)


@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event: MessageEvent) -> None:
    """
    Someone sent a photo. Buffer only its ID.

    The picture itself is NOT downloaded here — that is a network round trip,
    and this function is holding up the HTTP response. Downloading happens in
    the flush handler once the window closes.
    """
    user_id = _user_id_of(event)
    if user_id is None:
        return
    session.add_image(user_id, event.message.id, event.reply_token)


def _user_id_of(event: MessageEvent) -> str | None:
    """
    Pull the user ID out of an event.

    Messages can also arrive from groups and chat rooms, where there may be no
    user ID. getattr(..., None) returns None instead of raising in that case.
    """
    return getattr(event.source, "user_id", None)


# ===========================================================================
# Flush — the real work, on the timer thread, ~2.5s after the last message
# ===========================================================================

def process_session(sess: session.Session) -> None:
    """
    Handle one complete request: everything the user sent in one burst.

    Runs on the debounce timer's thread, so it may take as long as it needs
    without blocking the webhook. It must not raise — session._flush catches
    and logs, but a clean failure path here gives the user a better message.
    """
    # --- Step 1: download the photos -----------------------------------------
    image_paths = []
    for message_id in sess.image_ids:
        try:
            image_paths.append(_download_image(message_id, sess.user_id))
        except Exception as exc:
            # One bad download should not sink the whole reply. Skip it and
            # carry on with whatever else the user sent.
            print(f"[main] could not download image {message_id}: {exc}", flush=True)

    # --- Step 2: run detection on each photo ---------------------------------
    detected: list[str] = []
    for path in image_paths:
        # mock_cv.detect() is fake until Week 8, when Person 1's real detect()
        # replaces it. The return shape is already the agreed one, so that swap
        # touches nothing else.
        for item in mock_cv.detect(path):
            if item["confidence"] >= CONFIDENCE_THRESHOLD:
                detected.append(item["ingredient"])

    # Deduplicate while keeping order — the same ingredient may appear in
    # several photos. dict.fromkeys() preserves order where set() would not.
    detected = list(dict.fromkeys(detected))

    # --- Step 3: join the separate texts -------------------------------------
    # Several messages become one string so extract() sees the whole request.
    combined_text = " ".join(sess.texts)

    # --- Step 4: run the pipeline --------------------------------------------
    reply = handle_user_input(combined_text, detected_ingredients=detected)

    # --- Step 5: mention anything that was dropped ---------------------------
    if sess.dropped_images:
        reply += (
            f"\n\n(ส่งรูปมา {sess.dropped_images} รูปเกินกำหนด "
            f"ใช้แค่ {len(sess.image_ids)} รูปแรกนะคะ)"
        )

    send_reply(sess.user_id, sess.reply_token, reply)


def _download_image(message_id: str, user_id: str) -> str:
    """
    Fetch one photo from LINE and save it, returning the saved path.

    Worth knowing: image content on LINE expires. Saving a copy means the file
    is still there in Week 8 when YOLO can finally read it, and it doubles as
    real test data.
    """
    config.INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    with ApiClient(line_config) as api_client:
        blob = MessagingApiBlob(api_client)
        content = blob.get_message_content(message_id=message_id)

    # message_id is unique, so this cannot collide. user_id is included to make
    # the folder easy to read while debugging.
    path = config.INCOMING_DIR / f"{user_id[:8]}_{message_id}.jpg"
    path.write_bytes(content)

    print(f"[main] saved {path.name} ({len(content)} bytes)", flush=True)
    return str(path)


def send_reply(user_id: str, reply_token: str, text: str) -> None:
    """
    Send the reply. Try Reply first, fall back to Push only if that fails.

    WHY THE ORDER MATTERS — this is a budget decision, not a technical one.

    Reply messages are FREE and do not count against the monthly quota.
    Push messages DO count. The Thai free LINE OA plan caps messages per month
    and has NO way to buy more: once the quota is gone the bot goes silent
    until the month rolls over. Losing the bot mid-demo would be unrecoverable.

    So Push is strictly an emergency path. It only triggers when the reply
    token has already failed, which in practice means it expired — a token
    lasts ~30 seconds, and 2.5s of debounce plus several image downloads can
    occasionally exceed that.
    """
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[: MAX_MESSAGE_LENGTH - 3] + "..."

    message = TextMessage(text=text)

    with ApiClient(line_config) as api_client:
        api = MessagingApi(api_client)

        try:
            # --- Preferred path: free, no quota cost ---
            api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=[message])
            )
            return
        except Exception as exc:
            print(f"[main] reply failed ({exc}); falling back to push", flush=True)

        try:
            # --- Fallback: COSTS QUOTA. Only because reply already failed. ---
            api.push_message(PushMessageRequest(to=user_id, messages=[message]))
        except Exception as exc:
            # Both failed. Nothing more to try — log it and move on.
            print(f"[main] push also failed: {exc}", flush=True)


# ===========================================================================
# Pipeline (unchanged from Week 1)
# ===========================================================================

def handle_user_input(text: str = "", detected_ingredients: list[str] | None = None) -> str:
    """
    Run one full turn of the conversation: raw input in, reply text out.

    Args:
        text: what the user typed. Empty string if they only sent a photo.
        detected_ingredients: canonical keys found in photos. None if they only
                              sent text.

    Returns:
        The reply string, ready to hand to LINE.

    Handling text and photos through the same function is what makes the
    system genuinely multimodal rather than two separate features. A photo
    can show ไก่ sitting on the counter but can never show that the user wants
    something clean, and it cannot see the fish sauce inside a closed bottle.
    Text fills both gaps.
    """
    detected_ingredients = detected_ingredients or []

    # --- Step 1: pull structure out of the typed message -------------------
    parsed = extract(text)

    # --- Step 2: merge what the photo saw with what the text said ----------
    all_ingredients = list(dict.fromkeys(detected_ingredients + parsed["ingredients"]))

    # --- Step 3: score the dishes ------------------------------------------
    results = recommend(
        ingredients=all_ingredients,
        health_tags=parsed["health_tags"],
        excluded=parsed["excluded"],
    )

    # --- Step 4: build the reply from a template ---------------------------
    return format_reply(results)


def format_reply(results: list[dict]) -> str:
    """
    Turn recommender output into the message the user actually reads.

    Deliberately a plain template and not an LLM call. Templates are instant,
    and the reply token from LINE expires in 10-30 seconds — a slow LLM round
    trip risks missing that window entirely and losing the reply.
    """
    if not results:
        return "ไม่พบเมนูที่ตรงกับวัตถุดิบที่มีค่ะ ลองส่งวัตถุดิบเพิ่มเติมดูนะคะ"

    lines = ["🍳 เมนูแนะนำสำหรับคุณ", ""]

    for rank, dish in enumerate(results, start=1):
        lines.append(f"{rank}. {dish['name_th']}")

        if dish["have"]:
            lines.append(f"   ✅ มีแล้ว: {', '.join(dish['have'])}")
        if dish["missing"]:
            lines.append(f"   🛒 ต้องซื้อ: {', '.join(dish['missing'])}")

        nutrition = dish["nutrition"]
        lines.append(
            f"   📊 {nutrition['kcal']} kcal | "
            f"โปรตีน {nutrition['protein']}g | "
            f"ไขมัน {nutrition['fat']}g | "
            f"คาร์บ {nutrition['carb']}g"
        )
        lines.append("")

    return "\n".join(lines)


# ===========================================================================
# Startup
# ===========================================================================

# Wire session.py to this module's worker. Done here rather than by session.py
# importing main.py, which would be a circular import.
session.configure(
    debounce_seconds=config.DEBOUNCE_SECONDS,
    max_images=config.MAX_IMAGES_PER_SESSION,
)
session.set_flush_handler(process_session)


if __name__ == "__main__":
    # Two separate fixes in one call:
    #
    # encoding="utf-8"     — Thai-locale Windows consoles default to the cp874
    #                        codepage and cannot print emoji or Thai. Display
    #                        only; LINE is UTF-8 throughout.
    #
    # line_buffering=True  — without this, redirecting output to a file
    #                        (`python api/main.py > log.txt`) makes Python hold
    #                        print() output in a buffer instead of writing it
    #                        out. Your log then looks empty while the server is
    #                        running, which is maddening when you are trying to
    #                        see why a reply failed.
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    print("Starting LINE bot on http://localhost:5000")
    print("  health check : http://localhost:5000/health")
    print("  webhook      : POST /callback")
    print(f"  debounce     : {config.DEBOUNCE_SECONDS}s")

    # ⚠️ use_reloader=False is REQUIRED, not a preference.
    #
    # Flask's auto-reloader runs your app in TWO processes. Both would hold
    # their own session buffers and their own timers, so every message would be
    # processed twice and the bot would reply twice.
    #
    # That looks exactly like the "LINE retried my webhook" bug, so it is very
    # easy to spend an afternoon debugging the wrong thing. The cost is that
    # code changes need a manual restart.
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
