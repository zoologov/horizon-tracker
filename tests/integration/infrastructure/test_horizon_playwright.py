"""Tests of the Playwright Horizon client against a local HTML Access fixture, never the portal.

The fixture pages under ``tests/fixtures/htmlaccess/`` reproduce the structure the real
HTML Access 2312.1 bundle renders where the adapter reads the page: the tile, its menu
and the canvas the Blast session appends. A ``ThreadingHTTPServer`` on 127.0.0.1 serves
them and plays the broker: its XML endpoint ``/broker/xml`` (kill-session and the logout
of a credential cleanup), the fixture's own ``/fixture/*`` and a bare WebSocket handshake
on the Blast path (``/r/`` unless a test moves it), so the client's Blast connection is a
real socket the browser opens and closes.
"""

import base64
import hashlib
import json
import logging
import os
import re
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import partial
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, BrowserContext
from playwright.sync_api import Error as PlaywrightError

from horizon_tracker.domain.ports import HorizonClient, HorizonClientError
from horizon_tracker.domain.report import Reason
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import DesktopStatus, SessionState
from horizon_tracker.infrastructure import horizon_playwright
from horizon_tracker.infrastructure.horizon_playwright import (
    HorizonTimeouts,
    PlaywrightHorizonClient,
)
from tests.support.repository_root import repository_root

FIXTURE_DIR = repository_root() / "tests" / "fixtures" / "htmlaccess"
PRESET_CHROMIUM = Path("/opt/pw-browsers/chromium")

USERNAME = "jdoe"
PASSWORD = "correct-horse-battery-staple"
DESKTOP = "DEV desktop"
DESKTOP_ID = "dev-desktop-1"
OTHER_DESKTOP_ID = "test-desktop-2"
QUOTED_DESKTOP = 'Стенд "B" \\ 2'
QUOTED_DESKTOP_ID = "lab-desktop-3"

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SESSION_COOKIE = "fixture-session"

FAST = HorizonTimeouts(
    page_load_ms=10_000,
    action_ms=5_000,
    login_ms=5_000,
    desktop_open_ms=4_000,
    logoff_confirm_ms=3_000,
    poll_ms=100,
    kill_session_answer_ms=3_000,
)
# Longer than the live poll interval (1 s) the adapter once waited after OK, and well
# inside FAST.kill_session_answer_ms.
SLOW_KILL_SESSION_ANSWER_S = 1.5
# Long enough that the fixture's binary POST, sent on OK, is answered while the adapter
# still waits for the kill-session answer.
BINARY_POST_KILL_SESSION_ANSWER_S = 0.3
ADAPTER_LOGGER = "horizon_tracker.infrastructure.horizon_playwright"
KILL_SESSION_ANSWERED = re.compile(
    r"Horizon kill-session answered: (?P<status>\d{3}) after (?P<ms>\d+) ms"
)
# How long a kill-session the broker never answers holds its handler thread when the
# test does not release it first.
UNANSWERED_HOLD_S = 30.0


# --- the fixture portal ---------------------------------------------------------------


@dataclass
class PortalState:
    """What the fixture broker knows and how it is told to misbehave."""

    session: str = "none"
    refuse_blast: bool = False
    blast_path: str = "/r/"
    draw_canvas: bool = True
    ignore_logoff: bool = False
    # How many launch-items lists the broker still answers with the session after it was
    # told to log the desktop off: a broker that takes its time.
    logoff_lag_lists: int = 0
    logoff_pending: bool = False
    # False: a login's web session serves one launch-items list, so a reload of the page
    # lands on the login form (the live portal's answer to a reload is not measured).
    login_survives_reload: bool = True
    # The broker's enableCredentialCleanupForHTMLAccess: the client logs out of the
    # broker when the page unloads, which ends the web session and, in this fixture,
    # cuts off a kill-session the broker has not answered yet.
    credential_cleanup: bool = False
    # How long the broker takes to answer kill-session; it acts on it when it answers.
    kill_session_answer_s: float = 0.0
    kill_session_unanswered: bool = False
    # The HTTP status the broker answers kill-session with.
    kill_session_status: int = 200
    logoff_dialog: bool = True
    # The page posts a non-UTF-8 body to /fixture/telemetry on OK, beside the log off.
    binary_post: bool = False
    # The page sends kill-session as a synchronous XHR on OK: answered before the click returns.
    kill_session_sync: bool = False
    released: threading.Event = field(default_factory=threading.Event)
    logins: dict[str, int] = field(default_factory=dict)
    logged_out: set[str] = field(default_factory=set)
    events: list[str] = field(default_factory=list)
    user_agents: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, event: str) -> None:
        with self.lock:
            self.events.append(event)


