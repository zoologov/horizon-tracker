# Horizon portal

The VMware Horizon HTML Access web client and its connection broker, run by the
organisation that owns the desktop. An external system: this repository holds no code of
it and declares only the surface the service reads.

## Source

None in this repository. The node's `source` in `.beadloom/_graph/landscape.yml` is this
file, so the graph has no sourceless node. The portal's address is the setting
`HORIZON_URL`, for example `https://horizon.example.com/portal/webclient/`. The real
address lives only in the GitHub Environment `horizon-vps` and the host's `.env`.

## Specification

### Purpose

The portal is where the attendance record is made: a check-in is an open Blast connection
to the desktop with Windows logged on, and a check-out is Windows ending that session
after sign-out input through the open desktop. The broker's freshly fetched launch-items
list confirms that the session ended. The service reaches the portal only through the
Playwright adapter (`horizon-playwright-client`), headless Chrome walking the same pages
a person walks. The probe reads the client bundle without logging in, and it does so
through the same adapter, called through the `HorizonClient` port.

### Contracts

Three contracts, each declared from both ends in `landscape.yml`. Beadloom compares a
surface only for `amqp` and `graphql`, so the portal's map shows each as a dependency
with a presence verdict. The surface below is the one the code reads.

#### `http:horizon-client-bundle` — horizon-portal → horizon-playwright-client

- **Unauthenticated read.** `client_bundles()` sends `GET <HORIZON_URL>index.html` through
  Playwright's request API: no page opens and no credential is sent. A status other than
  200, or no answer within 30 s, is `PORTAL_UNREACHABLE`. The answer's
  `<script src="….js">` tags are reduced to their file names, and a page that names none
  is `UNEXPECTED`. The probe calls `client_bundles()` through the `HorizonClient` port,
  reports the names as its `portal` check and never reads a portal version. The contract
  therefore sits on the adapter only, as the calendar's does.
- **The markup the adapter's selectors were taken from.** HTML Access 2312.1, bundle
  `app-htmlaccess.4eb7424a56fc03317f06.js`. A new client version can rename any of these,
  and the probe's bundle names are where that shows first.

| What | Route or selector |
|------|-------------------|
| login page | `#/home`, with the fields `#username` and `#password` and the button `#loginButton` |
| desktop tiles | `#/launchitems`. A tile is `li:has(> button[id^='launch-'])`, its title on the launch button |
| tile menu | `button.overflow-button[aria-haspopup]` opens `.content-menu .context-menu-container` |
| log off item | `#menu-item-logoff-btn`, hidden (the `hidden` attribute) when the desktop holds no session |
| dialogs | `#okDialogBtn`, `#cancelDialogBtn` |
| desktop | `#/desktop`. The remote surface is a `canvas` or `video` inside `#canvas-container` |

#### `http:horizon-broker-session` — horizon-portal → horizon-playwright-client

The web client talks to the broker. The adapter drives the client and reads the pages,
never a broker document's content.

- **Login.** On `#/home` the adapter types the account into `#username` and `#password`
  and clicks `#loginButton`. The broker accepted the login once the client shows
  `#/launchitems`, and refused it once the error dialog's `#okDialogBtn` is visible
  (`LOGIN_REJECTED`). Neither within 30 s is `UNEXPECTED`.
- **Launch items.** The list of desktops the broker grants the account, one tile per
  desktop. A tile titled with `HORIZON_DESKTOP` that is absent is `DESKTOP_NOT_FOUND`. The
  tile's session state is read from the log off item's `hidden` attribute, on a list
  loaded afresh, because a tile already rendered in the page can retain its last fetched
  state. A desktop whose menu hides the item before sign-out starts is
  `ALREADY_LOGGED_OFF`.
- **Sign-out confirmation.** After the Windows sign-out input, every confirmation read
  reloads `#/launchitems` and reads the tile from the newly fetched list. A tile without
  a session within 60 s confirms the check-out. Otherwise the adapter fails closed as
  `LOGOFF_NOT_CONFIRMED`.

#### `blast:desktop-session` — horizon-portal → horizon-playwright-client

- **Opening.** A click on the tile's launch button opens `#/desktop`. The client offers
  Fullscreen in a dialog, which the adapter cancels (Cancel, never OK). The desktop counts
  as open once a canvas inside `#canvas-container` has a non-zero size, within 90 s, and
  otherwise the result is `DESKTOP_DID_NOT_OPEN`.
- **The WebSocket.** The Blast session is a WebSocket on a path that starts with `/r/` or
  `/d/`. The adapter records it and logs whether one was seen. It is not a verdict.
- **The hold and the disconnect.** The check-in holds the open desktop for
  `HT_HOLD_SECONDS` (120 s by default) so Windows completes its logon, then closes the
  browser context. Closing it closes the WebSocket: that is the quiet disconnect, and the
  Windows session lives on until the evening's sign-out.
- **Windows sign-out.** The evening opens the desktop and guards every action with
  painted/dialog-free readiness and restored surface focus. It right-clicks Start at
  remote `(20,700)` and left-clicks Run at `(85,600)`, scaling both owner-desktop points
  into the surface bounds, waits 2 s, replaces the field through Ctrl+A and paced
  `shutdown /l` typing, captures checkout evidence, then presses Enter once.
  This asks Windows to end its own session. The adapter sends no Meta+R or tile-menu
  `kill-session` request; the broker's fresh launch-items list remains the confirmation
  authority.

## Invariants

- No contract here is exercised from CI or from an agent's sandbox with a login. Tests run
  the adapter against a static copy of the 2312.1 markup (`tests/fixtures/htmlaccess/`,
  served on localhost). Only the host's timers and `horizon probe` reach the live portal.
- The password is typed into `#password` and goes nowhere else: no screenshot is taken on
  the login page, and no log line carries a value.
- Two readings are inferred from the bundle and not measured on a logged-in portal: the
  "desktop is open" signal and the tile's session state (see the
  `horizon-playwright-client` SPEC).

## Dependencies

Declared in `.beadloom/_graph/landscape.yml` as contract edges, not derived from
imports: an external system has no code here.

- Produces: `http:horizon-client-bundle`, `http:horizon-broker-session` and
  `blast:desktop-session` for `horizon-playwright-client`
- Consumes: (none)

## Parent

None: an external system, not part of `horizon-tracker`. The consumer is
`horizon-playwright-client`.
