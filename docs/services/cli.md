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
| `horizon probe` | check the settings, the portal (HTML Access bundles, no login), the calendar and the Chrome binary | 1 if the portal or Chrome check FAILED; an unreachable calendar is DEGRADED and keeps 0 |
| `horizon --version`, `horizon --help` | version; the three commands | 0 |

`--force` ignores the window and the calendar (a manual run from the VPS; the
report says the calendar was not asked). `--dry-run` prints the plan to stdout
and exits 0: it never calls login or any other Horizon method, sends no Telegram
report and prunes nothing. The two flags combine.

A configuration error is logged on stderr as `configuration error: <VAR>:
<problem>` without the credential's value, and every command exits 1. The retry
policy is a CLI constant (3 attempts, 30 s apart, still bounded by the window).

## Output

- stdout: only the dry-run plan and the probe lines (`settings:`, `portal:`,
  `calendar:`, `chrome:`).
- stderr: logging at INFO on the `horizon_tracker` logger; under systemd the
  journal captures it, so there is no log file and no rotation code.

## Environment

| Variable | Meaning |
|----------|---------|
| `HORIZON_URL` | the HTML Access portal, e.g. `https://horizon.example.com/portal/webclient/` (required) |
| `HORIZON_USERNAME`, `HORIZON_PASSWORD` | the AD account (secret; masked in every repr and log) |
| `HORIZON_DESKTOP` | the launch item's title, e.g. `DEV desktop` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | the the notification bot bot token and the owner's chat (secret) |
| `HT_TIMEZONE` | `Europe/Moscow` |
| `HT_CHECKIN_WINDOW`, `HT_CHECKOUT_WINDOW` | `HH:MM-HH:MM`, e.g. `07:55-08:00` and `17:00-17:05` |
| `HT_HOLD_SECONDS` | how long the opened desktop is held in the morning |
| `HT_CHROME_PATH` | the Chrome binary, `/usr/bin/google-chrome` on the VPS |
| `HT_ARTIFACTS_DIR` | where screenshots are written and pruned (older than 14 days) |

## Source

`src/horizon_tracker/cli.py`

## Dependencies

- Depends on: `application`, `infrastructure`
- Used by: the systemd timers on the VPS
