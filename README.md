# horizon-tracker

Scheduled check-in and check-out of a VMware Horizon VDI desktop, run on a Linux host
under systemd timers.

## What it does

- **Morning check-in.** The service opens the configured desktop through Horizon HTML
  Access and holds it until Windows has logged on, so the logon is recorded on the
  virtual machine, then disconnects quietly: the Windows session keeps running.
- **Evening check-out.** It reconnects to the portal and logs the Windows session off
  from the desktop's menu, then confirms the session ended.
- **Working days only.** Each run asks a production calendar (isdayoff.ru) whether
  today is a working day; when the calendar does not answer, Monday to Friday decides.
- **Moments drawn per date.** Each date draws a check-in moment inside
  `HT_CHECKIN_RANGE` and a check-out moment a session length later (plus up to a few
  minutes), clipped into `HT_CHECKOUT_RANGE`. The draw is deterministic for a date and
  a seed, so the morning and the evening run agree without sharing state. A timer fires
  at the start of each range and the run waits for its own moment.
- **Notifications.** Every run sends one report through a Telegram bot: what happened,
  when, which calendar rule decided and why, with a screenshot of the step when there is
  one. No report can carry a credential.
- **Language.** `HT_LANGUAGE` picks the language of the notification, `horizon probe`,
  a dry run and a configuration error: `en` (the default) or `ru`. Logs stay English.

## What it is made of

One Python package laid out as a hexagon. The `domain` holds the pure decision cores
and declares the ports; it reads no clock, no network and no browser. The `application`
layer holds the use cases over those ports. The `infrastructure` layer implements the
ports with adapters. The `cli` is the composition root that wires adapters into use
cases. Dependencies point inward only (`cli` → `infrastructure`/`application` →
`domain`); `beadloom lint --strict` enforces it. See `docs/architecture.md`.

| Path | What lives there |
|------|------------------|
| `src/horizon_tracker/domain/` | pure decision cores: the daily draw of the moments and the run windows, working-day verdicts, session state, the run report, the message catalogue, ports |
| `src/horizon_tracker/application/` | use cases: morning check-in, evening check-out, the shared run loop, the probe and the dry run |
| `src/horizon_tracker/infrastructure/` | adapters: Playwright driver, isdayoff.ru calendar, Telegram notifier, env config, system clock, artifact store |
| `src/horizon_tracker/cli.py` | the `horizon` command, composition root |
| `docs/` | AS-IS documentation held against the code by `beadloom sync-check` |
| `.beadloom/` | architecture graph, rules and the agentic flow configuration |

## Configuration

Every setting is an environment variable (in production, an `.env` file readable only by
the service user). The values below are examples.

```bash
# required
HORIZON_URL=https://horizon.example.com/portal/webclient/
HORIZON_USERNAME=jdoe
HORIZON_PASSWORD=...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789

# optional (default in brackets)
HORIZON_DESKTOP="DEV desktop"        # the launch item's title [DEV desktop]
HT_TIMEZONE=Europe/Berlin            # IANA zone of every wall time [Europe/Moscow]
HT_CHECKIN_RANGE=07:30-08:10         # check-in moment drawn from here [07:30-08:10]
HT_CHECKOUT_RANGE=16:30-17:10        # check-out moment clipped into here [16:30-17:10]
HT_SESSION_LENGTH_MINUTES=540        # check-out at least this long after check-in [540]
HT_SESSION_EXTRA_MAX_MINUTES=10      # up to this many minutes on top [10]
HT_WINDOW_GRACE_MINUTES=5            # how long a run's window stays open [5]
HT_JITTER_SEED=...                   # seed of the daily draw [HORIZON_USERNAME]
HT_HOLD_SECONDS=120                  # how long the opened desktop is held [120]
HT_LANGUAGE=en                       # en or ru [en]
```

The full list, with every check a value must pass, is in
`docs/domains/infrastructure/features/settings/SPEC.md`. `horizon probe` checks the
settings, the portal, the calendar and Chrome without logging in, and prints the day's
drawn moments; `horizon checkin --dry-run` prints the plan of a run without touching the
portal.

## Development

The project is developed with the beadloom agentic flow: `beadloom prime` for the
architecture context, `bd` for the work items (beads), test-first changes, and the gates
below before a change lands. See `.claude/CLAUDE.md` for the full flow.

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
beadloom ci                                # architecture + documentation gate
scripts/mutation.sh --changed-since main --out /tmp/mutation   # mutation gate, per change
```

The mutation gate covers the pure domain only (`[tool.mutmut]` in `pyproject.toml`).

## Deployment

See [`docs/guides/deployment.md`](docs/guides/deployment.md).
