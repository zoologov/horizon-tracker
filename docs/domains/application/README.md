# Application

Use cases of horizon-tracker. A use case orders domain decisions and port calls;
it owns no transport and no browser detail.

## Source

`src/horizon_tracker/application/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `checkin.py` | the morning check-in: open the desktop until Windows logs on, hold it, then disconnect (`MorningCheckin(client, clock, runner, desktop, hold)`) |
| `checkout.py` | the evening check-out: log the desktop's Windows session off and confirm it ended; a desktop with no session is reported as already logged off (`EveningCheckout(client, clock, runner, desktop)`) |
| `windowed_run.py` | drives one daily run through its window: decides each attempt with the domain, retries failures, sends exactly one report (`WindowedRun`, one per window); an early start is reported as `Reason.TOO_EARLY`, a late one as `WINDOW_MISSED` |
| `probe.py` | checks whether the service could run without ever logging in: `Probe` (settings, portal bundles via `client.probe()`, calendar, Chrome; an unreachable calendar is DEGRADED, not FAILED) and `DryRun` (names the plan's steps for a run kind, never touches the Horizon client) |

The use cases call the ports only. Waiting goes through `Clock.sleep`; a screenshot
travels inside the adapter's error and from there into the `RunReport`.

## Features

(none yet — added as the work lands)

## Dependencies

- Depends on: `domain`
- Used by: `cli`
