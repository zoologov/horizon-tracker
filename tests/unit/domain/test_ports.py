"""Unit tests for the ports: the error contract and the import boundary of the core."""

import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from horizon_tracker.domain import ports
from horizon_tracker.domain.ports import (
    ArtifactStore,
    Clock,
    HorizonClient,
    HorizonClientError,
    Notifier,
    WorkingDayCalendar,
)
from horizon_tracker.domain.report import Reason, RunReport
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import DesktopStatus, SessionState

ADAPTER_PACKAGES = {"playwright", "httpx", "click", "horizon_tracker.infrastructure"}


# --- HorizonClientError ---------------------------------------------------------


def test_client_error_carries_a_reason_from_the_report_vocabulary() -> None:
    error = HorizonClientError(Reason.DESKTOP_DID_NOT_OPEN)

    assert error.reason is Reason.DESKTOP_DID_NOT_OPEN
    assert error.screenshot is None


def test_client_error_can_point_at_the_screenshot_taken_on_failure() -> None:
    shot = Path("/var/lib/horizon/shots/checkin.png")

    assert HorizonClientError(Reason.LOGIN_REJECTED, screenshot=shot).screenshot == shot


def test_client_error_text_is_its_reason_and_nothing_else() -> None:
    assert str(HorizonClientError(Reason.LOGIN_REJECTED)) == "login_rejected"


# --- the Protocols are structural: a plain class satisfies them -------------------


class _FakeClient:
    def login(self) -> None: ...

    def desktop_status(self, name: str) -> DesktopStatus:
        return DesktopStatus(name=name, state=SessionState.DISCONNECTED)

    def open_desktop(self, name: str) -> None:
        return None

    def capture_open_desktop(self) -> Path | None:
        return None

    def disconnect(self) -> None: ...

    def log_off(self, name: str) -> Path | None:
        return None

    def client_bundles(self) -> tuple[str, ...]:
        return ("app-htmlaccess.2312.js",)

    def browser_version(self) -> str:
        return "131.0.6778.85"


class _FakeCalendar:
    def is_working_day(self, day: date) -> bool | None:
        return None


class _FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[RunReport] = []

    def send(self, report: RunReport) -> None:
        self.sent.append(report)


class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 10, 20, 7, 55)

    def sleep(self, seconds: float) -> None: ...


class _FakeArtifacts:
    def screenshot_path(self, kind: RunKind) -> Path:
        return Path(f"/tmp/{kind}.png")


def test_plain_fakes_satisfy_every_port() -> None:
    client: HorizonClient = _FakeClient()
    calendar: WorkingDayCalendar = _FakeCalendar()
    notifier: Notifier = _FakeNotifier()
    clock: Clock = _FakeClock()
    artifacts: ArtifactStore = _FakeArtifacts()

    assert client.desktop_status("DEV desktop").state is SessionState.DISCONNECTED
    assert calendar.is_working_day(date(2026, 10, 20)) is None
    assert clock.now().hour == 7
    assert artifacts.screenshot_path(RunKind.CHECKIN).name == "checkin.png"
    assert notifier is not None


def test_every_port_is_a_protocol() -> None:
    for port in (HorizonClient, WorkingDayCalendar, Notifier, Clock, ArtifactStore):
        assert getattr(port, "_is_protocol", False), port.__name__


def test_the_horizon_client_port_never_takes_credentials() -> None:
    # The adapter is built with the credentials; they never cross the port.
    login = HorizonClient.login
    assert list(login.__annotations__) == ["return"]


def test_open_desktop_returns_nothing_and_capture_answers_with_a_path_or_none() -> None:
    # Opening Blast is not the photograph. The photo is a later capture, and a missing
    # one never fails the step. Logging off still answers with its own photo or None.
    assert HorizonClient.open_desktop.__annotations__["return"] is None
    capture = HorizonClient.capture_open_desktop
    assert list(capture.__annotations__) == ["return"]
    assert capture.__annotations__["return"] == Path | None
    assert HorizonClient.log_off.__annotations__["return"] == Path | None


# --- the boundary: importing the ports pulls in no adapter --------------------------


def test_importing_the_ports_loads_no_adapter_package() -> None:
    probe = f"import sys, {ports.__name__}\nprint('\\n'.join(sorted(sys.modules)))\n"
    loaded = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.split()

    assert ports.__name__ in loaded  # the probe really imported the module under test
    leaked = [
        module
        for module in loaded
        if any(module == pkg or module.startswith(f"{pkg}.") for pkg in ADAPTER_PACKAGES)
    ]
    assert leaked == []
