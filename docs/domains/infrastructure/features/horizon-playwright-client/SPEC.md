# Horizon Playwright client

The `HorizonClient` port over Playwright and the system Chrome: drives the VMware
Horizon HTML Access web client headless and takes screenshots, of a success and of a
failure, only after the login page.

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
| `open_desktop(name)` | clicks the tile's launch button, cancels the Fullscreen offer (`#cancelDialogBtn`), and once the desktop is open logs whether a WebSocket on a Blast path was seen; returns `None` and takes no success photograph | `DESKTOP_DID_NOT_OPEN` |
| `capture_open_desktop()` | polls the largest canvas or video in `#canvas-container`: cancels a client dialog over it (never OK), takes an element screenshot, has the page decode that PNG onto a 32 by 32 grid, and saves the same PNG once at least 8 cells have `max(R, G, B) >= 24` and no dialog came into the frame, bounded by `desktop_paint_ms` (60 s); a blank or dialog-covered timeout, a page closed or outside the screenshot allowlist, or a screenshot or decode error returns `None` (see "The check-in capture") | none: a missing photo never fails the step |
| `disconnect()` | closes the browser context: the Blast connection goes with it, the Windows session keeps running | `UNEXPECTED` |
| `log_off(name)` | opens the tile's "…" menu, clicks `#menu-item-logoff-btn`, confirms `#okDialogBtn`, waits (bounded) for the broker's kill-session answer, then polls until a freshly loaded launch-items list shows the tile without a session (see "Confirming a log off"); answers with the success screenshot of that list, or `None` | `ALREADY_LOGGED_OFF` (the menu hides the item), `LOGOFF_NOT_CONFIRMED`, `DESKTOP_NOT_FOUND`, or the reasons of `login()` when a reload lands on the login form |
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
| `DIALOG_OK`, `DIALOG_CANCEL` | `#okDialogBtn`, `#cancelDialogBtn` | the client's dialog buttons: the rejected login, the Fullscreen offer, the Log Off confirmation. The check-in capture reads a dialog over the desktop by its visible buttons, clicks Cancel and never OK |
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
  canvas may stay empty; the first live run says whether that happens. The success
  photograph is a different reading: it judges an element screenshot of the largest
  canvas or video inside `#canvas-container`, while this signal still reads the canvas
  size only;
- `_tile_session_state()`: the tile's menu offers `#menu-item-logoff-btn` (no `hidden`
  attribute) only when Windows holds a session. The bundle derives it from the
  broker's `canLogoff` and a non-empty session `state`. The attribute is read rather
  than the item's visibility, which the client's stylesheet, not in the bundle, could
  override. The tile cannot tell whether another client is attached, so a session
  reads as `DISCONNECTED`, and `CONNECTED` is only ever this client's own open
  desktop. The tile shows the list the page last fetched, as the client has changed
  it since; "Confirming a log off" below is why that matters.

The probe never logs in, so it cannot confirm either reading. The first measurement is
the manual `checkin --force` and `checkout --force` on the VPS (`docs/guides/deployment.md`).

### Confirming a log off

On OK of the log-off confirmation the client clears the tile's `logoffEnabled` flag
at once and only then sends the kill-session request
(`launchItemsCtrlService._logoffDesktop` in the bundle). The menu derives "Log Off"
from that flag, so the tile on the same page reads "no session" before the broker has
answered, whatever it answers. `log_off()` therefore never confirms from that page:

- it waits for the broker's answer to the kill-session request before it reloads
  anything. The wait is armed before the OK click and matches a response from
  `…/broker/xml` whose request body carries `<kill-session>` (the bundle posts each
  broker command as one XML document there; `Kw.setRequestXML`, `Oi.createXML`). The
  path is checked before the body is read: every page response passes the match while
  the wait is armed, and Playwright decodes a request body as strict UTF-8, so an
  unrelated binary POST in that window (telemetry, an upload) must not reach the
  decode. A
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

An answer is logged at INFO as `Horizon kill-session answered: <status> after <ms>
ms`: `<status>` is the HTTP status of the broker's answer, whatever it is (a 401 or a
500 releases the wait too, and the fresh list decides), and `<ms>` is the time from the
OK click's return to the answer, on a monotonic clock. The line carries nothing else:
no URL, no body, no credential. The live check reads it to see that the request was
answered before the reload, with what, and how long it took; `<ms>` includes the
client's own path from OK to the request, so it is an upper bound on the broker's time,
and it is the number `kill_session_answer_ms` is sized from.

