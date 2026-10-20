# Infrastructure

Adapters behind the ports the domain declares.

## Source

`src/horizon_tracker/infrastructure/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `horizon_playwright.py` | drives the Horizon HTML Access web client in headless Chrome: the `HorizonClient` port (`PlaywrightHorizonClient`, keyword constructor; the "desktop is open" signal is isolated in one method and marked a hypothesis until the first probe on the VPS) |
| `isdayoff.py` | asks the isdayoff.ru production calendar whether a date is a working day: the `WorkingDayCalendar` port; any failure answers `None` |
| `telegram.py` | delivers run reports to the owner's Telegram chat through the Bot API: the `Notifier` port (`TelegramNotifier(token, chat_id, client)`); a send failure is logged, never raised, and the token is filtered out of httpx log lines |
| `config.py` | reads the service's settings from environment variables and refuses an incomplete set (`Settings.from_env`, `ConfigError`); `repr` masks the password, token, username and chat id |
| `clock.py` | the `Clock` port on the system's wall clock in the service's time zone (`SystemClock`) |
| `artifacts.py` | the `ArtifactStore` port on a directory: names screenshots and rotates them (`prune()` is called once per run by the CLI) |

Adapter tests never reach the real portal: the Playwright adapter runs against a
static copy of the client's markup under `tests/fixtures/htmlaccess/` served on
localhost, and the HTTP adapters run on `httpx.MockTransport`.

## Features

(none yet — added as the work lands)

## Dependencies

- Depends on: `domain` (the ports it implements)
- Used by: `cli`
