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
| `desktop_status(name)` | `CONNECTED` while this client holds that desktop open; otherwise opens the named tile's "…" menu, reads whether it offers Log Off, closes the menu; logs in first when no page is live | `DESKTOP_NOT_FOUND`, `UNEXPECTED`, or the reasons of `login()` when it logs in first |
| `open_desktop(name)` | clicks the tile's launch button, cancels the Fullscreen offer (`#cancelDialogBtn`), returns once the desktop is open; logs whether a WebSocket on a Blast path was seen | `DESKTOP_DID_NOT_OPEN` |
| `disconnect()` | closes the browser context: the Blast connection goes with it, the Windows session keeps running | `UNEXPECTED` |
| `log_off(name)` | opens the tile's "…" menu, clicks `#menu-item-logoff-btn`, confirms `#okDialogBtn`, waits (bounded) for the broker's kill-session answer, then polls until a freshly loaded launch-items list shows the tile without a session (see "Confirming a log off") | `ALREADY_LOGGED_OFF` (the menu hides the item), `LOGOFF_NOT_CONFIRMED`, `DESKTOP_NOT_FOUND`, or the reasons of `login()` when a reload lands on the login form |
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

### Selectors

Every selector was read from the compiled Angular templates of the HTML Access 2312.1
bundle (`app-htmlaccess.4eb7424a56fc03317f06.js`, client 8.12.1): first for RFC HT-001,
and again for HT-002 after the first live run found the tile, the canvas and the
log-off item wrong.

| Constant | Value | What the bundle renders there |
|----------|-------|-------------------------------|
| `USERNAME_FIELD`, `PASSWORD_FIELD`, `LOGIN_BUTTON` | `#username`, `#password`, `#loginButton` | the login form on `#/home` |
| `DIALOG_OK`, `DIALOG_CANCEL` | `#okDialogBtn`, `#cancelDialogBtn` | the client's dialog buttons: the rejected login, the Fullscreen offer, the Log Off confirmation |
| `ANY_TILE` | `li:has(> button[id^='launch-'])` | a desktop tile `li#<id>`, which carries no `title` |
| tile by name | `li:has(> button[id^='launch-'][title="<name>"])` | the tile whose launch button `button#launch-<id>` carries the desktop's name; the name is written as a CSS string, so quotes, backslashes and non-ASCII letters match |
| `LAUNCH_BUTTON` | `button[id^='launch-']` | the launch button; it also holds the tile's icons, the "…" button and, while open, the menu |
| `TILE_MENU_BUTTON` | `button.overflow-button[aria-haspopup]` | the tile's "…" button (`overflow-button app-item-action`), which stops its click, so opening the menu never launches the desktop |
| `TILE_MENU` | `.content-menu .context-menu-container` | `share-contextmenu.content-menu > ul#context-menu-container`, rendered inside the tile only while the menu is open |
| `LOGOFF_MENU_ITEM` | `#menu-item-logoff-btn` | an `li` the client hides with `[hidden]="!showLogOffDesktop"`; it is never disabled |
| `DESKTOP_CANVAS` | `#canvas-container canvas` | the canvas the Blast session appends to `#canvas-container` (WMKS `canvas#mainCanvas` in a `div#wmksContainer<N>` kept hidden until it connects; `canvas#primary-monitor` on the multi-monitor path). The service `canvas#canvas` beside the container is never shown |
| `BLAST_PATH_PREFIXES` | `/r/`, `/d/` | the WebSocket paths read for the Blast connection; logged, never decisive |

The tile menu ignores Escape: the client closes it on a click anywhere in the document
outside its trigger, so the adapter closes it with a click on the page body and waits
for it to go.

### Two readings that are hypotheses

Two readings were inferred from the bundle and not measured on a logged-in portal; the
code marks each as a hypothesis in the one method that holds it:

- `_desktop_is_open()`: a canvas inside `#canvas-container` has a non-zero size. A
  WebSocket on a Blast path (`/r/…` or `/d/…`) is looked for and logged with the
  "desktop open" line, but it does not decide the verdict: the paths cannot be checked
  without a login. If the client renders the desktop into a `<video>` (H.264), the
  canvas may stay empty; the first live run says whether that happens;
- `_tile_session_state()`: the tile's menu offers `#menu-item-logoff-btn` (no `hidden`
  attribute) only when Windows holds a session. The bundle derives it from the
  broker's `canLogoff` and a non-empty session `state`. The attribute is read rather
  than the item's visibility, which the client's stylesheet, not in the bundle, could
  override. The tile cannot tell whether another client is attached, so a session
  reads as `DISCONNECTED`, and `CONNECTED` is only ever this client's own open
  desktop. The tile shows the list the page last fetched, as the client has changed
  it since; "Confirming a log off" below is why that matters.

The probe never logs in, so it cannot confirm either reading. The first measurement is
the manual `checkin --force` and `checkout --force` on the VPS (`deploy/RUNBOOK.md` §4).

