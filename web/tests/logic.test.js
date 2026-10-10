// Run:  node --test web/tests
// Pure-logic tests: no browser, no network, no dependencies.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");

require("../js/logic.js");
const L = globalThis.FG.logic;

const NAMES = { chicken: "ไก่", egg: "ไข่ไก่", garlic: "กระเทียม", fish_sauce: "น้ำปลา", sugar: "น้ำตาล", holy_basil: "กะเพรา" };
const SEASONINGS = [["fish_sauce", "น้ำปลา"], ["sugar", "น้ำตาล"], ["salt", "เกลือ"]];

// ---------------------------------------------------------------- names / seasonings
test("nameOf falls back to the key, and extra names win", () => {
  assert.equal(L.nameOf("chicken", NAMES), "ไก่");
  assert.equal(L.nameOf("zzz", NAMES), "zzz");
  assert.equal(L.nameOf("chicken", NAMES, { chicken: "ไก่บ้าน" }), "ไก่บ้าน");
});

test("orderSeasonings follows tile order and drops unknown keys", () => {
  assert.deepEqual(L.orderSeasonings(["salt", "nope", "fish_sauce"], SEASONINGS), ["fish_sauce", "salt"]);
});

test("sameSet ignores order but not membership or length", () => {
  assert.equal(L.sameSet(["a", "b"], ["b", "a"]), true);
  assert.equal(L.sameSet(["a"], ["a", "b"]), false);
  assert.equal(L.sameSet(null, []), false);
});

test("seasoning note, subline and confirm label follow the design's wording", () => {
  assert.equal(L.seasoningNote(["fish_sauce", "sugar"], NAMES), "เครื่องปรุงที่ยืนยัน · น้ำปลา, น้ำตาล");
  assert.equal(L.seasoningNote([], NAMES), "ไม่ได้เลือกเครื่องปรุง");
  assert.equal(L.seasoningSubline(false, 0, 3, 26), "แตะเพื่อเลือก · เลือกแล้ว 3 จาก 26");
  assert.equal(L.seasoningSubline(true, 2, 5, 26), "เลือกไว้ 2 จาก 26 รายการ");
  assert.equal(L.seasoningConfirmLabel(true, true, false), "ล็อกแล้ว");
  assert.equal(L.seasoningConfirmLabel(false, true, true), "ยืนยันการเปลี่ยนแปลง");
  assert.equal(L.seasoningConfirmLabel(false, true, false), "ยืนยันแล้ว · ไปที่แชท");
  assert.equal(L.seasoningConfirmLabel(false, false, false), "ยืนยันและเริ่มแชท");
});

test("composer placeholder depends on confirmation and phase", () => {
  assert.match(L.composerPlaceholder(false, "compose"), /ยืนยันเครื่องปรุงก่อนเริ่มแชท/);
  assert.match(L.composerPlaceholder(true, "await_confirm"), /ใช่/);
  assert.match(L.composerPlaceholder(true, "compose"), /พิมพ์วัตถุดิบ/);
});

// ---------------------------------------------------------------- "show more"
test("isMoreRequest matches only when the whole message is the request", () => {
  for (const yes of ["ขอเพิ่ม", "ขอเพิ่มค่ะ", "  ขอเพิ่ม  ", "“ขอเพิ่ม”", "more", "More please", "เมนูอื่น", "เมนูอื่นๆ", "next", "ขออีก"]) {
    assert.equal(L.isMoreRequest(yes), true, yes);
  }
  // the design mock's /เพิ่ม|more/ would have matched these; they are ingredient edits
  for (const no of ["เพิ่มกระเทียม", "มีไข่เพิ่ม", "more garlic", "เพิ่มไข่ด้วย", "ใช่", "", "   ", null, undefined]) {
    assert.equal(L.isMoreRequest(no), false, String(no));
  }
});

test("pagination: 3 cards per page, capped at the backend's top_n 10", () => {
  assert.deepEqual([0, 1, 2, 3, 4].map(L.topNForPage), [3, 6, 9, 10, 10]);
  const recipes = Array.from({ length: 10 }, (_, i) => ({ id: i }));
  assert.deepEqual(L.sliceForPage(recipes, 0).map((r) => r.id), [0, 1, 2]);
  assert.deepEqual(L.sliceForPage(recipes, 3).map((r) => r.id), [9]);
  assert.deepEqual(L.sliceForPage(recipes, 4), []);
  assert.equal(L.canShowMore(0, 3), true);   // asked 3, got 3 -> maybe more
  assert.equal(L.canShowMore(0, 2), false);  // fewer than asked -> that's all of them
  assert.equal(L.canShowMore(3, 10), false); // at the cap
});

// ---------------------------------------------------------------- list bubble
test("buildGroups: photo + text groups, plain chips", () => {
  const g = L.buildGroups(
    { photoKeys: ["chicken"], textKeys: ["egg"], excluded: [], healthTags: [], combined: ["chicken", "egg"] },
    {}, NAMES
  );
  assert.deepEqual(g.map((x) => [x.source, x.label]), [["photo", "จากรูป"], ["text", "จากข้อความ"]]);
  assert.deepEqual(g[0].items, [{ label: "ไก่", mode: "plain" }]);
  assert.deepEqual(g[1].items, [{ label: "ไข่ไก่", mode: "plain" }]);
});

