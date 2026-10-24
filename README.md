![Status: production](https://img.shields.io/badge/status-production-brightgreen)
[![Release](https://img.shields.io/github/v/release/zoologov/horizon-tracker?sort=semver)](https://github.com/zoologov/horizon-tracker/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/zoologov/horizon-tracker/ci.yml?branch=main&label=CI)](https://github.com/zoologov/horizon-tracker/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
[![License: MIT](https://img.shields.io/github/license/zoologov/horizon-tracker)](LICENSE)
![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64?logo=ruff&logoColor=D7FF64)
![Type check: mypy strict](https://img.shields.io/badge/type%20check-mypy%20strict-blue)
![Versioning: SemVer](https://img.shields.io/badge/versioning-SemVer-informational)
[![Portal](https://img.shields.io/badge/portal-GitHub%20Pages-informational)](https://zoologov.github.io/horizon-tracker/)
![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-blueviolet?logo=anthropic&logoColor=white)

# horizon-tracker

Scheduled check-in and check-out of a VMware Horizon VDI desktop, run on a Linux host
under systemd timers.

> **An experiment in developing with Beadloom.** This repository is a proving ground for
> the [Beadloom](https://github.com/zoologov/beadloom) agentic flow: every work item here
> went through its documents, beads, waves and gates, and the rough edges found along the
> way are fed back to Beadloom. The service itself is real and runs in production.
>
> **Architecture portal:** <https://zoologov.github.io/horizon-tracker/> — the graph,
> the nodes and the documents of this repository, built by `beadloom docs site` on every
> release.

## What it does

- **Morning check-in.** The service opens the configured desktop through Horizon HTML
  Access and holds it until Windows has logged on, so the logon is recorded on the
  virtual machine, then disconnects quietly: the Windows session keeps running.
- **Evening check-out.** It reconnects to the portal and logs the Windows session off
  from the desktop's menu, then confirms the session ended.
- **Working days only.** Each run asks a production calendar (isdayoff.ru) whether
  today is a working day; when the calendar does not answer, Monday to Friday decides.
- **Absences through the bot.** The owner enters a vacation, a sick leave or a day off by
  writing to the same Telegram bot, with text commands: `/add vacation 03.11-14.11`
  (or `/add отпуск 03.11-14.11`), `/list`, `/edit 1 05.11-16.11`, `/del 1`, `/help`. The
  bot answers only the configured chat, in `HT_LANGUAGE`, and a run on a day an absence
  covers is skipped without asking the calendar. An absence for today entered once today's
  check-in range has begun starts tomorrow, because the morning may already have checked
  in; the reply says so. The bot runs as its own service, `horizon-bot.service`, beside
  the two timers, and keeps the absences in `HT_STATE_DIR/absences.json`
  (`/opt/horizon-tracker/state` by default, outside the checkout, so they survive every
  deploy and reboot).
- **Moments drawn per date.** Each date draws a check-in moment inside
  `HT_CHECKIN_RANGE` and a check-out moment a session length later (plus up to a few
  minutes), clipped into `HT_CHECKOUT_RANGE`. The draw is deterministic for a date and
  a seed, so the morning and the evening run agree without sharing state. A timer fires
  at the start of each range and the run waits for its own moment.
- **Notifications.** Every run sends one report through a Telegram bot: what happened,
  when, which calendar rule decided and why, with a screenshot of the step when there is
  one. A skipped day (a weekend, a holiday or an absence) is one notice from the morning
  run, with no time line, and the evening run of that day sends nothing. No report can
  carry a credential.
- **Language.** `HT_LANGUAGE` picks the language of the notification, the bot's replies,
  `horizon probe`, a dry run and a configuration error: `en` (the default) or `ru`. Logs stay English.

## What it is made of

One Python package laid out as a hexagon. The `domain` holds the pure decision cores
and declares the ports; it reads no clock, no network and no browser. The `application`
layer holds the use cases over those ports. The `infrastructure` layer implements the
ports with adapters. The `cli` is the composition root that wires adapters into use
cases. Dependencies point inward only (`cli` → `infrastructure`/`application` →
`domain`); `beadloom lint --strict` enforces it. See `docs/architecture.md`.

| Path | What lives there |
|------|------------------|
| `src/horizon_tracker/domain/` | pure decision cores: the daily draw of the moments and the run windows, working-day verdicts, session state, the owner's absences, the bot's command parser, the run report, the message catalogue, ports |
| `src/horizon_tracker/application/` | use cases: morning check-in, evening check-out, the shared run loop, the probe and the dry run, the absence service and the bot loop |
| `src/horizon_tracker/infrastructure/` | adapters: Playwright driver, isdayoff.ru calendar, Telegram notifier, Telegram bot transport, absence store, env config, system clock, artifact store |
| `src/horizon_tracker/cli.py` | the `horizon` command, composition root |
| `docs/` | AS-IS documentation held against the code by `beadloom sync-check` |
| `.beadloom/` | architecture graph, rules and the agentic flow configuration |

Outside the package, the service is bound to six external systems: the Horizon portal (the
HTML Access web client and its connection broker), the isdayoff.ru production calendar, the
Telegram Bot API, the owner's Telegram chat the reports go to and the bot's commands come
from, the VPS host (the `horizon` user, its `.env`, the state directory and the systemd
units) and the GitHub Environment `horizon-vps`, which the deploy turns into the host's
`.env`. Each is a node of the architecture graph. Its contracts
are declared in `.beadloom/_graph/landscape.yml`, and the surface of each is written out in
`docs/domains/external/<node>/SPEC.md`. The portal's
[landscape page](https://zoologov.github.io/horizon-tracker/landscape.html) draws them as a
map, rebuilt with every release, and `docs/architecture.md` (section Landscape) says what its
verdicts rest on.

## Requirements

To run the service, a host needs:

- Ubuntu (or another apt-based distribution) with systemd, reachable over SSH: the service
  runs as two systemd timers and their oneshot services, and the bot as one long-running
  service, `horizon-bot.service`, which the first deploy enables;
- Python 3.12 (`python3.12`, `python3.12-venv`) and `uv` at `/usr/local/bin/uv`;
- Google Chrome at `/usr/bin/google-chrome`, installed from Google's `.deb` and not the snap
  (another path is set with `HT_CHROME_PATH`): Playwright drives the system Chrome;
- the system user `horizon` with the home `/opt/horizon-tracker` (`deploy/bootstrap.sh`
  creates both);
- outbound network to the Horizon HTML Access portal, `isdayoff.ru`, `api.telegram.org` and
  `github.com`;
- a Horizon (AD) account and the title of its desktop, a Telegram bot token and the chat id the
  reports go to.

The deploy also needs a GitHub repository with Actions, the Environment `horizon-vps` holding
the secrets and variables listed in section 3 of the
[deployment guide](docs/guides/deployment.md), and SSH access from Actions to the host
(section 2.3 there).

## Getting started

**Locally**, to try the command against your portal without the timers:

```bash
git clone https://github.com/zoologov/horizon-tracker.git && cd horizon-tracker
uv sync --all-extras
uv run playwright install chromium    # the browser the adapter tests drive
# export the variables of the Configuration section below; the command reads the
# environment and loads no .env file itself (set HT_CHROME_PATH to your Chrome)
uv run horizon probe                  # settings, portal, calendar, Chrome, absences; never logs in
uv run horizon checkin --dry-run      # the plan of a run, without touching the portal
```

**On a host**, each step is a section of the
[deployment guide](docs/guides/deployment.md):

1. prepare the host once with `deploy/bootstrap.sh` (section 2);
2. create the GitHub Environment `horizon-vps` with its secrets and variables (section 3);
3. let the first release tag deploy, which writes `.env`, installs the units and starts the
   bot, which answers from then on while the timers stay off (section 4.1);
4. run `horizon probe` on the host (section 4.3), then a check-in and a check-out by hand
   with `--force` (section 4.4);
5. enable the timers (section 5).

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
HT_STATE_DIR=/opt/horizon-tracker/state  # where absences.json lives [/opt/horizon-tracker/state]
```

The full list, with every check a value must pass, is in
`docs/domains/infrastructure/features/settings/SPEC.md`. `horizon probe` checks the
settings, the portal, the calendar, Chrome and the absences file without logging in, and prints the day's
drawn moments; `horizon checkin --dry-run` prints the plan of a run without touching the
portal.

## Development

The project is developed with the Beadloom agentic flow: `beadloom prime` for the
architecture context, `bd` for the work items (beads), test-first changes, and the gates
below before a change lands. [`CONTRIBUTING.md`](CONTRIBUTING.md) covers the setup of a fresh
clone, and [`.claude/CLAUDE.md`](.claude/CLAUDE.md) the full flow.

```bash
uv sync --all-extras
uv run pytest
uv run ruff check                          # the whole repository, as CI runs it
uv run ruff format --check
uv run mypy                                # strict; the scope is [tool.mypy] files
beadloom ci                                # architecture + documentation gate
scripts/mutation.sh --changed-since main --out /tmp/mutation   # mutation gate, per change
```

The mutation gate covers the pure domain only (`[tool.mutmut]` in `pyproject.toml`).

Development is trunk-based: a branch per work item (`features/<KEY>`), one pull request to
`main`, the CI check `ci-ok` required before it merges, and no direct push to `main` for
anyone, the owner included.

## Releases

A release is a tag `vX.Y.Z` (strict semver, no pre-release suffix) on a commit of `main`. A
pull request runs CI alone; nothing reaches the host before a tag. Pushing the tag starts the
Release workflow, which runs these jobs in order, each only after the one before it passed:

1. **verify**: the tag is on `main`, equals the version in `pyproject.toml` and the version
   `uv.lock` locks, and has its section in [`CHANGELOG.md`](CHANGELOG.md). A run by hand (a
   redeploy) started from any branch but `main` stops here;
2. **CI** on the tagged commit;
3. **deploy** to the host;
4. **GitHub Release** with the changelog section as its notes and the wheel and the sdist as
   assets;
5. **portal**: the Beadloom architecture portal on GitHub Pages, at
   <https://zoologov.github.io/horizon-tracker/>.

What the version number promises and the release steps are in
[`docs/guides/releasing.md`](docs/guides/releasing.md).

## Deployment

A release tag deploys: the Release workflow updates the host, writes its `.env` from the
GitHub Environment `horizon-vps` and ends with a `horizon probe` smoke. The first install and
the operations are in [`docs/guides/deployment.md`](docs/guides/deployment.md).

## License

MIT, see [`LICENSE`](LICENSE).