class PortalHandler(SimpleHTTPRequestHandler):
    """Serves the fixture pages and answers the fixture broker and the Blast handshake."""

    protocol_version = "HTTP/1.1"
    state: PortalState

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output quiet."""

    def do_GET(self) -> None:
        self.state.user_agents.append(self.headers.get("User-Agent", ""))
        if self.path.startswith(self.state.blast_path):
            self._blast()
        elif self.path == "/fixture/launch-items":
            self._launch_items()
        elif self.path == "/fixture/behaviour":
            self._json(
                200,
                {
                    "draw_canvas": self.state.draw_canvas,
                    "blast_path": self.state.blast_path,
                    "credential_cleanup": self.state.credential_cleanup,
                    "logoff_dialog": self.state.logoff_dialog,
                    "binary_post": self.state.binary_post,
                    "kill_session_sync": self.state.kill_session_sync,
                },
            )
        else:
            super().do_GET()

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/broker/xml":
            self._broker_xml(raw.decode())
            return
        if self.path == "/fixture/telemetry":
            self.state.record("telemetry")
            self._json(200, {})
            return
        body: dict[str, object] = json.loads(raw or b"{}")
        if self.path == "/fixture/login":
            self._login(body)
        elif self.path == "/fixture/event":
            self.state.record(str(body["name"]))
            self._json(200, {})
        else:
            self._json(404, {})

    def _broker_xml(self, document: str) -> None:
        """The broker's XML endpoint: one ``<broker>`` document per POST, as the bundle sends."""
        if "<kill-session>" in document:
            self._kill_session()
        elif "<do-logout" in document:
            self._broker_logout()
        elif "<set-last-user-activity" in document:
            self._xml(200, "<set-last-user-activity><result>ok</result></set-last-user-activity>")
        else:
            self._json(400, {})

    def _json(self, status: int, payload: object, cookie: str | None = None) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def _xml(self, status: int, message: str) -> None:
        data = f"<?xml version='1.0' encoding='UTF-8'?><broker version='15.0'>{message}</broker>"
        self.send_response(status)
        self.send_header("Content-Type", "text/xml")
        self.send_header("Content-Length", str(len(data.encode())))
        self.end_headers()
        self.wfile.write(data.encode())

    def _login_token(self) -> str | None:
        morsel = SimpleCookie(self.headers.get("Cookie", "")).get(SESSION_COOKIE)
        if morsel is None or morsel.value not in self.state.logins:
            return None
        if morsel.value in self.state.logged_out:
            return None
        return morsel.value

    def _login(self, body: dict[str, object]) -> None:
        if body.get("username") == USERNAME and body.get("password") == PASSWORD:
            self.state.record("login-accepted")
            token = str(len(self.state.logins) + 1)
            self.state.logins[token] = 0
            self._json(200, {}, cookie=f"{SESSION_COOKIE}={token}; Path=/")
        else:
            self.state.record("login-rejected")
            self._json(401, {})

    def _launch_items(self) -> None:
        token = self._login_token()
        if token is None or (not self.state.login_survives_reload and self.state.logins[token] > 0):
            self._json(401, {})
            return
        self.state.logins[token] += 1
        if self.state.logoff_pending:
            if self.state.logoff_lag_lists > 0:
                self.state.logoff_lag_lists -= 1
            else:
                self.state.logoff_pending = False
                self.state.session = "none"
        self._json(
            200,
            [
                {"id": DESKTOP_ID, "name": DESKTOP, "session": self.state.session},
                {"id": OTHER_DESKTOP_ID, "name": "Test desktop", "session": "none"},
                {"id": QUOTED_DESKTOP_ID, "name": QUOTED_DESKTOP, "session": "none"},
            ],
        )

    def _kill_session(self) -> None:
        """Answer kill-session after the broker's delay, acting on it only if it is answered.

        A web session that ended while the answer was pending (the logout of a credential
        cleanup) cuts the request off: the session stays and nothing is answered.
        """
        token = self._login_token()
        if token is None:
            self._json(401, {})
            return
        self.state.record("kill-session")
        if self.state.kill_session_unanswered:
            self.state.released.wait(UNANSWERED_HOLD_S)
            self.close_connection = True
            return
        time.sleep(self.state.kill_session_answer_s)
        if token in self.state.logged_out:
            self.state.record("kill-session-cut-off")
            self.close_connection = True
            return
        if not self.state.ignore_logoff:
            self.state.logoff_pending = self.state.logoff_lag_lists > 0
            if not self.state.logoff_pending:
                self.state.session = "none"
        self.state.record("kill-session-answered")
        self._xml(
            self.state.kill_session_status, "<kill-session><result>ok</result></kill-session>"
        )

    def _broker_logout(self) -> None:
        """The client's logout on unload: the web session ends, the desktop's does not."""
        token = self._login_token()
        if token is not None:
            self.state.logged_out.add(token)
        self.state.record("broker-logout")
        self._xml(200, "<logout><result>ok</result></logout>")

    def _blast(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if self.state.refuse_blast or key is None:
            self._json(403, {})
            return
        accept = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest())
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept.decode())
        self.end_headers()
        self.wfile.flush()
        self.state.session = "connected"
        self.state.record("blast-open")
        self._hold_until_closed()
        if self.state.session == "connected":
            self.state.session = "disconnected"
        self.state.record("blast-closed")
        self.close_connection = True

    def _hold_until_closed(self) -> None:
        self.connection.settimeout(0.2)
        while True:
            try:
                if not self.connection.recv(4096):
                    return
            except TimeoutError:
                continue
            except OSError:
                return