### Confirming a log off

On OK of the log-off confirmation the client clears the tile's `logoffEnabled` flag
at once and only then sends the kill-session request
(`launchItemsCtrlService._logoffDesktop` in the bundle). The menu derives "Log Off"
from that flag, so the tile on the same page reads "no session" before the broker has
answered, whatever it answers. `log_off()` therefore never confirms from that page:

- it waits for the broker's answer to the kill-session request before it reloads
  anything. The wait is armed before the OK click and matches a response from
  `…/broker/xml` whose request body carries `<kill-session>` (the bundle posts each
  broker command as one XML document there; `Kw.setRequestXML`, `Oi.createXML`). A
  reload before the answer can cancel the request, and when the broker sets
  `enableCredentialCleanupForHTMLAccess` the client logs out of the broker on
  `beforeunload`, so a reload can end the web session under an unanswered
  kill-session. The wait is bounded by `HorizonTimeouts.kill_session_answer_ms`; an
  answer that does not come in time is logged (`Horizon kill-session unanswered after
  <N> ms`) and the confirmation below decides, so the log off fails closed. An OK
  click that fails is a `LOGOFF_NOT_CONFIRMED` at once, not an unanswered request;
- every confirmation read reloads `#/launchitems`, so the tiles are built from a list
  the broker sent, and reads the tile from that list. A reload that lands on the login
  form logs in again in a fresh context, which fetches the list as well;
- the page is left on the last list fetched, so a `desktop_status()` after `log_off()`
  (the check-out's second read) reads the broker's state too. The port contract is
  unchanged.

Not measured on the live portal: whether a reload keeps the web session (the fallback
covers both answers; the bundle ties it to the broker's
`enableCredentialCleanupForHTMLAccess`, and with it on the next login waits up to 3 s,
`waitForCredentialClean`) and how long the broker takes to answer kill-session. The
live `checkout --force` sees a successful log off either way, so it cannot tell a
broker's answer from the client's flag; a broker-side read after the check-out can.

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
  desktop_open_ms=90_000, logoff_confirm_ms=60_000, poll_ms=1_000,
  kill_session_answer_ms=30_000)` — frozen.
- Route and selector constants: `LOGIN_ROUTE`, `LAUNCH_ITEMS_ROUTE`, `DESKTOP_ROUTE`,
  `USERNAME_FIELD`, `PASSWORD_FIELD`, `LOGIN_BUTTON`, `DIALOG_OK`, `DIALOG_CANCEL`,
  `ANY_TILE`, `LAUNCH_BUTTON`, `TILE_MENU_BUTTON`, `TILE_MENU`, `LOGOFF_MENU_ITEM`,
  `DESKTOP_CANVAS`, `BLAST_PATH_PREFIXES`; the broker request a log off waits for:
  `BROKER_XML_PATH`, `KILL_SESSION_TAG`.

## Testing

Tests: `tests/integration/infrastructure/test_horizon_playwright.py`. They drive a real
Chromium against a local copy of the HTML Access markup
(`tests/fixtures/htmlaccess/`) served on localhost, never the portal; CI installs the
browser with `playwright install --with-deps chromium`. The fixture reproduces the
bundle's structure where the adapter reads the page: the tile, the tile menu with its
`[hidden]` items, its document-click dismissal and its "…" that toggles, and the canvas
the Blast session appends. It reproduces the client's behaviour on a log off too: the
tile's flag is cleared on OK, before the kill-session request leaves, and the menu reads
that flag, not the broker; the request is a POST of a `<broker>` XML document with
`<kill-session>` to `/broker/xml`, and with credential cleanup on, the page logs out of
the broker on `beforeunload`.

The fixture's own assumptions, each stated in its header and chosen so the adapter
cannot lean on them: the list is fetched only when the page loads and after a login,
never on a hash navigation; the kill-session request leaves a short hop after OK, so a
reload at once would cancel it; the broker acts on kill-session when it answers, and a
logout before the answer cuts the request off; OK also sends a
`set-last-user-activity` answered at once, so only the kill-session's answer releases
the wait; the menu closes a while after the document click,
which pins the adapter's wait for it to go; the tile geometry, which comes from a
stylesheet not in the bundle. The fixture broker can also refuse a log off, end the
session only a few lists later, serve one list per login, so that a reload lands on
the login form, answer kill-session late (1.5 s, beyond the 1 s the adapter once waited
after OK) with credential cleanup on, never answer it, and never show the log-off
confirmation.

No acceptance scenario reaches this adapter: the scenarios run on a fake of the port
(`tests/support/fakes.py`). A test on the fixture proves the fixture's contract; the
live portal is reached only on the VPS.

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `run-report`, `schedule`, `session-state`
- Used by: `cli`

## Parent

`infrastructure` — [infrastructure README](../../README.md)
