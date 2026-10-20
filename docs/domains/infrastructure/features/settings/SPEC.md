# Settings

Reads the service's settings from environment variables, refuses an incomplete set by
naming the variable, and never renders a credential.

## Source

`src/horizon_tracker/infrastructure/config.py`

## Specification

### Purpose

The composition root needs every value the adapters are built with, read once at the
start of a command. On the VPS the values come from `/opt/horizon-tracker/.env`, which
systemd reads as an `EnvironmentFile`. A missing or malformed value must stop the
command before anything is built, and a credential must never appear in an error, a
`repr` or a log.

### How it works

`Settings.from_env(environ)` reads the variables below and raises `ConfigError` on the
first bad one, in the order of the table:

| Variable | Field | Default | Check |
|----------|-------|---------|-------|
| `HORIZON_URL` | `horizon_url` | required | not blank |
| `HORIZON_USERNAME` | `username` | required, secret | not blank |
| `HORIZON_PASSWORD` | `password` | required, secret | not blank |
| `HORIZON_DESKTOP` | `desktop` | `DEV desktop` | — |
| `TELEGRAM_BOT_TOKEN` | `telegram_token` | required, secret | not blank |
| `TELEGRAM_CHAT_ID` | `telegram_chat_id` | required, secret | not blank |
| `HT_TIMEZONE` | `timezone` | `Europe/Moscow` | a known IANA zone |
| `HT_CHECKIN_WINDOW` | `checkin_window` | `07:55-08:00` | `HH:MM-HH:MM`, start before end |
| `HT_CHECKOUT_WINDOW` | `checkout_window` | `17:00-17:05` | `HH:MM-HH:MM`, start before end |
| `HT_HOLD_SECONDS` | `hold_seconds` | `120` | a whole number of seconds |
| `HT_CHROME_PATH` | `chrome_path` | `/usr/bin/google-chrome` | — |
| `HT_ARTIFACTS_DIR` | `artifacts_dir` | `/opt/horizon-tracker/artifacts` | — |

A blank optional variable takes its default. A required variable that is missing or
blank is reported as `<VAR>: is required and not set`. A malformed optional value is
reported with the value it got, because none of the optional variables is a secret.

## Invariants

- No credential has a default.
- `ConfigError` names the variable and the problem, never a credential's value.
- `repr` and `str` of `Settings` show `***` for `username`, `password`,
  `telegram_token` and `telegram_chat_id`.
- A `Settings` exists only for a complete, well-formed set of variables.

## API

Module `src/horizon_tracker/infrastructure/config.py`:

- `Settings` — frozen; classmethod `from_env(environ: Mapping[str, str]) -> Settings`.
  Fields: `horizon_url: str`, `username: str`, `password: str`, `desktop: str`,
  `telegram_token: str`, `telegram_chat_id: str`, `timezone: ZoneInfo`,
  `checkin_range: TimeRange` (`HT_CHECKIN_RANGE`, default `07:30-08:10`),
  `checkout_range: TimeRange` (`HT_CHECKOUT_RANGE`, default `16:30-17:10`),
  `session_length: timedelta` (`HT_SESSION_LENGTH_MINUTES`, default `540`),
  `session_extra_max: timedelta` (`HT_SESSION_EXTRA_MAX_MINUTES`, default `10`),
  `window_grace: timedelta` (`HT_WINDOW_GRACE_MINUTES`, default `5`),
  `jitter_seed: bytes` (`HT_JITTER_SEED` verbatim in UTF-8; unset or blank -> the
  username in UTF-8; masked), `hold_seconds: int`, `chrome_path: Path`,
  `artifacts_dir: Path`, and, until the CLI builds each run's window from the drawn
  moment (HT-003 BEAD-04), `checkin_window: Window` / `checkout_window: Window` fixed at
  `HT001_CHECKIN_WINDOW` (`07:55-08:00`) / `HT001_CHECKOUT_WINDOW` (`17:00-17:05`), set by
  no variable.
- `from_env` refuses `HT_CHECKIN_WINDOW` and `HT_CHECKOUT_WINDOW` when present (even
  blank), before any other check, with a hint naming their successors. Minutes are a
  whole number from 0 to 1440. The ranges, the session length and the grace are checked
  by the domain's own rules (`TimeRange`, `draw_moments`, `window_from` on the end of the
  check-out range); a refusal names the variable it concerns.
- `ConfigError(variable: str, problem: str)` — message `"<variable>: <problem>"`;
  attribute `variable`.
- Variable names: `CHECKIN_RANGE`, `CHECKOUT_RANGE`, `SESSION_LENGTH`,
  `SESSION_EXTRA_MAX`, `WINDOW_GRACE`, `JITTER_SEED`.
- Defaults: `DEFAULT_DESKTOP`, `DEFAULT_TIMEZONE`, `DEFAULT_CHECKIN_RANGE`,
  `DEFAULT_CHECKOUT_RANGE`, `DEFAULT_SESSION_LENGTH_MINUTES`,
  `DEFAULT_SESSION_EXTRA_MAX_MINUTES`, `DEFAULT_WINDOW_GRACE_MINUTES`,
  `DEFAULT_HOLD_SECONDS`, `DEFAULT_CHROME_PATH`, `DEFAULT_ARTIFACTS_DIR`; `MASK` (`"***"`).

The CLI logs a `ConfigError` on stderr as `configuration error: <VAR>: <problem>` and
exits 1 (`docs/services/cli.md`).

## Testing

Tests: `tests/unit/infrastructure/test_config.py`, `tests/unit/test_cli.py`. Every
acceptance scenario starts from `Settings.from_env` through the CLI.

## Dependencies

Derived from the imports on reindex.

- Depends on: `schedule`
- Used by: `cli`

## Parent

`infrastructure` — [infrastructure README](../../README.md)
