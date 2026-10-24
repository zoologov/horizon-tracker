# The VPS host

The Ubuntu host the service runs on, shared with a neighbouring service that this one
never touches. An external system: the repository ships what is installed on it
(`deploy/`), and this document declares what the service reads from it.

## Source

None in this repository beyond the files it installs: `deploy/bootstrap.sh` and the five
units under `deploy/`. The node's `source` in `.beadloom/_graph/landscape.yml` is this
file, so the graph has no sourceless node. The host's address is the secret `VPS_HOST`.

## Specification

### Purpose

The host gives the service a user of its own, a home, the settings and a schedule. Every
binding between the code and the machine passes through one of the three contracts below,
which is where a change on the host breaks a run.

What `bootstrap.sh` sets up:

- the system user `horizon` (`useradd -r`, shell `/usr/sbin/nologin`) with the home
  `/opt/horizon-tracker`, which holds the clone and its `.venv` built by `uv sync --locked`
- the directory `/opt/horizon-tracker/artifacts` (`horizon:horizon`, `0750`) for
  screenshots, which the service rotates after 14 days
- the directory `/opt/horizon-tracker/state` (`horizon:horizon`, `0700`), the default of
  `HT_STATE_DIR`, which holds `absences.json` outside the checkout
- the units in `/etc/systemd/system`

It checks for Chrome at `/usr/bin/google-chrome` and never installs it. It writes neither
`.env` nor an enabled timer, and it does not start `horizon-bot.service`: the deploy
enables the bot once it has written `.env`.

### Contracts

Three contracts, each declared from both ends in `landscape.yml`. The portal's map shows
each as a dependency with a presence verdict. The surface below is the one the code and
the deploy hold.

#### `env:dot-env` — vps-host → settings

- **The file.** `/opt/horizon-tracker/.env`, owner `horizon:horizon`, mode `0600`,
  read by systemd as the units' `EnvironmentFile` (systemd's format, not a shell's:
  values double-quoted, with `\`, `"`, `` ` `` and `$` escaped by a backslash).
- **The variables** `Settings.from_env` reads, with their defaults. A secret is never
  written in a document. The column says only whether a variable is one.

| Variable | Default | Secret |
|----------|---------|--------|
| `HORIZON_URL` | required | no |
| `HORIZON_USERNAME` | required | yes |
| `HORIZON_PASSWORD` | required | yes |
| `HORIZON_DESKTOP` | `DEV desktop` | no |
| `TELEGRAM_BOT_TOKEN` | required | yes |
| `TELEGRAM_CHAT_ID` | required | yes |
| `HT_TIMEZONE` | `Europe/Moscow` in the code, and the deploy writes `UTC` when the variable is unset | no |
| `HT_CHECKIN_RANGE` | `07:30-08:10` | no |
| `HT_CHECKOUT_RANGE` | `16:30-17:10` | no |
| `HT_SESSION_LENGTH_MINUTES` | `540` | no |
| `HT_SESSION_EXTRA_MAX_MINUTES` | `10` | no |
| `HT_WINDOW_GRACE_MINUTES` | `5` | no |
| `HT_JITTER_SEED` | `HORIZON_USERNAME` | yes |
| `HT_HOLD_SECONDS` | `120` | no |
| `HT_CHROME_PATH` | `/usr/bin/google-chrome` | no |
| `HT_ARTIFACTS_DIR` | `/opt/horizon-tracker/artifacts` | no |
| `HT_STATE_DIR` | `/opt/horizon-tracker/state`; the deploy does not write it | no |
| `HT_LANGUAGE` | `en` | no |

- **Refusals.** A missing or blank required variable stops every command with
  `configuration error: <VAR>: is required and not set`, and the retired
  `HT_CHECKIN_WINDOW` and `HT_CHECKOUT_WINDOW` are refused by name even when blank. The
  checks of each value are in the `settings` SPEC.

#### `systemd:units` — vps-host → cli

| Unit | What it holds |
|------|---------------|
| `horizon-checkin.timer` | `OnCalendar=*-*-* 07:30:00 Europe/Moscow`, `Persistent=no`, `AccuracySec=1s`, starts `horizon-checkin.service` |
| `horizon-checkin.service` | `Type=oneshot`, `User=horizon`, `Group=horizon`, `WorkingDirectory=/opt/horizon-tracker`, `EnvironmentFile=/opt/horizon-tracker/.env`, `ExecStart=/opt/horizon-tracker/.venv/bin/horizon checkin`, `TimeoutStartSec=60min`, after `network-online.target` |
| `horizon-checkout.timer` | `OnCalendar=*-*-* 16:30:00 Europe/Moscow`, `Persistent=no`, `AccuracySec=1s`, starts `horizon-checkout.service` |
| `horizon-checkout.service` | the same as the check-in service, with `ExecStart=… horizon checkout` |
| `horizon-bot.service` | `Type=simple`, `User=horizon`, `Group=horizon`, `WorkingDirectory=/opt/horizon-tracker`, `EnvironmentFile=/opt/horizon-tracker/.env`, `ExecStart=/opt/horizon-tracker/.venv/bin/horizon bot`, `KillSignal=SIGINT`, `Restart=always`, `RestartSec=10`, after `network-online.target`, `WantedBy=multi-user.target` |

- **The exit code.** `horizon` exits 1 only when the run's report is FAILED, and 0 on a
  success and on every deliberate skip, so systemd marks a unit `failed` exactly on a
  failed run.
- **The zone.** The timers fire at the range starts in the zone `OnCalendar` names. The
  deploy refuses a run whose `HT_TIMEZONE` differs from it, because two zones would start
  every run outside its range.
- **The bound.** `TimeoutStartSec=60min` covers the wait for the drawn moment (at most the
  40-minute range), the 5-minute window and the run itself. `tests/unit/deploy` checks
  the sum.
- **The bot.** The one unit that never exits on its own, and the bot's only `getUpdates`
  caller. Every deploy installs it, restarts a running one (`try-restart`) and enables it
  (`enable --now`), where the timers are only restarted when already enabled. `SIGINT` is
  its stop signal because `horizon bot` treats an interrupt as its clean stop.

#### `env:github-environment` — github-environment → vps-host

The host consumes what the Release's `deploy` job writes into `.env` from the GitHub
Environment `horizon-vps`. The names are in the `github-environment` SPEC. The job reaches
the host over SSH as `VPS_USER`, with the host key pinned by `VPS_KNOWN_HOSTS`.

## Invariants

- The service touches nothing of the neighbouring service: it has its own user, home and
  units.
- `.env` is rewritten by every deploy. A hand edit on the host lasts until the next one.
- Nothing in the repository holds a value of `.env`: it is in `.gitignore`.

## Dependencies

Declared in `.beadloom/_graph/landscape.yml` as contract edges, not derived from
imports: an external system has no code here.

- Produces: `env:dot-env` for `settings`, and `systemd:units` for `cli`
- Consumes: `env:github-environment` from `github-environment`

## Parent

None: an external system, not part of `horizon-tracker`. The consumers are `settings`
and `cli`, and the producer it consumes from is `github-environment`.
