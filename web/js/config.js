/*
 * web/js/config.js  --  the only file you normally edit to point the UI somewhere else.
 *
 * API_BASE
 *   ""                       (the default) same origin as the page: nginx serves the page and
 *                            the API on one host, so the page calls whatever host it was
 *                            opened from. Works with any server IP or domain; no CORS.
 *   "http://localhost:8000"  a locally running backend, for local development. Cross-origin,
 *                            so start it with CORS_ORIGINS=http://localhost:8080 (see web/README.md).
 *
 * One-off override without editing anything:  index.html?api=http://localhost:8000
 *
 * Do not hard-code a server IP here: an instance can get a new public IP, and a page that
 * points at the old one hangs on every API call.
 */
window.FG_CONFIG = {
  API_BASE: "",
};
