"""The ports: what the core needs from the outside world, as ``typing.Protocol``s.

The domain declares them and the adapters in ``infrastructure`` implement them, so the
dependency points inward. Nothing here imports a browser, a network client or a CLI
framework. Credentials never cross a port: the Horizon adapter is built with them.
"""

# beadloom:domain=domain

from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from horizon_tracker.domain.report import Reason, RunReport
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import DesktopStatus


class HorizonClientError(Exception):
    """A Horizon step failed; carries a reason from the report vocabulary, never free text.

    ``screenshot`` points at the page captured on failure, if the adapter took one
    (it never captures the login page, so the screenshot cannot show the password).
    """

    def __init__(self, reason: Reason, screenshot: Path | None = None) -> None:
        super().__init__(reason.value)
        self.reason = reason
        self.screenshot = screenshot


class HorizonClient(Protocol):
    """Drives the Horizon web client; every method raises ``HorizonClientError`` on failure."""

    def login(self) -> None:
        """Authenticate on the portal with the credentials the adapter was built with."""
        ...

    def desktop_status(self, name: str) -> DesktopStatus:
        """The session state of the named desktop, read after login."""
        ...

    def open_desktop(self, name: str) -> None:
        """Open the named desktop. Returns once Blast is connected and the desktop drawn.

        The photograph of that desktop is ``capture_open_desktop``, not this call.
        """
        ...

    def capture_open_desktop(self) -> Path | None:
        """The first non-blank frame of the open remote surface, or ``None``.

        ``None`` when none appears in time, the page left the screenshot allowlist,
        or the shot failed. A missing photo never fails the step.
        """
        ...

    def disconnect(self) -> None:
        """Let the client go and leave the Windows session running."""
        ...

    def log_off(self, name: str) -> Path | None:
        """Log the Windows session of the named desktop off and wait for the confirmation.

        Answers with the path of the success screenshot of the desktop list without the
        session, ``None`` when none could be taken; a missing screenshot never fails the step.
        """
        ...

    def client_bundles(self) -> tuple[str, ...]:
        """The file names of the HTML Access client bundles the portal serves; no login."""
        ...

    def browser_version(self) -> str:
        """The version the Chrome binary reports once started headless; it opens no page."""
        ...


class WorkingDayCalendar(Protocol):
    """Answers whether a date is a working day by the production calendar."""

    def is_working_day(self, day: date) -> bool | None:
        """``True``/``False`` by the calendar, ``None`` when it could not be asked."""
        ...


class Notifier(Protocol):
    """Delivers a run report to the owner; attaches ``report.screenshot`` when present."""

    def send(self, report: RunReport) -> None:
        """Send the rendered report, with its screenshot as an attachment if it has one."""
        ...


class Clock(Protocol):
    """The service's wall clock and its way of waiting; the core never reads time itself."""

    def now(self) -> datetime:
        """The current time, aware, in the service's time zone."""
        ...

    def sleep(self, seconds: float) -> None:
        """Wait for the given number of seconds."""
        ...


class ArtifactStore(Protocol):
    """Where a run's artifacts are written."""

    def screenshot_path(self, kind: RunKind) -> Path:
        """A fresh path for a screenshot taken during a run of the given kind."""
        ...
