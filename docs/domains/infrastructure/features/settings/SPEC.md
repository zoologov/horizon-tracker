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

`Settings.from_env(environ)` first refuses the retired `HT_CHECKIN_WINDOW` and
`HT_CHECKOUT_WINDOW`, then reads the variables below and raises `ConfigError` on the
first bad one:

| Variable | Field | Default | Check |
|----------|-------|---------|-------|
| `HORIZON_URL` | `horizon_url` | required | not blank |
| `HORIZON_USERNAME` | `username` | required, secret | not blank |
| `HORIZON_PASSWORD` | `password` | required, secret | not blank |
| `HORIZON_DESKTOP` | `desktop` | `DEV desktop` | — |
| `TELEGRAM_BOT_TOKEN` | `telegram_token` | required, secret | not blank |
| `TELEGRAM_CHAT_ID` | `telegram_chat_id` | required, secret | not blank |
| `HT_TIMEZONE` | `timezone` | `Europe/Moscow` | a known IANA zone |
| `HT_CHECKIN_RANGE` | `checkin_range` | `07:30-08:10` | `HH:MM-HH:MM`, start before end |
| `HT_CHECKOUT_RANGE` | `checkout_range` | `16:30-17:10` | `HH:MM-HH:MM`, start before end, starts after the check-in range ends |
| `HT_SESSION_LENGTH_MINUTES` | `session_length` | `540` | whole minutes 0..1440, not 0 |
| `HT_SESSION_EXTRA_MAX_MINUTES` | `session_extra_max` | `10` | whole minutes 0..1440 |
| `HT_WINDOW_GRACE_MINUTES` | `window_grace` | `5` | whole minutes 0..1440, not 0, the last window ends before midnight |
| `HT_JITTER_SEED` | `jitter_seed` | `HORIZON_USERNAME`, secret | taken verbatim in UTF-8 |
| `HT_HOLD_SECONDS` | `hold_seconds` | `120` | a whole number of seconds |
| `HT_CHROME_PATH` | `chrome_path` | `/usr/bin/google-chrome` | — |
| `HT_ARTIFACTS_DIR` | `artifacts_dir` | `/opt/horizon-tracker/artifacts` | — |
| `HT_LANGUAGE` | `language` | `en` | `en` or `ru`, exactly (`RU` is refused) |

A blank optional variable takes its default. A required variable that is missing or
blank is reported as `<VAR>: is required and not set`. A malformed optional value is
reported with the value it got; the seed, the one optional secret, is taken as it is and
never refused, so it is never reported. An unknown language is reported with the codes
that are accepted: `HT_LANGUAGE: expected one of en, ru, got 'de'`.

`HT_LANGUAGE` picks the language of what a person reads: the notification, the probe,
the dry run and a configuration error. The logs stay English. `language_from_env(environ)`
reads it on its own; `from_env` uses it, and the CLI calls it to say a configuration error
in the configured language when the rest of the settings did not load.

A refusal carries its problem as a `Message` (a catalogue key and its fields, see the
`messages` SPEC), so it reads in either language; `str(error)` is the English text, the
one the log carries.

## Invariants

- No credential has a default.
- `ConfigError` names the variable and the problem, never a credential's value, in
  every language.
- `repr` and `str` of `Settings` show `***` for `username`, `password`,
  `telegram_token`, `telegram_chat_id` and `jitter_seed`.
- One source for one fact: no field holds a window. A run's window is built by the CLI
  from the day's drawn moment and `window_grace`.
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
  `artifacts_dir: Path`, `language: Language` (`HT_LANGUAGE`, default `en`). No field
  holds a window: the CLI draws the day's moments from
  these fields and builds each run's window with `window_from`.
- `from_env` refuses `HT_CHECKIN_WINDOW` and `HT_CHECKOUT_WINDOW` when present (even
  blank), before any other check, with a hint naming their successors. Minutes are a
  whole number from 0 to 1440. The ranges, the session length and the grace are checked
  by the domain's own rules (`TimeRange`, `draw_moments`, `window_from` on the end of the
  check-out range); a refusal names the variable it concerns.
- `language_from_env(environ: Mapping[str, str]) -> Language` — `HT_LANGUAGE`, `en` when
  unset or blank; raises `ConfigError` on an unknown code.
- `ConfigError(variable: str, problem: Message)` — attributes `variable` and `problem`;
  `in_language(language) -> str` is `"<variable>: <problem>"` in that language, and the
  exception's message (`str`) is the English one.
- Variable names: `CHECKIN_RANGE`, `CHECKOUT_RANGE`, `SESSION_LENGTH`,
  `SESSION_EXTRA_MAX`, `WINDOW_GRACE`, `JITTER_SEED`, `LANGUAGE`.
- Defaults: `DEFAULT_DESKTOP`, `DEFAULT_TIMEZONE`, `DEFAULT_CHECKIN_RANGE`,
  `DEFAULT_CHECKOUT_RANGE`, `DEFAULT_SESSION_LENGTH_MINUTES`,
  `DEFAULT_SESSION_EXTRA_MAX_MINUTES`, `DEFAULT_WINDOW_GRACE_MINUTES`,
  `DEFAULT_HOLD_SECONDS`, `DEFAULT_CHROME_PATH`, `DEFAULT_ARTIFACTS_DIR`; `MASK` (`"***"`).

The CLI logs a `ConfigError` on stderr as `configuration error: <VAR>: <problem>` in
English and exits 1; when the configured language is not English it also prints the
error in that language on stderr, the catalogue's `config.error` text, which `ru` renders in Russian
(`docs/services/cli.md`).

## Testing

Tests: `tests/unit/infrastructure/test_config.py`, `tests/unit/test_cli.py`. Every
acceptance scenario starts from `Settings.from_env` through the CLI.

## Dependencies

Derived from the imports on reindex.

- Depends on: `schedule`, `messages`
- Used by: `cli`

## Parent

`infrastructure` — [infrastructure README](../../README.md)