Not measured on the live portal: whether a reload keeps the web session (the fallback
covers both answers; the bundle ties it to the broker's
`enableCredentialCleanupForHTMLAccess`, and with it on the next login waits up to 3 s,
`waitForCredentialClean`) and how long the broker takes to answer kill-session. The
live `checkout --force` sees a successful log off either way, so it cannot tell a
broker's answer from the client's flag; a broker-side read after the check-out can.

### Success screenshots

`open_desktop()` returns `None` and does not take the success photograph.
`capture_open_desktop()` and `log_off()` answer with the path of a screenshot the use
case can put into the run report. A screenshot never changes a step's verdict.
`success_settle_ms` is gone.

- `capture_open_desktop()`: the first painted frame of the remote surface with no
  client dialog in it, written through `screenshot_path(RunKind.CHECKIN)`, or `None`.
  "The check-in capture" below is the whole rule.
- `log_off()`: after the fresh launch-items list has confirmed the session gone, that
  list is photographed as `RunKind.CHECKOUT` through the shared page screenshot. There
  is no settle. The list is already loaded. Checkout is unchanged.

The shared page screenshot is what failures and `log_off` use. Its allowlist is the
same pair of routes, read when the shot is taken, so a page on `#/home` is not
photographed and the answer is `None`. A Playwright error or a disk error (an
`OSError`, for instance from writing the file) while taking that screenshot is logged
as `Horizon screenshot failed: <Type>` and answers `None`. The step still succeeds. A
failure screenshot is named by the `run_kind` the client was built with. Because the
shared method catches disk errors too, a failure whose screenshot the disk refuses
raises a `HorizonClientError` without a screenshot rather than an `OSError`.
`capture_open_desktop` catches the same disk error and returns `None` instead of
failing the step.

### The check-in capture

`capture_open_desktop()` takes samples until one is saved or its bound runs out. One
sample does this, in order:

1. The page must be live and on `#/launchitems` or `#/desktop`. A page that is gone,
   closed or on any other route stops the capture before anything is read or
   photographed: it returns `None`, writes nothing and logs no "still blank" line.
2. A client dialog over the desktop is read by its visible buttons
   (`#cancelDialogBtn:visible`, `#okDialogBtn:visible`). A visible Cancel is clicked,
   with a timeout of what is left of the bound, and logged as `Horizon client dialog
   cancelled before the photo`. OK is never clicked, because on the Fullscreen offer it
   grants full screen, so a dialog that shows only OK is waited out. Either way this
   sample takes no frame and the next poll looks again, so a dialog that closes slowly
   or comes straight back is not photographed. `open_desktop` cancels the first
   Fullscreen offer. The client can show it again after that, as in the check-in photo
   of 2026-10-24, and this step is what keeps it out of the frame.
3. The surface is the largest canvas or video inside `#canvas-container`
   (`#canvas-container canvas, #canvas-container video`) by the area of its bounding
   box, so a smaller bright canvas does not paint a black desktop. A missing surface,
   or one that holds no bitmap yet (a canvas of width 0, a video with no frame), waits.
4. An element screenshot of that surface is taken as a PNG, with a timeout of what is
   left of the bound.
5. The page judges that PNG. The bytes arrive as base64 and become a `Blob` and an
   `ImageBitmap` (`createImageBitmap`), drawn onto a 32 by 32 canvas (`_SAMPLE_SIDE`)
   with smoothing off, so each cell is one pixel of the frame. The page answers the
   number of cells with `max(R, G, B) >= 24` (`_LIT_CHANNEL`), and Python counts the
   frame painted when that number is at least 8 (`_LIT_CELLS_REQUIRED`).
6. A painted frame is checked for a client dialog once more, as in step 2. A dialog
   that came in after the first look is in this frame, so the frame is discarded and
   the next poll looks again.
7. Otherwise the same PNG bytes are written to `screenshot_path(RunKind.CHECKIN)`. The
   pixels judged are the pixels saved, and no second screenshot is taken.

