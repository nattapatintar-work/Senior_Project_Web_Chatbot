"""
api/main.py
===========
The LINE chatbot webhook.

STATUS: Week 8/9 — everything real
-----------------------------------
extract() (Week 5), recommend() (Week 7), and detect() (Week 8/9, wrapping
Person 1's delivered YOLO model in api/mock_cv.py) are all real now. The LINE
plumbing — signature verification, session buffering, image download,
replies, the Week 8 confirm-before-recommending flow — has been real since
Week 2.

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
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, abort, request

# --- line-bot-sdk v3 imports (NOT v2 — see the warning above) ---------------
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessageAction,
    MessagingApi,
    MessagingApiBlob,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent

from api import config, confirmation, mock_cv, session
from nlp.extract import extract
from recommender.recommend import recommend

# The Quick Reply button attached to every "anything else?" confirmation
# prompt (Week 8). Built once at import time, same reasoning as nlp/extract.py
# building its Trie once: this object is identical on every use, so there is
# no reason to reconstruct it per message. Its label/text is
# confirmation.PRIMARY_CONFIRM_PHRASE — the single source of truth also used
# by confirmation.is_confirmation_text() — so the button always produces text
# that gets recognised as a confirmation, not a second literal that could
# silently drift out of sync with the one in confirmation.py.
_CONFIRM_QUICK_REPLY = QuickReply(
    items=[
        QuickReplyItem(
            action=MessageAction(
                label=confirmation.PRIMARY_CONFIRM_PHRASE,
                text=confirmation.PRIMARY_CONFIRM_PHRASE,
            )
        )
    ]
)

# Detections below this confidence are thrown away.
#
# Low-confidence boxes are usually shadows, reflections or stains that YOLO has
# mistaken for food. Acting on them is worse than missing an ingredient: the
# bot confidently recommends a dish based on something that was never there.
#
# Read from data/thresholds.yaml (Week 8/9 handoff #4 from Person 1) via
# config.CONFIDENCE_THRESHOLD, not hardcoded here any more — see
# api/config.py's _load_confidence_threshold() for the non-fatal-missing
# fallback (this handoff is documented as "not blocking," unlike the LINE
# credentials).

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


def _log(msg: str) -> None:
    """
    One print helper for the whole webhook->reply path, tagged "[bot]" so the
    full chain for one message is a single grep away in the terminal.

    Debugging note (2026-08-12): before this, the happy path for a text-only
    message printed NOTHING — the only print() anywhere in main.py sat inside
    _download_image(), which a text-only message never reaches. That made a
    silent success and several silent early-return bugs (unhandled event type,
    no user_id, flush handler not wired) look identical: "200, no reply, no
    log" either way. Every step below now logs, success included.
    """
    print(f"[bot] {msg}", flush=True)


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

    _log(f"callback: received {len(body)} bytes")

    # Log what kind of event(s) this body actually contains, independent of
    # whether handler.handle() finds a matching @handler.add() for them. This
    # is what separates "no handler registered for this event type" (e.g. a
    # sticker, a follow event, a postback) from every other silent path — that
    # case logs an SDK-internal "No handler of ..." at INFO level, which is
    # easy to miss even with logging configured.
    try:
        import json as _json

        events = _json.loads(body).get("events", [])
        kinds = [f"{e.get('type')}/{e.get('message', {}).get('type')}" for e in events]
        _log(f"callback: {len(events)} event(s): {kinds}")
    except Exception:
        _log("callback: could not pre-parse body for logging (non-fatal)")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        # Wrong or missing signature. Either the request is not from LINE, or
        # LINE_CHANNEL_SECRET in .env does not match the channel.
        app.logger.warning("Rejected a webhook with an invalid signature")
        _log("callback: REJECTED — invalid signature (check LINE_CHANNEL_SECRET)")
        abort(400)
    except Exception:
        # handler.handle() dispatches to on_text/on_image, and Flask's default
        # error handling would turn an exception here into a 500 with no
        # traceback in this terminal (only in Flask's own log stream). Printing
        # explicitly keeps every failure visible in the same place.
        _log("callback: UNHANDLED EXCEPTION during handler.handle()")
        traceback.print_exc()
        raise

    _log("callback: dispatched OK, returning 200")
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
    _log(f"on_text: buffered text for {user_id[:8]}..., token={event.reply_token[:8]}...")
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
    _log(f"on_image: buffered image for {user_id[:8]}..., token={event.reply_token[:8]}...")
    session.add_image(user_id, event.message.id, event.reply_token)


def _user_id_of(event: MessageEvent) -> str | None:
    """
    Pull the user ID out of an event.

    Messages can also arrive from groups and chat rooms, where there may be no
    user ID. getattr(..., None) returns None instead of raising in that case.
    """
    user_id = getattr(event.source, "user_id", None)
    if user_id is None:
        # Silent by design before this change — a message from a group/room
        # source with no user_id would vanish here with zero log output,
        # looking identical to a successful-but-unreplied flush.
        source_type = getattr(event.source, "type", "unknown")
        _log(f"_user_id_of: no user_id on this event (source.type={source_type!r}) — dropped")
    return user_id


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
    _log(
        f"process_session: start for {sess.user_id[:8]}..., "
        f"{len(sess.texts)} text(s), {len(sess.image_ids)} image(s)"
    )

    try:
        # --- Step 1: download the photos -------------------------------------
        image_paths = []
        for message_id in sess.image_ids:
            try:
                image_paths.append(_download_image(message_id, sess.user_id))
            except Exception as exc:
                # One bad download should not sink the whole reply. Skip it and
                # carry on with whatever else the user sent.
                print(f"[main] could not download image {message_id}: {exc}", flush=True)

        # --- Step 2: run detection on each photo ------------------------------
        # Per unique ingredient name, keep only the highest-confidence
        # detection seen across ALL images in this session -- not just
        # "whichever occurrence came first." A plain dict.fromkeys() dedup
        # would have kept the first-seen occurrence regardless of confidence,
        # which happens to equal "highest confidence" within a single image
        # (mock_cv.detect() already sorts its own return value by confidence
        # descending) but is not guaranteed correct across multiple images --
        # e.g. a weak detection in photo 1 processed before a strong one in
        # photo 2 would have silently won under first-occurrence dedup. This
        # doesn't change recommend()'s TF-IDF scoring (confidence never
        # reaches recommend() either way, so the final name list was already
        # duplicate-free), but it matters for anything that later cares which
        # confidence a kept ingredient represents (e.g. the deferred
        # low-confidence-verification feature), and testing at a very low
        # threshold surfaces far more of these multi-box/multi-photo cases.
        detected_confidence: dict[str, float] = {}
        for path in image_paths:
            # mock_cv.detect() is real as of Week 8/9 (Person 1's delivered
            # YOLO model, models/best_phase1_n_ceiling1000_img640.pt) — the
            # return shape was agreed from the start, so this swap touched
            # nothing else here.
            for item in mock_cv.detect(path):
                if item["confidence"] < config.CONFIDENCE_THRESHOLD:
                    continue
                name = item["ingredient"]
                if name not in detected_confidence or item["confidence"] > detected_confidence[name]:
                    detected_confidence[name] = item["confidence"]

        # dict preserves insertion order (first-seen name), same as the old
        # dict.fromkeys() call -- only the VALUE kept per name changed.
        detected = list(detected_confidence.keys())
        _log(f"process_session: detected={detected} (confidences={detected_confidence})")

        # --- Step 3: join the separate texts -----------------------------------
        # Several messages become one string so extract() sees the whole request.
        combined_text = " ".join(sess.texts)
        _log(f"process_session: combined_text={combined_text!r}")

        # --- Step 4: confirm-before-recommending (Week 8) -----------------------
        # Every completed debounce round either starts a NEW confirmation
        # ("anything else?") or answers an EXISTING one for this user — see
        # api/confirmation.py's module docstring for why this needs state
        # beyond what session.py already tracks. quick_reply stays None for a
        # final recommendation; it's only attached to a confirmation prompt.
        quick_reply = None
        pending = confirmation.get(sess.user_id)

        if pending is None:
            # Fresh request: gather everything this round, then ASK before
            # recommending instead of answering immediately.
            ingredients, health_tags, excluded = _gather_ingredients(combined_text, detected)
            confirmation.start(sess.user_id, ingredients, health_tags, excluded)
            reply = _confirmation_prompt(ingredients)
            quick_reply = _CONFIRM_QUICK_REPLY
            _log(f"process_session: asked {sess.user_id[:8]}... to confirm, ingredients={ingredients}")

        elif confirmation.is_confirmation_text(combined_text) and not detected:
            # User confirmed: no new photos this round, and the text matches.
            # (A confirmation tap that somehow also carries new photos is
            # treated as "added more" below instead — new images are
            # unambiguous evidence of intent to add something, so they win
            # the tie-break over a possibly-coincidental text match.)
            resolved = confirmation.resolve(sess.user_id)
            reply = _finalize(resolved)
            _log(f"process_session: {sess.user_id[:8]}... confirmed, recommending")

        else:
            # User sent something else instead of confirming: fold it in.
            new_ingredients, new_health_tags, new_excluded = _gather_ingredients(
                combined_text, detected
            )
            merged = confirmation.merge(sess.user_id, new_ingredients, new_health_tags, new_excluded)
            if merged.prompts_sent < confirmation.MAX_CONFIRMATION_PROMPTS:
                confirmation.record_reprompt(sess.user_id)
                reply = _confirmation_prompt(merged.ingredients)
                quick_reply = _CONFIRM_QUICK_REPLY
                _log(
                    f"process_session: {sess.user_id[:8]}... added more, asking again "
                    f"({merged.prompts_sent} prompts sent so far)"
                )
            else:
                resolved = confirmation.resolve(sess.user_id)
                reply = _finalize(resolved)
                _log(
                    f"process_session: {sess.user_id[:8]}... hit the confirmation-prompt "
                    f"cap, recommending without asking again"
                )

        _log(f"process_session: reply built, {len(reply)} chars")

        # --- Step 5: mention anything that was dropped ---------------------------
        if sess.dropped_images:
            reply += (
                f"\n\n(ส่งรูปมา {sess.dropped_images} รูปเกินกำหนด "
                f"ใช้แค่ {len(sess.image_ids)} รูปแรกนะคะ)"
            )

        send_reply(
            sess.user_id,
            sess.reply_token,
            reply,
            first_seen=sess.first_seen,
            quick_reply=quick_reply,
        )
    except Exception:
        # Belt and braces alongside session._flush's own try/except — having
        # both means a traceback prints regardless of which layer is reached
        # first as this file evolves, and this one has the [bot] tag context.
        _log(f"process_session: UNHANDLED EXCEPTION for {sess.user_id[:8]}...")
        traceback.print_exc()


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


def send_reply(
    user_id: str,
    reply_token: str,
    text: str,
    first_seen: float | None = None,
    quick_reply: QuickReply | None = None,
) -> None:
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

    first_seen: time.monotonic() timestamp of the session's first message, if
    known. Logged as elapsed time before the reply call — this is the
    reply-token-expiry measurement: a token lasts ~30s, and without this
    number a hang and a slow-but-successful call look the same in hindsight.

    quick_reply: attached to the outgoing message as-is (or omitted if None).
    Week 8's confirmation flow uses this to attach the "anything else?"
    button; a final recommendation passes nothing.
    """
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[: MAX_MESSAGE_LENGTH - 3] + "..."

    message = TextMessage(text=text, quick_reply=quick_reply)

    elapsed = f"{time.monotonic() - first_seen:.1f}s" if first_seen is not None else "unknown"
    _log(
        f"send_reply: token={reply_token[:8]}... len={len(reply_token)} "
        f"elapsed_since_first_message={elapsed} text_len={len(text)}"
    )

    with ApiClient(line_config) as api_client:
        api = MessagingApi(api_client)

        try:
            # --- Preferred path: free, no quota cost ---
            # _request_timeout is explicit because the SDK's default is None
            # (no timeout at all). Without it, a stalled HTTPS call to
            # api.line.me blocks this daemon timer thread forever, printing
            # nothing — indistinguishable from a call that quietly succeeded.
            # (connect_timeout, read_timeout) in seconds.
            result = api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=[message]),
                _request_timeout=(5, 10),
            )
            _log(f"send_reply: reply OK — result={result}")
            return
        except ApiException as exc:
            # LINE's real reason (e.g. "Invalid reply token", "The reply
            # token is already used") lives in exc.body, not in str(exc).
            _log(
                f"send_reply: reply FAILED — ApiException status={exc.status} "
                f"body={exc.body!r}; falling back to push"
            )
        except Exception as exc:
            _log(
                f"send_reply: reply FAILED — {type(exc).__name__}: {exc}; "
                f"falling back to push"
            )

        _push(user_id, message)


