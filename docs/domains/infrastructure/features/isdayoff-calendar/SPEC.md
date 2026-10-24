# isdayoff.ru calendar

The `WorkingDayCalendar` port over isdayoff.ru: any answer that is not clean is
`None`, logged and never raised.

## Source

`src/horizon_tracker/infrastructure/isdayoff.py`

## Specification

### Purpose

The Russian production calendar moves working days: holidays fall on weekdays and some
Saturdays are working. isdayoff.ru answers that question for a single date. The adapter
turns its answer into the port's `True`, `False` or `None`, and the domain falls back to
the Monday-Friday rule on `None`.

### How it works

`is_working_day(day)` sends `GET https://isdayoff.ru/YYYYMMDD` with a 5-second timeout
over the `httpx.Client` it was built with, and reads the one-character day code:

| Code | Meaning | Answer |
|------|---------|--------|
| `0` | working day | `True` |
| `1` | non-working day | `False` |
| `2` | shortened pre-holiday day, still working | `True` |

A network failure, a timeout, a status other than 200 or any other body is `None`, and
the adapter logs a warning naming the date and what went wrong.

## Invariants

- The adapter never raises for a calendar failure; it answers `None`.
- A shortened pre-holiday day counts as a working day.
- The adapter does not own its HTTP client: the CLI shares one `httpx.Client` between
  the calendar and the notifier and closes it.

## API

Module `src/horizon_tracker/infrastructure/isdayoff.py`:

- `IsDayOffCalendar(client: httpx.Client)` — implements `WorkingDayCalendar`;
  `is_working_day(day: date) -> bool | None`.
- `ISDAYOFF_URL` — `"https://isdayoff.ru/{day:%Y%m%d}"`.
- `TIMEOUT_SECONDS` — `5.0`.

## Testing

Tests: `tests/unit/infrastructure/test_isdayoff.py`, on `httpx.MockTransport`.

The scenarios in `tests/acceptance/features/production_calendar.feature` run on a fake
calendar, so they pin the fallback rule and its notice, not this adapter.

## Dependencies

Derived from the imports on reindex.

- Depends on: (none)
- Used by: `cli`
- External contract (declared in `.beadloom/_graph/landscape.yml`, not derived): consumes
  `http:isdayoff-day` from [`isdayoff`](../../../external/isdayoff/SPEC.md)

## Parent

`infrastructure` — [infrastructure README](../../README.md)
