# horizon-tracker

Scheduled check-in and check-out of a VMware Horizon VDI session, run on a VPS.

Every working day (per the Russian production calendar, isdayoff.ru) the service
opens the "DEV desktop" through Horizon HTML Access so the Windows logon is
recorded, then disconnects. Later the same day it reconnects and logs off.

The two moments change from day to day. Each date draws a check-in moment from
`HT_CHECKIN_RANGE` (default 07:30-08:10) and a check-out moment 540 to 550 minutes
later (`HT_SESSION_LENGTH_MINUTES` plus up to `HT_SESSION_EXTRA_MAX_MINUTES`),
clipped into `HT_CHECKOUT_RANGE` (default 16:30-17:10). The draw is deterministic
for a date and a seed (`HT_JITTER_SEED`, by default the username), so the morning
and the evening run agree without sharing state. The systemd timers fire at the
start of each range, and each run waits for its own moment before it acts. All
wall times are in the zone set by `HT_TIMEZONE`. Each run reports to Telegram.

The notification, the output of `horizon probe` and of a dry run, and a configuration
error are written in the language `HT_LANGUAGE` names: `en` (the default) or `ru`. Any
other value is refused at start. The logs stay English whatever the language.

## Layout

| Path | What lives there |
|------|------------------|
| `src/horizon_tracker/domain/` | pure decision cores: the daily draw of the moments and the run windows, working-day verdicts, session state, the run report, the message catalogue, ports |
| `src/horizon_tracker/application/` | use cases: morning check-in, evening check-out, the shared run loop, the probe and the dry run |
| `src/horizon_tracker/infrastructure/` | adapters: Playwright driver, isdayoff.ru calendar, Telegram notifier, env config |
| `src/horizon_tracker/cli.py` | the `horizon` command, composition root |
| `docs/` | AS-IS architecture documentation held against the code by `beadloom sync-check` |
| `.beadloom/` | architecture graph, rules and the agentic flow configuration |

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
beadloom ci            # architecture + documentation gate
```

See `.claude/CLAUDE.md` for the development flow and `docs/architecture.md`
for the dependency direction between layers.