def _push(user_id: str, message: TextMessage) -> None:
    """
    Send one message via Push. COSTS LINE QUOTA — see send_reply()'s docstring
    for why Push is an emergency-only path on the Thai free LINE OA plan.

    Factored out of send_reply()'s fallback branch so the confirmation-
    timeout path (api/confirmation.py's timer fires with no reply token
    available at all — it isn't triggered by an incoming webhook) can reuse
    the exact same call instead of duplicating it.
    """
    with ApiClient(line_config) as api_client:
        api = MessagingApi(api_client)
        try:
            result = api.push_message(
                PushMessageRequest(to=user_id, messages=[message]),
                _request_timeout=(5, 10),
            )
            _log(f"_push: push OK — result={result}")
        except ApiException as exc:
            _log(f"_push: push FAILED — ApiException status={exc.status} body={exc.body!r}")
        except Exception as exc:
            # Nothing more to try — log it and move on.
            _log(f"_push: push FAILED — {type(exc).__name__}: {exc}")


# ===========================================================================
# Pipeline (unchanged from Week 1)
# ===========================================================================

def _gather_ingredients(
    text: str, detected_ingredients: list[str] | None = None
) -> tuple[list[str], list[str], list[str]]:
    """
    Parse `text` and merge it with `detected_ingredients` into the three
    lists recommend() needs: (ingredients, health_tags, excluded).

    Factored out of handle_user_input() so it and Week 8's confirmation flow
    (process_session()'s three branches, which each need to parse one round
    of new input without immediately recommending) share exactly one merge
    implementation, instead of two copies quietly drifting apart over time.

    Handling text and photos through the same function is what makes the
    system genuinely multimodal rather than two separate features. A photo
    can show ไก่ sitting on the counter but can never show that the user wants
    something clean, and it cannot see the fish sauce inside a closed bottle.
    Text fills both gaps.
    """
    detected_ingredients = detected_ingredients or []
    parsed = extract(text)
    all_ingredients = list(dict.fromkeys(detected_ingredients + parsed["ingredients"]))
    return all_ingredients, parsed["health_tags"], parsed["excluded"]


