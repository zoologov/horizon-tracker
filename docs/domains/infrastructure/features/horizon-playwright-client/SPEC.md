# Horizon Playwright client

The `HorizonClient` port over Playwright and the system Chrome: drives the VMware
Horizon HTML Access web client headless and takes screenshots only after the login
page.

## Source

`src/horizon_tracker/infrastructure/horizon_playwright.py`

## Specification

### Purpose

The accounting system sees a Windows logon only when a real client opens the desktop
over Blast. This adapter walks the HTML Access web client the way a person does, in
headless Chrome, and reports every failure as a `Reason` from the report vocabulary.

### How it works

The path is `#/home` (login) → `#/launchitems` (desktop tiles) → `#/desktop` (the
Blast canvas). One instance serves one run. The browser starts on the first call that
needs it, and each `login` opens a fresh browser context on it.

| Method | What it does | Reason on failure |
|--------|--------------|-------------------|
| `login()` | opens `#/home`, fills `#username` and `#password`, clicks `#loginButton`, then polls: `#/launchitems` means accepted, a visible `#okDialogBtn` means rejected | `PORTAL_UNREACHABLE` (the page does not load), `LOGIN_REJECTED`, `UNEXPECTED` (no verdict in time) |
| `desktop_status(name)` | `CONNECTED` while this client holds that desktop open; otherwise reads the tile `li[title="<name>"]` and logs in first when no page is live | `DESKTOP_NOT_FOUND`, `UNEXPECTED`, or the reasons of `login()` when it logs in first |
| `open_desktop(name)` | clicks the tile's `[id^='launch-']` button, cancels the Fullscreen offer (`#cancelDialogBtn`), returns once the desktop is open | `DESKTOP_DID_NOT_OPEN` |
| `disconnect()` | closes the browser context: the Blast connection goes with it, the Windows session keeps running | `UNEXPECTED` |
| `log_off(name)` | opens the tile's "…" menu, clicks `#menu-item-logoff-btn`, confirms `#okDialogBtn`, polls until the tile shows no session | `ALREADY_LOGGED_OFF` (the menu item is disabled), `LOGOFF_NOT_CONFIRMED`, `DESKTOP_NOT_FOUND` |
| `client_bundles()` | GETs `<portal>/index.html` through Playwright's request API, opens no page and does not log in, returns the file names of its `<script src="*.js">` bundles | `PORTAL_UNREACHABLE` (no answer or a status other than 200), `UNEXPECTED` (no bundle named) |
| `browser_version()` | starts headless Chrome at `chrome_path` as a browser of its own, reads its version, closes it; opens no context and no page | `UNEXPECTED` |

`client_bundles()` and `browser_version()` take no screenshot. A browser of its own
for `browser_version()` lets the deploy smoke find a Chrome that Playwright can no
longer drive without touching the portal or the run's browser.

A run starts the browser inside the first `login()`, in the step whose failure reason
is `PORTAL_UNREACHABLE`. A Chrome that does not start therefore fails a run as
`PORTAL_UNREACHABLE`; only the probe, through `browser_version()`, tells the two apart.

Each context presents an ordinary Chrome user agent whose major version is the started
browser's. Every step has a timeout from `HorizonTimeouts`; the defaults are for the
live portal.

### Two readings that are hypotheses

Every selector was read from the HTML Access 2312 bundle (RFC HT-001), except the
tile's "…" button, which the RFC names only by its glyph. Two readings were inferred
from the bundle and not measured on the live portal; the code marks each as a
hypothesis in the one method that holds it:

- `_desktop_is_open()`: `#canvas` inside `#canvas-container` has a non-zero size and a
  WebSocket on a Blast path (`/r/…` or `/d/…`) is still open;
- `_tile_session_state()`: the tile's menu offers an enabled `#menu-item-logoff-btn`
  only when Windows holds a session. The tile cannot tell whether another client is
  attached, so a session reads as `DISCONNECTED`, and `CONNECTED` is only ever this
  client's own open desktop.

The code says these hold "until the first `horizon probe` on the VPS". The probe never
logs in, so it cannot confirm either reading. The first measurement is the manual
`checkin --force` and `checkout --force` on the VPS (`deploy/RUNBOOK.md` §4).

### Secrets and failures

The password is typed into `#password` and goes nowhere else. A failure screenshot is
taken only on an allowlist of routes after the login page (`#/launchitems`,
`#/desktop`); a page on any other route is never photographed. Playwright tracing is
never started. A Playwright error inside a step is re-raised as `HorizonClientError`
without its cause (`from None`) and logged by its type only, so no message text the
library composed can carry a value.

`close()` is best-effort. By the time it runs, the run has reported, so a context or a
browser that fails to close is logged as `Horizon <part> did not close: <Type>` and not
raised; the Playwright driver is stopped whatever happened before. A run that
succeeded therefore does not exit 1 on the way out.

## Invariants

- The login page is never photographed: screenshots use an allowlist of routes.
- No Playwright error message reaches a log or a `HorizonClientError`.
- `client_bundles()` and `browser_version()` never log in and never open a page.
- `disconnect()` never logs off.
- `close()` never raises a `PlaywrightError` and is safe to call more than once.
- One instance per process at a time: the sync Playwright driver refuses a second one
  in the same thread, so a client is closed before the next starts.

## API

Module `src/horizon_tracker/infrastructure/horizon_playwright.py`:

- `PlaywrightHorizonClient(*, horizon_url: str, username: str, password: str,
  chrome_path: Path | None, artifacts: ArtifactStore, run_kind: RunKind, timeouts:
  HorizonTimeouts | None = None)` — implements `HorizonClient`; a context manager whose
  exit calls `close()`. `chrome_path=None` uses Playwright's own Chromium. `repr` shows
  the portal URL and the run kind only.
- `HorizonTimeouts(page_load_ms=30_000, action_ms=15_000, login_ms=30_000,
  desktop_open_ms=90_000, logoff_confirm_ms=60_000, poll_ms=1_000)` — frozen.
- Route and selector constants: `LOGIN_ROUTE`, `LAUNCH_ITEMS_ROUTE`, `DESKTOP_ROUTE`,
  `USERNAME_FIELD`, `PASSWORD_FIELD`, `LOGIN_BUTTON`, `DIALOG_OK`, `DIALOG_CANCEL`,
  `ANY_TILE`, `LAUNCH_BUTTON`, `TILE_MENU_BUTTON`, `LOGOFF_MENU_ITEM`, `DESKTOP_CANVAS`,
  `BLAST_PATH_PREFIXES`.

## Testing

Tests: `tests/integration/infrastructure/test_horizon_playwright.py`. They drive a real
Chromium against a local copy of the HTML Access markup
(`tests/fixtures/htmlaccess/`) served on localhost, never the portal; CI installs the
browser with `playwright install --with-deps chromium`.

No acceptance scenario reaches this adapter: the scenarios run on a fake of the port
(`tests/support/fakes.py`). A test on the fixture proves the fixture's contract; the
live portal is reached only on the VPS.

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `run-report`, `schedule`, `session-state`
- Used by: `cli`

## Parent

`infrastructure` — [infrastructure README](../../README.md)
