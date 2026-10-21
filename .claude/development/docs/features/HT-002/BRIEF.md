# BRIEF: HT-002 — HTML Access 2312.1 selectors: tile, canvas, the Log Off item

> **Type:** bug
> **Status:** Done
> **Created:** 2026-10-20

---

## Problem

The first live `horizon checkin --force` on the VPS (2026-10-20, report of the local agent): the login
succeeds ("Horizon login accepted"), then all three attempts fail exactly 30 s later on
`page.locator("li[title]").first.wait_for(...)` in `_tile()`. The three screenshots of `#/launchitems`
are byte-for-byte identical, the tiles "Base desktop" and "DEV desktop" are in place, no dialogs.
No Windows session was created.

A breakdown of the HTML Access 2312.1 bundle (client 8.12.1, the same version as in the HT-001 RFC) showed
three discrepancies between the adapter and the real markup:

1. **The tile.** The `li` carries no `title`; it is on the button inside:
   `<li id="{item.id}" tabindex="-1"><button id="launch-{item.id}" title="{name}" class="ui-btn ui-btn-a ui-desktop-corner">… <button class="overflow-button app-item-action" aria-haspopup="true">…</button> …</button><p class="ui-desktop-name" title="{name}">{name}</p></li>`
   (the "…" button is nested inside the launch button, not placed beside it — refined by review ht-75w).
   So `ANY_TILE = "li[title]"` and `li[title="DEV desktop"]` match nothing.
   `LAUNCH_BUTTON = "[id^='launch-']"` is correct; `TILE_MENU_BUTTON` will work through
   `button[aria-haspopup]`.
2. **The desktop canvas.** `#canvas-container #canvas` does not exist. In `app-root`, side by side, lie
   `<canvas id="canvas" width=320 height=240 style="display:none">` (auxiliary, a sibling, not a
   descendant) and `<div id="canvas-container" class="web-container">`. The Blast canvas is created
   dynamically: `createPrimaryCanvas` makes `<canvas id="primary-monitor">` and appends it to
   `#canvas-container`. So `_desktop_is_open()` is always False: after the fix of item 1
   `open_desktop` would fail after 90 s with `desktop_did_not_open`.
3. **Session state.** `#menu-item-logoff-btn` is an `li` with `[hidden]="!showLogOffDesktop"`;
   it gets hidden rather than becoming `disabled`. Consequences: `_tile_session_state` through
   `is_enabled()` always answers DISCONNECTED even without a session; `_open_tile_menu` waits with
   `wait_for(state="visible")` on the logoff item and without a session gets a 15 s timeout and
   `UNEXPECTED`/`LOGOFF_NOT_CONFIRMED` instead of `ALREADY_LOGGED_OFF`.

Matched the bundle: `#username`, `#password`, `#loginButton`, `#okDialogBtn`,
`#cancelDialogBtn`, `#sidebar-toggler`, the routes `#/launchitems` and `#/desktop`.

The fixture `tests/fixtures/htmlaccess/` reproduced the wrong markup, so 21
adapter tests were green on a false contract: a test on a fake proved the fake's contract
(the project layer of CLAUDE.md, the rule about fakes).

## Solution

In `src/horizon_tracker/infrastructure/horizon_playwright.py`:

- `ANY_TILE = "li:has(button[id^='launch-'])"`, the tile by name —
  `li:has(button[id^='launch-'][title="<name>"])`; the launch click goes to `button[id^='launch-']`
  inside the tile.
- `DESKTOP_CANVAS = "#canvas-container canvas"` (the dynamic `#primary-monitor`);
  `_desktop_is_open()` waits for the canvas to appear in the container and to have a non-zero size.
  The WebSocket check on `/r/`, `/d/` remains a hypothesis: it cannot be verified without a login,
  so it does not block the "desktop is open" verdict and is only logged.
- The tile menu: wait for the visibility of the menu container itself (the share-contextmenu component,
  `.content-menu`), and read the session state through `is_visible()` / the `hidden` attribute
  of the `#menu-item-logoff-btn` item: visible → there is a session, hidden → `NO_SESSION`.