test("buildGroups: an update shows removed (struck) and added (+) chips", () => {
  const g = L.buildGroups(
    { photoKeys: ["chicken", "egg"], textKeys: ["garlic"], excluded: [], healthTags: [], combined: ["chicken", "garlic"] },
    { added: ["garlic"], removed: ["egg"] }, NAMES
  );
  assert.deepEqual(g[0].items, [{ label: "ไก่", mode: "plain" }, { label: "ไข่ไก่", mode: "removed" }]);
  assert.deepEqual(g[1].items, [{ label: "กระเทียม", mode: "added" }]);
  assert.equal(L.chipText(g[1].items[0]), "+ กระเทียม");
  assert.equal(L.chipText(g[0].items[0]), "ไก่");
});

test("buildGroups: previously removed items no longer appear unless removed in THIS update", () => {
  const g = L.buildGroups(
    { photoKeys: ["chicken", "egg"], textKeys: [], excluded: [], healthTags: [], combined: ["chicken"] },
    {}, NAMES
  );
  assert.deepEqual(g[0].items, [{ label: "ไก่", mode: "plain" }]);
});

test("buildGroups: excluded items and health tags get their own groups; empty groups are omitted", () => {
  const g = L.buildGroups(
    { photoKeys: [], textKeys: ["chicken"], excluded: ["egg"], healthTags: ["clean"], combined: ["chicken"] },
    {}, NAMES
  );
  assert.deepEqual(g.map((x) => x.source), ["text", "excluded", "tags"]);
  assert.deepEqual(g[1].items, [{ label: "ไข่ไก่", mode: "removed" }]);
  assert.deepEqual(g[2].items, [{ label: "clean", mode: "plain" }]);
});

test("buildGroups: a listed ingredient neither source explains is still shown", () => {
  const g = L.buildGroups({ photoKeys: [], textKeys: [], excluded: [], healthTags: [], combined: ["garlic"] }, {}, NAMES);
  assert.deepEqual(g[0].items, [{ label: "กระเทียม", mode: "plain" }]);
});

// ---------------------------------------------------------------- first reply: six message categories
// (mocked /extract_bert answers; app.js applies view.phase and renders view.text / view.footer)
const NOTHING_FOUND = { kind: "empty", phase: "compose", text: "", footer: "" };
const CONDITIONS = { kind: "conditions", phase: "compose", text: "รับทราบเงื่อนไขแล้วนะ", footer: "ตอนนี้มีวัตถุดิบอะไรบ้าง? พิมพ์บอกได้เลย" };
const LIST = { kind: "list", phase: "await_confirm", text: "เจอวัตถุดิบเหล่านี้", footer: L.CONFIRM_PROMPT };

test("firstReplyView A: nothing at all -> the nothing-found message, phase stays compose", () => {
  assert.deepEqual(L.firstReplyView([], [], []), NOTHING_FOUND);
  assert.deepEqual(L.firstReplyView(undefined, undefined, undefined), NOTHING_FOUND);
});

test("firstReplyView B: ingredients only -> the unchanged confirm card", () => {
  assert.deepEqual(L.firstReplyView(["egg", "pork"], [], []), LIST);
  assert.equal(L.CONFIRM_PROMPT, "ถูกต้องไหม? ตอบกลับได้เลย เช่น “ใช่” หรือ “เอา…ออก เพิ่ม…”");
});

test("firstReplyView C: exclude only -> conditions card, phase compose (next message is new input)", () => {
  assert.deepEqual(L.firstReplyView([], ["pork"], []), CONDITIONS);
});

test("firstReplyView D: ingredients + exclude -> the unchanged confirm card", () => {
  assert.deepEqual(L.firstReplyView(["egg"], ["pork"], []), LIST);
});

test("firstReplyView E: health tag only -> conditions card, phase compose", () => {
  assert.deepEqual(L.firstReplyView([], [], ["keto"]), CONDITIONS);
});

test("firstReplyView F: tag + exclude without ingredients -> conditions card; with ingredients -> confirm card", () => {
  assert.deepEqual(L.firstReplyView([], ["pork"], ["keto"]), CONDITIONS);
  assert.deepEqual(L.firstReplyView(["egg"], ["pork"], ["keto"]), LIST);
  assert.deepEqual(L.firstReplyView(["egg"], [], ["keto"]), LIST);
});

test("conditions card groups: only ไม่เอา / เงื่อนไข, no ingredient group", () => {
  const g = L.buildGroups({ excluded: ["egg"], healthTags: ["keto"], combined: [] }, {}, NAMES);
  assert.deepEqual(g.map((x) => [x.source, x.label]), [["excluded", "ไม่เอา"], ["tags", "เงื่อนไข"]]);
  assert.deepEqual(L.buildGroups({ excluded: ["egg"], healthTags: [], combined: [] }, {}, NAMES).map((x) => x.source), ["excluded"]);
  assert.deepEqual(L.buildGroups({ excluded: [], healthTags: ["keto"], combined: [] }, {}, NAMES).map((x) => x.source), ["tags"]);
});

