# CLI — `horizon`

The command-line entry point and the composition root: it reads the settings
from the environment, builds the adapters (one `httpx.Client`, the Playwright
Horizon client, the isdayoff calendar, the Telegram notifier, the system clock,
the artifact store) and hands them to the use cases. Tests replace the adapter
factory through click's context object and drive the commands with `CliRunner`.

**Source:** `src/horizon_tracker/cli.py`

## Commands

| Command | What it does | Exit code |
|---------|--------------|-----------|
| `horizon checkin [--dry-run] [--force]` | the morning check-in: open the desktop, hold it until Windows logs on, then disconnect | 1 only when the run's report is FAILED; 0 for success and for every deliberate skip |
| `horizon checkout [--dry-run] [--force]` | the evening check-out: log the desktop's Windows session off and confirm it ended | same rule |
| `horizon probe` | check the settings, the portal (the HTML Access client bundles it serves, no login), the calendar, and Chrome (found at `HT_CHROME_PATH`, started headless, its version named); name today's drawn moments last | 1 if the portal or Chrome check FAILED; an unreachable calendar is DEGRADED and keeps 0 |
| `horizon --version`, `horizon --help` | version; the three commands | 0 |

Each run draws today's moments first: `draw_moments` over today's date (the clock's,
in `HT_TIMEZONE`), the seed and the ranges and durations from the settings gives the
check-in and the check-out moment. The run's own moment opens its window, which lasts
`HT_WINDOW_GRACE_MINUTES` (`window_from`). A run started from the start of its range
(`HT_CHECKIN_RANGE` or `HT_CHECKOUT_RANGE`; the timers fire there) and before its moment
waits for the moment in one sleep and then runs; a run started before its range is
skipped as too early; a run started after its window is skipped as too late. The report
names the drawn moment beside the actual time. The same date and settings draw the same
moments in every command, so the probe, a dry run and both runs of a day agree.

`--force` runs now: no wait for the drawn moment, no window and no calendar (a manual
run from the VPS; the report says the calendar was not asked and names no planned
moment). `--dry-run` prints the plan to stdout and exits 0: it never calls login or any
other Horizon method, sends no Telegram report, sleeps for nothing and prunes nothing.
The two flags combine.

A configuration error is logged on stderr as `configuration error: <VAR>:
<problem>` without the credential's value, and every command exits 1. The retry
policy is a CLI constant (3 attempts, 30 s apart, still bounded by the window).

Before a run that is not a dry run, the CLI removes screenshots older than 14 days
from `HT_ARTIFACTS_DIR`. This is best-effort: an `OSError` is logged as
`artifact prune failed, the run goes on: <Type>` and the run goes on. A dry run and
the probe delete nothing.

The use cases, the probe and the dry run are specified in
`docs/domains/application/features/*/SPEC.md`; the settings in
`docs/domains/infrastructure/features/settings/SPEC.md`.

## Output

- stdout: only the dry-run plan and the probe lines.
- stderr: logging at INFO on the `horizon_tracker` logger; under systemd the
  journal captures it, so there is no log file and no rotation code.

### `horizon probe`

The probe never logs in. It prints one line per check, `<check>: <status> - <detail>`,
after the settings line, and then the day's drawn moments as `schedule: today HH:MM /
HH:MM` (check-in / check-out; the same draw a run makes today, so it can be compared on
the VPS without a login):

| Line | `ok` | Otherwise |
|------|------|-----------|
| `settings:` | `ok - portal <HORIZON_URL>, desktop '<HORIZON_DESKTOP>', check-in <HT_CHECKIN_RANGE>, check-out <HT_CHECKOUT_RANGE>, <zone>`; no credential and no seed is named | no probe lines; `configuration error: ...` on stderr, exit 1 |
| `portal:` | `ok - client bundles: <file names>` | `failed - no answer: portal_unreachable` (no answer, or a status other than 200) or `failed - no answer: unexpected` (no bundle named) |
| `calendar:` | `ok - isdayoff.ru: <date> is a working day` or `... is a day off` | `degraded - isdayoff.ru did not answer for <date>; runs fall back to the Mon-Fri rule` |
| `chrome:` | `ok - Chrome <version> started from <path>` | `failed - not found at <path>` (nothing is started) or `failed - found at <path> but did not start: unexpected` |
| `schedule:` | `today <check-in HH:MM> / <check-out HH:MM>`, no status: information, never a failure | — |

The probe reads no portal version: the portal is asked for the client bundles it
serves and Chrome for the version it reports once started.

### `horizon checkin --dry-run`, `horizon checkout --dry-run`

```text
dry run: checkin at 2026-10-21 07:30:00 MSK
would run now: yes (run)
would wait until: 07:41
calendar: isdayoff.ru
schedule: today 07:41 / 16:43
steps of one attempt:
  1. log in to the Horizon portal
  ...
```

`would run now` is the decision the run loop would take on its first attempt: now, or,
when the run would first wait for its drawn moment, at that moment. `would wait until`
appears only then. Under `--force` the parenthesis reads
`(run, forced: window and calendar ignored)` and nothing is waited for. The calendar
line is `isdayoff.ru`, `isdayoff.ru unreachable, Mon-Fri rule` or `not asked (forced)`.
`schedule:` names the day's drawn check-in and check-out moments, as the probe does.
The steps are the use case's own list followed by the loop's: the wait for the moment,
the retries and the one Telegram report.

## Environment

| Variable | Meaning |
|----------|---------|
| `HORIZON_URL` | the HTML Access portal, e.g. `https://horizon.example.com/portal/webclient/` (required) |
| `HORIZON_USERNAME`, `HORIZON_PASSWORD` | the AD account (secret; masked in every repr and log) |
| `HORIZON_DESKTOP` | the launch item's title, e.g. `DEV desktop` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | the the notification bot bot token and the owner's chat (secret) |
| `HT_TIMEZONE` | the IANA zone of every wall time: the ranges, the drawn moments and the report, default `Europe/Moscow` |
| `HT_CHECKIN_RANGE` | `HH:MM-HH:MM` the check-in moment is drawn from, default `07:30-08:10`; the check-in timer fires at its start |
| `HT_CHECKOUT_RANGE` | `HH:MM-HH:MM` the check-out moment is clipped to, default `16:30-17:10`; the check-out timer fires at its start |
| `HT_SESSION_LENGTH_MINUTES` | the check-out moment is at least this long after the check-in one when the range allows, default `540` |
| `HT_SESSION_EXTRA_MAX_MINUTES` | up to this many minutes drawn on top of the session, default `10` |
| `HT_WINDOW_GRACE_MINUTES` | how long a run's window stays open from its moment, default `5` |
| `HT_JITTER_SEED` | optional seed of the daily draw (masked in every repr, never printed); unset or blank: `HORIZON_USERNAME` in UTF-8 |
| `HT_HOLD_SECONDS` | how long the opened desktop is held in the morning, default `120` |
| `HT_CHROME_PATH` | the Chrome binary, `/usr/bin/google-chrome` on the VPS |
| `HT_ARTIFACTS_DIR` | where screenshots are written and pruned (older than 14 days) |

`HT_CHECKIN_WINDOW` and `HT_CHECKOUT_WINDOW` are no longer read: either one present
in the environment, even blank, makes every command exit 1 with
`configuration error: HT_CHECKIN_WINDOW: ...` naming its successors.

## Source

`src/horizon_tracker/cli.py`

## Dependencies

- Depends on: `application`, `infrastructure`
- Used by: the systemd timers on the VPS
