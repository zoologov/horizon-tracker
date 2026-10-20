"""The evening check-out: log the desktop's Windows session off and confirm it ended.

One attempt logs in, reads the session state the broker shows and, if a session
exists, logs it off from the tile menu and reads the state again. A desktop that had
no session when the run first looked is reported as already logged off and the run
stops; there is nothing to log off and nothing to retry. A confirmed check-out
reports the screenshot the client took of the launch list after its log off, if any.

The state the run first saw is kept across its attempts: if a log off went through
but its confirmation was lost, the retry finds no session and counts the run as the
check-out it was, not as "already logged off".
"""

# beadloom:domain=application

from dataclasses import dataclass
from pathlib import Path

from horizon_tracker.application.windowed_run import AttemptResult, WindowedRun
from horizon_tracker.domain.ports import Clock, HorizonClient
from horizon_tracker.domain.report import Outcome, Reason, RunReport
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import SessionState, checkout_succeeded


@dataclass(frozen=True)
class EveningCheckout:
    """Logs the named desktop off from its tile menu and confirms the session is gone."""

    client: HorizonClient
    clock: Clock
    runner: WindowedRun
    desktop: str

    @property
    def kind(self) -> RunKind:
        """The check-out run."""
        return RunKind.CHECKOUT

    def run(self, *, force: bool = False) -> RunReport:
        """Check out as the window allows and send the run's one report."""
        attempt = _CheckoutAttempt(self.client, self.clock, self.desktop)
        return self.runner.run(self.kind, attempt, force=force)

    def steps(self) -> tuple[str, ...]:
        """What one ``_CheckoutAttempt`` does, in the owner's words; the dry run prints them."""
        return (
            "log in to the Horizon portal",
            f"read the session state of desktop {self.desktop!r}; stop if there is no session",
            "log off from the tile menu and confirm the dialog",
            "confirm the session is gone (NO_SESSION)",
        )


class _CheckoutAttempt:
    """One run's check-out attempts, remembering the state the run first saw."""

    def __init__(self, client: HorizonClient, clock: Clock, desktop: str) -> None:
        self._client = client
        self._clock = clock
        self._desktop = desktop
        self._before: SessionState | None = None

    def __call__(self) -> AttemptResult:
        self._client.login()
        state = self._client.desktop_status(self._desktop).state
        if self._before is None:
            self._before = state
        before = self._before
        logged_off: Path | None = None
        if state.has_session:
            logged_off = self._client.log_off(self._desktop)
            state = self._client.desktop_status(self._desktop).state
        if checkout_succeeded(before, state):
            return AttemptResult(Outcome.SUCCEEDED, self._clock.now(), screenshot=logged_off)
        if not before.has_session:
            return AttemptResult(Outcome.SKIPPED, self._clock.now(), Reason.ALREADY_LOGGED_OFF)
        return AttemptResult(Outcome.FAILED, self._clock.now(), Reason.LOGOFF_NOT_CONFIRMED)
