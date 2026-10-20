# Domain

Pure decision cores of horizon-tracker. Nothing here performs I/O: no browser,
no network, no wall clock other than the one passed in. Every verdict is
deterministic and unit-tested first.

## Source

`src/horizon_tracker/domain/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `schedule.py` | the run window and the decision for one attempt: `Window`, `RunKind` (CHECKIN, CHECKOUT), `RetryPolicy`, `decide(now, window, verdict, attempt, policy)` → `Decision` (RUN, RETRY, SKIP_EARLY, SKIP_LATE, SKIP_NON_WORKING_DAY, GIVE_UP) |
| `calendar.py` | the working-day verdict: `WorkingDayVerdict(is_working, source)` with `VerdictSource` CALENDAR or WEEKDAY_FALLBACK, `weekday_rule(day)`, `resolve(calendar_answer, day)` |
| `session.py` | the states a Horizon session moves through and the two success rules: `SessionState` (NO_SESSION, CONNECTED, DISCONNECTED), `DesktopStatus`, `checkin_succeeded(while_open, after_disconnect)`, `checkout_succeeded(before, after)` |
| `report.py` | the record of one run and its notification text: `RunReport`, `Outcome`, `Reason`, `render(report)`; the report has no password field by construction |
| `ports.py` | the Protocols the adapters implement: `HorizonClient`, `WorkingDayCalendar`, `Notifier` (`send(report)`, the screenshot travels inside the report), `Clock`, `ArtifactStore` |

## Features

(none yet — added as the work lands)

## Dependencies

- Depends on: (none) — the domain imports nothing from the other layers
- Used by: `application`, `infrastructure`
