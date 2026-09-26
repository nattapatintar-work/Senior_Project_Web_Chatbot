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
