# Application

Use cases of horizon-tracker. A use case orders domain decisions and port calls;
it owns no transport and no browser detail.

## Source

`src/horizon_tracker/application/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `checkin.py` | the morning check-in: open the desktop until Windows logs on, hold it, then disconnect (`MorningCheckin(client, clock, runner, desktop, hold)` with `kind`, `run(force=...)` and `steps()`) |
| `checkout.py` | the evening check-out: log the desktop's Windows session off and confirm it ended; a desktop with no session is reported as already logged off (`EveningCheckout(client, clock, runner, desktop)` with `kind`, `run(force=...)` and `steps()`) |
| `windowed_run.py` | drives one daily run through its window: decides each attempt with the domain, retries failures, sends exactly one report (`WindowedRun`, one per window, with `run()`, `first_decision()` and `steps()`); an early start is reported as `Reason.TOO_EARLY`, a late one as `WINDOW_MISSED` |
| `probe.py` | checks whether the service could run without ever logging in: `Probe` (portal client bundles via `client_bundles()`, the calendar, Chrome found and started via `browser_version()`; an unreachable calendar is DEGRADED, not FAILED) and `DryRun(use_case)` (plans the use case a run would execute from `WindowedRun.first_decision()` and the steps of the use case and the loop; never touches the Horizon client) |

The use cases call the ports only. Waiting goes through `Clock.sleep`; a screenshot
travels inside the adapter's error and from there into the `RunReport`.

## Features

Each feature has a `SPEC.md` (Purpose, How it works, Invariants, API, Testing):

- **[Windowed run](features/windowed-run/SPEC.md)** — `windowed_run.py`: the run loop
  both use cases share; one report per run.
- **[Morning check-in](features/morning-checkin/SPEC.md)** — `checkin.py`: open, hold,
  disconnect, confirm `CONNECTED` -> `DISCONNECTED`.
- **[Evening check-out](features/evening-checkout/SPEC.md)** — `checkout.py`: log off
  from the tile menu and confirm `NO_SESSION`.
- **[Probe and dry run](features/probe/SPEC.md)** — `probe.py`: the dependency probe and
  the plan of a run, both without logging in.

## Dependencies

- Depends on: `domain`
- Used by: `cli`