test("firstReplyView reads only its arguments: stale accumulated lists cannot change the answer", () => {
  const stale = { excluded: ["pork"], healthTags: ["keto"] };   // what S would still hold from an earlier round
  assert.deepEqual(L.firstReplyView([], [], []), NOTHING_FOUND);
  assert.equal(stale.excluded.length + stale.healthTags.length, 2);
});

// ---------------------------------------------------------------- one session, stubbed /extract_bert answers
// turn() composes the same pure functions in the same order as app.js opInput(); the DOM/network wiring itself
// (rendering, runOp, the real send()) is not exercised here.
const NAMES2 = Object.assign({ pork: "หมู", kang_kong: "ผักบุ้ง", egg: "ไข่ไก่" }, NAMES);

function newSession() {
  return { phase: "compose", photoKeys: [], textKeys: [], excluded: [], healthTags: [], combined: [], lastListId: null };
}

/** `answer` is a stubbed /extract_bert body; `ingredients` is the stub's merged list. Returns what the chat would show. */
function turn(S, text, answer) {
  const route = L.sendRoute(S.phase, false, text);
  if (route !== "input") return { route };
  const round = L.startRound(S);
  S.excluded = round.excluded; S.healthTags = round.healthTags;
  S.textKeys = L.unionInOrder(S.textKeys, answer.include);
  const held = L.applyExtract(S, answer);
  S.excluded = held.excluded; S.healthTags = held.healthTags;
  S.combined = answer.ingredients;
  const view = L.firstReplyView(S.combined, answer.exclude, answer.health_tags);
  S.phase = view.phase;
  let groups = null;
  if (view.kind === "conditions") groups = L.buildGroups({ excluded: S.excluded, healthTags: S.healthTags, combined: [] }, {}, NAMES2);
  else if (view.kind === "list") { groups = L.buildGroups(S, {}, NAMES2); S.lastListId = "list1"; }
  return { route, view, groups };
}
const ans = (include, exclude, health_tags, ingredients) => ({ include, exclude, health_tags, ingredients: ingredients || include });
const labels = (groups, source) => (groups.find((g) => g.source === source) || { items: [] }).items.map((i) => i.label);

test("session 1: 'สวัสดีครับ' -> nothing-found, phase compose", () => {
  const S = newSession();
  const r = turn(S, "สวัสดีครับ", ans([], [], []));
  assert.equal(r.view.kind, "empty");
  assert.equal(S.phase, "compose");
  assert.equal(r.groups, null);
});

test("session 2: 'ไม่เอาหมู' -> conditions card, only the ไม่เอา group, no picker, phase compose", () => {
  const S = newSession();
  const r = turn(S, "ไม่เอาหมู", ans([], ["pork"], []));
  assert.equal(r.view.kind, "conditions");
  assert.equal(r.view.text, "รับทราบเงื่อนไขแล้วนะ");
  assert.equal(r.view.footer, "ตอนนี้มีวัตถุดิบอะไรบ้าง? พิมพ์บอกได้เลย");
  assert.deepEqual(r.groups.map((g) => g.source), ["excluded"]);
  assert.deepEqual(labels(r.groups, "excluded"), ["หมู"]);
  assert.equal(S.lastListId, null);          // app.js shows the category picker only for the newest list id
  assert.equal(S.phase, "compose");
});

test("session 3: after the conditions card, the next message is a NEW extract (not /confirm) and keeps the held 'no X'", () => {
  const S = newSession();
  turn(S, "ไม่เอาหมู", ans([], ["pork"], []));
  const r = turn(S, "มีไข่กับผักบุ้ง", ans(["egg", "kang_kong"], [], []));
  assert.equal(r.route, "input");
  assert.equal(L.sendRoute("compose", false, "ใช่"), "input");     // even "ใช่" is new input while in compose
  assert.equal(r.view.kind, "list");
  assert.equal(r.view.phase, "await_confirm");
  assert.equal(S.phase, "await_confirm");
  assert.deepEqual(labels(r.groups, "text"), ["ไข่ไก่", "ผักบุ้ง"]);
  assert.deepEqual(labels(r.groups, "excluded"), ["หมู"]);          // the server still holds it
  assert.equal(S.lastListId, "list1");
  assert.equal(L.sendRoute(S.phase, false, "ใช่"), "confirm");      // and only now does a reply go to /confirm
});

test("session 4: a new session 'อยากกินคีโต' -> เงื่อนไข: keto, ingredients requested, phase compose", () => {
  const S = newSession();
  const r = turn(S, "อยากกินคีโต", ans([], [], ["keto"]));
  assert.equal(r.view.kind, "conditions");
  assert.deepEqual(r.groups.map((g) => g.source), ["tags"]);
  assert.deepEqual(labels(r.groups, "tags"), ["keto"]);
  assert.equal(r.view.footer, "ตอนนี้มีวัตถุดิบอะไรบ้าง? พิมพ์บอกได้เลย");
  assert.equal(S.phase, "compose");
});