Between samples the capture waits `poll_ms`, or what is left of the bound when that is
shorter. A page that has closed is not waited on, and the next sample stops at step 1.

**The composited frame, not the surface.** The verdict judges the element screenshot,
the composited pixels Telegram receives, and never reads the live surface's bitmap.
HT-009's RFC decided this ("not a WebGL readback"). HT-010 briefly read the surface with
`drawImage` instead, and its review measured a 1920 by 1080 WebGL canvas without
`preserveDrawingBuffer` reading 0 of 1024 lit cells that way while its element
screenshot read 1024 (Google Chrome 155 and Playwright Chromium 156, headless). HT-010
therefore restored the decision. Nothing in the repository records whether the 2312.1
client draws `#mainCanvas` through 2D, WebGL or a `<video>`. The decode loads no URL, so
the portal's content security policy cannot block it, and a `Blob` never taints the
canvas. The adapter carries no PNG codec.

**The bound.** `HorizonTimeouts.desktop_paint_ms` (60 s by default) bounds the whole
capture. A sample starts only while at least `_SAMPLE_FLOOR_MS` (250 ms) of the bound
are left. The Cancel click, the screenshot and the pause each wait at most what is left,
and at least 1 ms, because Playwright reads 0 as no timeout. The in-page decode takes no
timeout, since Playwright's `evaluate` has none, so the bound holds to within one
in-page decode: about 0.5 s in the worst case measured. A sample needs about one
screenshot plus one decode. HT-010's fix and its review measured a 1920 by 1080 noise
frame (5.9 MiB, the worst-case PNG) at 261–409 ms for the screenshot and 468–562 ms for
the decode, and a solid 1920 by 1080 desktop at 46–90 ms plus 4–9 ms (Chrome 155 and
Chromium 156, headless, on a Mac). `_SAMPLE_FLOOR_MS` is therefore a floor, not a
guarantee: a sample started with 250–850 ms left can still run out on a worst-case
frame, and it then logs `Horizon screenshot failed: TimeoutError` and returns `None`.

**What it answers.** When the bound runs out, the capture logs what its last sample saw
and returns `None`: `Horizon desktop still blank` after a blank or missing surface,
`Horizon client dialog still open` after a dialog. A bound shorter than the floor starts
no sample and logs `Horizon desktop still blank`. A `PlaywrightError` (a screenshot that
fails or times out, a frame the page cannot decode, a page that closes inside a sample),
an `OSError` (the disk) or a `ValueError` (the page answered something other than a
surface reading or a count) is logged as `Horizon screenshot failed: <Type>` and returns
`None`. No file is written in any of these cases, and none of them raises out of the
capture.

### Secrets and failures

The password is typed into `#password` and goes nowhere else. A screenshot, of a
failure or of a success, is taken only on an allowlist of routes after the login page
(`#/launchitems`, `#/desktop`); a page on any other route is never photographed.
Playwright tracing is never started. A Playwright error inside a step is re-raised as `HorizonClientError`
without its cause (`from None`) and logged by its type only, so no message text the
library composed can carry a value.

`close()` is best-effort. By the time it runs, the run has reported, so a context or a
browser that fails to close is logged as `Horizon <part> did not close: <Type>` and not
raised; the Playwright driver is stopped whatever happened before. A run that
succeeded therefore does not exit 1 on the way out.

## Invariants

- The login page is never photographed. Page screenshots and the capture sample both
  refuse a route outside `#/launchitems` and `#/desktop`.
- The capture never answers a client dialog with OK. It clicks Cancel or waits, and it
  saves no frame a dialog showed in.
- The check-in photo is the frame that was judged: the composited element screenshot,
  never a readback of the surface's bitmap.
