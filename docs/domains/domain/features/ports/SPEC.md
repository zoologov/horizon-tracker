# Ports

The contracts the core needs from the outside world, declared as `typing.Protocol`s:
`HorizonClient`, `WorkingDayCalendar`, `Notifier`, `Clock`, `ArtifactStore`.

## Source

`src/horizon_tracker/domain/ports.py`

## Specification

### Purpose

The domain declares what it needs and the adapters in `infrastructure` implement it,
so every dependency points inward. This module has no behaviour beyond the
`HorizonClientError` constructor. It is a node of its own rather than a part of
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

## Testing

Tests: `tests/unit/domain/test_ports.py` (every port is a `Protocol`, plain fakes
satisfy them, the Horizon port takes no credential, `open_desktop` returns `None`,
`capture_open_desktop` and `log_off` answer `Path | None`, importing the module loads
no adapter). The adapters are checked
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

- Depends on: `run-report`, `schedule`, `session-state`
- Used by: `artifact-store`, `cli`, `evening-checkout`, `horizon-playwright-client`, `morning-checkin`, `probe`, `windowed-run`

## Parent

`domain` — [domain README](../../README.md)
