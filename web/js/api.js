/*
 * web/js/api.js
 * =============
 * Thin fetch wrapper over the seven backend endpoints. `FG.createApi(options)`
 * is a factory so tests can inject a fake fetch; the page calls it once.
 *
 * Every failure is normalised into ONE error shape so the UI has one place to
 * handle it:
 *     err.kind      "network" | "timeout" | "http"
 *     err.status    HTTP status (http only)
 *     err.detail    the backend's `detail` text (see logic.detailText)
 *     err.code      logic.classifyError code, e.g. "session_expired"
 *     err.message   Thai, user-facing
 *     err.retryable whether "try again" can help
 */
(function (root) {
  "use strict";

  var FG = (root.FG = root.FG || {});

  function makeError(info, logic) {
    var c = logic.classifyError(info);
    var err = new Error(c.message);
    err.name = "ApiError";
    err.kind = info.kind;
    err.status = info.status || 0;
    err.detail = info.detail || "";
    err.code = c.code;
    err.retryable = c.retryable;
    return err;
  }

  /**
   * options.base        API base URL, "" = same origin
   * options.fetchImpl   defaults to window.fetch
   * options.timeoutMs   default per-request timeout (detect uses detectTimeoutMs)
   */
  FG.createApi = function (options) {
    var logic = FG.logic;
    var base = String(options.base || "").replace(/\/+$/, "");
    var fetchImpl = options.fetchImpl || (typeof fetch === "function" ? fetch.bind(root) : null);
    var timeoutMs = options.timeoutMs || 30000;
    var detectTimeoutMs = options.detectTimeoutMs || 60000;

    async function request(path, init, ms) {
      var controller = typeof AbortController === "function" ? new AbortController() : null;
      var timer = controller ? setTimeout(function () { controller.abort(); }, ms || timeoutMs) : null;
      var response;
      try {
        response = await fetchImpl(base + path, Object.assign({}, init, controller ? { signal: controller.signal } : {}));
      } catch (e) {
        throw makeError({ kind: e && e.name === "AbortError" ? "timeout" : "network" }, logic);
      } finally {
        if (timer) clearTimeout(timer);
      }

      var text = "";
      try { text = await response.text(); } catch (e) { /* body unreadable: fall through with "" */ }
      var body = null;
      try { body = text ? JSON.parse(text) : null; } catch (e) { body = null; }

      if (!response.ok) {
        throw makeError({ kind: "http", status: response.status, detail: logic.detailText(body) }, logic);
      }
      if (body === null) {
        // A 200 that is not JSON is almost always a proxy/error page in front of the API.
        throw makeError({ kind: "http", status: 502, detail: "non-JSON response" }, logic);
      }
      return body;
    }

    function postJson(path, payload) {
      return request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    return {
      base: base,

      health: function () { return request("/health", { method: "GET" }, 8000); },

      /** seasonings omitted/undefined = read-only; [] = clear. sessionId may be null. */
      seasoning: function (sessionId, seasonings) {
        var payload = { session_id: sessionId || null };
        if (seasonings !== undefined) payload.seasonings = seasonings;
        return postJson("/seasoning", payload);
      },

      /** files: array of Blob/File (1-5). */
      detect: function (sessionId, files) {
        var form = new FormData();
        files.forEach(function (f) { form.append("images", f, f.name || "photo.jpg"); });
        if (sessionId) form.append("session_id", sessionId);
        return request("/detect", { method: "POST", body: form }, detectTimeoutMs);
      },

      extract: function (sessionId, text) {
        return postJson("/extract", { text: text, session_id: sessionId || null });
      },

      confirm: function (sessionId, reply) {
        return postJson("/confirm", { session_id: sessionId, reply: reply });
      },

      correct: function (sessionId, exclude, addText) {
        var payload = { session_id: sessionId, exclude: exclude || [] };
        if (addText) payload.add_text = addText;
        return postJson("/correct", payload);
      },

      recommend: function (sessionId, topN) {
        return postJson("/recommend", { session_id: sessionId, top_n: topN });
      },
    };
  };

  if (typeof module !== "undefined" && module.exports) module.exports = FG;
})(typeof window !== "undefined" ? window : globalThis);
