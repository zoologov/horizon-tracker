# Morning check-in

Opens the desktop over Blast, holds it until Windows logs on, disconnects without
logging off and confirms the session runs on.

## Source

`src/horizon_tracker/application/checkin.py`

## Specification

### Purpose

At the day's drawn check-in moment (inside `HT_CHECKIN_RANGE`, default 07:30-08:10) the
accounting system must see a Windows logon on the VM. A portal login is not enough: the desktop has to be opened over Blast and drawn. Then
the client lets go and leaves the Windows session running until the evening check-out.

### How it works

`MorningCheckin.run(force=...)` hands one attempt to `WindowedRun.run(RunKind.CHECKIN,
...)`. The run loop waits for the drawn moment and decides each attempt (see the
[windowed run](../windowed-run/SPEC.md)). One attempt:

1. `client.login()`;
2. `client.open_desktop(desktop)`, which returns `None` and takes no success
   photograph. The time is read from `Clock.now()` right after the call returns and
   kept as `opened_at`;
3. `clock.sleep(hold)`, so the Windows logon completes, then
   `client.capture_open_desktop()` while the desktop is still open, then reads the
   session state;
4. `client.disconnect()`, called in a `finally` block, so the client lets go even when
   the hold, the capture or the read fails;
5. `client.login()` again, because the disconnect closed the client, and reads the
   state the disconnect left.

`open_desktop` returns once Blast is connected and the desktop is drawn. It does not
photograph the desktop. `success_settle_ms` is gone. `opened_at` is that return, before
the hold. The photograph is `capture_open_desktop`, taken after the hold and before
`disconnect`. The frame rules are in the
[Horizon Playwright client](../../../infrastructure/features/horizon-playwright-client/SPEC.md).

The attempt succeeds when `checkin_succeeded(while_open, after_disconnect)` holds, that
is the transition `CONNECTED` -> `DISCONNECTED`. The report then carries `opened_at`
and, as `screenshot`, the path `capture_open_desktop` returned, so the notifier sends
the opened desktop as a photo with the text as its caption. With `None` the report goes
out as text. Any other pair of states is `FAILED` with
`Reason.DESKTOP_DID_NOT_OPEN` and no screenshot. The capture path is attached only when
the attempt succeeds. A `HorizonClientError` from any step is turned into a failed
attempt by the run loop and retried while the window allows.

`steps()` lists the five steps as `Message`s (keys `plan.step.login` and
`plan.step.checkin.*`); `horizon checkin --dry-run` prints them in the configured
language, followed by the loop's steps.

## Invariants

- The check-in never logs off; it only disconnects.
- The disconnect happens whenever the desktop was opened, even if the hold, the capture
  or the state read failed.
- Success is decided by the domain rule on session states, never by the portal login.
- A successful report carries `opened_at`, the time `open_desktop` returned, before the
  hold and before the photograph.
- Only a successful report carries the capture path. A failed attempt reports the
  screenshot of its `HorizonClientError`, if any. An unconfirmed attempt does not
  carry the capture path. A forced run behaves the same.

## API

Module `src/horizon_tracker/application/checkin.py`:

- `MorningCheckin(client: HorizonClient, clock: Clock, runner: WindowedRun, desktop:
  str, hold: timedelta)` — frozen:
  - `kind -> RunKind` — property, `RunKind.CHECKIN`;
  - `run(*, force: bool = False) -> RunReport`;
  - `steps() -> tuple[Message, ...]`.

The CLI builds it with `HORIZON_DESKTOP` and `HT_HOLD_SECONDS` (120 by default).

## Testing

Tests: `tests/unit/application/test_checkin.py`, `tests/unit/test_cli.py`.

Scenarios (`tests/acceptance/features/morning_checkin.feature`):

- `Morning check-in opens the desktop and disconnects`
- `Morning check-in reports success with the recorded time`

Scenarios (`tests/acceptance/features/screenshot_preview.feature`):

- `A successful check-in sends a screenshot of the opened desktop`
- `A successful check-in's screenshot is taken after the desktop was held`
- `A check-in whose screenshot failed still reports success as text`
- `A check-in the broker did not confirm sends no photo of the opened desktop`

These scenarios record `opened_at` at the return of `open_desktop`, before the hold.
The photograph is the later `capture_open_desktop`.

The retry and calendar scenarios in `window_and_retries.feature` and
`production_calendar.feature`, and the drawn-moment scenarios in
`randomised_moments.feature`, run the check-in as well.

## Dependencies

Derived from the imports on reindex.

- Depends on: `messages`, `ports`, `run-report`, `schedule`, `session-state`, `windowed-run`
- Used by: `cli` (through the `application` package)

## Parent

`application` — [application README](../../README.md)
