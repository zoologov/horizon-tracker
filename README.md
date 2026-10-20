# horizon-tracker

Scheduled check-in and check-out of a VMware Horizon VDI session, run on a VPS.

Every working day (per the Russian production calendar, isdayoff.ru) a systemd
timer opens the "DEV desktop" through Horizon HTML Access at 07:55 MSK so the
Windows logon is recorded, then disconnects; at 17:00 MSK it reconnects and
logs off. Each run reports to Telegram.

## Layout

| Path | What lives there |
|------|------------------|
| `src/horizon_tracker/domain/` | pure decision cores: schedule windows, working-day verdicts, session state, ports |
| `src/horizon_tracker/application/` | use cases: morning check-in, evening check-out |
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
