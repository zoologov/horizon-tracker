"""Unit tests for the ports: the error contract and the import boundary of the core."""

import dataclasses
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from horizon_tracker.domain import ports
from horizon_tracker.domain.absence import AbsenceBook
from horizon_tracker.domain.ports import (
    AbsenceStore,
    AbsenceStoreError,
    ArtifactStore,
    BotTransport,
    BotTransportError,
    Clock,
    HorizonClient,
    HorizonClientError,
    IncomingMessage,
    Notifier,
    WorkingDayCalendar,
)
from horizon_tracker.domain.report import Reason, RunReport
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import DesktopStatus, SessionState
from tests.support.fakes import FakeAbsenceStore

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


class _FakeAbsenceStore:
    def __init__(self) -> None:
        self.book = AbsenceBook()

    def load(self) -> AbsenceBook:
        return self.book

    def save(self, book: AbsenceBook) -> None:
        self.book = book


class _FakeBotTransport:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def poll(self, offset: int | None) -> tuple[IncomingMessage, ...]:
        return (IncomingMessage(update_id=offset or 1, chat_id="42", text="/list"),)

    def reply(self, chat_id: str, text: str) -> None:
        self.replies.append((chat_id, text))


def test_plain_fakes_satisfy_every_port() -> None:
    client: HorizonClient = _FakeClient()
    calendar: WorkingDayCalendar = _FakeCalendar()
    notifier: Notifier = _FakeNotifier()
    clock: Clock = _FakeClock()
    artifacts: ArtifactStore = _FakeArtifacts()
    absences: AbsenceStore = _FakeAbsenceStore()
    transport: BotTransport = _FakeBotTransport()

    assert client.desktop_status("DEV desktop").state is SessionState.DISCONNECTED
    assert calendar.is_working_day(date(2026, 10, 20)) is None
    assert clock.now().hour == 7
    assert artifacts.screenshot_path(RunKind.CHECKIN).name == "checkin.png"
    assert notifier is not None
    assert absences.load() == AbsenceBook()
    assert transport.poll(None)[0].text == "/list"


def test_every_port_is_a_protocol() -> None:
    every_port = (
        HorizonClient,
        WorkingDayCalendar,
        Notifier,
        Clock,
        ArtifactStore,
        AbsenceStore,
        BotTransport,
    )
    for port in every_port:
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


# --- the absence store and the bot transport ----------------------------------------


def test_the_absence_store_loads_and_saves_a_whole_book() -> None:
    assert AbsenceStore.load.__annotations__ == {"return": AbsenceBook}
    assert AbsenceStore.save.__annotations__ == {"book": AbsenceBook, "return": None}


def test_the_shared_fake_store_keeps_one_book_and_plays_a_broken_file_and_a_failed_save() -> None:
    fake = FakeAbsenceStore()
    store: AbsenceStore = fake
    book = AbsenceBook(last_issued=3)

    store.save(book)
    fake.fail_save = True
    with pytest.raises(AbsenceStoreError):
        store.save(AbsenceBook())
    assert store.load() == book
    fake.broken = True
    with pytest.raises(AbsenceStoreError):
        store.load()
    assert (fake.saved, fake.loads) == ([book], 2)


def test_the_bot_transport_polls_from_an_offset_and_replies_to_a_chat() -> None:
    assert BotTransport.poll.__annotations__ == {
        "offset": int | None,
        "return": tuple[IncomingMessage, ...],
    }
    assert BotTransport.reply.__annotations__ == {"chat_id": str, "text": str, "return": None}


def test_an_incoming_message_carries_its_update_id_its_chat_and_its_text() -> None:
    message = IncomingMessage(update_id=7, chat_id="-100", text="/add vacation 03.11-14.11")

    assert (message.update_id, message.chat_id, message.text) == (
        7,
        "-100",
        "/add vacation 03.11-14.11",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.text = "/list"  # type: ignore[misc]  # the assignment is the thing under test


def test_an_absence_store_error_names_the_file_and_what_is_wrong_with_it() -> None:
    path = Path("/opt/horizon-tracker/state/absences.json")

    error = AbsenceStoreError(path, "not valid JSON")

    assert error.path == path
    assert error.detail == "not valid JSON"
    assert str(error) == "/opt/horizon-tracker/state/absences.json: not valid JSON"


def test_a_bot_transport_error_is_an_exception_of_its_own() -> None:
    assert issubclass(BotTransportError, Exception)
    assert not issubclass(BotTransportError, HorizonClientError)


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
