/** @odoo-module **/

/**
 * Keep odoo.csrf_token in step with the current session.
 *
 * A tab holds the upload token it was loaded with. Once the session changes -
 * a new Microsoft login in this or another tab - that token stops validating,
 * and uploads fail with "Session expired (invalid CSRF token)" while the rest
 * of the tab keeps working. Uploads read odoo.csrf_token at the moment they
 * are sent, so refreshing it whenever the tab becomes active again is enough.
 *
 * Plain fetch rather than rpc(): rpc() drives the global loading indicator,
 * which would flash on every tab switch.
 */

const MIN_INTERVAL_MS = 5000;
let lastRefresh = 0;

async function refreshCsrfToken() {
    const now = Date.now();
    if (now - lastRefresh < MIN_INTERVAL_MS) {
        return; // focus and visibilitychange usually fire together
    }
    lastRefresh = now;
    try {
        const response = await fetch("/auth_oauth_autolink/session/csrf_token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: {} }),
        });
        const { result } = await response.json();
        if (result) {
            odoo.csrf_token = result;
        }
    } catch {
        // Session gone or network down: Odoo's own handling takes over on the
        // next real request, so there is nothing useful to do here.
    }
}

document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
        refreshCsrfToken();
    }
});
window.addEventListener("focus", refreshCsrfToken);
// Restored from the back/forward cache: the page never reloaded.
window.addEventListener("pageshow", (ev) => {
    if (ev.persisted) {
        refreshCsrfToken();
    }
});