- `desktop_paint_ms` bounds the capture to within one in-page decode.
- A missing photograph never changes a step's verdict. `open_desktop` returns `None`
  and takes no success photograph. `capture_open_desktop` and `log_off` answer `None`
  when the photograph cannot be taken.
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
  kill_session_answer_ms=30_000, desktop_paint_ms=60_000)` — frozen.
  `success_settle_ms` is not a field.
- `open_desktop(name) -> None` — returns once the desktop is open. It takes no
  success photograph.
- `capture_open_desktop() -> Path | None` — the saved PNG of the first painted frame
  of the remote surface with no client dialog in it, or `None`.
- `log_off(name) -> Path | None` — the path of the success screenshot of the launch
  list, `None` when none could be taken.
- Route and selector constants: `LOGIN_ROUTE`, `LAUNCH_ITEMS_ROUTE`, `DESKTOP_ROUTE`,
  `USERNAME_FIELD`, `PASSWORD_FIELD`, `LOGIN_BUTTON`, `DIALOG_OK`, `DIALOG_CANCEL`,
  `ANY_TILE`, `LAUNCH_BUTTON`, `TILE_MENU_BUTTON`, `TILE_MENU`, `LOGOFF_MENU_ITEM`,
  `DESKTOP_CANVAS`, `BLAST_PATH_PREFIXES`; the broker request a log off waits for:
  `BROKER_XML_PATH`, `KILL_SESSION_TAG`.

## Testing

Tests: `tests/integration/infrastructure/test_horizon_playwright.py`,
`tests/acceptance/steps/test_client_dialog_in_the_photo.py`. The adapter tests drive a
real Chromium against a local copy of the HTML Access markup
(`tests/fixtures/htmlaccess/`) served on localhost by `tests/support/htmlaccess_portal.py`,
never the portal; CI installs the browser with `playwright install --with-deps
chromium`. The paint rule is tested through `capture_open_desktop`, not through a
private name. The fixture reproduces the
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
logout before the answer cuts the request off; OK also sends a `set-last-user-activity`
answered at once, so only the kill-session's answer releases the wait; the menu closes a
while after the document click, which pins the adapter's wait for it to go; the tile
geometry, which comes from a stylesheet not in the bundle. The fixture broker can also
refuse a log off, end the session only a few lists later, serve one list per login, so
that a reload lands on the login form, answer kill-session late (1.5 s, beyond the 1 s
the adapter once waited after OK) with credential cleanup on, answer it with an error
status, never answer it, and never show the log-off confirmation. The page can fall back
to `#/home` a while after the desktop drew. `capture_open_desktop` then saves nothing
and does not log `Horizon desktop still blank`. The fixture can paint the desktop when
it draws (`paint_desktop`), offer Fullscreen again a while after the desktop drew
(`fullscreen_again_after_ms`), as the live client did on 2026-10-24, and let that offer
ignore Cancel (`fullscreen_sticks`). Its dialog is a modal over the remote surface, so a
frame taken while it shows carries it. The tests also make the remote surface black,
painted, painted later by a page timer, lit in seven or eight cells or at a channel of
23, lit past its top-left corner only, a WebGL canvas that keeps no drawing buffer
(skipped when the browser offers no WebGL context), a transparent bitmap over a painted
CSS background, a smaller bright canvas placed before a black desktop, or a larger video
with no frame. They can fail the element screenshot, hand the page a PNG it cannot
decode, close the page after a blank sample, and give the capture less than a sample
needs. Every case the rule refuses returns `None` and writes no file. The page can also
post a non-UTF-8 body beside the log off, answered while the adapter waits, and send
kill-session as a synchronous XHR inside OK's click handler, so that the answer is in
before the click returns. The real client sends it asynchronously after a hop; that
extreme exists only to pin a wait armed before the click. That pin rests on an ordering
measured, not promised by Playwright: with the synchronous request, a wait armed after
the click missed the answer in 100 of 100 runs and one armed before it caught it in 100
of 100. A wait armed late costs the bound and a warning, not a false result, since the
fresh list still decides.

Two acceptance scenarios drive this adapter on the fixture portal, through the
check-in to the message the owner gets
(`tests/acceptance/features/client_dialog_in_the_photo.feature`):

- `A successful check-in's photo shows the desktop without a client dialog`
- `A client dialog that cannot be dismissed leaves the check-in a text success`

They read the photo with `tests/support/photo.py`, which decodes the PNG in a browser
page. Every other scenario runs on a fake of the port (`tests/support/fakes.py`). A test
on the fixture proves the fixture's contract. The live portal is reached only on the
VPS.

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `run-report`, `schedule`, `session-state`
- Used by: `cli`

## Parent

`infrastructure` — [infrastructure README](../../README.md)