class PortalServer(ThreadingHTTPServer):
    """The fixture's HTTP server; a browser hanging up mid-request is normal, not an error."""

    daemon_threads = True

    def handle_error(self, request: object, client_address: object) -> None:
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)  # type: ignore[arg-type]  # typeshed: private aliases


@dataclass(frozen=True)
class Portal:
    """A running fixture portal: its base URL and the broker state the tests steer."""

    url: str
    state: PortalState


@pytest.fixture
def portal() -> Iterator[Portal]:
    state = PortalState()
    handler = partial(type("Handler", (PortalHandler,), {"state": state}), directory=FIXTURE_DIR)
    server = PortalServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Portal(url=f"http://127.0.0.1:{server.server_address[1]}/", state=state)
    finally:
        state.released.set()
        server.shutdown()
        server.server_close()


def closed_port_url() -> str:
    """A localhost URL nothing listens on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}/"


def wait_for(condition: Callable[[], bool], seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


# --- the client under test ------------------------------------------------------------


class RecordingArtifacts:
    """An ``ArtifactStore`` that hands out paths in a temporary directory and counts asks."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.asked: list[RunKind] = []

    def screenshot_path(self, kind: RunKind) -> Path:
        self.asked.append(kind)
        return self.root / f"{kind.value}-{len(self.asked)}.png"


def chrome_for_tests() -> Path | None:
    """The browser binary: ``HT_TEST_CHROME_PATH``, the preinstalled one, or Playwright's."""
    configured = os.environ.get("HT_TEST_CHROME_PATH")
    if configured:
        return Path(configured)
    return PRESET_CHROMIUM if PRESET_CHROMIUM.exists() else None


