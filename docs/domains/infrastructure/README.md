# Infrastructure

Adapters behind the ports the domain declares.

## Source

`src/horizon_tracker/infrastructure/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `horizon_playwright.py` | drives the Horizon HTML Access web client in headless Chrome: the `HorizonClient` port (`PlaywrightHorizonClient`, keyword constructor; `client_bundles()` reads `index.html` without logging in, `browser_version()` starts Chrome headless and opens no page; `close()` is best-effort and logs a teardown error by its type; the "desktop is open" signal and the tile's session state are each isolated in one method and marked a hypothesis; `log_off()` waits (bounded) for the broker's kill-session answer before it reloads, matching the `/broker/xml` path before it reads a request body, logs the answer as `Horizon kill-session answered: <status> after <ms> ms`, then confirms on a freshly loaded launch-items list, never on the flag the client clears on OK; `open_desktop()` returns `None` and takes no success photograph. `capture_open_desktop()` cancels a client dialog over the desktop (Cancel, never OK) and takes an element screenshot of the largest canvas or video in `#canvas-container`; the page decodes that PNG onto a 32 by 32 grid, and once at least 8 cells have `max(R, G, B) >= 24` and no dialog came into the frame the same PNG is saved, so the pixels judged are the pixels sent and the live surface is never read back. `desktop_paint_ms` (60 s) bounds the capture to within one in-page decode. A blank or dialog-covered timeout, a page closed or outside the screenshot allowlist, or a screenshot or decode error returns `None`; the module holds no PNG codec. `log_off()` answers with a screenshot of the list without the session, or `None` when it cannot be taken, which never changes the step's verdict. `success_settle_ms` is gone) |
| `isdayoff.py` | asks the isdayoff.ru production calendar whether a date is a working day: the `WorkingDayCalendar` port; any failure answers `None` |
| `telegram.py` | delivers run reports to the owner's Telegram chat through the Bot API: the `Notifier` port (`TelegramNotifier(token, chat_id, client, language)`), the text rendered through `render(report, language)` in the language it was built with (`HT_LANGUAGE`, English by default); a send failure is logged, never raised, and the token is filtered out of httpx log lines; the token discipline (`check_bot_token`, `redact_token`, `mask_token_in_httpx_log`, `bot_api_description`) is public for the bot transport |
| `telegram_bot.py` | carries the owner's messages to the bot and its replies back: the `BotTransport` port (`TelegramBotTransport(token, client)`); `poll` long-polls `getUpdates` (30 s, messages only) and returns the text messages, skipping and confirming any other update; `reply` is `sendMessage`; a refusal or network error is logged by status or type and raised as `BotTransportError`, never with the token |
| `config.py` | reads the service's settings from environment variables and refuses an incomplete set (`Settings.from_env`, `ConfigError`); `repr` masks the password, token, username, chat id and the jitter seed; it parses `HT_CHECKIN_RANGE`, `HT_CHECKOUT_RANGE`, `HT_SESSION_LENGTH_MINUTES`, `HT_SESSION_EXTRA_MAX_MINUTES`, `HT_WINDOW_GRACE_MINUTES` and the optional `HT_JITTER_SEED` into the domain's `TimeRange`/`timedelta` values, validated at load by the domain's own rules, reads `HT_LANGUAGE` (`en` by default, `ru`; `language_from_env`) and `HT_STATE_DIR` (`/opt/horizon-tracker/state` by default; `absences_file` is `absences.json` in it), and refuses the retired `HT_CHECKIN_WINDOW`/`HT_CHECKOUT_WINDOW` with a hint; a `ConfigError` carries its problem as a `Message`, English in `str`, and a refusal by the domain's rules carries the domain's reason as a `Message` too |
| `absence_store.py` | keeps the owner's absences in one JSON file: the `AbsenceStore` port (`JsonAbsenceStore(path)`); `{"last_issued": N, "absences": [...]}` with ISO dates, a missing file is the empty book, a malformed one raises `AbsenceStoreError`; the write is atomic (a temporary file, `fsync`, `os.replace`), the file 0600 and a state directory it creates 0700 |
| `clock.py` | the `Clock` port on the system's wall clock in the service's time zone (`SystemClock`) |
| `artifacts.py` | the `ArtifactStore` port on a directory: names screenshots and rotates them (`prune()` is called once per run by the CLI, best-effort) |

Adapter tests never reach the real portal: the Playwright adapter runs against a
static copy of the client's markup under `tests/fixtures/htmlaccess/` served on
localhost by `tests/support/htmlaccess_portal.py` (`tests/integration/infrastructure/`
and the scenarios of `client_dialog_in_the_photo.feature`), and the HTTP adapters run
on `httpx.MockTransport`.

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
- **[Absence store](features/absence-store/SPEC.md)** — `absence_store.py`: the
  absences file, its refusals and the atomic private write.
- **[Telegram bot transport](features/telegram-bot/SPEC.md)** — `telegram_bot.py`:
  long polling for the owner's text messages and the replies, a failure raised, never a
  logged token.

`config.py`, `clock.py` and `artifacts.py` are three nodes rather than one
`runtime-config` node: reading the settings and implementing two ports are three
responsibilities.

## Dependencies

- Depends on: `domain` (the ports it implements)
- Used by: `cli`
