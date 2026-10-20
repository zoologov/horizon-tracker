"""Tests of the Playwright Horizon client against a local HTML Access fixture, never the portal.

The fixture pages under ``tests/fixtures/htmlaccess/`` carry the ids of the real HTML
Access 2312 bundle; a ``ThreadingHTTPServer`` on 127.0.0.1 serves them and plays the
broker behind ``/fixture/*``, including a bare WebSocket handshake on ``/r/`` so the
client's Blast connection is a real socket the browser opens and closes.
"""

import base64
import hashlib
import json
import logging
import os
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

import pytest

from horizon_tracker.domain.ports import HorizonClient, HorizonClientError
from horizon_tracker.domain.report import Reason
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import DesktopStatus, SessionState
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

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SESSION_COOKIE = "fixture-session"

FAST = HorizonTimeouts(
    page_load_ms=10_000,
    action_ms=5_000,
    login_ms=5_000,
    desktop_open_ms=4_000,
    logoff_confirm_ms=3_000,
    poll_ms=100,
)


# --- the fixture portal ---------------------------------------------------------------


@dataclass
class PortalState:
    """What the fixture broker knows and how it is told to misbehave."""

    session: str = "none"
    refuse_blast: bool = False
    draw_canvas: bool = True
    ignore_logoff: bool = False
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
        if self.path.startswith("/r/"):
            self._blast()
        elif self.path == "/fixture/launch-items":
            self._launch_items()
        elif self.path == "/fixture/behaviour":
            self._json(200, {"draw_canvas": self.state.draw_canvas})
        else:
            super().do_GET()

    def do_POST(self) -> None:
        body = self._body()
        if self.path == "/fixture/login":
            self._login(body)
        elif self.path == "/fixture/kill-session":
            self._kill_session()
        elif self.path == "/fixture/event":
            self.state.record(str(body["name"]))
            self._json(200, {})
        else:
            self._json(404, {})

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        loaded: dict[str, object] = json.loads(self.rfile.read(length) or b"{}")
        return loaded

    def _json(self, status: int, payload: object, cookie: str | None = None) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def _logged_in(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return SESSION_COOKIE in cookie

    def _login(self, body: dict[str, object]) -> None:
        if body.get("username") == USERNAME and body.get("password") == PASSWORD:
            self.state.record("login-accepted")
            self._json(200, {}, cookie=f"{SESSION_COOKIE}=1; Path=/")
        else:
            self.state.record("login-rejected")
            self._json(401, {})

    def _launch_items(self) -> None:
        if not self._logged_in():
            self._json(401, {})
            return
        self._json(
            200,
            [
                {"id": DESKTOP_ID, "name": DESKTOP, "session": self.state.session},
                {"id": OTHER_DESKTOP_ID, "name": "Test desktop", "session": "none"},
            ],
        )

    def _kill_session(self) -> None:
        if not self._logged_in():
            self._json(401, {})
            return
        self.state.record("kill-session")
        if not self.state.ignore_logoff:
            self.state.session = "none"
        self._json(200, {})

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
    ) -> PlaywrightHorizonClient:
        client = PlaywrightHorizonClient(
            horizon_url=url or portal.url,
            username=USERNAME,
            password=password,
            chrome_path=chrome_for_tests(),
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


def fails_with(reason: Reason, action: Callable[[], object]) -> HorizonClientError:
    with pytest.raises(HorizonClientError) as caught:
        action()
    assert caught.value.reason is reason
    return caught.value


# --- the port --------------------------------------------------------------------------


def test_the_client_satisfies_the_horizon_port(client: PlaywrightHorizonClient) -> None:
    port: HorizonClient = client
    assert callable(port.login)


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


def test_log_off_without_a_session_is_already_logged_off(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    client.login()

    fails_with(Reason.ALREADY_LOGGED_OFF, lambda: client.log_off(DESKTOP))

    assert "kill-session" not in portal.state.events


# --- probe ---------------------------------------------------------------------------------


def test_probe_names_the_bundles_without_logging_in(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    answer = client.probe()

    assert "app-htmlaccess.fixture.js" in answer
    assert portal.state.events == []


def test_probe_of_an_unreachable_portal_is_named(
    make_client: Callable[..., PlaywrightHorizonClient],
) -> None:
    client = make_client(url=closed_port_url())

    fails_with(Reason.PORTAL_UNREACHABLE, client.probe)


def test_probe_of_a_portal_without_the_client_is_unreachable(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    client = make_client(url=portal.url + "no-client-here/")

    fails_with(Reason.PORTAL_UNREACHABLE, client.probe)


# --- secrets -------------------------------------------------------------------------------


def test_the_password_never_leaves_the_adapter(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
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

    written = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert written, "the failure should have left a screenshot to search"
    assert not any(PASSWORD.encode() in path.read_bytes() for path in written)
    assert not any(path.suffix == ".zip" for path in written), "a trace was recorded"
    assert PASSWORD not in caplog.text
    assert PASSWORD not in repr(client)
    assert PASSWORD not in f"{error} {error!r} {rejected} {rejected!r}"