@pytest.fixture
def artifacts(tmp_path: Path) -> RecordingArtifacts:
    root = tmp_path / "artifacts"
    root.mkdir()
    return RecordingArtifacts(root)


@pytest.fixture
def make_client(
    portal: Portal, artifacts: RecordingArtifacts
) -> Iterator[Callable[..., PlaywrightHorizonClient]]:
    built: list[PlaywrightHorizonClient] = []

    def build(
        password: str = PASSWORD,
        url: str | None = None,
        run_kind: RunKind = RunKind.CHECKIN,
        chrome_path: Path | None = None,
    ) -> PlaywrightHorizonClient:
        client = PlaywrightHorizonClient(
            horizon_url=url or portal.url,
            username=USERNAME,
            password=password,
            chrome_path=chrome_path or chrome_for_tests(),
            artifacts=artifacts,
            run_kind=run_kind,
            timeouts=FAST,
        )
        built.append(client)
        return client

    yield build
    for client in built:
        client.close()


@pytest.fixture
def client(make_client: Callable[..., PlaywrightHorizonClient]) -> PlaywrightHorizonClient:
    return make_client()


def kill_session_answers(caplog: pytest.LogCaptureFixture) -> list[re.Match[str]]:
    """The adapter's "kill-session answered" lines, each matched against the whole line."""
    return [
        match
        for record in caplog.records
        if record.name == ADAPTER_LOGGER
        and (match := KILL_SESSION_ANSWERED.fullmatch(record.getMessage())) is not None
    ]


def fails_with(reason: Reason, action: Callable[[], object]) -> HorizonClientError:
    with pytest.raises(HorizonClientError) as caught:
        action()
    assert caught.value.reason is reason
    return caught.value


# --- the port --------------------------------------------------------------------------


def test_the_client_satisfies_the_horizon_port(client: PlaywrightHorizonClient) -> None:
    port: HorizonClient = client
    assert callable(port.login)


# --- the browser's lifetime ----------------------------------------------------------------


def child_processes() -> set[int]:
    """The ids of the processes this test process has started and not yet reaped (Linux)."""
    return {
        int(pid)
        for children in Path("/proc/self/task").glob("*/children")
        for pid in children.read_text().split()
    }


@dataclass
class Starts:
    """How many Playwright drivers and browsers the client has started."""

    drivers: int = 0
    browsers: int = 0


@pytest.fixture
def starts(monkeypatch: pytest.MonkeyPatch) -> Starts:
    counted = Starts()
    real_driver = horizon_playwright.sync_playwright
    real_launch = PlaywrightHorizonClient._launch

    def driver() -> object:
        counted.drivers += 1
        return real_driver()

    def launch(client: PlaywrightHorizonClient) -> Browser:
        counted.browsers += 1
        return real_launch(client)

    monkeypatch.setattr(horizon_playwright, "sync_playwright", driver)
    monkeypatch.setattr(PlaywrightHorizonClient, "_launch", launch)
    return counted


@pytest.mark.parametrize(
    ("first_step", "browsers"),
    [("login", 1), ("browser_version", 1), ("client_bundles", 0)],
)
def test_entering_the_client_starts_nothing_until_a_step_needs_the_browser(
    make_client: Callable[..., PlaywrightHorizonClient],
    starts: Starts,
    first_step: str,
    browsers: int,
) -> None:
    # A scheduled run waits up to 40 minutes for its drawn moment with the client
    # already built: nothing may be running while it waits.
    before = child_processes()

    with make_client() as client:
        assert (starts.drivers, starts.browsers) == (0, 0)
        assert child_processes() <= before, "building or entering the client started a process"

        getattr(client, first_step)()

        assert (starts.drivers, starts.browsers) == (1, browsers)
        assert child_processes() - before, "the first step started no process"


# --- login -------------------------------------------------------------------------------


def test_login_reaches_the_launch_items(client: PlaywrightHorizonClient, portal: Portal) -> None:
    client.login()

    assert portal.state.events == ["login-accepted"]
    assert client.desktop_status(DESKTOP) == DesktopStatus(DESKTOP, SessionState.NO_SESSION)


