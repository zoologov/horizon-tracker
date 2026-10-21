# Working-day calendar

Decides whether a date is a working day: the production calendar's answer first,
Monday to Friday as the fallback, and names which rule decided.

## Source

`src/horizon_tracker/domain/calendar.py`

## Specification

### Purpose

Runs happen on working days of a production calendar (isdayoff.ru). The calendar is an
external service and may be unreachable, so the decision needs a fallback, and the
owner needs to know which of the two rules decided a given day.

### How it works

The `WorkingDayCalendar` port (isdayoff.ru in production) answers `True`, `False`, or
`None` when it could not be asked. `resolve(calendar_answer, day)` turns that answer
into a `WorkingDayVerdict`:

- `True` or `False` becomes a verdict with source `CALENDAR`;
- `None` falls back to `weekday_rule(day)` (Monday to Friday) with source
  `WEEKDAY_FALLBACK`.

The source travels into the `RunReport`, and the notification names it in its
"Calendar:" line (`report.calendar`, in the configured language).

## Invariants

- A calendar answer, when there is one, always wins over the weekday rule.
- The weekday rule counts Monday to Friday as working and Saturday and Sunday as not.
- Every verdict names its source.

## API

Module `src/horizon_tracker/domain/calendar.py`:

- `VerdictSource` — `StrEnum`: `CALENDAR`, `WEEKDAY_FALLBACK`.
- `WorkingDayVerdict(is_working: bool, source: VerdictSource)` — frozen.
- `weekday_rule(day: date) -> bool` — `True` for Monday to Friday.
- `resolve(calendar_answer: bool | None, day: date) -> WorkingDayVerdict` — the
  calendar's answer, or the weekday rule on `None`.

## Testing

Tests: `tests/unit/domain/test_calendar.py`. The module is inside the mutation gate.

Scenarios (`tests/acceptance/features/production_calendar.feature`):

- `A day the calendar marks as a holiday is skipped with a notice`
- `When the calendar is unreachable the weekday rule decides and says so`

## Dependencies

Derived from the imports on reindex.

- Depends on: (none)
- Used by: `cli`, `probe`, `run-report`, `schedule`, `windowed-run`

## Parent

`domain` — [domain README](../../README.md)