test("session 5: 'ไม่เอาหมู' then 'อยากกินคีโต' in one session -> the card shows BOTH conditions", () => {
  const S = newSession();
  turn(S, "ไม่เอาหมู", ans([], ["pork"], []));
  const r = turn(S, "อยากกินคีโต", ans([], [], ["keto"]));       // this answer carries only keto
  assert.equal(r.view.kind, "conditions");
  assert.deepEqual(r.groups.map((g) => g.source), ["excluded", "tags"]);
  assert.deepEqual(labels(r.groups, "excluded"), ["หมู"]);
  assert.deepEqual(labels(r.groups, "tags"), ["keto"]);
});

test("session 6: a nothing-found message after a conditions card is still 'nothing found'", () => {
  const S = newSession();
  turn(S, "ไม่เอาหมู", ans([], ["pork"], []));
  const r = turn(S, "สวัสดีครับ", ans([], [], []));
  assert.equal(r.view.kind, "empty");
  assert.deepEqual(S.excluded, ["pork"]);                            // still held for the next message
});

test("session 7: input after results starts a new round: held conditions are cleared, none leak into the card", () => {
  const S = newSession();
  turn(S, "มีไข่ ไม่เอาหมู อยากกินคีโต", ans(["egg"], ["pork"], ["keto"]));
  S.phase = "results";                                               // confirmed and recommended
  const r = turn(S, "ไม่เอาไข่", ans([], ["egg"], []));
  assert.equal(r.view.kind, "conditions");
  assert.deepEqual(labels(r.groups, "excluded"), ["ไข่ไก่"]);        // not หมู
  assert.deepEqual(r.groups.map((g) => g.source), ["excluded"]);     // keto from round 1 is gone too
});

test("startRound keeps the held conditions outside the results phase and returns fresh arrays after it", () => {
  const s = { phase: "await_confirm", excluded: ["pork"], healthTags: ["keto"] };
  assert.deepEqual(L.startRound(s), { excluded: ["pork"], healthTags: ["keto"] });
  assert.deepEqual(L.startRound(Object.assign({}, s, { phase: "results" })), { excluded: [], healthTags: [] });
});

test("sendRoute: confirm replies, 'ขอเพิ่ม' after results, images always start new input", () => {
  assert.equal(L.sendRoute("await_confirm", false, "ใช่"), "confirm");
  assert.equal(L.sendRoute("await_correction", false, "เอาออก"), "confirm");
  assert.equal(L.sendRoute("results", false, "ขอเพิ่ม"), "more");
  assert.equal(L.sendRoute("results", false, "มีไข่"), "input");
  assert.equal(L.sendRoute("await_confirm", true, ""), "input");
  assert.equal(L.sendRoute("compose", false, "มีไข่"), "input");
});

test("applyExtract: exclusions accumulate, a tag-less message keeps the tags, a new tag replaces them", () => {
  let s = { excluded: [], healthTags: [] };
  s = L.applyExtract(s, { exclude: ["pork"], health_tags: ["keto"] });
  s = L.applyExtract(s, { exclude: ["egg"], health_tags: [] });
  assert.deepEqual(s, { excluded: ["pork", "egg"], healthTags: ["keto"] });
  s = L.applyExtract(s, { exclude: [], health_tags: ["vegan"] });
  assert.deepEqual(s, { excluded: ["pork", "egg"], healthTags: ["vegan"] });
});

test("unionInOrder keeps first-seen order without duplicates", () => {
  assert.deepEqual(L.unionInOrder(["a", "b"], ["b", "c", "a", "d"]), ["a", "b", "c", "d"]);
  assert.deepEqual(L.unionInOrder(undefined, ["x"]), ["x"]);
});

// ---------------------------------------------------------------- recipe card
const RECIPE = {
  id: "th_306", name_th: "กะเพราเนื้อ", score: 0.8,
  have: ["chicken", "garlic", "egg"],          // egg is OPTIONAL: must not appear as a main chip
  missing: ["holy_basil"],
  main_ingredients: ["chicken", "garlic", "holy_basil"],
  seasonings: ["fish_sauce", "sugar"],
  seasonings_matched: ["fish_sauce"],
  nutrition: { kcal: 430.6, protein: 30 },
  health_tags: ["keto"],
  cook_time_min: 10,
  recipe_source_url: "https://example.com/r",
};

test("buildCard derives have/miss chips from mains and the ticked seasoning subset", () => {
  const c = L.buildCard(RECIPE, 1, NAMES);
  assert.deepEqual(c.main, [
    { label: "ไก่", have: true }, { label: "กระเทียม", have: true }, { label: "กะเพรา", have: false },
  ]);
  assert.equal(c.haveMain, 2);
  assert.equal(c.totalMain, 3);
  assert.deepEqual(c.seas, [{ label: "น้ำปลา", have: true }, { label: "น้ำตาล", have: false }]);
  assert.equal(c.seasSummary, "ขาด 1");
  assert.equal(c.kcal, 431);
  assert.equal(c.time, 10);
  assert.deepEqual(c.tags, ["keto"]);
  assert.equal(c.url, "https://example.com/r");
  assert.equal(c.rank, 1);
});