def test_a_rejected_login_takes_no_screenshot_of_the_login_page(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
) -> None:
    client = make_client(password="wrong")

    error = fails_with(Reason.LOGIN_REJECTED, client.login)

    assert portal.state.events == ["login-rejected"]
    assert error.screenshot is None
    assert artifacts.asked == []
    assert list(artifacts.root.iterdir()) == []


def test_an_unreachable_portal_is_named(
    make_client: Callable[..., PlaywrightHorizonClient], artifacts: RecordingArtifacts
) -> None:
    client = make_client(url=closed_port_url())

    error = fails_with(Reason.PORTAL_UNREACHABLE, client.login)

    assert error.screenshot is None
    assert artifacts.asked == []
    assert error.__cause__ is None, "the Playwright error, and its text, must not ride along"


def test_the_browser_presents_an_ordinary_user_agent(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    client.login()

    assert portal.state.user_agents
    assert all("Chrome/" in agent for agent in portal.state.user_agents)
    assert not any("Headless" in agent for agent in portal.state.user_agents)


# --- desktop status ------------------------------------------------------------------


def test_a_desktop_with_a_session_reads_as_disconnected(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    portal.state.session = "disconnected"
    client.login()

    assert client.desktop_status(DESKTOP).state is SessionState.DISCONNECTED


def test_the_state_is_read_from_the_named_tile_only(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    portal.state.session = "disconnected"
    client.login()

    assert client.desktop_status("Test desktop").state is SessionState.NO_SESSION


def test_a_tile_is_found_by_a_name_with_quotes_and_a_backslash(
    client: PlaywrightHorizonClient,
) -> None:
    client.login()

    assert client.desktop_status(QUOTED_DESKTOP).state is SessionState.NO_SESSION


def test_reading_the_state_waits_for_the_tile_menu_to_close(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    # The fixture closes the menu a while after the document click. A read that returned
    # with the menu still open would make the next read click "…" on an open menu, which
    # toggles it shut: that read would find no menu and fail.
    portal.state.session = "disconnected"
    client.login()

    states = [client.desktop_status(DESKTOP).state for _ in range(3)]

    assert states == [SessionState.DISCONNECTED] * 3


@pytest.mark.parametrize("step", ["desktop_status", "open_desktop", "log_off"])
def test_an_unknown_desktop_is_not_found(
    client: PlaywrightHorizonClient, portal: Portal, step: str
) -> None:
    client.login()

    fails_with(Reason.DESKTOP_NOT_FOUND, lambda: getattr(client, step)("Nope desktop"))

    assert "blast-open" not in portal.state.events
    assert "kill-session" not in portal.state.events


# --- opening the desktop ---------------------------------------------------------------


def test_open_desktop_cancels_fullscreen_and_returns_once_blast_is_up(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    client.login()

    client.open_desktop(DESKTOP)

    assert "fullscreen-cancelled" in portal.state.events
    assert "fullscreen-accepted" not in portal.state.events
    assert portal.state.session == "connected"
    assert client.desktop_status(DESKTOP).state is SessionState.CONNECTED


def test_a_desktop_whose_blast_never_connects_did_not_open(
    client: PlaywrightHorizonClient, portal: Portal, artifacts: RecordingArtifacts
) -> None:
    portal.state.refuse_blast = True
    client.login()

    error = fails_with(Reason.DESKTOP_DID_NOT_OPEN, lambda: client.open_desktop(DESKTOP))

    assert "fullscreen-cancelled" in portal.state.events
    assert artifacts.asked == [RunKind.CHECKIN]
    assert error.screenshot is not None
    assert error.screenshot.read_bytes().startswith(b"\x89PNG")


def test_a_desktop_never_drawn_did_not_open(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    portal.state.draw_canvas = False
    client.login()

    fails_with(Reason.DESKTOP_DID_NOT_OPEN, lambda: client.open_desktop(DESKTOP))

    assert "blast-open" in portal.state.events


def test_the_blast_socket_path_does_not_decide_whether_the_desktop_opened(
    client: PlaywrightHorizonClient, portal: Portal, caplog: pytest.LogCaptureFixture
) -> None:
    # The /r/, /d/ reading is unverified without a login, so it is logged and never
    # gates the verdict: a drawn canvas over a socket on another path is an open desktop.
    caplog.set_level(logging.INFO)
    portal.state.blast_path = "/elsewhere/"
    client.login()

    client.open_desktop(DESKTOP)

    assert "blast-open" in portal.state.events
    assert client.desktop_status(DESKTOP).state is SessionState.CONNECTED
    assert "no WebSocket on a Blast path seen" in caplog.text


def test_disconnect_lets_go_and_leaves_the_windows_session_running(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    client.login()
    client.open_desktop(DESKTOP)

    client.disconnect()

    assert wait_for(lambda: portal.state.session == "disconnected")
    assert "kill-session" not in portal.state.events
    assert client.desktop_status(DESKTOP).state is SessionState.DISCONNECTED
    assert portal.state.events.count("login-accepted") == 2


# --- teardown ------------------------------------------------------------------------------


@pytest.mark.parametrize(("owner", "part"), [(Browser, "browser"), (BrowserContext, "context")])
def test_a_teardown_error_is_logged_by_type_and_never_raised(
    make_client: Callable[..., PlaywrightHorizonClient],
    owner: type[Browser] | type[BrowserContext],
    part: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A run that already reported SUCCEEDED must not exit 1 because the browser died
    # on the way out: close() is the last thing the composition root does.
    client = make_client()
    client.login()

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise PlaywrightError(f"Target closed {PASSWORD}")

    monkeypatch.setattr(owner, "close", refuse)
    client.close()
    monkeypatch.undo()

    assert f"Horizon {part} did not close: Error" in caplog.text
    assert PASSWORD not in caplog.text
    # The driver was still stopped: a second client can start one in this thread.
    make_client().login()


# --- log off -------------------------------------------------------------------------------


def test_log_off_through_the_tile_menu_ends_the_session(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    portal.state.session = "disconnected"
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    assert portal.state.events.count("kill-session") == 1
    assert "blast-open" not in portal.state.events
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_log_off_after_reading_the_state_ends_the_session(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    # The check-out's own order: read the state, then log off. The menu the read opened
    # must be closed by then, and the client's menu ignores Escape.
    portal.state.session = "disconnected"
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    assert client.desktop_status(DESKTOP).state is SessionState.DISCONNECTED
    client.log_off(DESKTOP)

    assert portal.state.events.count("kill-session") == 1
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_a_log_off_the_portal_never_confirms_fails_with_a_screenshot(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
) -> None:
    portal.state.session = "disconnected"
    portal.state.ignore_logoff = True
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    error = fails_with(Reason.LOGOFF_NOT_CONFIRMED, lambda: client.log_off(DESKTOP))

    assert "kill-session" in portal.state.events
    assert artifacts.asked == [RunKind.CHECKOUT]
    assert error.screenshot is not None
    # The check-out reads the state again; it must see the broker's session, not the
    # flag the client cleared on OK.
    assert client.desktop_status(DESKTOP).state is SessionState.DISCONNECTED


def test_a_log_off_is_confirmed_only_once_a_fresh_list_shows_the_session_gone(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    # The client hides "Log Off" the moment OK is clicked; a broker that ends the session
    # a few lists later must be waited for, not taken at the client's word.
    portal.state.session = "disconnected"
    portal.state.logoff_lag_lists = 2
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    assert portal.state.session == "none", "log_off returned before the broker ended the session"
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_a_log_off_is_confirmed_through_a_fresh_login_when_a_reload_ends_the_web_session(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    portal.state.session = "disconnected"
    portal.state.login_survives_reload = False
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    assert portal.state.events.count("kill-session") == 1
    assert portal.state.events.count("login-accepted") == 2
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_a_log_off_waits_for_the_brokers_kill_session_answer_before_reloading(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # With credential cleanup on, a reload logs out of the broker; a kill-session still
    # unanswered then is cut off and the session stays.
    caplog.set_level(logging.INFO, logger=ADAPTER_LOGGER)
    portal.state.session = "disconnected"
    portal.state.credential_cleanup = True
    portal.state.kill_session_answer_s = SLOW_KILL_SESSION_ANSWER_S
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    events = portal.state.events
    assert "kill-session-cut-off" not in events
    assert events.count("kill-session-answered") == 1
    assert events.index("kill-session-answered") < events.index("broker-logout"), (
        "the page was reloaded before the broker answered kill-session"
    )
    # The logged time is the wait's own, measured on a clock, not the bound.
    (answer,) = kill_session_answers(caplog)
    assert int(answer.group("ms")) >= SLOW_KILL_SESSION_ANSWER_S * 1000
    assert portal.state.session == "none"
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_the_kill_session_answer_is_logged_with_its_status_and_time_and_no_secret(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The live check reads the broker's answer and sizes kill_session_answer_ms from it.
    caplog.set_level(logging.INFO, logger=ADAPTER_LOGGER)
    portal.state.session = "disconnected"
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    (answer,) = kill_session_answers(caplog)
    assert answer.group("status") == "200"
    line = answer.string
    assert PASSWORD not in line
    assert USERNAME not in line
    assert "unanswered" not in caplog.text


def test_a_kill_session_answered_with_an_error_is_logged_and_the_fresh_list_decides(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Any status releases the wait; the log names it, and a broker that did not act
    # fails the log off closed.
    caplog.set_level(logging.INFO, logger=ADAPTER_LOGGER)
    portal.state.session = "disconnected"
    portal.state.kill_session_status = 500
    portal.state.ignore_logoff = True
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    fails_with(Reason.LOGOFF_NOT_CONFIRMED, lambda: client.log_off(DESKTOP))

    (answer,) = kill_session_answers(caplog)
    assert answer.group("status") == "500"


def test_the_wait_for_the_answer_is_armed_before_the_ok_click(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The page answers kill-session inside OK's click handler, so the answer is in before
    # the click returns: a wait armed after the click misses it (measured 100 of 100) and
    # sits out the bound. The fresh list still confirms, so only the log tells.
    caplog.set_level(logging.INFO, logger=ADAPTER_LOGGER)
    portal.state.session = "disconnected"
    portal.state.kill_session_sync = True
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    assert portal.state.events.count("kill-session-answered") == 1
    assert "unanswered" not in caplog.text, "the wait was armed after the answer came"
    assert len(kill_session_answers(caplog)) == 1


def test_a_log_off_whose_kill_session_is_never_answered_is_not_confirmed(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The wait for the answer is bounded; past it the fresh-list confirmation decides,
    # and a broker that never acted fails the log off closed.
    portal.state.session = "disconnected"
    portal.state.kill_session_unanswered = True
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    error = fails_with(Reason.LOGOFF_NOT_CONFIRMED, lambda: client.log_off(DESKTOP))

    assert "kill-session" in portal.state.events
    assert "kill-session-answered" not in portal.state.events
    assert "Horizon kill-session unanswered after 3000 ms" in caplog.text
    assert error.screenshot is not None
    assert client.desktop_status(DESKTOP).state is SessionState.DISCONNECTED


def test_a_log_off_whose_confirmation_never_shows_fails_without_awaiting_an_answer(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    portal.state.session = "disconnected"
    portal.state.logoff_dialog = False
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    fails_with(Reason.LOGOFF_NOT_CONFIRMED, lambda: client.log_off(DESKTOP))

    assert "kill-session" not in portal.state.events
    assert "kill-session unanswered" not in caplog.text, "a failed OK click read as no answer"


def test_an_unrelated_binary_post_while_awaiting_the_answer_does_not_fail_the_log_off(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    # Every page response passes the wait's predicate. A POST whose body is not UTF-8
    # (telemetry, an upload) answered before the kill-session must not be read as text.
    portal.state.session = "disconnected"
    portal.state.binary_post = True
    portal.state.kill_session_answer_s = BINARY_POST_KILL_SESSION_ANSWER_S
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    events = portal.state.events
    assert events.index("telemetry") < events.index("kill-session-answered"), (
        "the binary POST was not answered inside the wait"
    )
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_log_off_without_a_session_is_already_logged_off(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    client.login()

    fails_with(Reason.ALREADY_LOGGED_OFF, lambda: client.log_off(DESKTOP))

    assert "kill-session" not in portal.state.events


def test_a_checkout_of_a_desktop_without_a_session_reads_it_and_is_already_logged_off(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    # The tile menu hides "Log Off" (the hidden attribute, never disabled) when Windows
    # holds no session: the state reads NO_SESSION and a log off says so, in that order.
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION
    fails_with(Reason.ALREADY_LOGGED_OFF, lambda: client.log_off(DESKTOP))

    assert "kill-session" not in portal.state.events
    assert "blast-open" not in portal.state.events


# --- probe ---------------------------------------------------------------------------------


def test_the_client_bundles_are_named_without_logging_in(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    assert client.client_bundles() == ("app-htmlaccess.fixture.js",)
    assert portal.state.events == []


def test_the_bundles_of_an_unreachable_portal_are_named_unreachable(
    make_client: Callable[..., PlaywrightHorizonClient],
) -> None:
    client = make_client(url=closed_port_url())

    fails_with(Reason.PORTAL_UNREACHABLE, client.client_bundles)


def test_a_portal_without_the_client_is_unreachable(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    client = make_client(url=portal.url + "no-client-here/")

    fails_with(Reason.PORTAL_UNREACHABLE, client.client_bundles)


def test_the_browser_version_is_read_from_a_started_chrome_that_opens_no_page(
    client: PlaywrightHorizonClient, portal: Portal, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[str] = []
    real_close = Browser.close

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the version probe opened a context or a page")

    def record_close(browser: Browser, *args: Any, **kwargs: Any) -> None:
        closed.append(browser.version)
        real_close(browser, *args, **kwargs)

    monkeypatch.setattr(Browser, "new_context", refuse)
    monkeypatch.setattr(Browser, "new_page", refuse)
    monkeypatch.setattr(Browser, "close", record_close)

    version = client.browser_version()

    assert re.fullmatch(r"\d+(\.\d+)+", version), version
    assert closed == [version], "the started browser was not closed"
    assert portal.state.user_agents == [], "the version probe reached the portal"


def test_a_chrome_that_does_not_start_is_named(
    make_client: Callable[..., PlaywrightHorizonClient], tmp_path: Path
) -> None:
    client = make_client(chrome_path=tmp_path / "no-chrome-here")

    error = fails_with(Reason.UNEXPECTED, client.browser_version)

    assert error.screenshot is None


# --- secrets -------------------------------------------------------------------------------


def test_the_password_never_leaves_the_adapter(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    portal.state.refuse_blast = True
    client = make_client()
    client.login()
    error = fails_with(Reason.DESKTOP_DID_NOT_OPEN, lambda: client.open_desktop(DESKTOP))
    client.close()  # one sync Playwright driver per thread: the run's client, then the next
    rejected = fails_with(Reason.LOGIN_REJECTED, make_client(password=PASSWORD + "-x").login)

    # A PNG holds pixels, not the typed text, so the files are not searched for the
    # password. What is asserted is which failures the adapter asked the store to
    # photograph: the desktop page's, and not the login page that holds the password.
    assert error.screenshot is not None
    assert rejected.screenshot is None
    assert artifacts.asked == [RunKind.CHECKIN]
    written = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert written == [error.screenshot], "the run wrote more than the desktop screenshot"
    assert PASSWORD not in caplog.text
    assert PASSWORD not in repr(client)
    assert PASSWORD not in f"{error} {error!r} {rejected} {rejected!r}"
