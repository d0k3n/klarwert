# Free Distribution with Donation Support

## Overview

The app currently ships with a paid, LemonSqueezy-hosted license gate: a full-screen
overlay in `templates/index.html` blocks the dashboard until a valid license key is
entered, validated at runtime against LemonSqueezy (`licensing.py`), with three backend
routes in `app.py` (`/api/license/status`, `/api/license/activate`,
`/api/license/deactivate`) and a startup check in `static/dashboard.js`.

The goal is to distribute the app **for free** with no activation gate, replace the paid
flow with a **simple static donation link**, and let anyone **request features via a
public GitHub Issues URL**. This is a minimal, low-risk change: remove the gate, add a
small support config and two header buttons plus a footer, and open the links in the
system default browser.

## Current State (what is being removed)

- **`licensing.py`** — LemonSqueezy activate/validate/deactivate logic.
- **`app.py`** — `import licensing as license_module` and routes:
  - `GET /api/license/status`
  - `POST /api/license/activate`
  - `POST /api/license/deactivate`
- **`templates/index.html`** — the `#license-overlay` full-screen block (lines ~11–19).
- **`static/dashboard.js`** — `activateLicense` function and the startup
  license-status check that shows/hides the overlay.

No test file references licensing (`tests/*` were checked), so there is no test
migration.

## Design

### 1. Remove the license gate

1. **Delete `licensing.py`** entirely.
2. **`app.py`** — remove `import licensing as license_module` and the three
   `/api/license/*` route handlers.
3. **`templates/index.html`** — remove the entire `#license-overlay` div.
4. **`static/dashboard.js`** — remove `activateLicense` and the startup
   license-status call (the function that fetches `/api/license/status` and toggles
   the overlay).

### 2. Support config

New module **`support.py`** holding two URL placeholders (empty strings initially, to
be filled by the user):

```python
DONATION_URL = ""   # ko-fi / Buy Me a Coffee / LemonSqueezy donate link
GITHUB_URL   = ""   # public GitHub repo (feature requests / issues)
```

These are imported by `desktop_app.py` and surfaced to the frontend so the buttons can
open them in the OS browser.

### 3. UI: Support + Request a Feature

**Header** (`header-right` in `index.html`) — two small, subtle buttons:
- **"Support"** → opens `DONATION_URL`
- **"Request a Feature"** → opens `GITHUB_URL`

**Footer** — a small centered credit line: `Made with <3 · Free forever. Support the
project` where "Support the project" links to `DONATION_URL`.

Styling in `static/style.css` reusing existing button styles; kept unobtrusive
(secondary/ghost look, not a call-to-action banner).

### 4. Opening links in the system default browser

The dashboard runs as a local page inside a **pywebview** window in the packaged app
and as a normal browser tab in dev. Links must open in the **OS default browser**, not
inside the webview window.

- Add a tiny `js_api` bridge in `desktop_app.py` exposing `open_url(url)` that calls
  `webbrowser.open(url)`. Pass it to `webview.create_window(...)` via `js_api`.
- In `dashboard.js`, the button handlers call
  `window.pywebview.api.open_url(url)` when the pywebview API is present, and fall back
  to `window.open(url, '_blank')` when not (dev / plain-browser mode).

## Files to Modify

1. **`licensing.py`** — delete.
2. **`support.py`** — new (URL constants).
3. **`app.py`** — remove licensing import + routes.
4. **`desktop_app.py`** — add `js_api` bridge (`open_url`).
5. **`templates/index.html`** — remove `#license-overlay`, add header buttons + footer.
6. **`static/dashboard.js`** — remove license logic, add `open_url`/button handlers.
7. **`static/style.css`** — styles for the new buttons + footer.
8. **`requirements.txt`** — remove `requests` (only used by `licensing.py`) as optional
   cleanup.

## Error Handling

- If `DONATION_URL` / `GITHUB_URL` are empty, the buttons are hidden or disabled so the
  UI never renders dead links before the user fills the config.
- Link opening is best-effort: `webbrowser.open` failures are swallowed (nothing breaks
  the dashboard).

## Testing

- Run the existing test suite (`pytest`) after changes — none reference licensing, but
  confirm `app.py` still imports and serves correctly.
- Manual: dev mode — buttons shown once URLs are set, clicking opens a new browser tab.
- Manual: packaged mode — clicking opens the OS default browser via the pywebview bridge.

## Non-Goals

- No payment/tracking backend, no "benefactor" badge, no tiers, no in-app form/email
  backend.
- No soft "consider donating" interstitial prompt (the header/footer links are the only
  ask).
- No changes to portfolio analysis logic (parser, engine, tax report).
