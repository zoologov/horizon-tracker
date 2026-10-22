"""In-memory fakes of the domain ports, recording what the use cases asked of them.

Each fake models the one thing a use case can observe through its port and nothing
more. The Horizon fake keeps a single desktop's session state the way the broker
would move it; a scripted failure is queued per method and raised on its next call.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from horizon_tracker.domain.report import RunReport
from horizon_tracker.domain.session import DesktopStatus, SessionState

# The port methods that change the desktop's state, so a lost confirmation means something.
_EFFECTFUL = frozenset({"open_desktop", "disconnect", "log_off"})


@dataclass
class FakeClock:
    """A wall clock that stands still until someone sleeps; records every sleep."""

    current: datetime
    sleeps: list[float] = field(default_factory=list)

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


@dataclass
class FakeCalendar:
    """Answers every date with the same answer; ``None`` plays an unreachable calendar."""

    answer: bool | None
    asked: list[date] = field(default_factory=list)

    def is_working_day(self, day: date) -> bool | None:
        self.asked.append(day)
        return self.answer


@dataclass
class FakeNotifier:
    """Keeps every report it was asked to send, in order."""

    sent: list[RunReport] = field(default_factory=list)

    def send(self, report: RunReport) -> None:
        self.sent.append(report)


@dataclass
class FakeHorizonClient:
    """One desktop behind a broker: open connects, disconnect detaches, log off ends.

    ``calls`` records each port call by method name. ``fail_on(method, error)`` queues
    an exception that a later call of ``method`` raises before it has any effect;
    ``lose_on(method, error)`` one that it raises after its effect, as a step that went
    through and whose confirmation was lost.
    ``open_connects``, ``disconnect_keeps_session`` and ``log_off_takes_effect`` script
    a broker that does not do what it was asked; ``bundles`` are the client bundles the
    portal names and ``browser`` the version the Chrome binary reports. ``success_screenshot``
    is the path ``log_off`` and ``capture_open_desktop`` answer with. ``open_desktop``
    returns nothing. ``None`` plays a screenshot that could not be taken. Given a
    ``clock``, ``called_at`` records the clock's time of each call beside ``calls``.
    """

    desktop: str
    state: SessionState = SessionState.NO_SESSION
    open_connects: bool = True
    disconnect_keeps_session: bool = True
    log_off_takes_effect: bool = True
    bundles: tuple[str, ...] = ("app-htmlaccess.fake-2312.js",)
    browser: str = "131.0.6778.85"
    success_screenshot: Path | None = None
    clock: FakeClock | None = None
    calls: list[str] = field(default_factory=list)
    called_at: list[datetime] = field(default_factory=list)
    _script: dict[str, list[Exception | None]] = field(default_factory=dict)
    _lost: dict[str, list[Exception]] = field(default_factory=dict)

    def fail_on(self, method: str, error: Exception, *, times: int = 1, after: int = 0) -> None:
        """Let the next ``after`` calls of ``method`` pass, then raise ``error`` ``times`` times."""
        self._script.setdefault(method, []).extend([None] * after + [error] * times)

    def lose_on(self, method: str, error: Exception, *, times: int = 1) -> None:
        """Let the next ``times`` calls of ``method`` take effect, then raise ``error``."""
        if method not in _EFFECTFUL:
            raise ValueError(f"{method} has no effect to lose the confirmation of")
        self._lost.setdefault(method, []).extend([error] * times)

    def _leave(self, method: str) -> None:
        queued = self._lost.get(method)
        if queued:
            raise queued.pop(0)

    def _enter(self, method: str, name: str | None = None) -> None:
        self.calls.append(method)
        if self.clock is not None:
            self.called_at.append(self.clock.now())
        if name is not None and name != self.desktop:
            raise AssertionError(f"use case asked for desktop {name!r}, not {self.desktop!r}")
        queued = self._script.get(method)
        if queued:
            error = queued.pop(0)
            if error is not None:
                raise error

    def login(self) -> None:
        self._enter("login")

    def desktop_status(self, name: str) -> DesktopStatus:
        self._enter("desktop_status", name)
        return DesktopStatus(name=name, state=self.state)

    def open_desktop(self, name: str) -> None:
        self._enter("open_desktop", name)
        if self.open_connects:
            self.state = SessionState.CONNECTED
        self._leave("open_desktop")

    def capture_open_desktop(self) -> Path | None:
        self._enter("capture_open_desktop")
        return self.success_screenshot

    def disconnect(self) -> None:
        self._enter("disconnect")
        if self.state is SessionState.CONNECTED:
            self.state = (
                SessionState.DISCONNECTED
                if self.disconnect_keeps_session
                else SessionState.NO_SESSION
            )
        self._leave("disconnect")

    def log_off(self, name: str) -> Path | None:
        self._enter("log_off", name)
        if self.log_off_takes_effect:
            self.state = SessionState.NO_SESSION
        self._leave("log_off")
        return self.success_screenshot

    def client_bundles(self) -> tuple[str, ...]:
        self._enter("client_bundles")
        return self.bundles

    def browser_version(self) -> str:
        self._enter("browser_version")
        return self.browser
