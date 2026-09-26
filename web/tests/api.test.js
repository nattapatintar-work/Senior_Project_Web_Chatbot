// Run:  node --test web/tests
// API-wrapper tests against a fake fetch: request shapes, error normalisation, timeouts.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");

require("../js/logic.js");
require("../js/api.js");
const FG = globalThis.FG;

const SID = "a".repeat(32);

/** A fake fetch that records calls and answers from a queue of {status, body|text} or a thrown error. */
function fakeFetch(...answers) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    const a = answers.shift();
    if (a instanceof Error) throw a;
    const text = a.text !== undefined ? a.text : JSON.stringify(a.body);
    return { ok: a.status >= 200 && a.status < 300, status: a.status, text: async () => text };
  };
  fn.calls = calls;
  return fn;
}
const api = (fetchImpl, extra) => FG.createApi({ base: "http://host:8000/", fetchImpl, ...extra });

test("JSON endpoints post the exact payloads the backend expects", async () => {
  const f = fakeFetch(
    { status: 200, body: { session_id: SID, seasonings: ["sugar"], locked: false } },
    { status: 200, body: { ok: 1 } }, { status: 200, body: { ok: 2 } }, { status: 200, body: { ok: 3 } }, { status: 200, body: { ok: 4 } },
    { status: 200, body: { ok: 5 } }
  );
  const a = api(f);
  await a.seasoning(null, ["sugar"]);
  await a.extract(SID, "มีไก่");
  await a.confirm(SID, "ใช่");
  await a.correct(SID, ["egg"], "กระเทียม");
  await a.correct(SID, ["egg"]);
  await a.recommend(SID, 6);

  const sent = f.calls.map((c) => [c.url, c.init.method, JSON.parse(c.init.body)]);
  assert.deepEqual(sent, [
    ["http://host:8000/seasoning", "POST", { session_id: null, seasonings: ["sugar"] }],
    ["http://host:8000/extract", "POST", { text: "มีไก่", session_id: SID }],
    ["http://host:8000/confirm", "POST", { session_id: SID, reply: "ใช่" }],
    ["http://host:8000/correct", "POST", { session_id: SID, exclude: ["egg"], add_text: "กระเทียม" }],
    ["http://host:8000/correct", "POST", { session_id: SID, exclude: ["egg"] }],
    ["http://host:8000/recommend", "POST", { session_id: SID, top_n: 6 }],
  ]);
  assert.equal(f.calls[0].init.headers["Content-Type"], "application/json");
});

test("seasoning: omitting the list is a read-only call, [] clears", async () => {
  const f = fakeFetch({ status: 200, body: {} }, { status: 200, body: {} });
  const a = api(f);
  await a.seasoning(SID);
  await a.seasoning(SID, []);
  assert.deepEqual(JSON.parse(f.calls[0].init.body), { session_id: SID });
  assert.deepEqual(JSON.parse(f.calls[1].init.body), { session_id: SID, seasonings: [] });
});

test("detect sends multipart 'images' parts plus session_id (no manual Content-Type)", async () => {
  const f = fakeFetch({ status: 200, body: { session_id: SID, detected: [] } });
  const files = [new File(["x"], "a.jpg", { type: "image/jpeg" }), new File(["y"], "b.png", { type: "image/png" })];
  await api(f).detect(SID, files);
  const { url, init } = f.calls[0];
  assert.equal(url, "http://host:8000/detect");
  assert.ok(init.body instanceof FormData);
  assert.deepEqual(init.body.getAll("images").map((x) => x.name), ["a.jpg", "b.png"]);
  assert.equal(init.body.get("session_id"), SID);
  assert.equal(init.headers, undefined, "the browser must set the multipart boundary itself");
});

test("detect omits session_id when there is none", async () => {
  const f = fakeFetch({ status: 200, body: {} });
  await api(f).detect(null, [new File(["x"], "a.jpg", { type: "image/jpeg" })]);
  assert.equal(f.calls[0].init.body.has("session_id"), false);
});

test("an empty base means same-origin (relative URL)", async () => {
  const f = fakeFetch({ status: 200, body: { status: "ok", detector: "loaded" } });
  const r = await FG.createApi({ base: "", fetchImpl: f }).health();
  assert.equal(f.calls[0].url, "/health");
  assert.equal(r.detector, "loaded");
});

test("HTTP errors are normalised: string detail (404 unknown session)", async () => {
  const a = api(fakeFetch({ status: 404, body: { detail: "unknown session" } }));
  await assert.rejects(a.confirm(SID, "ใช่"), (e) => {
    assert.equal(e.kind, "http");
    assert.equal(e.status, 404);
    assert.equal(e.code, "session_expired");
    assert.equal(e.detail, "unknown session");
    assert.match(e.message, /เซสชัน/);
    return true;
  });
});

test("HTTP errors are normalised: FastAPI validation list detail (422)", async () => {
  const body = { detail: [{ type: "string_too_short", loc: ["body", "text"], msg: "String should have at least 1 character" }] };
  await assert.rejects(api(fakeFetch({ status: 422, body })).extract(SID, ""), (e) => {
    assert.equal(e.code, "invalid");
    assert.equal(e.detail, "String should have at least 1 character");
    return true;
  });
});

test("429 from the rate limiter is retryable", async () => {
  await assert.rejects(
    api(fakeFetch({ status: 429, body: { detail: "rate limit exceeded: 5 per 1 minute" } })).detect(SID, [new File(["x"], "a.jpg")]),
    (e) => e.code === "rate_limited" && e.retryable === true
  );
});

test("nginx 413 (an HTML body, not JSON) still becomes too_large", async () => {
  await assert.rejects(api(fakeFetch({ status: 413, text: "<html>413 Request Entity Too Large</html>" })).detect(SID, [new File(["x"], "a.jpg")]), (e) => e.code === "too_large");
});

test("a 200 with a non-JSON body (a proxy error page) is an error, not data", async () => {
  await assert.rejects(api(fakeFetch({ status: 200, text: "<html>Bad gateway</html>" })).recommend(SID, 3), (e) => e.kind === "http" && e.code === "server_error");
});

test("a fetch that throws is a network error", async () => {
  await assert.rejects(api(fakeFetch(new TypeError("Failed to fetch"))).extract(SID, "x"), (e) => e.kind === "network" && e.code === "network" && e.retryable);
});

test("a hung request is aborted and reported as a timeout", async () => {
  const hung = async (url, init) => new Promise((_, reject) => {
    init.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
  });
  const started = Date.now();
  await assert.rejects(FG.createApi({ base: "", fetchImpl: hung, timeoutMs: 40 }).extract(SID, "x"), (e) => e.kind === "timeout" && e.code === "timeout");
  assert.ok(Date.now() - started < 1000, "must give up promptly");
});

test("detect uses its own (longer) timeout", async () => {
  const hung = async (url, init) => new Promise((_, reject) => {
    init.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
  });
  const a = FG.createApi({ base: "", fetchImpl: hung, timeoutMs: 20, detectTimeoutMs: 120 });
  const t0 = Date.now();
  await assert.rejects(a.detect(SID, [new File(["x"], "a.jpg")]), (e) => e.kind === "timeout");
  assert.ok(Date.now() - t0 >= 100, "detect should wait for detectTimeoutMs, not timeoutMs");
});
