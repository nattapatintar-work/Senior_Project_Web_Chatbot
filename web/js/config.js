/*
 * web/js/config.js  --  the only file you normally edit to point the UI somewhere else.
 *
 * API_BASE
 *   "http://15.135.217.132"  the deployed EC2 backend (default). When this page is ALSO
 *                            served by that server's nginx it is the same origin: no CORS.
 *   ""                       same origin as the page, whatever host that is (use this
 *                            once nginx serves the page and the API on one domain).
 *   "http://localhost:8000"  a locally running backend. Cross-origin, so start it with
 *                            CORS_ORIGINS=http://localhost:8080 (see web/README.md).
 *
 * One-off override without editing anything:  index.html?api=http://localhost:8000
 */
window.FG_CONFIG = {
  API_BASE: "http://15.135.217.132",
};
