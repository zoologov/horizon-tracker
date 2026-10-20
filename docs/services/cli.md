# CLI — `horizon`

The command-line entry point and the composition root: it reads configuration,
builds the adapters and hands them to the use cases.

**Source:** `src/horizon_tracker/cli.py`

## Commands

| Command | What it does |
|---------|--------------|
| `horizon --version` | prints the package version |

More commands are added as the work lands.

## Source

`src/horizon_tracker/cli.py`

## Dependencies

- Depends on: `application`, `infrastructure`
- Used by: the systemd timers on the VPS
