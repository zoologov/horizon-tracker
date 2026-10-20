"""The morning check-in: open the desktop until Windows logs on, hold it, then disconnect.

One attempt logs in, opens the desktop over Blast, holds it open for ``hold`` so the
Windows logon completes, reads the session state the broker shows, and disconnects
-- never logs off -- so the session runs on until the evening. The disconnect closes
the client, so the attempt logs in again to read the state the disconnect left.
The check-in counts only if the broker saw the transition CONNECTED -> DISCONNECTED;
then its report carries the screenshot the client took of the opened desktop, if any.
"""

# beadloom:domain=application

from dataclasses import dataclass
from datetime import timedelta

from horizon_tracker.application.windowed_run import AttemptResult, WindowedRun, in_seconds
from horizon_tracker.domain.ports import Clock, HorizonClient
from horizon_tracker.domain.report import Outcome, Reason, RunReport
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import checkin_succeeded


@dataclass(frozen=True)
class MorningCheckin:
    """Opens the named desktop over Blast, holds it for ``hold``, disconnects, reports."""

    client: HorizonClient
    clock: Clock
    runner: WindowedRun
    desktop: str
    hold: timedelta

    @property
    def kind(self) -> RunKind:
        """The check-in run."""
        return RunKind.CHECKIN

    def run(self, *, force: bool = False) -> RunReport:
        """Check in as the window allows and send the run's one report."""
        return self.runner.run(self.kind, self._attempt, force=force)

    def steps(self) -> tuple[str, ...]:
        """What ``_attempt`` does, in the owner's words; the dry run prints them."""
        return (
            "log in to the Horizon portal",
            f"open desktop {self.desktop!r} and wait for the Blast connection and a drawn desktop",
            f"hold the desktop open for {in_seconds(self.hold)} s so the Windows logon completes",
            "read the session state, then disconnect (the Windows session keeps running)",
            "log in again and confirm the session is DISCONNECTED",
        )

    def _attempt(self) -> AttemptResult:
        self.client.login()
        opened = self.client.open_desktop(self.desktop)
        opened_at = self.clock.now()
        try:
            self.clock.sleep(self.hold.total_seconds())
            while_open = self.client.desktop_status(self.desktop).state
        finally:
            self.client.disconnect()
        self.client.login()
        after_disconnect = self.client.desktop_status(self.desktop).state
        if checkin_succeeded(while_open, after_disconnect):
            return AttemptResult(Outcome.SUCCEEDED, opened_at, screenshot=opened)
        return AttemptResult(Outcome.FAILED, self.clock.now(), Reason.DESKTOP_DID_NOT_OPEN)
