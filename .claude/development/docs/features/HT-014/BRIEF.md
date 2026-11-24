# BRIEF: HT-014 — Sign out of Windows during evening check-out

> **Type:** bug
> **Status:** Approved
> **Created:** 2026-11-22

---

## Problem

The evening check-out currently chooses **Log Off** from the Horizon desktop tile's menu. That sends the broker's
`kill-session` command without opening the Windows desktop. Although the broker can subsequently report that the
desktop has no session, the owner's attendance record does not observe the Windows logoff. The evening run therefore
needs to perform the same real Windows sign-out as the owner's manual **Start → account → Sign out** path.

## Solution

Keep the `HorizonClient.log_off(name)` contract and the `EveningCheckout` use case unchanged. Inside the Playwright
adapter, open the named desktop over Blast and wait until the remote desktop is drawn and ready for input. Right-click
Start at remote `(20,700)`, left-click Run at `(85,600)` on the owner's 1280×720 desktop, scaling both points into the
current surface bounds, then use **Ctrl+A**, type `shutdown /l` with pacing, capture the field, and press **Enter**
once. Cancel any HTML Access dialog and restore painted readiness and surface focus at every action boundary. Then read
freshly fetched launch items until the broker reports `NO_SESSION`, preserving the existing confirmation, failure and
screenshot semantics. This live-proven Win+X path replaces both Meta+R and the broker's tile-menu `kill-session` path.

The work is sequential: dev changes the adapter, test extends its local HTML Access fixture and adapter checks,
review verifies the result, and tech-writer refreshes the affected documentation. No live portal login is permitted
from the development sandbox; a live `checkout --force` and an attendance-record check remain a VPS verification
step after deployment.

## Axes

Derived, never authored. Run `beadloom impact <path|symbol>`, paste its answer into the table, then take the scope
decision in the last two columns — the derivation says what a change ranges over, a person says how much of it this
work item takes. The `refs:` of every bead below is generated from the rows kept in scope, so a bead naming a node
this table does not is a finding.

Rule each row by the node's role in the change — the axis a node surfaced under is not its role. The axis is the
node's relation to the seed, so a `callers` row can be a work site — a node that calls into the change can also own
what the change must edit. `Owns unread` names the files the node owns that the derivation could not read, because
`beadloom impact` reads Python and a template is not; a count there is a question to answer before the `no`, not a
detail.

> **Derived by:** `beadloom impact src/horizon_tracker/infrastructure/horizon_playwright.py` over `src/horizon_tracker`
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 10 name-defined-more-than-once, 1 no-seed, 16 unresolved-terminator-name

