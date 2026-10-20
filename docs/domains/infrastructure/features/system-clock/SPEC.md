# System clock

The `Clock` port on the system's wall clock: an aware `now()` in the service's time
zone and a blocking `sleep()`.

## Source

`src/horizon_tracker/infrastructure/clock.py`

## Specification

### Purpose

The domain never reads time; the run loop asks the `Clock` port. This adapter is the
production clock, so a test can replace it with a fake that moves time on demand.

### How it works

`SystemClock(tz)` answers `now()` with `datetime.now(tz)`, the current instant as wall
time in the configured zone (`HT_TIMEZONE`, `Europe/Moscow` by default). `sleep(seconds)`
blocks through `time.sleep`.

## Invariants

- `now()` is always time-zone aware.
- A negative wait raises `ValueError`, as `time.sleep` does.

## API

Module `src/horizon_tracker/infrastructure/clock.py`:

- `SystemClock(tz: ZoneInfo)` — implements `Clock`; `now() -> datetime`,
  `sleep(seconds: float) -> None`.

## Testing

Tests: `tests/unit/infrastructure/test_clock.py`. The acceptance suite runs on a fake
clock (`tests/support/fakes.py`).

## Dependencies

Derived from the imports on reindex.

- Depends on: (none)
- Used by: `cli`

## Parent

`infrastructure` — [infrastructure README](../../README.md)
