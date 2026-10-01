/*
 * web/js/app.js
 * =============
 * State, rendering and the real conversation flow. Decisions that don't need a
 * browser live in logic.js (tested under Node); HTTP lives in api.js.
 *
 * THE FLOW (see design_reference/Main.dc.EXACT.html for the look; the real
 * backend drives the steps the design mocked):
 *
 *   Seasoning tab  --confirm-->  POST /seasoning           (creates the session)
 *   Chat, phase "compose":
 *       photos and/or text  -->  POST /detect, POST /extract (same session)
 *                            -->  list bubble               phase "await_confirm"
 *   Chat, phase "await_confirm" / "await_correction", text-only reply:
 *       POST /confirm  -->  confirm            -> POST /recommend -> cards   phase "results"
 *                           confirm+correction -> updated list, ask again
 *                           reject             -> checklist bubble           phase "await_correction"
 *                           unclear            -> re-ask
 *   Checklist "update"  -->  POST /correct  -> updated list, ask again
 *   Phase "results": "ขอเพิ่ม" -> next 3 cards; anything else = new input (compose path)
 *
 * All text from the server is written with textContent, never innerHTML.
 */
(function () {
  "use strict";

  var FG = window.FG;
  var L = FG.logic;
  var TILES = window.FG_DATA.seasonings;   // [[key, thai name], ...] in display order
  var NAMES = window.FG_DATA.names;        // key -> thai name
  var DRAFT_KEY = "fg.seasoningDraft";

  // ---- API base: ?api=... beats config.js; "" means same origin --------------------------
  var apiParam = new URLSearchParams(window.location.search).get("api");
  var api = FG.createApi({
    base: apiParam !== null ? apiParam : (window.FG_CONFIG && window.FG_CONFIG.API_BASE) || "",
  });

  // ---- tiny DOM helpers ---------------------------------------------------------------------
  function $(id) { return document.getElementById(id); }

  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k === "on") Object.keys(v).forEach(function (ev) { el.addEventListener(ev, v[ev]); });
        else el.setAttribute(k, v === true ? "" : v);
      });
    }
    (kids || []).forEach(function (kid) {
      if (kid === null || kid === undefined || kid === false) return;
      el.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
    });
    return el;
  }

  // Icon paths copied from the design. These are static constants (no server text).
  var ICONS = {
    lock: '<rect x="5" y="11" width="14" height="9" rx="2"></rect><path d="M8 11V8a4 4 0 0 1 8 0v3"></path>',
    user: '<circle cx="12" cy="8" r="3.5"></circle><path d="M5 19.5c1.2-3.3 3.9-5 7-5s5.8 1.7 7 5"></path>',
    bot: '<path d="M7.5 14.5A3.6 3.6 0 0 1 6.6 7.4 4.2 4.2 0 0 1 12 4.8a4.2 4.2 0 0 1 5.4 2.6 3.6 3.6 0 0 1-.9 7.1"></path><path d="M7.5 12.5V19.5h9v-7"></path><path d="M7.5 16.8h9"></path>',
    image: '<rect x="3" y="5" width="18" height="14" rx="2"></rect><circle cx="9" cy="10" r="1.8"></circle><path d="M21 16l-5-5-8 8"></path>',
    lines: '<path d="M5 6h14M5 12h14M5 18h9"></path>',
    clock: '<circle cx="12" cy="12" r="8.5"></circle><path d="M12 7.5V12l3 2"></path>',
    external: '<path d="M14 4h6v6"></path><path d="M20 4l-9 9"></path><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"></path>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"></path>',
    ring: '<circle cx="12" cy="12" r="6.5"></circle>',
    close: '<path d="M6 6l12 12M18 6L6 18"></path>',
  };

  function svg(name, size, strokeWidth) {
    var el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    el.setAttribute("viewBox", "0 0 24 24");
    el.setAttribute("width", size);
    el.setAttribute("height", size);
    el.setAttribute("aria-hidden", "true");
    if (strokeWidth) el.style.strokeWidth = strokeWidth;
    el.innerHTML = ICONS[name];
    return el;
  }

  // ---- state -------------------------------------------------------------------------------------
  var S;

  function loadDraft() {
    try {
      var v = JSON.parse(window.localStorage.getItem(DRAFT_KEY));
      return Array.isArray(v) ? L.orderSeasonings(v.filter(function (k) { return typeof k === "string"; }), TILES) : [];
    } catch (e) { return []; }
  }
  function saveDraft() {
    try { window.localStorage.setItem(DRAFT_KEY, JSON.stringify(S.draft)); } catch (e) { /* private mode: fine */ }
  }

  function freshState(draft) {
    return {
      tab: "seasoning", draft: draft, applied: null, locked: false,
      seasBusy: false, seasError: "",
      sid: null, phase: "compose",                 // compose | await_confirm | await_correction | results
      messages: [], text: "", atts: [], busy: false, anchor: null,
      seq: 0, attSeq: 0,
      photoKeys: [], textKeys: [], excluded: [], healthTags: [], combined: [],
      category: L.DEFAULT_CATEGORY,                // the category picker's choice for this round
      categoryEmpty: false,                        // the server said the chosen category has nothing (picker stays live)
      page: 0, moreAvailable: false, lastListId: null, extraNames: {},
    };
  }

  function nid(prefix) { S.seq += 1; return prefix + S.seq; }

  // ---- messages ----------------------------------------------------------------------------------
  var GREETING = "สวัสดี! ส่งรูปวัตถุดิบในตู้เย็น หรือพิมพ์บอกได้เลยว่ามีอะไรบ้าง";
  var CONFIRM_PROMPT = "ถูกต้องไหม? ตอบกลับได้เลย เช่น “ใช่” หรือ “เอา…ออก เพิ่ม…”";

  function botText(text, extra) { return Object.assign({ id: nid("b"), role: "bot", kind: "text", text: text }, extra || {}); }
  function typingMsg() { return { id: "typing", role: "bot", kind: "typing" }; }

  function addMsgs(list) { S.messages = S.messages.concat(list); }
  function withoutTyping() { return S.messages.filter(function (m) { return m.kind !== "typing"; }); }
  function replaceTyping(list) { S.messages = withoutTyping().concat(list); }
  function ensureTyping() {
    if (!S.messages.some(function (m) { return m.kind === "typing"; })) addMsgs([typingMsg()]);
  }

  // ---- rendering ---------------------------------------------------------------------------------
  /** Elements are rebuilt on every render; give focus back to the one that had it (matched by data-fid). */
  function keepFocus(fn) {
    var active = document.activeElement;
    var fid = active && active.getAttribute ? active.getAttribute("data-fid") : null;
    fn();
    if (fid) {
      var again = document.querySelector('[data-fid="' + fid + '"]');
      if (again && !again.disabled) again.focus({ preventScroll: true });
    }
  }

  function render(opts) {
    opts = opts || {};
    keepFocus(function () {
      renderTabs();
      renderChat(opts);
      renderComposer();
      renderSeasoning();
    });
  }

  function renderTabs() {
    var chat = S.tab === "chat";
    $("chatView").hidden = !chat;
    $("seasoningView").hidden = chat;
    $("tabChat").setAttribute("aria-pressed", String(chat));
    $("tabSeas").setAttribute("aria-pressed", String(!chat));
    $("tabLock").hidden = !S.locked;
  }

  function renderChat(opts) {
    if (S.tab !== "chat") return;

    // gate: seasonings must be confirmed before the chat is usable
    var gate = $("gate");
    gate.textContent = "";
    if (!S.applied) {
      gate.appendChild(h("div", { class: "gate" }, [
        h("div", { class: "gate-icon" }, [svg("lock", 26, 1.8)]),
        h("div", { class: "gate-title", text: "ยืนยันเครื่องปรุงก่อนเริ่มแชท" }),
        h("div", { class: "gate-text", text: "เลือกเครื่องปรุงที่มีในครัวแล้วกดยืนยัน บอทจะใช้รายการนี้ประกอบการแนะนำเมนู" }),
        h("button", { type: "button", class: "gate-btn", text: "ไปที่ Seasoning", on: { click: function () { setTab("seasoning"); } } }),
      ]));
    }

    var box = $("messages");
    var scroller = $("scroll");
    var keep = scroller.scrollTop;
    box.textContent = "";
    S.messages.forEach(function (m) { box.appendChild(renderMessage(m)); });

    if (opts.keepScroll) scroller.scrollTop = keep;
    else scrollChat();
  }

  // Ported from the design's scrollChat(): a tall bubble (or an anchor) aligns to the top so its start is
  // readable; otherwise stick to the bottom.
  function scrollChat() {
    var el = $("scroll");
    var nodes = el.querySelectorAll("[data-mid]");
    var target = null;
    if (S.anchor) target = el.querySelector('[data-mid="' + S.anchor + '"]');
    if (!target && nodes.length) target = nodes[nodes.length - 1];
    if (target && target.offsetHeight > el.clientHeight - 24) el.scrollTop = target.offsetTop - 12;
    else if (S.anchor && target) el.scrollTop = target.offsetTop - 12;
    else el.scrollTop = el.scrollHeight;
  }

  function renderMessage(m) {
    if (m.role === "note") {
      return h("div", { class: "note" + (m.error ? " note-error" : ""), "data-mid": m.id }, [h("div", { text: m.text })]);
    }
    if (m.role === "user") return renderUser(m);
    return renderBot(m);
  }

  function renderUser(m) {
    var col = [];
    if (m.images && m.images.length) {
      col.push(h("div", { class: "user-images" + (m.images.length === 1 ? " one" : "") },
        m.images.map(function (url, i) {
          return h("div", { class: "user-img" }, [h("img", { src: url, alt: "รูปวัตถุดิบ " + (i + 1) })]);
        })));
    }
    if (m.text) col.push(h("div", { class: "user-text", text: m.text }));
    return h("div", { class: "msg msg-user", "data-mid": m.id }, [
      h("div", { class: "avatar avatar-user", "aria-hidden": "true" }, [svg("user", 18, 1.8)]),
      h("div", { class: "user-col" }, col),
    ]);
  }

  function botShell(m, kids) {
    return h("div", { class: "msg", "data-mid": m.id }, [
      h("div", { class: "avatar avatar-bot", "aria-hidden": "true" }, [svg("bot", 18, 1.8)]),
      h("div", { class: "bot-col" }, kids),
    ]);
  }

  function renderBot(m) {
    if (m.kind === "typing") {
      return botShell(m, [h("div", { class: "typing", "aria-label": "บอทกำลังพิมพ์" }, [h("span"), h("span"), h("span")])]);
    }
    if (m.kind === "results") return renderResults(m);
    if (m.kind === "checklist") return renderChecklist(m);

    var body = [];
    if (m.text) body.push(h("div", { class: "bubble-text", text: m.text }));
    if (m.kind === "list") body.push(renderGroups(m.groups));
    // the picker lives in the ingredient-confirm screen, only in the newest list bubble
    if (m.kind === "list" && m.id === S.lastListId) body.push(renderCategoryPicker());
    if (m.footer) body.push(h("div", { class: "bubble-footer", text: m.footer }));
    if (m.retry) {
      body.push(h("button", {
        type: "button", class: "action-btn secondary", text: "ลองอีกครั้ง",
        on: { click: function () { retryFrom(m); } },
      }));
    }
    return botShell(m, [h("div", { class: "bubble" }, body)]);
  }

  /** all / savory / dessert as segmented buttons (aria-pressed); read-only once results are shown. */
  function renderCategoryPicker() {
    var enabled = L.categoryPickerEnabled(S.phase, S.busy, S.categoryEmpty);
    return h("div", { class: "seg", role: "group", "aria-label": "ประเภทเมนู" }, L.CATEGORIES.map(function (pair) {
      var value = pair[0];
      return h("button", {
        type: "button", class: "seg-btn", text: pair[1], "data-fid": "cat:" + value,
        "aria-pressed": String(S.category === value), disabled: !enabled,
        on: { click: function () { setCategory(value); } },
      });
    }));
  }

  function setCategory(value) {
    var next = L.normalizeCategory(value);
    var action = L.categoryClickAction(S.phase, S.busy, S.categoryEmpty, S.category, next);
    if (action === "ignore") return;
    S.category = next;
    if (action === "rerequest") runOp(opRecommend());     // the chosen category was empty: try another, same session
    else render({ keepScroll: true });
  }

  /** First page of recommendations again, with whatever category is now chosen (nothing else is reset). */
  function opRecommend() {
    return async function () { await recommendPage(0); };
  }

  function renderGroups(groups) {
    return h("div", { class: "groups" }, groups.map(function (g) {
      return h("div", { class: "group" }, [
        h("div", { class: "group-label" }, [svg(g.source === "photo" ? "image" : "lines", 15, 1.8), h("span", { text: g.label })]),
        h("div", { class: "chips" }, g.items.map(function (it) {
          return h("span", { class: "chip chip-" + it.mode, text: L.chipText(it) });
        })),
      ]);
    }));
  }

  function renderChecklist(m) {
    var kids = [h("div", { class: "bubble-text", text: "เลือกวัตถุดิบที่ไม่ถูกต้อง แล้วพิมพ์สิ่งที่อยากเพิ่ม (ถ้ามี)" })];
    if (!m.done) kids.push(h("div", { class: "check-hint", text: "แตะเพื่อเอาออก" }));

    kids.push(h("div", { class: "chips" }, m.keys.map(function (k) {
      var on = !!m.selected[k];
      return h("button", {
        type: "button", class: "check-chip", "aria-pressed": String(on), disabled: m.done, "data-fid": "chk:" + m.id + ":" + k,
        text: L.nameOf(k, NAMES, S.extraNames),
        on: { click: function () { m.selected[k] = !m.selected[k]; render({ keepScroll: true }); } },
      });
    })));

    var input = h("input", {
      type: "text", class: "add-input", placeholder: "เพิ่มวัตถุดิบ เช่น กระเทียม, ไข่", maxlength: "500",
      value: m.addText || "", disabled: m.done, "aria-label": "เพิ่มวัตถุดิบ",
    });
    var submit = h("button", { type: "button", class: "action-btn", text: m.done ? "ส่งแล้ว" : "อัปเดตรายการ" });
    function sync() { submit.disabled = m.done || S.busy || !(hasSelection(m) || m.addText.trim()); }
    input.addEventListener("input", function () { m.addText = input.value; sync(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.isComposing && !submit.disabled) { e.preventDefault(); submitChecklist(m); }
    });
    submit.addEventListener("click", function () { submitChecklist(m); });
    sync();

    if (!m.done) { kids.push(input); kids.push(submit); }
    return botShell(m, [h("div", { class: "bubble" }, kids)]);
  }

  function hasSelection(m) { return m.keys.some(function (k) { return m.selected[k]; }); }

  function renderResults(m) {
    var kids = [];
    if (m.text) kids.push(h("div", { class: "bubble" }, [h("div", { class: "bubble-text", text: m.text })]));
    kids.push(h("div", { class: "cards" }, m.cards.map(renderCard)));
    if (m.cardFooter) kids.push(h("div", { class: "card-footer", text: m.cardFooter }));
    return botShell(m, kids);
  }

  function ingChip(item) {
    return h("span", { class: "ing " + (item.have ? "ing-have" : "ing-miss") }, [
      item.have ? svg("check", 13, 2.4) : svg("ring", 13, 2),
      h("span", { text: item.label }),
    ]);
  }

  function renderCard(c) {
    var meta = [];
    if (c.time !== null) meta.push(h("span", { class: "time" }, [svg("clock", 14, 1.8), h("span", { text: c.time + " นาที" })]));
    if (c.kcal !== null) meta.push(h("span", { text: c.kcal + " kcal" }));
    c.tags.forEach(function (t) { meta.push(h("span", { class: "tag", text: t })); });

    var head = [h("div", { class: "card-title-col" }, [
      h("div", { class: "card-title", text: c.rank + ". " + c.name }),
      h("div", { class: "card-meta" }, meta),
    ])];
    if (c.url) {
      head.push(h("a", { class: "card-link", href: c.url, target: "_blank", rel: "noopener noreferrer" }, [
        h("span", { text: "ดูสูตร" }), svg("external", 14, 2),
      ]));
    }

    var parts = [h("div", { class: "card-head" }, head), h("div", { class: "card-divider" })];
    parts.push(h("div", { class: "card-section" }, [
      h("div", { class: "card-section-head" }, [
        h("span", { class: "card-section-title", text: "วัตถุดิบหลัก" }),
        h("span", { class: "card-have-pill", text: "มี " + c.haveMain + "/" + c.totalMain + " วัตถุดิบหลัก" }),
      ]),
      h("div", { class: "chips" }, c.main.map(ingChip)),
    ]));
    if (c.seas.length) {
      parts.push(h("div", { class: "card-section" }, [
        h("div", { class: "card-section-head" }, [
          h("span", { class: "card-section-title", text: "เครื่องปรุง" }),
          h("span", { class: "card-seas-summary", text: c.seasSummary }),
        ]),
        h("div", { class: "chips" }, c.seas.map(ingChip)),
      ]));
    }
    return h("div", { class: "card" }, parts);
  }

  // ---- composer ----------------------------------------------------------------------------------
  function renderComposer() {
    var confirmed = !!S.applied;
    var input = $("fg-composer");
    input.disabled = !confirmed;
    input.placeholder = L.composerPlaceholder(confirmed, S.phase);
    if (input.value !== S.text) input.value = S.text;
    $("composer").classList.toggle("disabled", !confirmed);

    $("attachBtn").disabled = !confirmed || S.atts.length >= L.MAX_IMAGES;
    var hasContent = S.text.trim().length > 0 || S.atts.length > 0;
    $("sendBtn").disabled = !(confirmed && !S.busy && hasContent);

    var row = $("atts");
    row.hidden = S.atts.length === 0;
    if (renderComposer.lastAtts === S.atts) return;
    renderComposer.lastAtts = S.atts;
    row.textContent = "";
    S.atts.forEach(function (a, i) {
      row.appendChild(h("div", { class: "att" }, [
        h("div", { class: "att-img" }, [h("img", { src: a.url, alt: "รูป " + (i + 1) })]),
        h("button", {
          type: "button", class: "att-remove", "aria-label": "ลบรูป " + (i + 1),
          on: { click: function () { removeAtt(a.id); } },
        }, [svg("close", 12, 3)]),
      ]));
    });
  }

  var toastTimer = null;
  function toast(msg) {
    var el = $("toast");
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 4500);
  }

  // ---- seasoning tab -----------------------------------------------------------------------------
  function renderSeasoning() {
    var confirmed = !!S.applied;
    var pending = confirmed && !S.locked && !L.sameSet(L.orderSeasonings(S.draft, TILES), S.applied);

    $("lockBanner").hidden = !S.locked;
    $("seasSub").textContent = L.seasoningSubline(S.locked, confirmed ? S.applied.length : 0, S.draft.length, TILES.length);
    $("seasPending").hidden = !pending;
    $("seasError").hidden = !S.seasError;
    $("seasError").textContent = S.seasError;

    var grid = $("tiles");
    grid.className = "tiles" + (S.locked ? " locked" : "");
    grid.textContent = "";
    TILES.forEach(function (pair) {
      var key = pair[0];
      var selected = S.draft.indexOf(key) !== -1;
      var kids = [h("span", { text: pair[1] })];
      if (selected) kids.push(h("span", { class: "tile-check", "aria-hidden": "true" }, [svg("check", 12, 3.2)]));
      grid.appendChild(h("button", {
        type: "button", class: "tile", "aria-pressed": String(selected), disabled: S.locked || S.seasBusy, "data-fid": "tile:" + key,
        on: { click: function () { toggleTile(key); } },
      }, kids));
    });

    var btn = $("confirmBtn");
    btn.disabled = S.locked || S.seasBusy;
    btn.textContent = S.seasBusy ? "กำลังยืนยัน…" : L.seasoningConfirmLabel(S.locked, confirmed, pending);
  }

  function toggleTile(key) {
    if (S.locked || S.seasBusy) return;
    var d = S.draft.slice();
    var at = d.indexOf(key);
    if (at === -1) d.push(key); else d.splice(at, 1);
    S.draft = d;
    saveDraft();
    S.seasError = "";
    keepFocus(renderSeasoning);
  }

  async function confirmSeasonings() {
    if (S.locked || S.seasBusy) return;
    var st = S;
    var applied = L.orderSeasonings(S.draft, TILES);
    S.seasBusy = true; S.seasError = "";
    renderSeasoning();
    try {
      var resp;
      try {
        resp = await api.seasoning(S.sid, applied);
      } catch (e) {
        if (e.code !== "session_expired") throw e;
        resp = await api.seasoning(null, applied);          // the old session timed out: start a fresh one
      }
      guard(st);
      S.sid = resp.session_id;
      S.applied = L.orderSeasonings(resp.seasonings, TILES);
      var note = { id: "note", role: "note", text: L.seasoningNote(S.applied, NAMES) };
      S.messages = S.messages.length
        ? S.messages.map(function (m) { return m.id === "note" ? note : m; })
        : [{ id: "greet", role: "bot", kind: "text", text: GREETING }, note];
      S.tab = "chat";
      S.anchor = null;
    } catch (e) {
      if (e === CANCELLED || S !== st) return;
      e = asApiError(e);
      if (e.code === "seasoning_locked") S.locked = true;
      S.seasError = e.message;
    } finally {
      if (S === st) { S.seasBusy = false; render(); }
    }
  }

  function setTab(tab) {
    S.tab = tab;
    if (tab === "chat") S.anchor = null;
    render();
  }

  function newChat() {
    S.messages.forEach(function (m) { (m.images || []).forEach(revoke); });
    S.atts.forEach(function (a) { revoke(a.url); });
    var draft = S.draft;
    S = freshState(draft);           // any request still in flight belongs to the OLD state and is ignored (see guard)
    $("fg-composer").value = "";
    render();
  }

  function revoke(url) { try { URL.revokeObjectURL(url); } catch (e) { /* ignore */ } }

  // ---- attachments -------------------------------------------------------------------------------
  async function addFiles(fileList) {
    if (!S.applied) return;
    var files = Array.prototype.slice.call(fileList || []).filter(function (f) { return f && /^image\//i.test(f.type || "") || (f && !f.type); });
    if (!files.length) return;
    if (S.atts.length + files.length > L.MAX_IMAGES) {
      toast("แนบได้สูงสุด " + L.MAX_IMAGES + " รูปต่อครั้ง");
      files = files.slice(0, Math.max(0, L.MAX_IMAGES - S.atts.length));
    }
    var st = S;
    for (var i = 0; i < files.length; i++) {
      if (S.atts.length >= L.MAX_IMAGES) break;
      try {
        var p = await FG.images.prepare(files[i]);
        if (S !== st) { revoke(p.url); return; }          // "new chat" happened while the photo was being prepared
        S.attSeq += 1;
        p.id = S.attSeq;
        S.atts = S.atts.concat([p]);
        renderComposer();
      } catch (e) {
        toast((e && e.message) || FG.images.MESSAGES.undecodable);
      }
    }
  }

  function removeAtt(id) {
    S.atts.forEach(function (a) { if (a.id === id) revoke(a.url); });
    S.atts = S.atts.filter(function (a) { return a.id !== id; });
    renderComposer();
  }

  // ---- errors ------------------------------------------------------------------------------------
  function asApiError(e) {
    if (e && e.name === "ApiError") return e;
    if (window.console) console.error(e);
    var c = L.classifyError({ kind: "http", status: 0 });
    var err = new Error(c.message);
    err.code = c.code; err.retryable = c.retryable; err.name = "ApiError";
    return err;
  }

  /** The server forgot this session (idle > 1 h). Rebuild it with the confirmed seasonings and start the list over. */
  async function handleExpired(err) {
    var st = S;
    var sid = null;
    try { sid = (await api.seasoning(null, S.applied || [])).session_id; } catch (e) { /* next request will retry creating it */ }
    if (S !== st) return;
    S.sid = sid;
    S.locked = false;
    S.phase = "compose";
    S.photoKeys = []; S.textKeys = []; S.excluded = []; S.healthTags = []; S.combined = [];
    S.category = L.DEFAULT_CATEGORY; S.categoryEmpty = false;
    S.page = 0; S.moreAvailable = false;
    S.messages = withoutTyping().concat([{ id: nid("n"), role: "note", text: err.message, error: true }]);
    S.busy = false;
    render();
  }

  var CANCELLED = { cancelled: true };
  /** Throw if "new chat" replaced the state this operation started with. */
  function guard(st) { if (S !== st) throw CANCELLED; }

  function retryFrom(errMsg) {
    var op = errMsg.retry;
    S.messages = S.messages.filter(function (m) { return m.id !== errMsg.id; });
    runOp(op);
  }

  /** Runs one server operation with the typing indicator; every failure ends in a Thai bubble (with retry when it can help). */
  function runOp(op) {
    var st = S;
    S.busy = true;
    ensureTyping();
    render();
    return op().then(function () {
      if (S !== st) return;
      S.busy = false;
      render();
    }).catch(function (e) {
      if (e === CANCELLED || S !== st) return;
      e = asApiError(e);
      if (e.code === "session_expired") return handleExpired(e);
      replaceTyping([botText(e.message, e.retryable ? { retry: op } : {})]);
      S.busy = false;
      render();
    });
  }

  async function ensureSession() {
    var st = S;
    if (S.sid) return;
    var sid = (await api.seasoning(null, S.applied || [])).session_id;
    guard(st);
    S.sid = sid;
  }

  // ---- the conversation --------------------------------------------------------------------------
  function send() {
    var text = S.text.trim();
    var atts = S.atts.slice();
    if (!S.applied || S.busy || (!text && !atts.length)) return;

    S.messages = S.messages.concat([{ id: nid("u"), role: "user", images: atts.map(function (a) { return a.url; }), text: text }]);
    S.text = "";
    S.atts = [];
    S.anchor = null;
    $("fg-composer").value = "";

    var replyToConfirm = !atts.length && (S.phase === "await_confirm" || S.phase === "await_correction");
    var wantsMore = !atts.length && S.phase === "results" && L.isMoreRequest(text);
    runOp(replyToConfirm ? opConfirm(text) : wantsMore ? opMore() : opInput(text, atts));
  }

  // Each op* returns a function so a retry can run it again. Work already done stays done (detect is never repeated).
  function opInput(text, atts) {
    var detected = null;
    return async function () {
      var st = S;
      await ensureSession();
      // New input after results were shown starts a new round (the server resets its copy in start_new_round()).
      if (L.shouldResetCategory(S.phase)) { S.category = L.DEFAULT_CATEGORY; S.categoryEmpty = false; }
      if (atts.length && !detected) {
        var d = await api.detect(S.sid, atts.map(function (a) { return a.blob; }));
        guard(st);
        detected = d;
        S.sid = detected.session_id;
        S.locked = true;
        S.photoKeys = L.unionInOrder(S.photoKeys, detected.detected.map(function (d) { return d.ingredient; }));
        detected.detected.forEach(function (d) { if (d.name_th) S.extraNames[d.ingredient] = d.name_th; });
        S.combined = detected.ingredients;
      }
      var extracted = null;
      if (text) {
        extracted = await api.extract(S.sid, text);
        guard(st);
        S.sid = extracted.session_id;
        S.locked = true;
        S.textKeys = L.unionInOrder(S.textKeys, extracted.include);
        S.excluded = L.unionInOrder(S.excluded, extracted.exclude);
        S.healthTags = L.unionInOrder(S.healthTags, extracted.health_tags);
        S.combined = extracted.ingredients;
      }

      var out = [];
      var skipped = detected && detected.images_skipped ? detected.images_skipped.length : 0;
      if (skipped) out.push({ id: nid("n"), role: "note", text: "ข้ามรูปที่ใช้ไม่ได้ " + skipped + " รูป", error: true });
      // Words the server read as ingredients but has no dictionary key for: tell the user, don't block the flow.
      var unknownNote = extracted ? L.unknownNote(extracted.unknown) : "";
      if (unknownNote) out.push({ id: nid("n"), role: "note", text: unknownNote });

      S.page = 0;
      S.moreAvailable = false;
      if (!S.combined.length) {
        S.phase = "compose";
        out.push(botText("ยังไม่พบวัตถุดิบเลย ลองพิมพ์ชื่อวัตถุดิบ หรือถ่ายรูปให้ชัดขึ้นแล้วส่งอีกครั้งนะ"));
      } else {
        S.phase = "await_confirm";
        var list = { id: nid("list"), role: "bot", kind: "list", text: "เจอวัตถุดิบเหล่านี้", groups: L.buildGroups(S, {}, NAMES, S.extraNames), footer: CONFIRM_PROMPT };
        S.lastListId = list.id;
        out.push(list);
      }
      replaceTyping(out);
    };
  }

  function opConfirm(reply) {
    return async function () {
      var st = S;
      var resp = await api.confirm(S.sid, reply);
      guard(st);
      S.combined = resp.ingredients;

      if (resp.intent === "confirm") {
        await recommendPage(0);
      } else if (resp.intent === "confirm+correction") {
        var add = resp.corrections.add || [];
        var remove = resp.corrections.remove || [];
        // A removal is a struck chip only; it is NOT a "ไม่เอา" entry (the backend does not ban dishes for it).
        var next = L.applyConfirmCorrection(S, add, remove);
        replaceTyping([updatedList(add, remove, next.view)]);
        S.photoKeys = next.photoKeys;
        S.textKeys = next.textKeys;
        S.phase = "await_confirm";
      } else if (resp.intent === "reject") {
        S.phase = "await_correction";
        replaceTyping([{ id: nid("chk"), role: "bot", kind: "checklist", keys: S.combined.slice(), selected: {}, addText: "", done: false }]);
      } else {
        replaceTyping([botText("ขอโทษนะ ไม่แน่ใจว่าหมายถึงอะไร ตอบ “ใช่” ถ้ารายการถูกต้อง หรือบอกได้เลยว่าจะเอาอะไรออก/เพิ่มอะไร")]);
      }
    };
  }

  /** Bubble shown after the list changed: chips +added / struck removed, then the confirm prompt again. */
  function updatedList(added, removed, view) {
    view = view || { photoKeys: S.photoKeys, textKeys: S.textKeys, excluded: S.excluded, healthTags: S.healthTags, combined: S.combined };
    var list = { id: nid("list"), role: "bot", kind: "list", text: "อัปเดตรายการแล้ว", groups: L.buildGroups(view, { added: added, removed: removed }, NAMES, S.extraNames), footer: CONFIRM_PROMPT };
    S.lastListId = list.id;
    return list;
  }

  function opMore() {
    return async function () {
      if (!S.moreAvailable) {
        replaceTyping([botText("ไม่มีเมนูเพิ่มเติมแล้ว ลองเพิ่มวัตถุดิบเพื่อค้นหาใหม่ได้เลย")]);
        return;
      }
      await recommendPage(S.page + 1);
    };
  }

  async function recommendPage(page) {
    var st = S;
    var resp = await api.recommend(S.sid, L.topNForPage(page), S.category);
    guard(st);
    var slice = L.sliceForPage(resp.recipes, page);
    S.phase = "results";
    // The picker stays live only while the chosen category is the reason for an empty first page.
    S.categoryEmpty = page === 0 && !slice.length && resp.empty_for_category === true;
    if (!slice.length) {
      S.moreAvailable = false;
      if (S.categoryEmpty) S.anchor = S.lastListId;       // keep the picker in view: it is the way out
      replaceTyping([botText(L.emptyRecommendMessage(page, S.category, resp.empty_for_category))]);
      return;
    }
    S.page = page;
    S.moreAvailable = L.canShowMore(page, resp.count);
    var first = page === 0;
    replaceTyping([{
      id: nid("r"), role: "bot", kind: "results",
      text: first ? (slice.length < L.PAGE_SIZE ? "เมนูที่ทำได้จากของที่มี" : "เมนูที่ทำได้จากของที่มี 3 อันดับแรก") : "เมนูถัดไปที่ใกล้เคียง",
      cards: slice.map(function (r, i) { return L.buildCard(r, L.PAGE_SIZE * page + i + 1, NAMES); }),
      cardFooter: S.moreAvailable ? "อยากดูเมนูอื่น พิมพ์ “ขอเพิ่ม” ได้เลย" : "",
    }]);
    S.anchor = S.lastListId;
  }

  function submitChecklist(m) {
    if (m.done || S.busy) return;
    var selected = m.keys.filter(function (k) { return m.selected[k]; });
    var addText = m.addText.trim();
    if (!selected.length && !addText) return;
    S.anchor = null;
    runOp(opCorrect(m, selected, addText));
  }

  function opCorrect(m, selected, addText) {
    return async function () {
      var st = S;
      var resp = await api.correct(S.sid, selected, addText);
      guard(st);
      m.done = true;
      S.combined = resp.ingredients;
      S.healthTags = L.unionInOrder(S.healthTags, resp.health_tags);
      S.textKeys = L.unionInOrder(S.textKeys, resp.added);

      var out;
      if (!S.combined.length) {
        S.phase = "compose";
        out = botText("รายการว่างแล้ว พิมพ์หรือส่งรูปวัตถุดิบเพิ่มได้เลย");
        replaceTyping([out]);
      } else {
        S.phase = "await_confirm";
        replaceTyping([updatedList(resp.added, resp.removed)]);
      }
      // wrong detections are dropped for good (they are NOT banned dishes: only a typed "no X" does that)
      S.photoKeys = S.photoKeys.filter(function (k) { return resp.removed.indexOf(k) === -1; });
      S.textKeys = S.textKeys.filter(function (k) { return resp.removed.indexOf(k) === -1; });
    };
  }

  // ---- wiring ------------------------------------------------------------------------------------
  function init() {
    S = freshState(loadDraft());

    $("tabChat").addEventListener("click", function () { setTab("chat"); });
    $("tabSeas").addEventListener("click", function () { setTab("seasoning"); });
    $("newChat").addEventListener("click", newChat);
    $("lockNewChat").addEventListener("click", newChat);
    $("confirmBtn").addEventListener("click", confirmSeasonings);

    var input = $("fg-composer");
    input.addEventListener("input", function () { S.text = input.value; renderComposer(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    });
    input.addEventListener("paste", function (e) {
      var files = [];
      var items = (e.clipboardData && e.clipboardData.items) || [];
      for (var i = 0; i < items.length; i++) {
        if (items[i].kind === "file" && /^image\//i.test(items[i].type)) files.push(items[i].getAsFile());
      }
      if (files.length) { e.preventDefault(); addFiles(files); }
    });
    $("sendBtn").addEventListener("click", send);

    $("attachBtn").addEventListener("click", function () { $("fileInput").click(); });
    $("fileInput").addEventListener("change", function (e) {
      addFiles(e.target.files);
      e.target.value = "";            // picking the same photo again must still fire "change"
    });

    render();
  }

  // exposed for the browser test harness and console debugging; not used by the page itself
  FG.app = { state: function () { return S; }, api: api };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