def handle_user_input(text: str = "", detected_ingredients: list[str] | None = None) -> str:
    """
    Run one full turn of the conversation: raw input in, reply text out.

    Args:
        text: what the user typed. Empty string if they only sent a photo.
        detected_ingredients: canonical keys found in photos. None if they only
                              sent text.

    Returns:
        The reply string, ready to hand to LINE.

    Not called by process_session() any more as of Week 8 (see
    _confirmation_prompt()/_finalize() below — a fresh request now gets a
    confirmation prompt before a recommendation, not an immediate one). Kept
    as a real, correct one-shot pipeline function in its own right: skip the
    confirmation step entirely and go straight from raw input to a
    recommendation. No test currently calls it directly, but its behavior is
    unchanged and still exercised end-to-end via _gather_ingredients() and
    format_reply(), both of which are.
    """
    ingredients, health_tags, excluded = _gather_ingredients(text, detected_ingredients)
    results = recommend(ingredients=ingredients, health_tags=health_tags, excluded=excluded)
    return format_reply(results, requested_health_tags=health_tags)


def _confirmation_prompt(ingredients: list[str]) -> str:
    """
    Build the "anything else?" prompt text. The Quick Reply button itself is
    attached separately by the caller, via send_reply()'s quick_reply param
    (_CONFIRM_QUICK_REPLY) — this function only builds the message text.
    """
    if ingredients:
        have_line = f"ตอนนี้มีวัตถุดิบ: {', '.join(ingredients)}\n\n"
    else:
        have_line = ""
    return (
        f"{have_line}มีวัตถุดิบอื่นเพิ่มเติมไหมคะ? "
        f'พิมพ์เพิ่มได้เลย หรือกด "{confirmation.PRIMARY_CONFIRM_PHRASE}" ถ้าพร้อมแล้วค่ะ'
    )