test("buildCard says ครบ when every seasoning is ticked, and tolerates missing fields", () => {
  const c = L.buildCard({ ...RECIPE, seasonings_matched: ["fish_sauce", "sugar"] }, 2, NAMES);
  assert.equal(c.seasSummary, "ครบ");
  const bare = L.buildCard({ name_th: "x", have: [], nutrition: {} }, 3, NAMES);
  assert.equal(bare.time, null);
  assert.equal(bare.kcal, null);
  assert.equal(bare.url, null);
  assert.deepEqual(bare.main, []);
});

// ---------------------------------------------------------------- C15 keto caveat
// A dish's keto tag is per dish, but a Thai meal comes with rice, so the qualifier is shown only when
// the user asked for keto. The requested tags are the SERVER's (used.health_tags of /recommend).
test("keto caveat: the label is exactly คีโต (ไม่รวมข้าว)", () => {
  assert.equal(L.KETO_CAVEAT_LABEL, "คีโต (ไม่รวมข้าว)");
});

test("keto caveat: keto dish + keto requested -> caveat", () => {
  assert.equal(L.shouldShowKetoCaveat(["keto"], ["keto"]), true);
  assert.equal(L.shouldShowKetoCaveat(["clean", "keto"], ["keto", "clean"]), true);
});

test("keto caveat: keto dish + nothing requested -> no caveat", () => {
  assert.equal(L.shouldShowKetoCaveat(["keto"], []), false);
  assert.equal(L.shouldShowKetoCaveat(["keto"], undefined), false);
  assert.equal(L.shouldShowKetoCaveat(["keto"], null), false);
});

test("keto caveat: keto dish + only vegan requested -> no caveat", () => {
  assert.equal(L.shouldShowKetoCaveat(["keto", "vegan"], ["vegan"]), false);
});

test("keto caveat: non-keto dish + keto requested -> no caveat", () => {
  assert.equal(L.shouldShowKetoCaveat(["vegan", "clean"], ["keto"]), false);
  assert.equal(L.shouldShowKetoCaveat([], ["keto"]), false);
  assert.equal(L.shouldShowKetoCaveat(undefined, ["keto"]), false);
});

test("buildCard: ketoCaveat follows the requested tags and the raw tags are never changed", () => {
  assert.equal(L.buildCard(RECIPE, 1, NAMES, ["keto"]).ketoCaveat, true);
  assert.equal(L.buildCard(RECIPE, 1, NAMES, []).ketoCaveat, false);
  assert.equal(L.buildCard(RECIPE, 1, NAMES, ["vegan"]).ketoCaveat, false);
  assert.equal(L.buildCard(RECIPE, 1, NAMES).ketoCaveat, false);          // an old server without `used`
  assert.deepEqual(L.buildCard(RECIPE, 1, NAMES, ["keto"]).tags, ["keto"]);
});

test("buildCard: other tags are unaffected by the keto caveat", () => {
  const other = { ...RECIPE, health_tags: ["clean", "vegan"] };
  const c = L.buildCard(other, 1, NAMES, ["clean", "keto"]);
  assert.deepEqual(c.tags, ["clean", "vegan"]);
  assert.equal(c.ketoCaveat, false);
  assert.deepEqual(L.buildCard(other, 1, NAMES, []).tags, ["clean", "vegan"]);
});

// ---------------------------------------------------------------- health tags: replace like the server
// api/state.py SessionState.apply_text_result: the latest parse that mentions a tag REPLACES the tags;
// a message with no tag leaves them alone.
test("nextHealthTags: the first tags are set", () => {
  assert.deepEqual(L.nextHealthTags([], ["keto"]), ["keto"]);
});

test("nextHealthTags: a second tag REPLACES the first (keto then vegan -> vegan only)", () => {
  assert.deepEqual(L.nextHealthTags(["keto"], ["vegan"]), ["vegan"]);
});

test("nextHealthTags: a message with no tags leaves the tags unchanged", () => {
  assert.deepEqual(L.nextHealthTags(["keto"], []), ["keto"]);
  assert.deepEqual(L.nextHealthTags(["keto"], undefined), ["keto"]);
  assert.deepEqual(L.nextHealthTags(["keto"], null), ["keto"]);
});

test("nextHealthTags: duplicates in one message are dropped, order preserved", () => {
  assert.deepEqual(L.nextHealthTags([], ["vegan", "keto", "vegan", "keto"]), ["vegan", "keto"]);
  assert.deepEqual(L.nextHealthTags(["clean"], ["keto", "keto", "vegan"]), ["keto", "vegan"]);
});

test("nextHealthTags: empty incoming on an empty state stays empty", () => {
  assert.deepEqual(L.nextHealthTags([], []), []);
  assert.deepEqual(L.nextHealthTags(undefined, undefined), []);
  assert.deepEqual(L.nextHealthTags(null, []), []);
});

test("nextHealthTags: always returns a new array and never mutates its inputs", () => {
  const current = ["keto"];
  const incoming = ["vegan", "vegan"];
  assert.notEqual(L.nextHealthTags(current, []), current);
  assert.notEqual(L.nextHealthTags(current, incoming), incoming);
  assert.deepEqual(current, ["keto"]);
  assert.deepEqual(incoming, ["vegan", "vegan"]);
});

