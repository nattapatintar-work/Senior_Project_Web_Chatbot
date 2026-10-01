/*
 * web/js/logic.js
 * ===============
 * Pure functions with NO DOM and NO network, so `node --test web/tests` can
 * exercise them. Everything the UI decides (what a chip looks like, which
 * error message to show, whether "เพิ่ม..." means "show more") lives here;
 * app.js only wires it to the page.
 *
 * Loaded as a classic <script> (works over file:// too) and also as a
 * CommonJS module under Node.
 */
(function (root) {
  "use strict";

  var FG = (root.FG = root.FG || {});
  var logic = {};

  // ---------------------------------------------------------------------
  // Names and seasonings
  // ---------------------------------------------------------------------

  /** Thai name for a canonical key; falls back to the key so nothing renders blank. */
  logic.nameOf = function (key, names, extra) {
    return (extra && extra[key]) || (names && names[key]) || key;
  };

  /** Keys reordered into the tile order (the design's order). Unknown keys are dropped. */
  logic.orderSeasonings = function (keys, seasonings) {
    var wanted = {};
    keys.forEach(function (k) { wanted[k] = true; });
    return seasonings.map(function (pair) { return pair[0]; }).filter(function (k) { return wanted[k]; });
  };

  logic.sameSet = function (a, b) {
    if (!a || !b || a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) if (b.indexOf(a[i]) === -1) return false;
    return true;
  };

  /** The system note shown under the greeting once seasonings are confirmed. */
  logic.seasoningNote = function (applied, names) {
    var labels = applied.map(function (k) { return logic.nameOf(k, names); });
    return labels.length ? "เครื่องปรุงที่ยืนยัน · " + labels.join(", ") : "ไม่ได้เลือกเครื่องปรุง";
  };

  logic.seasoningSubline = function (locked, appliedCount, draftCount, total) {
    return locked
      ? "เลือกไว้ " + appliedCount + " จาก " + total + " รายการ"
      : "แตะเพื่อเลือก · เลือกแล้ว " + draftCount + " จาก " + total;
  };

  logic.seasoningConfirmLabel = function (locked, confirmed, pendingChange) {
    if (locked) return "ล็อกแล้ว";
    if (pendingChange) return "ยืนยันการเปลี่ยนแปลง";
    if (confirmed) return "ยืนยันแล้ว · ไปที่แชท";
    return "ยืนยันและเริ่มแชท";
  };

  logic.composerPlaceholder = function (confirmed, phase) {
    if (!confirmed) return "ยืนยันเครื่องปรุงก่อนเริ่มแชท";
    if (phase === "await_confirm" || phase === "await_correction") return "เช่น ใช่ แต่เอามะเขือเทศออก…";
    return "พิมพ์วัตถุดิบ หรือแนบรูป…";
  };

  // ---------------------------------------------------------------------
  // "Show more" -- only when the WHOLE message is the request. The design's
  // mock used /เพิ่ม|more/, which would also fire on "เพิ่มกระเทียม" (add garlic).
  // ---------------------------------------------------------------------

  var MORE_RE = new RegExp(
    "^(ขอเพิ่ม|ขอเมนูเพิ่ม|ขอเมนูอื่น(ๆ)?|เมนูอื่น(ๆ)?(อีก)?|เมนูเพิ่มเติม|เพิ่มอีก|ขออีก|อีก|" +
      "more|show more|see more|more please|next)" +
      "\\s*(ครับ|ค่ะ|คะ|นะ|หน่อย|ด้วย|ได้ไหม)?\\s*$",
    "i"
  );

  logic.isMoreRequest = function (text) {
    var t = String(text || "")
      .trim()
      .replace(/^[\s"“”'‘’.,!?…]+|[\s"“”'‘’.,!?…]+$/g, "");
    return t.length > 0 && MORE_RE.test(t);
  };

  /** Recommendation pages are 3 cards each; page p asks the server for the top min(10, 3*(p+1)). */
  logic.PAGE_SIZE = 3;
  logic.MAX_RESULTS = 10;
  logic.topNForPage = function (page) {
    return Math.min(logic.MAX_RESULTS, logic.PAGE_SIZE * (page + 1));
  };
  logic.sliceForPage = function (recipes, page) {
    var start = logic.PAGE_SIZE * page;
    return recipes.slice(start, start + logic.PAGE_SIZE);
  };
  /** True while a further page could exist: the server filled the request AND we are below the cap. */
  logic.canShowMore = function (page, returnedCount) {
    var asked = logic.topNForPage(page);
    return returnedCount >= asked && asked < logic.MAX_RESULTS;
  };

  // ---------------------------------------------------------------------
  // Category picker (all / savory / dessert): the hard filter POST /recommend applies before scoring.
  // "all" is the only mode that includes snack and drink recipes; condiments are never shown.
  // ---------------------------------------------------------------------

  /** [value, Thai label] in display order; the values are exactly what the backend accepts. */
  logic.CATEGORIES = [["all", "ทั้งหมด"], ["savory", "อาหารคาว"], ["dessert", "ขนมหวาน"]];
  logic.DEFAULT_CATEGORY = "all";

  /** Anything that is not one of the three values falls back to "all". */
  logic.normalizeCategory = function (value) {
    var known = logic.CATEGORIES.some(function (pair) { return pair[0] === value; });
    return known ? value : logic.DEFAULT_CATEGORY;
  };

  /** A new round (any new input after results were shown) starts from "all" again, like the server's start_new_round(). */
  logic.shouldResetCategory = function (phase) { return phase === "results"; };

  /**
   * The picker is live while the list waits for confirmation. Once results are out it is read-only, EXCEPT
   * when the chosen category came back empty (`emptyForCategory`, the server's flag): then it stays live so
   * the user can pick another option instead of hitting a dead end.
   */
  logic.categoryPickerEnabled = function (phase, busy, emptyForCategory) {
    if (busy) return false;
    return phase === "await_confirm" || phase === "await_correction" || (phase === "results" && emptyForCategory === true);
  };

  /**
   * What a click on a picker option does:
   *   "ignore"     the picker is not live, or (dead-end state) the option is already the chosen one
   *   "set"        before confirmation: just remember the choice (it is sent with /recommend)
   *   "rerequest"  the chosen category was empty: ask /recommend for the first page again with the new one
   *                (same session and ingredients, nothing reset)
   */
  logic.categoryClickAction = function (phase, busy, emptyForCategory, current, next) {
    if (!logic.categoryPickerEnabled(phase, busy, emptyForCategory)) return "ignore";
    if (phase === "results") return next === current ? "ignore" : "rerequest";
    return "set";
  };

  /** Shown when the chosen category has nothing for these ingredients (but "all" would). "" for any other category. */
  logic.categoryEmptyMessage = function (category) {
    if (category === "savory") return "ไม่พบอาหารคาวที่ใช้วัตถุดิบเหล่านี้ได้";
    if (category === "dessert") return "ไม่พบขนมหวานที่ใช้วัตถุดิบเหล่านี้ได้";
    return "";
  };

  /**
   * Message for an empty /recommend page. `emptyForCategory` is the server's flag (true only when the
   * chosen category is empty although "all" is not); otherwise the pre-existing wording is kept.
   */
  logic.emptyRecommendMessage = function (page, category, emptyForCategory) {
    if (page > 0) return "ไม่มีเมนูเพิ่มเติมแล้ว ลองเพิ่มวัตถุดิบเพื่อค้นหาใหม่ได้เลย";
    var forCategory = emptyForCategory ? logic.categoryEmptyMessage(category) : "";
    return forCategory || "ยังไม่พบเมนูที่ตรงกับวัตถุดิบที่มี ลองเพิ่มวัตถุดิบดูนะ";
  };

  // ---------------------------------------------------------------------
  // Ingredient-list bubble (groups of chips)
  // ---------------------------------------------------------------------

  /**
   * @param s  { photoKeys, textKeys, excluded, healthTags, combined }  (arrays of keys)
   * @param opt { added: [keys], removed: [keys] }  what THIS update changed (for +/strikethrough chips)
   * @returns [{source: photo|text|excluded|tags, label, items: [{label, mode: plain|removed|added}]}]
   */
  logic.buildGroups = function (s, opt, names, extraNames) {
    opt = opt || {};
    var added = opt.added || [];
    var removed = opt.removed || [];
    var combined = s.combined || [];
    var label = function (k) { return logic.nameOf(k, names, extraNames); };
    var has = function (arr, k) { return arr.indexOf(k) !== -1; };
    var groups = [];

    var photoItems = [];
    (s.photoKeys || []).forEach(function (k) {
      if (has(combined, k)) photoItems.push({ label: label(k), mode: "plain" });
      else if (has(removed, k)) photoItems.push({ label: label(k), mode: "removed" });
    });
    if (photoItems.length) groups.push({ source: "photo", label: "จากรูป", items: photoItems });

    var textItems = [];
    var seenText = {};
    (s.textKeys || []).forEach(function (k) {
      if (seenText[k]) return;
      seenText[k] = true;
      if (has(added, k)) textItems.push({ label: label(k), mode: "added" });
      else if (has(combined, k)) textItems.push({ label: label(k), mode: "plain" });
      else if (has(removed, k)) textItems.push({ label: label(k), mode: "removed" });
    });
    added.forEach(function (k) {
      if (!seenText[k] && has(combined, k)) { seenText[k] = true; textItems.push({ label: label(k), mode: "added" }); }
    });
    // Anything in the final list that neither source list explains still has to be visible.
    combined.forEach(function (k) {
      var inPhoto = has(s.photoKeys || [], k);
      if (!seenText[k] && !inPhoto) { seenText[k] = true; textItems.push({ label: label(k), mode: "plain" }); }
    });
    if (textItems.length) groups.push({ source: "text", label: "จากข้อความ", items: textItems });

    if ((s.excluded || []).length) {
      groups.push({
        source: "excluded", label: "ไม่เอา",
        items: s.excluded.map(function (k) { return { label: label(k), mode: "removed" }; }),
      });
    }
    if ((s.healthTags || []).length) {
      groups.push({
        source: "tags", label: "เงื่อนไข",
        items: s.healthTags.map(function (t) { return { label: t, mode: "plain" }; }),
      });
    }
    return groups;
  };

  /**
   * UI lists after a /confirm confirm+correction (`add` / `remove` are the server's resolved keys).
   *
   * A removal FIXES the list ("not chicken, pork"): it shows as a struck chip and never goes into
   * `excluded`, because the backend no longer bans dishes for it (api/app.py: ban_excluded=False).
   * `excluded` only holds typed "no X" from ExtractResponse.exclude, so it is passed through untouched:
   * an item excluded by the first message stays in the "ไม่เอา" group even if it is removed again here.
   *
   * @returns { view, photoKeys, textKeys }
   *   view       what buildGroups needs for THIS bubble; removed keys are still in the key lists so they
   *              render struck-through
   *   photoKeys / textKeys   the lists to keep afterwards (removed keys dropped)
   */
  logic.applyConfirmCorrection = function (s, add, remove) {
    add = add || [];
    remove = remove || [];
    var textKeys = logic.unionInOrder(s.textKeys, add);
    var without = function (keys) { return keys.filter(function (k) { return remove.indexOf(k) === -1; }); };
    return {
      view: { photoKeys: s.photoKeys, textKeys: textKeys, excluded: s.excluded, healthTags: s.healthTags, combined: s.combined },
      photoKeys: without(s.photoKeys),
      textKeys: without(textKeys),
    };
  };

  logic.chipText = function (item) {
    return (item.mode === "added" ? "+ " : "") + item.label;
  };

  /**
   * Note for words the server labelled as ingredients but has no key for (ExtractResponse.unknown).
   * Informational only: the confirm flow carries on. Returns "" when there is nothing to say.
   * Capped so a long pasted text can't produce a wall of words.
   */
  logic.MAX_UNKNOWN_SHOWN = 5;
  logic.unknownNote = function (words) {
    var list = (words || []).filter(function (w) { return typeof w === "string" && w.trim(); });
    if (!list.length) return "";
    var shown = list.slice(0, logic.MAX_UNKNOWN_SHOWN).map(function (w) { return w.trim(); });
    var more = list.length > shown.length ? " และอีก " + (list.length - shown.length) + " รายการ" : "";
    return "ไม่พบวัตถุดิบเหล่านี้ในระบบ: " + shown.join(", ") + more;
  };

  logic.unionInOrder = function (base, more) {
    var out = (base || []).slice();
    (more || []).forEach(function (k) { if (out.indexOf(k) === -1) out.push(k); });
    return out;
  };

  // ---------------------------------------------------------------------
  // Recipe card view-model
  // ---------------------------------------------------------------------

  logic.safeUrl = function (u) {
    if (typeof u !== "string" || !/^https?:\/\//i.test(u.trim())) return null;
    try { new URL(u.trim()); } catch (e) { return null; }
    return u.trim();
  };

  /**
   * One /recommend recipe -> everything the card template needs.
   * `have` from the server includes optional ingredients, so main-ingredient
   * chips are the recipe's mains checked against it; seasoning chips are the
   * recipe's own seasonings checked against `seasonings_matched` (the user's ticked subset).
   */
  logic.buildCard = function (recipe, rank, names) {
    var haveSet = {};
    (recipe.have || []).forEach(function (k) { haveSet[k] = true; });
    var matched = {};
    (recipe.seasonings_matched || []).forEach(function (k) { matched[k] = true; });

    var main = (recipe.main_ingredients || []).map(function (k) {
      return { label: logic.nameOf(k, names), have: !!haveSet[k] };
    });
    var seas = (recipe.seasonings || []).map(function (k) {
      return { label: logic.nameOf(k, names), have: !!matched[k] };
    });
    var haveMain = main.filter(function (x) { return x.have; }).length;
    var missSeas = seas.filter(function (x) { return !x.have; }).length;
    var kcal = recipe.nutrition && recipe.nutrition.kcal;

    return {
      rank: rank,
      name: recipe.name_th,
      time: recipe.cook_time_min == null ? null : Math.round(recipe.cook_time_min),
      kcal: kcal == null ? null : Math.round(kcal),
      tags: (recipe.health_tags || []).slice(),
      url: logic.safeUrl(recipe.recipe_source_url),
      main: main,
      haveMain: haveMain,
      totalMain: main.length,
      seas: seas,
      seasSummary: missSeas === 0 ? "ครบ" : "ขาด " + missSeas,
    };
  };

  // ---------------------------------------------------------------------
  // Errors: the backend answers in two shapes, so normalise both.
  //   {"detail": "unknown session"}                       (our HTTPExceptions, 429)
  //   {"detail": [{"loc": [...], "msg": "..."}, ...]}    (FastAPI validation, 422)
  // ---------------------------------------------------------------------

  logic.detailText = function (body) {
    if (!body || typeof body !== "object") return "";
    var d = body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d
        .map(function (e) { return e && typeof e === "object" ? e.msg || "" : String(e); })
        .filter(Boolean)
        .join("; ");
    }
    return "";
  };

  /**
   * @param err { kind: "network"|"timeout"|"http", status?: number, detail?: string }
   * @returns { code, message (Thai, user-facing), retryable }
   */
  logic.classifyError = function (err) {
    var status = err.status || 0;
    var detail = err.detail || "";
    if (err.kind === "network") {
      return { code: "network", retryable: true, message: "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบอินเทอร์เน็ตแล้วลองอีกครั้ง" };
    }
    if (err.kind === "timeout") {
      return { code: "timeout", retryable: true, message: "เซิร์ฟเวอร์ตอบช้าเกินไป ลองอีกครั้ง" };
    }
    if (status === 404 && /unknown session/i.test(detail)) {
      return { code: "session_expired", retryable: false, message: "เซสชันหมดอายุแล้ว เริ่มรายการใหม่ให้แล้ว กรุณาส่งวัตถุดิบอีกครั้ง" };
    }
    if (status === 429) {
      return { code: "rate_limited", retryable: true, message: "ส่งถี่เกินไป รอสักครู่แล้วลองอีกครั้ง" };
    }
    if (status === 413) {
      return { code: "too_large", retryable: false, message: "ไฟล์รูปใหญ่เกินไป ลองรูปที่เล็กลงหรือส่งทีละน้อย" };
    }
    if (status === 503) {
      return { code: "detector_unavailable", retryable: true, message: "ระบบอ่านรูปยังไม่พร้อมตอนนี้ ลองพิมพ์บอกวัตถุดิบแทนได้" };
    }
    if (status === 409 && /locked/i.test(detail)) {
      return { code: "seasoning_locked", retryable: false, message: "เครื่องปรุงถูกล็อกแล้ว เริ่มแชทใหม่เพื่อแก้ไขรายการ" };
    }
    if (status === 409) {
      return { code: "conflict", retryable: false, message: "ยังทำขั้นตอนนี้ไม่ได้ ลองตอบยืนยันรายการวัตถุดิบก่อน" };
    }
    if (status === 422 && /no usable images/i.test(detail)) {
      return { code: "bad_images", retryable: false, message: "ใช้รูปนี้ไม่ได้ (ไฟล์ไม่รองรับ อ่านไม่ได้ หรือใหญ่เกิน 8 MB)" };
    }
    if (status === 422 && /not in the current ingredient list/i.test(detail)) {
      return { code: "stale_list", retryable: false, message: "รายการเปลี่ยนไปแล้ว ลองเลือกใหม่อีกครั้ง" };
    }
    if (status === 422) {
      return { code: "invalid", retryable: false, message: "ข้อมูลที่ส่งไม่ถูกต้อง ลองแก้ข้อความหรือรูปแล้วส่งอีกครั้ง" };
    }
    if (status >= 500) {
      return { code: "server_error", retryable: true, message: "เซิร์ฟเวอร์ขัดข้อง ลองอีกครั้งในอีกสักครู่" };
    }
    return { code: "unknown", retryable: true, message: "มีบางอย่างผิดพลาด ลองอีกครั้ง" };
  };

  // ---------------------------------------------------------------------
  // Images
  // ---------------------------------------------------------------------

  logic.ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
  logic.MAX_IMAGES = 5;
  logic.MAX_IMAGE_BYTES = 8 * 1024 * 1024;
  logic.MAX_IMAGE_SIDE = 1600;
  logic.KEEP_ORIGINAL_BELOW_BYTES = 1.5 * 1024 * 1024;

  /** Scale (w, h) down so the longer side is <= max, keeping aspect ratio. Never scales up. */
  logic.fitWithin = function (w, h, max) {
    var longest = Math.max(w, h);
    if (longest <= max) return { width: w, height: h, scaled: false };
    var k = max / longest;
    return { width: Math.max(1, Math.round(w * k)), height: Math.max(1, Math.round(h * k)), scaled: true };
  };

  logic.jpegName = function (name) {
    var base = String(name || "photo").replace(/\.[^./\\]+$/, "");
    return (base || "photo") + ".jpg";
  };

  FG.logic = logic;
  if (typeof module !== "undefined" && module.exports) module.exports = FG;
})(typeof window !== "undefined" ? window : globalThis);