def _finalize(pending: confirmation.PendingConfirmation) -> str:
    """
    Build the actual recommendation reply from a resolved PendingConfirmation
    — the confirmation-flow equivalent of handle_user_input()'s last two
    steps, but starting from already-gathered data instead of raw text
    (nothing new to extract at this point, the confirmation round is over).
    """
    results = recommend(
        ingredients=pending.ingredients,
        health_tags=pending.health_tags,
        excluded=pending.excluded,
    )
    return format_reply(results, requested_health_tags=pending.health_tags)


def _on_confirmation_timeout(pending: confirmation.PendingConfirmation) -> None:
    """
    Called on confirmation.py's own timer thread when a user never responds
    to the "anything else?" prompt within CONFIRM_TIMEOUT_SECONDS.

    No fresh reply token exists for this path — it is triggered by our own
    timer, not an incoming webhook — so this pushes directly via _push()
    rather than going through send_reply()'s reply-then-push-fallback order.
    This is the one place this feature costs LINE push quota by design; see
    confirmation.py's CONFIRM_TIMEOUT_SECONDS comment for why the timeout is
    generous enough that this should be rare.
    """
    _log(f"confirmation timeout: pushing final recommendation to {pending.user_id[:8]}...")
    reply = _finalize(pending)
    if len(reply) > MAX_MESSAGE_LENGTH:
        reply = reply[: MAX_MESSAGE_LENGTH - 3] + "..."
    _push(pending.user_id, TextMessage(text=reply))