test("nextHealthTags: the repro sequence (keto, then vegan, then a message with no tag)", () => {
  let tags = [];
  tags = L.nextHealthTags(tags, ["keto"]);            // "มีไข่ อยากกินคีโต"
  assert.deepEqual(tags, ["keto"]);
  tags = L.nextHealthTags(tags, ["vegan"]);           // "เปลี่ยนเป็นวีแกน"
  assert.deepEqual(tags, ["vegan"], "the server holds only vegan, so the chips must not still show keto");
  tags = L.nextHealthTags(tags, []);                  // "มีไก่" mentions no tag
  assert.deepEqual(tags, ["vegan"]);
  // what the old accumulating merge produced for the same two messages
  assert.deepEqual(L.unionInOrder(L.unionInOrder([], ["keto"]), ["vegan"]), ["keto", "vegan"]);
});

test("safeUrl only lets http(s) links through", () => {
  assert.equal(L.safeUrl("https://a.com/x"), "https://a.com/x");
  assert.equal(L.safeUrl("http://a.com"), "http://a.com");
  for (const bad of ["javascript:alert(1)", "data:text/html,x", "//a.com", "ftp://a.com", "", null, undefined, 5]) {
    assert.equal(L.safeUrl(bad), null, String(bad));
  }
});

// ---------------------------------------------------------------- errors
test("detailText handles both backend error shapes", () => {
  assert.equal(L.detailText({ detail: "unknown session" }), "unknown session");
  assert.equal(
    L.detailText({ detail: [{ loc: ["body", "text"], msg: "String should have at least 1 character" }, { msg: "second" }] }),
    "String should have at least 1 character; second"
  );
  assert.equal(L.detailText(null), "");
  assert.equal(L.detailText({}), "");
  assert.equal(L.detailText("oops"), "");
});

test("classifyError maps every backend condition to a Thai message and a retry flag", () => {
  const c = (e) => L.classifyError(e);
  assert.deepEqual([c({ kind: "network" }).code, c({ kind: "network" }).retryable], ["network", true]);
  assert.equal(c({ kind: "timeout" }).code, "timeout");
  assert.equal(c({ kind: "http", status: 404, detail: "unknown session" }).code, "session_expired");
  assert.equal(c({ kind: "http", status: 429, detail: "rate limit exceeded: 5 per 1 minute" }).code, "rate_limited");
  assert.equal(c({ kind: "http", status: 413 }).code, "too_large");
  assert.equal(c({ kind: "http", status: 503, detail: "detector unavailable" }).code, "detector_unavailable");
  assert.equal(c({ kind: "http", status: 409, detail: "seasonings are locked once the chat starts" }).code, "seasoning_locked");
  assert.equal(c({ kind: "http", status: 409, detail: "ingredients not confirmed yet: call /confirm first" }).code, "conflict");
  assert.equal(c({ kind: "http", status: 422, detail: "no usable images: ['a.gif: unsupported type']" }).code, "bad_images");
  assert.equal(c({ kind: "http", status: 422, detail: "not in the current ingredient list: ['x']" }).code, "stale_list");
  assert.equal(c({ kind: "http", status: 422, detail: "String should have at least 1 character" }).code, "invalid");
  assert.equal(c({ kind: "http", status: 500 }).code, "server_error");
  assert.equal(c({ kind: "http", status: 502 }).retryable, true);
  assert.equal(c({ kind: "http", status: 418 }).code, "unknown");
  for (const status of [404, 409, 413, 422, 429, 500, 503]) {
    assert.match(c({ kind: "http", status, detail: "x" }).message, /[฀-๿]/, `Thai text for ${status}`);
  }
});

// ---------------------------------------------------------------- images
test("fitWithin scales the longer side down, keeps aspect ratio, never scales up", () => {
  assert.deepEqual(L.fitWithin(4000, 3000, 1600), { width: 1600, height: 1200, scaled: true });
  assert.deepEqual(L.fitWithin(3000, 4000, 1600), { width: 1200, height: 1600, scaled: true });
  assert.deepEqual(L.fitWithin(800, 600, 1600), { width: 800, height: 600, scaled: false });
  assert.deepEqual(L.fitWithin(1600, 1600, 1600), { width: 1600, height: 1600, scaled: false });
  assert.equal(L.fitWithin(10000, 1, 1600).height, 1);
});

test("jpegName swaps the extension", () => {
  assert.equal(L.jpegName("IMG_001.HEIC"), "IMG_001.jpg");
  assert.equal(L.jpegName("a.b.png"), "a.b.jpg");
  assert.equal(L.jpegName(""), "photo.jpg");
  assert.equal(L.jpegName(undefined), "photo.jpg");
});

test("image limits match the backend (5 images, 8 MB, jpeg/png/webp)", () => {
  assert.equal(L.MAX_IMAGES, 5);
  assert.equal(L.MAX_IMAGE_BYTES, 8 * 1024 * 1024);
  assert.deepEqual(L.ALLOWED_IMAGE_TYPES, ["image/jpeg", "image/png", "image/webp"]);
});

