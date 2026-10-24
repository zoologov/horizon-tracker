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
to the desktop with Windows logged on, and a check-out is the broker ending that Windows
session. The service reaches the portal only through the Playwright adapter
(`horizon-playwright-client`), headless Chrome walking the same pages a person walks. The
probe reads the client bundle without logging in, and it does so through the same adapter,
called through the `HorizonClient` port.

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

The web client talks to the broker. The adapter drives the client and reads the pages and
one broker request, never a broker document's content.

- **Login.** On `#/home` the adapter types the account into `#username` and `#password`
  and clicks `#loginButton`. The broker accepted the login once the client shows
  `#/launchitems`, and refused it once the error dialog's `#okDialogBtn` is visible
  (`LOGIN_REJECTED`). Neither within 30 s is `UNEXPECTED`.
- **Launch items.** The list of desktops the broker grants the account, one tile per
  desktop. A tile titled with `HORIZON_DESKTOP` that is absent is `DESKTOP_NOT_FOUND`. The
  tile's session state is read from the log off item's `hidden` attribute, on a list
  loaded afresh, because the client clears that flag on OK before the broker has answered.
  A desktop whose menu hides the item before the log off starts is `ALREADY_LOGGED_OFF`.
- **`kill-session`.** A log off is the client's `POST` of one XML document to a path that
  contains `/broker/xml`, with `<kill-session` in its body. The adapter arms a wait for
  the answer before it clicks OK, bounded at 30 s, and logs
  `Horizon kill-session answered: <status> after <ms> ms` whatever the status is. The
  status decides nothing: the check-out is confirmed only when a freshly loaded
  `#/launchitems` shows the tile without a session within 60 s, and otherwise fails
  closed as `LOGOFF_NOT_CONFIRMED`.

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
  Windows session lives on until the evening's log off.

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
