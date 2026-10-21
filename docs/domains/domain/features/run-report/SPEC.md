# Run report

The run report as a value of closed vocabularies, and the notification text rendered
from it in the language the caller names. No field can carry a password.

## Source

`src/horizon_tracker/domain/report.py`

## Specification

### Purpose

Every run ends in exactly one report to the owner. The report must say what happened,
when, on whose working-day verdict and why, and it must be impossible for it to carry
a credential. A value with no free-text field gives both properties by construction.

### How it works

`RunReport` holds the run kind, an `Outcome`, an aware `datetime`, the `VerdictSource`
(or `None` for a `--force` run, which asks no calendar), a `Reason`, an optional
screenshot `Path` and `planned_at`, the drawn moment the run was due at. `planned_at`
is set for every scheduled run, whether or not it reached its window: a skip on a day
off or a run started after its window names its moment as well. Only a `--force` run
leaves it `None`. `__post_init__` checks the type of every field and refuses a value
of the wrong type with `TypeError`, rather than trusting the caller.

`render(report, language)` builds the message text from the message catalogue
([messages](../messages/SPEC.md)) in `language`. The same failure in English and in
Russian:

```text
Check-in failed
Time: 21.10.2026 07:39:12 MSK, planned for 07:38
Calendar: the isdayoff.ru production calendar
Reason: the desktop did not open
```

```text
Check-in failed
Time: 21.10.2026 07:39:12 MSK, planned for 07:38
Calendar: the isdayoff.ru production calendar
Reason: the desktop did not open
```

The first line is the run kind and the outcome, one catalogue key per pair
(`report.checkin.failed`). The time line carries the actual time with the abbreviation
of the configured zone (`MSK` for the default `Europe/Moscow`), followed by the planned
moment (`planned for HH:MM`, the `report.time_planned` key) when `planned_at` is set. The calendar
line names the source: the isdayoff.ru calendar, the Monday-Friday fallback, or "not
asked, manual run --force" for a run that asked no calendar. The reason line is present
only when there is a reason. The two formatted times are the only values the report puts
into the text; every word comes from the catalogue. The Russian texts are the ones the
notification carried before the catalogue existed. The screenshot never appears in
the text: the notifier attaches it beside the text. A failure carries the screenshot of
the step that failed; a success carries the use case's photo of the step it completed
(the opened desktop, the launch list without the session). Either may be `None`, and
the report then goes out as text.

## Invariants

- No field holds free text: the outcome and the reason come from closed vocabularies,
  so a rendered message cannot quote an exception or a password.
- `RunReport.at` carries a time zone; a naive `datetime` raises `ValueError`.
- A reason is present exactly when the outcome is not `SUCCEEDED`; any other
  combination raises `ValueError`.
- Every `Reason` has a phrase in every language; an exception message is never a reason.
- An English notification holds no Cyrillic letter, for every kind, outcome, source,
  reason and planned moment.

## API

Module `src/horizon_tracker/domain/report.py`:

- `Outcome` — `StrEnum`: `SUCCEEDED`, `FAILED`, `SKIPPED`.
- `Reason` — `StrEnum`: `NON_WORKING_DAY`, `TOO_EARLY`, `WINDOW_MISSED`,
  `ALREADY_LOGGED_OFF`, `PORTAL_UNREACHABLE`, `LOGIN_REJECTED`, `DESKTOP_NOT_FOUND`,
  `DESKTOP_DID_NOT_OPEN`, `LOGOFF_NOT_CONFIRMED`, `UNEXPECTED`.
- `RunReport(kind, outcome, at, verdict_source, reason=None, screenshot=None,
  planned_at=None)` — frozen; validated at construction as described above.
  `planned_at: time | None` is the drawn moment the run was due at, local wall time,
  set whether or not the run reached its window. It is `None` for a `--force` run. A
  value of any other type is refused with `TypeError`.
- `render(report: RunReport, language: Language) -> str` — the notification text in
  `language`; there is no default, so every caller names the language it renders in.
  When `planned_at` is set, the time line carries it beside the actual time:
  `Time: 20.10.2026 07:56:12 MSK, planned for 07:43`.

## Testing

Tests: `tests/unit/domain/test_report.py`, each text test in both languages. The module
is inside the mutation gate.

Scenarios:

- `tests/acceptance/features/notifications.feature`:
  - `A failed run sends the reason and a screenshot`
  - `A notification never contains the password`
- `tests/acceptance/features/morning_checkin.feature`:
  - `Morning check-in reports success with the recorded time`

## Dependencies

Derived from the imports on reindex.

- Depends on: `messages`, `schedule`, `working-day-calendar`
- Used by: `cli`, `evening-checkout`, `horizon-playwright-client`, `morning-checkin`, `ports`, `telegram-notifier`, `windowed-run`

## Parent

`domain` — [domain README](../../README.md)
