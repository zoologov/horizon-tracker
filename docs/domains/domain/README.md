# Domain

Pure decision cores of horizon-tracker. Nothing here performs I/O: no browser,
no network, no wall clock other than the one passed in. Every verdict is
deterministic and unit-tested first.

## Source

`src/horizon_tracker/domain/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `schedule.py` | the run window and the decision for one attempt: `Window`, `RunKind` (CHECKIN, CHECKOUT), `RetryPolicy`, `FIRST_ATTEMPT` (1, the number the run loop counts from), `decide(now, window, verdict, attempt, policy)` → `Decision` (RUN, RETRY, SKIP_EARLY, SKIP_LATE, SKIP_NON_WORKING_DAY, GIVE_UP) |
| `calendar.py` | the working-day verdict: `WorkingDayVerdict(is_working, source)` with `VerdictSource` CALENDAR or WEEKDAY_FALLBACK, `weekday_rule(day)`, `resolve(calendar_answer, day)` |
| `session.py` | the states a Horizon session moves through and the two success rules: `SessionState` (NO_SESSION, CONNECTED, DISCONNECTED), `DesktopStatus`, `checkin_succeeded(while_open, after_disconnect)`, `checkout_succeeded(before, after)` |
| `report.py` | the record of one run and its notification text: `RunReport` (with `planned_at`, the day's drawn moment, since HT-003), `Outcome`, `Reason`, `render(report)`; the report has no password field by construction |
| `ports.py` | the Protocols the adapters implement: `HorizonClient` (the run's `login`, `desktop_status`, `open_desktop`, `disconnect`, `log_off`, and the probe's `client_bundles()` and `browser_version()`), `WorkingDayCalendar`, `Notifier` (`send(report)`, the screenshot travels inside the report), `Clock`, `ArtifactStore`; `HorizonClientError(reason, screenshot)` |

The whole package is the scope of the mutation gate (`scripts/mutation.sh`).

## Features

Each feature has a `SPEC.md` (Purpose, How it works, Invariants, API, Testing):

- **[Schedule](features/schedule/SPEC.md)** — `schedule.py`: run, retry or skip, given
  the window, the working-day verdict and the retry policy.
- **[Working-day calendar](features/working-day-calendar/SPEC.md)** — `calendar.py`: the
  calendar's answer first, Monday to Friday as the fallback, and the source named.
- **[Session state](features/session-state/SPEC.md)** — `session.py`: the three session
  states and the check-in and check-out success rules.
- **[Run report](features/run-report/SPEC.md)** — `report.py`: the report value of
  closed vocabularies and the Russian notification text.
- **[Ports](features/ports/SPEC.md)** — `ports.py`: the five contracts the adapters
  implement, including the two-method probe contract of `HorizonClient`.

## Dependencies

- Depends on: (none) — the domain imports nothing from the other layers
- Used by: `application`, `infrastructure`