def format_reply(
    results: list[dict], requested_health_tags: list[str] | None = None
) -> str:
    """
    Turn recommender output into the message the user actually reads.

    Deliberately a plain template and not an LLM call. Templates are instant,
    and the reply token from LINE expires in 10-30 seconds — a slow LLM round
    trip risks missing that window entirely and losing the reply.

    requested_health_tags: what the user actually asked for (parsed["health_tags"]
    from extract()), NOT a dish's own health_tags. Used only for the C15 fix
    below (concern.md) — everything else in this function still reads solely
    from each dish's own fields.

    C15 (concern.md): a dish's "keto" tag is correct about the dish itself, but
    misleading about the meal as eaten, because curry servings are costed
    without rice (200g curry, ~6g carb) while nobody eats curry without it
    (~60g carb once a normal rice portion is added). The tagging logic in
    recommend()/HEALTH_TAGS.md is deliberately left alone — it is accurate for
    what it measures. The fix belongs here, in the display layer: when a dish
    is keto AND the user specifically asked for keto, qualify it with
    "(ไม่รวมข้าว)" so the claim is honest about what's being promised. If the
    user never asked for keto, the tag is not shown at all — a dish being
    incidentally keto is not something an unrelated user needs to see.
    """
    if not results:
        return "ไม่พบเมนูที่ตรงกับวัตถุดิบที่มีค่ะ ลองส่งวัตถุดิบเพิ่มเติมดูนะคะ"

    requested_health_tags = requested_health_tags or []

    lines = ["🍳 เมนูแนะนำสำหรับคุณ", ""]

    for rank, dish in enumerate(results, start=1):
        lines.append(f"{rank}. {dish['name_th']}")

        if dish["have"]:
            lines.append(f"   ✅ มีแล้ว: {', '.join(dish['have'])}")
        if dish["missing"]:
            lines.append(f"   🛒 ต้องซื้อ: {', '.join(dish['missing'])}")

        if "keto" in dish["health_tags"] and "keto" in requested_health_tags:
            lines.append("   🏷️ คีโต (ไม่รวมข้าว)")

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
confirmation.set_timeout_handler(_on_confirmation_timeout)


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

    # The line-bot-sdk logs "No handler of <EventType>" at INFO level whenever
    # an event arrives that has no matching @handler.add() — e.g. a sticker,
    # a "follow" event, or a postback. Python's logging defaults to WARNING,
    # so that line is silently dropped unless this is configured. Without it,
    # sending the bot anything other than plain text/image looks exactly like
    # every other silent failure path.
    import logging

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

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
