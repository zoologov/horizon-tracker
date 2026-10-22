# Infrastructure

Adapters behind the ports the domain declares.

## Source

`src/horizon_tracker/infrastructure/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `horizon_playwright.py` | drives the Horizon HTML Access web client in headless Chrome: the `HorizonClient` port (`PlaywrightHorizonClient`, keyword constructor; `client_bundles()` reads `index.html` without logging in, `browser_version()` starts Chrome headless and opens no page; `close()` is best-effort and logs a teardown error by its type; the "desktop is open" signal and the tile's session state are each isolated in one method and marked a hypothesis; `log_off()` waits (bounded) for the broker's kill-session answer before it reloads, matching the `/broker/xml` path before it reads a request body, logs the answer as `Horizon kill-session answered: <status> after <ms> ms`, then confirms on a freshly loaded launch-items list, never on the flag the client clears on OK; `open_desktop()` returns `None` and takes no success photograph. `capture_open_desktop()` polls an element screenshot of the largest canvas or video in `#canvas-container` until a 32 by 32 sample has at least 8 pixels with `max(R, G, B) >= 24`, bounded by `desktop_paint_ms` (60 s), and saves that PNG. A blank timeout, a page outside the screenshot allowlist, or a screenshot error returns `None`. `log_off()` answers with a screenshot of the list without the session, or `None` when it cannot be taken, which never changes the step's verdict. `success_settle_ms` is gone) |
| `isdayoff.py` | asks the isdayoff.ru production calendar whether a date is a working day: the `WorkingDayCalendar` port; any failure answers `None` |
| `telegram.py` | delivers run reports to the owner's Telegram chat through the Bot API: the `Notifier` port (`TelegramNotifier(token, chat_id, client, language)`), the text rendered through `render(report, language)` in the language it was built with (`HT_LANGUAGE`, English by default); a send failure is logged, never raised, and the token is filtered out of httpx log lines |
| `config.py` | reads the service's settings from environment variables and refuses an incomplete set (`Settings.from_env`, `ConfigError`); `repr` masks the password, token, username, chat id and the jitter seed; it parses `HT_CHECKIN_RANGE`, `HT_CHECKOUT_RANGE`, `HT_SESSION_LENGTH_MINUTES`, `HT_SESSION_EXTRA_MAX_MINUTES`, `HT_WINDOW_GRACE_MINUTES` and the optional `HT_JITTER_SEED` into the domain's `TimeRange`/`timedelta` values, validated at load by the domain's own rules, reads `HT_LANGUAGE` (`en` by default, `ru`; `language_from_env`), and refuses the retired `HT_CHECKIN_WINDOW`/`HT_CHECKOUT_WINDOW` with a hint; a `ConfigError` carries its problem as a `Message`, English in `str`, and a refusal by the domain's rules carries the domain's reason as a `Message` too |
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