// ---------------------------------------------------------------- unknown ingredient words
test("unknownNote lists words the server could not match, and is empty when there are none", () => {
  assert.equal(L.unknownNote(undefined), "");
  assert.equal(L.unknownNote([]), "");
  assert.equal(L.unknownNote(["", "  "]), "");
  assert.equal(L.unknownNote(["มังคุด"]), "ไม่พบวัตถุดิบเหล่านี้ในระบบ: มังคุด");
  assert.equal(L.unknownNote([" มังคุด ", "ลำไย"]), "ไม่พบวัตถุดิบเหล่านี้ในระบบ: มังคุด, ลำไย");
});

test("unknownNote caps the words shown and says how many more there are", () => {
  var many = ["a", "b", "c", "d", "e", "f", "g"];
  assert.equal(L.unknownNote(many), "ไม่พบวัตถุดิบเหล่านี้ในระบบ: a, b, c, d, e และอีก 2 รายการ");
});

// ---------------------------------------------------------------- /confirm removals vs the "ไม่เอา" group
// The backend no longer bans dishes for a removal made at /confirm (ban_excluded=False), so the UI must not
// list it under "ไม่เอา". Only typed "no X" (ExtractResponse.exclude) belongs there.
const NAMES_PORK = Object.assign({ pork: "หมู", chili: "พริก" }, NAMES);
const sourcesOf = (groups) => groups.map((x) => x.source);

test("confirm removal is a struck chip in the list and is NOT an excluded (ไม่เอา) entry", () => {
  const s = { photoKeys: ["chicken", "egg"], textKeys: [], excluded: [], healthTags: [], combined: ["egg", "pork"] };
  const next = L.applyConfirmCorrection(s, ["pork"], ["chicken"]);
  const g = L.buildGroups(next.view, { added: ["pork"], removed: ["chicken"] }, NAMES_PORK);

  assert.ok(!sourcesOf(g).includes("excluded"));
  assert.deepEqual(next.view.excluded, []);
  assert.deepEqual(g[0].items, [{ label: "ไก่", mode: "removed" }, { label: "ไข่ไก่", mode: "plain" }]);   // struck chip, other chip stays
  assert.deepEqual(g[1].items, [{ label: "หมู", mode: "added" }]);                                           // new ingredient shown with "+"
  assert.equal(L.chipText(g[1].items[0]), "+ หมู");
  // the lists kept afterwards no longer carry the removed key, so the NEXT bubble does not show it again
  assert.deepEqual(next.photoKeys, ["egg"]);
  assert.deepEqual(next.textKeys, ["pork"]);
});

test("first-message negation still shows in the excluded (ไม่เอา) group, also after a later correction", () => {
  const s = { photoKeys: [], textKeys: ["egg", "chicken"], excluded: ["pork"], healthTags: [], combined: ["egg", "chicken"] };
  const first = L.buildGroups(s, {}, NAMES_PORK);
  assert.deepEqual(sourcesOf(first), ["text", "excluded"]);
  assert.deepEqual(first[1].items, [{ label: "หมู", mode: "removed" }]);

  const next = L.applyConfirmCorrection(s, ["garlic"], []);
  const after = L.buildGroups(next.view, { added: ["garlic"], removed: [] }, NAMES_PORK);
  assert.deepEqual(next.view.excluded, ["pork"]);
  assert.ok(sourcesOf(after).includes("excluded"));
});

test("removing an item that the first message excluded leaves it in the excluded group", () => {
  const s = { photoKeys: [], textKeys: ["egg", "chicken"], excluded: ["pork"], healthTags: [], combined: ["egg", "chicken"] };
  const next = L.applyConfirmCorrection(s, [], ["pork"]);
  const g = L.buildGroups(next.view, { added: [], removed: ["pork"] }, NAMES_PORK);

  assert.deepEqual(next.view.excluded, ["pork"]);                                   // the backend still bans it
  const excluded = g.find((x) => x.source === "excluded");
  assert.deepEqual(excluded.items, [{ label: "หมู", mode: "removed" }]);
  const text = g.find((x) => x.source === "text");
  assert.ok(!text.items.some((i) => i.label === "หมู"));                            // and no duplicate struck chip
});

test("removing something that was never listed shows nothing and adds no excluded entry", () => {
  const s = { photoKeys: ["chicken"], textKeys: [], excluded: [], healthTags: [], combined: ["chicken"] };
  const next = L.applyConfirmCorrection(s, [], ["chili"]);
  const g = L.buildGroups(next.view, { added: [], removed: ["chili"] }, NAMES_PORK);
  assert.deepEqual(sourcesOf(g), ["photo"]);
  assert.deepEqual(g[0].items, [{ label: "ไก่", mode: "plain" }]);
});

test("applyConfirmCorrection does not mutate the state it is given", () => {
  const s = { photoKeys: ["chicken", "egg"], textKeys: ["garlic"], excluded: ["pork"], healthTags: [], combined: ["egg"] };
  const copy = JSON.parse(JSON.stringify(s));
  L.applyConfirmCorrection(s, ["rice"], ["chicken"]);
  assert.deepEqual(s, copy);
});

// ---------------------------------------------------------------- category picker (all / savory / dessert)
test("the picker offers exactly all / savory / dessert, in that order, with the agreed Thai labels", () => {
  assert.deepEqual(L.CATEGORIES, [["all", "ทั้งหมด"], ["savory", "อาหารคาว"], ["dessert", "ขนมหวาน"]]);
  assert.equal(L.DEFAULT_CATEGORY, "all");
});