| Axis | Node | Sites | Owns unread | In scope | Why |
|---|---|---|---|---|---|
| co-writers | — | unresolved — no declared effect rule found a sink this target reaches, so there is no commit point to ask who else writes through | — | no | No co-writer was derived; the adapter-only change creates no shared commit point. |
| callers | evening-checkout | 1 — `src/horizon_tracker/application/checkout.py:65` | none | no | The use case already calls `log_off` and confirms the resulting state; its contract and ordering stay unchanged. |
| callers | morning-checkin | 1 — `src/horizon_tracker/application/checkin.py:57` | none | no | The morning open/hold/disconnect behaviour is unaffected. |
| callers | ports | 2 — `src/horizon_tracker/domain/ports.py:29` | none | no | `HorizonClient.log_off(name)` keeps its signature and result contract. |
| callers | probe | 2 — `src/horizon_tracker/application/probe.py:119` | none | no | Unauthenticated probes and dry-run orchestration need no structural change. |
| callers | schedule | 1 — `src/horizon_tracker/domain/schedule.py:48` | none | no | Run timing and retry decisions are unaffected. |
| callers | settings | 1 — `src/horizon_tracker/infrastructure/config.py:95` | none | no | The existing adapter timeouts and settings are sufficient; no setting is added. |
| branches | horizon-playwright-client | `_log_screenshot_failure`: 1 branch(es), 0 exit form(s), over every call | none | yes | The change is confined to this adapter; its branch rows describe the single implementation and test work site, not separate nodes. |
| branches | horizon-playwright-client | `_remaining_ms`: 1 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; only the methods needed by the Windows sign-out path will change. |
| branches | horizon-playwright-client | `_largest_surface`: 3 branch(es), 3 exit form(s), over every call | none | yes | Same adapter work site; desktop readiness may reuse its surface handling. |
| branches | horizon-playwright-client | `_frame_is_painted`: 2 branch(es), 2 exit form(s), over every call | none | yes | Same adapter work site; desktop readiness may reuse its painted-frame check. |
| branches | horizon-playwright-client | `_close_quietly`: 1 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; no separate component is introduced. |
| branches | horizon-playwright-client | `_answers_kill_session`: 1 branch(es), 2 exit form(s), over every call | none | yes | Same adapter work site; the old kill-session response helper may become obsolete. |
| branches | horizon-playwright-client | `_offered`: 1 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; tile-menu logoff helpers may become obsolete. |
| branches | horizon-playwright-client | `_css_string`: 1 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; existing tile lookup remains available. |
| branches | horizon-playwright-client | `_route`: 1 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; screenshot safety remains unchanged. |
| branches | horizon-playwright-client | `__init__`: 1 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; existing configuration is retained unless implementation requires otherwise. |
| branches | horizon-playwright-client | `__repr__`: 0 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; credential-safe representation remains unchanged. |
| branches | horizon-playwright-client | `__enter__`: 0 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; lifecycle behaviour remains unchanged. |
| branches | horizon-playwright-client | `__exit__`: 0 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; lifecycle behaviour remains unchanged. |
| branches | horizon-playwright-client | `login`: 3 branch(es), 2 exit form(s), over every call | none | yes | Same adapter work site; authentication remains a prerequisite, not a new responsibility. |
| branches | horizon-playwright-client | `desktop_status`: 2 branch(es), 2 exit form(s), over every call | none | yes | Same adapter work site; existing session-state semantics are preserved. |
| branches | horizon-playwright-client | `open_desktop`: 2 branch(es), 1 exit form(s), over every call | none | yes | The evening path must reuse opening the desktop over Blast before sending Windows input. |
| branches | horizon-playwright-client | `capture_open_desktop`: 1 branch(es), 2 exit form(s), over every call | none | yes | Same adapter work site; its readiness logic may inform the input wait without changing its public contract. |
| branches | horizon-playwright-client | `_nonblank_frame`: 1 branch(es), 4 exit form(s), over every call | none | yes | Same adapter work site; a painted desktop is part of safe keyboard input. |
| branches | horizon-playwright-client | `_pause_between_samples`: 1 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; polling helpers remain shared. |
| branches | horizon-playwright-client | `_dialog_in_the_way`: 2 branch(es), 2 exit form(s), over every call | none | yes | Same adapter work site; client dialogs must not receive the Windows input. |
| branches | horizon-playwright-client | `disconnect`: 1 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; morning disconnect semantics remain unchanged. |
| branches | horizon-playwright-client | `log_off`: 3 branch(es), 3 exit form(s), over every call | none | yes | This is the primary replacement site: desktop input followed by broker confirmation. |
| branches | horizon-playwright-client | `client_bundles`: 3 branch(es), 2 exit form(s), over every call | none | yes | Same adapter work site; unauthenticated bundle probing remains unchanged. |
| branches | horizon-playwright-client | `browser_version`: 1 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; browser probing remains unchanged. |
| branches | horizon-playwright-client | `close`: 4 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; cleanup remains best-effort. |
| branches | horizon-playwright-client | `_desktop_is_open`: 1 branch(es), 2 exit form(s), over every call | none | yes | The sign-out path must recognise the live desktop and its loss after Windows logoff. |
| branches | horizon-playwright-client | `_blast_socket_open`: 1 branch(es), 1 exit form(s), over every call | none | yes | The sign-out path needs the existing Blast connection diagnostics. |
| branches | horizon-playwright-client | `_tile_session_state`: 1 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; existing tile-state behaviour remains unchanged. |
| branches | horizon-playwright-client | `_broker_session_state`: 1 branch(es), 1 exit form(s), over every call | none | yes | Fresh broker reads remain the confirmation mechanism after the Windows command. |
| branches | horizon-playwright-client | `_login_verdict`: 1 branch(es), 3 exit form(s), over every call | none | yes | Same adapter work site; login verdicts remain unchanged. |
| branches | horizon-playwright-client | `_settle_desktop`: 2 branch(es), 1 exit form(s), over every call | none | yes | Desktop readiness before keyboard input is part of the fix. |
| branches | horizon-playwright-client | `_confirm_logoff_dialog`: 1 branch(es), 2 exit form(s), over every call | none | yes | Same adapter work site; the tile-menu confirmation helper may become obsolete. |
| branches | horizon-playwright-client | `_tile`: 2 branch(es), 2 exit form(s), over every call | none | yes | The adapter still launches the named desktop through its tile. |
| branches | horizon-playwright-client | `_launch_items_page`: 3 branch(es), 1 exit form(s), over every call | none | yes | Fresh launch-item reads remain part of confirmation. |
| branches | horizon-playwright-client | `_reload_launch_items`: 2 branch(es), 0 exit form(s), over every call | none | yes | Confirmation must continue to bypass the stale in-page tile state. |
| branches | horizon-playwright-client | `_open_tile_menu`: 1 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; the logoff menu path is replaced while state reads may retain menu handling. |
| branches | horizon-playwright-client | `_close_tile_menu`: 1 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; retained state-read helpers must remain coherent. |
| branches | horizon-playwright-client | `_driver`: 1 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; lazy driver startup remains unchanged. |
| branches | horizon-playwright-client | `_launch`: 1 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; Chrome startup remains unchanged. |
| branches | horizon-playwright-client | `_new_page`: 2 branch(es), 2 exit form(s), over every call | none | yes | Same adapter work site; the page and WebSocket lifecycle remain shared. |
| branches | horizon-playwright-client | `_release_context`: 0 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; context ownership remains unchanged. |
| branches | horizon-playwright-client | `_record_websocket`: 1 branch(es), 0 exit form(s), over every call | none | yes | Same adapter work site; Blast diagnostics remain shared. |
| branches | horizon-playwright-client | `_live_page`: 2 branch(es), 2 exit form(s), over every call | none | yes | Keyboard input must go to the current live desktop page. |
| branches | horizon-playwright-client | `_url`: 0 branch(es), 1 exit form(s), over every call | none | yes | Same adapter work site; route construction remains unchanged. |
| branches | horizon-playwright-client | `_poll`: 1 branch(es), 0 exit form(s), over every call | none | yes | The existing bounded poll remains the confirmation mechanism. |
| branches | horizon-playwright-client | `_step`: 1 branch(es), 1 exit form(s), over every call | none | yes | Failures must retain the established reason and safe-screenshot wrapping. |
| branches | horizon-playwright-client | `_failure`: 1 branch(es), 1 exit form(s), over every call | none | yes | Failure reporting remains within the adapter's existing contract. |
| branches | horizon-playwright-client | `_screenshot`: 1 branch(es), 2 exit form(s), over every call | none | yes | The existing post-logout screenshot behaviour is preserved. |
| branches | morning-checkin | `_attempt`: 2 branch(es), 2 exit form(s), over every call, from a caller's seat | none | no | Morning behaviour and its attempt logic do not change. |
| branches | evening-checkout | `__call__`: 4 branch(es), 3 exit form(s), over every call, from a caller's seat | none | no | The use case already supplies the required call and confirmation sequence. |
| branches | probe | `_portal`: 1 branch(es), 2 exit form(s), over every call, from a caller's seat | none | no | Portal probing is unaffected. |
| branches | probe | `_chrome`: 1 branch(es), 3 exit form(s), over every call, from a caller's seat | none | no | Chrome probing is unaffected. |
| branches | ports | `__init__`: 1 branch(es), 0 exit form(s), over every call, from a caller's seat | none | no | No port implementation or value object changes. |
| branches | ports | `__init__`: 1 branch(es), 0 exit form(s), over every call, from a caller's seat | none | no | No port implementation or value object changes. |
| branches | schedule | `__init__`: 1 branch(es), 0 exit form(s), over every call, from a caller's seat | none | no | Scheduling is unaffected. |
| branches | settings | `__init__`: 1 branch(es), 0 exit form(s), over every call, from a caller's seat | none | no | No configuration surface changes. |

## Beads

Status lives in ACTIVE.md, reconciled from the tracker by the pre-commit active-sync, so this table names the beads
and carries no status. The Tracker cell holds `-` until the beads are created, and then the id the tracker answered.

| ID | Tracker | Name | Priority |
|----|---------|------|----------|
| BEAD-01 | ht-oe6 | Implement Windows keyboard sign-out in the Playwright adapter | P1 |
| BEAD-02 | ht-0tu | Verify desktop input, confirmation and failure paths | P1 |
| BEAD-03 | ht-pea | Review the adapter-only logout fix | P1 |
| BEAD-04 | ht-ga0 | Refresh the logout documentation | P1 |

## Acceptance Criteria

- [ ] Scenario: `Windows Win+X sign-out is confirmed by a fresh broker list`
- [ ] Scenario: `Evening check-out on an already logged-off desktop reports it and stops`
