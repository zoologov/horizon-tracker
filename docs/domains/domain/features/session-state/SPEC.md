# Session state

Horizon session states and the two rules for a completed check-in
(CONNECTED -> DISCONNECTED) and check-out (a session -> NO_SESSION).

## Source

`src/horizon_tracker/domain/session.py`

## Specification

### Purpose

The accounting system observes the Windows logon and logoff on the VM, not the web
portal. A check-in or a check-out therefore counts only by the state of the Windows
session behind the desktop. This module names those states and states both success
rules in them and nothing else.

### How it works

A desktop is in one of three states, as the broker sees it:

| State | Meaning |
|-------|---------|
| `NO_SESSION` | Windows has no logged-on session on the VM |
| `CONNECTED` | a session exists and a client holds an open Blast connection to it |
| `DISCONNECTED` | a session exists and no client is attached; it keeps running |

- `checkin_succeeded(while_open, after_disconnect)` is true only for the transition
  `CONNECTED` -> `DISCONNECTED`: the desktop was open over Blast, so Windows completed
  the logon, and then the client let go without logging off.
- `checkout_succeeded(before, after)` is true only when a session existed before the
  run and `NO_SESSION` holds after it. A desktop that had no session before the run was
  not logged off by it, so that case is not a success: the check-out use case reports it
  as "already logged off".

## Invariants

- `SessionState.has_session` is true for `CONNECTED` and `DISCONNECTED`, false for
  `NO_SESSION`.
- A disconnect is never a log off: the check-in rule requires `DISCONNECTED`, not
  `NO_SESSION`, after the client lets go.
- The rules read session states only; they know nothing of the portal's pages.

## API

Module `src/horizon_tracker/domain/session.py`:

- `SessionState` — `StrEnum`: `NO_SESSION`, `CONNECTED`, `DISCONNECTED`; property
  `has_session -> bool`.
- `DesktopStatus(name: str, state: SessionState)` — frozen; one desktop tile as the
  portal reports it.
- `checkin_succeeded(while_open: SessionState, after_disconnect: SessionState) -> bool`.
- `checkout_succeeded(before: SessionState, after: SessionState) -> bool`.

## Testing

Tests: `tests/unit/domain/test_session.py`. The module is inside the mutation gate.

Scenarios:

- `tests/acceptance/features/morning_checkin.feature`:
  - `Morning check-in opens the desktop and disconnects`
- `tests/acceptance/features/evening_checkout.feature`:
  - `Evening check-out logs the desktop off`
  - `Evening check-out on an already logged-off desktop reports it and stops`

## Dependencies

Derived from the imports on reindex.

- Depends on: (none)
- Used by: `evening-checkout`, `horizon-playwright-client`, `morning-checkin`, `ports`

## Parent

`domain` — [domain README](../../README.md)