- The fixture `tests/fixtures/htmlaccess/` is rewritten to the real markup from the bundle
  (the `li`/`button` structure, the dynamic `primary-monitor`, `[hidden]` on the menu item);
  the bundle `app-htmlaccess.4eb7424a56fc03317f06.js` is in the cloud session's scratchpad and with
  the local agent for cross-checking. The adapter tests gain the case "desktop without a session →
  ALREADY_LOGGED_OFF".

The live check after the roll-out — by the local agent from the VPS: `checkin --force`,
a check in an external Horizon client that the session exists and is disconnected, `checkout --force`, a check that
there is no session; only after that are the timers enabled (BEAD-13 HT-001).

## Axes

Derived, never authored. Run `beadloom impact <path|symbol>`, paste its answer into the table,
then take the scope decision in the last two columns — the derivation says what a change ranges
over, a person says how much of it this work item takes. The `refs:` of every bead below is
generated from the rows kept in scope, so a bead naming a node this table does not is a finding.

Rule each row by the node's role in the change: the axis a node surfaced under is not its role.
The axis is the node's relation to the seed, so a `callers` row can be a work site — a node that
calls into the change can also own what the change must edit. `Owns unread` names the files the
node owns that the derivation could not read; a count there is a question to answer before `no`.

> **Derived by:** `beadloom impact src/horizon_tracker/infrastructure/horizon_playwright.py --section` over `src/horizon_tracker`, 2026-10-20, role explore
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 9 name-defined-more-than-once, 1 no-seed, 14 unresolved-terminator-name (run of 2026-10-20); the fixture `tests/fixtures/htmlaccess/` lies outside the `src/` root and the derivation does not read it — it is fixed together with the node `horizon-playwright-client`, which owns its contract

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — no declared effect rule found a sink this target reaches, so there is no commit point to ask who else writes through | — | no | no row: no seed found, no node named |
| callers | evening-checkout | 1 — `src/horizon_tracker/application/checkout.py:62` | none | no | calls `log_off`/`desktop_status`; the port contract does not change, the fix is inside the adapter |
| callers | morning-checkin | 1 — `src/horizon_tracker/application/checkin.py:51` | none | no | calls `open_desktop`; the contract does not change |
| callers | ports | 1 — `src/horizon_tracker/domain/ports.py:26` | none | no | the site is the `__init__` of the exception, not resolved by the derivation; the Protocol does not change |
| callers | probe | 1 — `src/horizon_tracker/application/probe.py:84` | none | no | calls `client_bundles`/`browser_version`; they are correct, left untouched |
| callers | settings | 1 — `src/horizon_tracker/infrastructure/config.py:38` | none | no | the site is the `__init__` of the exception; the fix adds no settings |
| branches | horizon-playwright-client | `_close_quietly`: 1 branch(es), 0 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_route`: 1 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `__init__`: 1 branch(es), 0 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `__repr__`: 0 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `__enter__`: 0 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `__exit__`: 1 branch(es), 0 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `login`: 3 branch(es), 2 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `desktop_status`: 2 branch(es), 2 exit form(s), over every call | none | yes | a branch in the node under fix: selectors and waits for the menu/canvas |
| branches | horizon-playwright-client | `open_desktop`: 2 branch(es), 1 exit form(s), over every call | none | yes | a branch in the node under fix: selectors and waits for the menu/canvas |
| branches | horizon-playwright-client | `disconnect`: 1 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `log_off`: 3 branch(es), 2 exit form(s), over every call | none | yes | a branch in the node under fix: selectors and waits for the menu/canvas |
| branches | horizon-playwright-client | `client_bundles`: 3 branch(es), 3 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `browser_version`: 1 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `close`: 4 branch(es), 0 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_desktop_is_open`: 1 branch(es), 2 exit form(s), over every call | none | yes | a branch in the node under fix: selectors and waits for the menu/canvas |
| branches | horizon-playwright-client | `_tile_session_state`: 1 branch(es), 1 exit form(s), over every call | none | yes | a branch in the node under fix: selectors and waits for the menu/canvas |
| branches | horizon-playwright-client | `_login_verdict`: 1 branch(es), 3 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_settle_desktop`: 2 branch(es), 1 exit form(s), over every call | none | yes | a branch in the node under fix: selectors and waits for the menu/canvas |
| branches | horizon-playwright-client | `_tile`: 2 branch(es), 2 exit form(s), over every call | none | yes | a branch in the node under fix: selectors and waits for the menu/canvas |
| branches | horizon-playwright-client | `_launch_items_page`: 3 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_open_tile_menu`: 1 branch(es), 1 exit form(s), over every call | none | yes | a branch in the node under fix: selectors and waits for the menu/canvas |
| branches | horizon-playwright-client | `_close_tile_menu`: 1 branch(es), 0 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_driver`: 1 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_launch`: 1 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_new_page`: 2 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_release_context`: 0 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_record_websocket`: 1 branch(es), 0 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_live_page`: 2 branch(es), 2 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_url`: 0 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_poll`: 1 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_step`: 1 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_failure`: 1 branch(es), 1 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | horizon-playwright-client | `_screenshot`: 1 branch(es), 2 exit form(s), over every call | none | yes | the same node; the code does not change, but the node's tests run in full |
| branches | morning-checkin | `_attempt`: 2 branch(es), 2 exit form(s), over every call, from a caller's seat | none | no | the call site, the port contract does not change |
| branches | evening-checkout | `__call__`: 4 branch(es), 3 exit form(s), over every call, from a caller's seat | none | no | the call site, the port contract does not change |
| branches | probe | `_portal`: 1 branch(es), 2 exit form(s), over every call, from a caller's seat | none | no | the call site, the port contract does not change |
| branches | probe | `_chrome`: 2 branch(es), 3 exit form(s), over every call, from a caller's seat | none | no | the call site, the port contract does not change |
| branches | ports | `__init__`: 1 branch(es), 0 exit form(s), over every call, from a caller's seat | none | no | the call site, the port contract does not change |
| branches | settings | `__init__`: 1 branch(es), 0 exit form(s), over every call, from a caller's seat | none | no | the call site, the port contract does not change |

