# Infrastructure

Adapters behind the ports the domain declares.

## Source

`src/horizon_tracker/infrastructure/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `horizon_playwright.py` | drives the Horizon HTML Access web client in headless Chrome: the `HorizonClient` port (`PlaywrightHorizonClient`, keyword constructor; `client_bundles()` reads `index.html` without logging in, `browser_version()` starts Chrome headless and opens no page; `close()` is best-effort and logs a teardown error by its type; the "desktop is open" signal and the tile's session state are each isolated in one method and marked a hypothesis; `log_off()` confirms on a freshly loaded launch-items list, never on the flag the client clears on OK) |
| `isdayoff.py` | asks the isdayoff.ru production calendar whether a date is a working day: the `WorkingDayCalendar` port; any failure answers `None` |
| `telegram.py` | delivers run reports to the owner's Telegram chat through the Bot API: the `Notifier` port (`TelegramNotifier(token, chat_id, client)`); a send failure is logged, never raised, and the token is filtered out of httpx log lines |
| `config.py` | reads the service's settings from environment variables and refuses an incomplete set (`Settings.from_env`, `ConfigError`); `repr` masks the password, token, username and chat id |
| `clock.py` | the `Clock` port on the system's wall clock in the service's time zone (`SystemClock`) |
| `artifacts.py` | the `ArtifactStore` port on a directory: names screenshots and rotates them (`prune()` is called once per run by the CLI, best-effort) |

Adapter tests never reach the real portal: the Playwright adapter runs against a
static copy of the client's markup under `tests/fixtures/htmlaccess/` served on
localhost (`tests/integration/infrastructure/`), and the HTTP adapters run on
`httpx.MockTransport`.

## Features

Each feature has a `SPEC.md` (Purpose, How it works, Invariants, API, Testing):

- **[Horizon Playwright client](features/horizon-playwright-client/SPEC.md)** —
  `horizon_playwright.py`: the web client walked in headless Chrome, screenshots only
  after the login page.
- **[isdayoff.ru calendar](features/isdayoff-calendar/SPEC.md)** — `isdayoff.py`: the
  day code turned into `True`, `False` or `None`.
- **[Telegram notifier](features/telegram-notifier/SPEC.md)** — `telegram.py`: a photo
  or a text message, never a raised failure, never a logged token.
- **[Settings](features/settings/SPEC.md)** — `config.py`: the environment variables,
  their defaults and checks, and the masked `repr`.
- **[Artifact store](features/artifact-store/SPEC.md)** — `artifacts.py`: screenshot
  names and the 14-day rotation.
- **[System clock](features/system-clock/SPEC.md)** — `clock.py`: the production
  `Clock`.

`config.py`, `clock.py` and `artifacts.py` are three nodes rather than one
`runtime-config` node: reading the settings and implementing two ports are three
responsibilities.

## Dependencies

- Depends on: `domain` (the ports it implements)
- Used by: `cli`
