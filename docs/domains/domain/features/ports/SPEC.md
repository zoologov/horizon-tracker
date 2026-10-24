# Ports

The contracts the core needs from the outside world, declared as `typing.Protocol`s:
`HorizonClient`, `WorkingDayCalendar`, `Notifier`, `Clock`, `ArtifactStore`,
`AbsenceStore`, `BotTransport`.

## Source

`src/horizon_tracker/domain/ports.py`

## Specification

### Purpose

The domain declares what it needs and the adapters in `infrastructure` implement it,
so every dependency points inward. This module has no behaviour beyond the
constructors of its errors and of `IncomingMessage`. It is a node of its own rather than a part of
`session-state`, because it is the boundary of the whole core: it names the report,
the schedule and the session types, and folding it into one of them would give that
module a second responsibility.

### How it works

| Port | What the core asks of it | Production adapter |
|------|--------------------------|--------------------|
| `HorizonClient` | drive the Horizon web client | `PlaywrightHorizonClient` |
| `WorkingDayCalendar` | `is_working_day(day)` → `True`, `False` or `None` | `IsDayOffCalendar` |
| `Notifier` | `send(report)`, with `report.screenshot` attached when present | `TelegramNotifier` |
| `Clock` | `now()` (aware, in the service's zone) and `sleep(seconds)` | `SystemClock` |
| `ArtifactStore` | `screenshot_path(kind)`, a fresh path for one screenshot | `DirectoryArtifactStore` |
| `AbsenceStore` | `load()` the `AbsenceBook` last saved (empty when none was), `save(book)` the whole book or nothing | `JsonAbsenceStore` |
| `BotTransport` | `poll(offset)` the owner's messages as `IncomingMessage`s, `reply(chat_id, text)` | `TelegramBotTransport` |

`HorizonClient` answers two kinds of question. The run's methods log in and act on a
desktop: `login`, `desktop_status`, `open_desktop`, `capture_open_desktop`,
`disconnect`, `log_off`. `open_desktop` returns `None` once the desktop is open and
takes no photograph. `capture_open_desktop` answers with the path of the first
non-blank frame of the open remote surface, or `None` when none appears in time, the
page left the screenshot allowlist, or the shot failed. `log_off` answers with the
path of a screenshot of the desktop list without the session, or `None` when none
could be taken. A missing screenshot never fails the step. Checkout still calls
`log_off` and does not call `capture_open_desktop`. The probe's methods never log in
and each answers one question, so each can fail on its own:

- `client_bundles()` — the file names of the HTML Access client bundles the portal
  serves in `index.html`;
- `browser_version()` — the version the Chrome binary reports once started headless;
  it opens no page.

A Chrome that does not start therefore fails `browser_version()` and is never read as
an unreachable portal.

`AbsenceStore` keeps the owner's absences between runs as one `AbsenceBook` (the
absences and the highest id ever issued, see the `absence` SPEC). `load()` answers an
empty book when nothing was saved yet. `save(book)` replaces the stored book as a whole,
and a save that fails leaves the previous one in place. Both raise `AbsenceStoreError`,
which names the file and what is wrong with it, so a use case can treat a broken store as
empty and say why without knowing the adapter. The error lives here, not with the
adapter, because the application catches it.

`BotTransport` carries the owner's text messages to the bot and the replies back.
`poll(offset)` answers the messages from `offset` on (every pending one when `None`) as
frozen `IncomingMessage(update_id, chat_id, text)` values, and `reply(chat_id, text)`
sends one text. Both raise `BotTransportError` on a failure. Like the Horizon adapter, the
transport is built with its secret, the bot token, and the token never crosses the port.

Every `HorizonClient` method raises `HorizonClientError` on failure. The error carries a
`Reason` from the report vocabulary and, optionally, the path of the screenshot the
adapter took; its text is the reason's value and nothing else.

## Invariants

- No port method takes a credential: the Horizon adapter is built with the account,
  and the password never crosses a port.
- Importing this module loads no adapter package: no browser, no HTTP client, no CLI
  framework.
- `HorizonClientError` carries a `Reason`, never free text; `str(error)` is
  `reason.value`.
- `AbsenceStoreError` carries the file's path and a short technical `detail`;
  `str(error)` is `<path>: <detail>`. The absences file holds no secret.
- `BotTransportError` never carries the bot token.
- The adapter never photographs the login page, so a `screenshot` cannot show the
  password.

## API

Module `src/horizon_tracker/domain/ports.py`:

- `HorizonClientError(reason: Reason, screenshot: Path | None = None)` — attributes
  `reason`, `screenshot`.
- `HorizonClient` — `login() -> None`, `desktop_status(name) -> DesktopStatus`,
  `open_desktop(name) -> None`, `capture_open_desktop() -> Path | None`,
  `disconnect() -> None`, `log_off(name) -> Path | None`,
  `client_bundles() -> tuple[str, ...]`, `browser_version() -> str`.
- `WorkingDayCalendar` — `is_working_day(day: date) -> bool | None`.
- `Notifier` — `send(report: RunReport) -> None`.
- `Clock` — `now() -> datetime`, `sleep(seconds: float) -> None`.
- `ArtifactStore` — `screenshot_path(kind: RunKind) -> Path`.
- `AbsenceStore` — `load() -> AbsenceBook`, `save(book: AbsenceBook) -> None`.
- `AbsenceStoreError(path: Path, detail: str)` — attributes `path`, `detail`.
- `BotTransport` — `poll(offset: int | None) -> tuple[IncomingMessage, ...]`,
  `reply(chat_id: str, text: str) -> None`.
- `IncomingMessage(update_id: int, chat_id: str, text: str)` — frozen.
- `BotTransportError` — an `Exception` of its own.

## Testing

Tests: `tests/unit/domain/test_ports.py` (every port is a `Protocol`, plain fakes
satisfy them, the Horizon port takes no credential, `open_desktop` returns `None`,
`capture_open_desktop` and `log_off` answer `Path | None`, the absence store loads and
saves a whole `AbsenceBook`, the bot transport polls from an offset and replies to a
chat, the errors name what they carry, importing the module loads no adapter). The shared
`FakeAbsenceStore` is checked against the port there as well. The adapters are checked
against their port in their own tests, for
example `test_the_client_satisfies_the_horizon_port` in
`tests/integration/infrastructure/test_horizon_playwright.py`. The fakes the
acceptance suite runs on live in `tests/support/fakes.py`.

Scenario: `tests/acceptance/features/checks_without_login.feature`,
`Probe reports the portal version without logging in`. Its last checks hold the two-method
contract: the portal is asked for its client bundles, Chrome for its version, and nothing
else.

## Dependencies

Derived from the imports on reindex.

- Depends on: `absence`, `run-report`, `schedule`, `session-state`
- Used by: `absence-store`, `artifact-store`, `cli`, `evening-checkout`, `horizon-playwright-client`, `morning-checkin`, `probe`, `windowed-run`

## Parent

`domain` — [domain README](../../README.md)