## Beads

**Parent bead:** ht-tvn

Status lives in ACTIVE.md, reconciled from the tracker by the pre-commit active-sync, so this
table names the beads and carries no status. The Tracker cell holds `-` until the beads are
created, and then the id the tracker answered.

| ID | Tracker | Name | Priority |
|----|---------|------|----------|
| BEAD-01 | ht-m7u | Adapter: tile, canvas and menu selectors from the 2312.1 bundle; fixture and tests | P0 |
| BEAD-02 | ht-75w | Review: the adapter against the bundle, whether the new tests bite | P0 |
| BEAD-03 | ht-28a | Live check from the VPS: checkin --force, session disconnected, checkout --force (the local agent) | P0 |
| BEAD-04 | ht-tvn.1 | Fix after review: Log Off confirmation by the broker's state; the fixture models the optimistic flag | P0 |
| BEAD-05 | ht-tvn.2 | Re-review | P0 |
| BEAD-06 | ht-tvn.3 | Fix: wait for the broker's answer to kill-session before reloading the list | P0 |
| BEAD-07 | ht-tvn.4 | Narrow re-review of BEAD-06 | P0 |
| BEAD-08 | ht-tvn.5 | Fix: the kill-session predicate by path, a log of the answer's status and duration | P0 |

## Acceptance Criteria

- [ ] Scenario: `Morning check-in opens the desktop and disconnects`
- [ ] Scenario: `Evening check-out logs the desktop off`
- [ ] Scenario: `Evening check-out on an already logged-off desktop reports it and stops`
- [ ] Live `checkin --force` from the VPS: exit 0, in an external Horizon client "DEV desktop" has a disconnected session — non-behavioural: the observer is outside our system
- [ ] Live `checkout --force`: exit 0, no session — non-behavioural: the observer is outside our system
- [ ] Live measurements (review ht-75w item c, ht-tvn.2 minor 2): reloading the list keeps the web session; the `kill-session` request goes out and gets its answer before the reload (per the log); in an external Horizon client there is no session after the check-out and a disconnected one after the check-in — non-behavioural: the observer is outside our system