test("normalizeCategory keeps the three values and sends anything else back to all", () => {
  ["all", "savory", "dessert"].forEach((v) => assert.equal(L.normalizeCategory(v), v));
  ["snack", "drink", "condiment", "SAVORY", "", null, undefined, 3].forEach((v) => assert.equal(L.normalizeCategory(v), "all"));
});

test("a new input after results were shown resets the choice; no other phase does", () => {
  assert.equal(L.shouldResetCategory("results"), true);
  ["compose", "await_confirm", "await_correction"].forEach((p) => assert.equal(L.shouldResetCategory(p), false));
});

test("the picker is live only while the list awaits confirmation and nothing is in flight", () => {
  assert.equal(L.categoryPickerEnabled("await_confirm", false), true);
  assert.equal(L.categoryPickerEnabled("await_correction", false), true);
  assert.equal(L.categoryPickerEnabled("await_confirm", true), false);      // a request is running
  assert.equal(L.categoryPickerEnabled("results", false), false);           // read-only once results are shown
  assert.equal(L.categoryPickerEnabled("compose", false), false);
});

test("zero-result messages: the two category sentences, nothing for all", () => {
  assert.equal(L.categoryEmptyMessage("savory"), "ไม่พบอาหารคาวที่ใช้วัตถุดิบเหล่านี้ได้");
  assert.equal(L.categoryEmptyMessage("dessert"), "ไม่พบขนมหวานที่ใช้วัตถุดิบเหล่านี้ได้");
  assert.equal(L.categoryEmptyMessage("all"), "");
});

test("emptyRecommendMessage: category sentence only for an empty first page the server blames on the category", () => {
  const generic = "ยังไม่พบเมนูที่ตรงกับวัตถุดิบที่มี ลองเพิ่มวัตถุดิบดูนะ";
  const noMore = "ไม่มีเมนูเพิ่มเติมแล้ว ลองเพิ่มวัตถุดิบเพื่อค้นหาใหม่ได้เลย";
  assert.equal(L.emptyRecommendMessage(0, "savory", true), "ไม่พบอาหารคาวที่ใช้วัตถุดิบเหล่านี้ได้");
  assert.equal(L.emptyRecommendMessage(0, "dessert", true), "ไม่พบขนมหวานที่ใช้วัตถุดิบเหล่านี้ได้");
  assert.equal(L.emptyRecommendMessage(0, "savory", false), generic);      // "all" would be empty too: existing behavior
  assert.equal(L.emptyRecommendMessage(0, "all", false), generic);
  assert.equal(L.emptyRecommendMessage(0, "all", true), generic);          // a flag without a category sentence falls back
  assert.equal(L.emptyRecommendMessage(0, "savory", undefined), generic);  // older server: no flag
  assert.equal(L.emptyRecommendMessage(1, "savory", true), noMore);        // later pages keep their own wording
});

// ---------------------------------------------------------------- picker: no dead end after an empty category
test("after results the picker stays locked, unless the chosen category came back empty", () => {
  assert.equal(L.categoryPickerEnabled("results", false, true), true);        // empty_for_category: the way out
  assert.equal(L.categoryPickerEnabled("results", false, false), false);      // results shown: locked
  assert.equal(L.categoryPickerEnabled("results", false, undefined), false);  // flag absent: locked
  assert.equal(L.categoryPickerEnabled("results", false, "true"), false);     // only a real true counts
  assert.equal(L.categoryPickerEnabled("results", true, true), false);        // a request is running
  assert.equal(L.categoryPickerEnabled("compose", false, true), false);       // the flag means nothing outside "results"
  ["await_confirm", "await_correction"].forEach((p) => {
    assert.equal(L.categoryPickerEnabled(p, false, false), true);             // before confirmation: unchanged
    assert.equal(L.categoryPickerEnabled(p, false, true), true);
    assert.equal(L.categoryPickerEnabled(p, true, false), false);
  });
});

test("a click before confirmation just remembers the choice", () => {
  assert.equal(L.categoryClickAction("await_confirm", false, false, "all", "dessert"), "set");
  assert.equal(L.categoryClickAction("await_correction", false, false, "savory", "all"), "set");
});

test("a click in the dead-end state asks for the first page again with the new category", () => {
  assert.equal(L.categoryClickAction("results", false, true, "savory", "dessert"), "rerequest");
  assert.equal(L.categoryClickAction("results", false, true, "savory", "all"), "rerequest");
  assert.equal(L.categoryClickAction("results", false, true, "dessert", "savory"), "rerequest");
});

test("clicks that must do nothing: already-chosen option, locked picker, request in flight", () => {
  assert.equal(L.categoryClickAction("results", false, true, "savory", "savory"), "ignore");   // nothing new to ask
  assert.equal(L.categoryClickAction("results", false, false, "savory", "dessert"), "ignore"); // results shown: locked
  assert.equal(L.categoryClickAction("results", true, true, "savory", "dessert"), "ignore");   // busy
  assert.equal(L.categoryClickAction("await_confirm", true, false, "all", "dessert"), "ignore");
  assert.equal(L.categoryClickAction("compose", false, false, "all", "dessert"), "ignore");
});
