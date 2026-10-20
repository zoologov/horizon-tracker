# Domain

Pure decision cores of horizon-tracker. Nothing here performs I/O: no browser,
no network, no wall clock other than the one passed in. Every verdict is
deterministic and unit-tested first.

## Source

`src/horizon_tracker/domain/`

## Responsibilities

- schedule windows: when a check-in or check-out may run, and when it is too late
- working-day verdicts: whether a given date is a working day
- session state: the states a Horizon session moves through (connected,
  disconnected, logged off)
- ports: the Protocols the adapters implement

## Features

(none yet — added as the work lands)

## Dependencies

- Depends on: (none) — the domain imports nothing from the other layers
- Used by: `application`, `infrastructure`
