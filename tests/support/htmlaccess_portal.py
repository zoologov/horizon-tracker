"""The HTML Access fixture portal the Playwright adapter is driven against, never the live one.

The fixture pages under ``tests/fixtures/htmlaccess/`` reproduce the structure the real
HTML Access 2312.1 bundle renders where the adapter reads the page: the tile, its menu,
the client's dialogs and the canvas the Blast session appends. A ``ThreadingHTTPServer``
on 127.0.0.1 serves them and plays the broker: its XML endpoint ``/broker/xml``
(kill-session and the logout of a credential cleanup), the fixture's own ``/fixture/*``
and a bare WebSocket handshake on the Blast path (``/r/`` unless a test moves it), so the
client's Blast connection is a real socket the browser opens and closes. The adapter's
integration tests and the acceptance scenarios that need the real adapter share it.
"""

import base64
import hashlib
import json
import os
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.infrastructure.horizon_playwright import HorizonTimeouts
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
    desktop_paint_ms=600,
)
# How long a kill-session the broker never answers holds its handler thread when the
# test does not release it first.
UNANSWERED_HOLD_S = 30.0


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
    # The page falls back to #/home this many ms after the desktop drew; 0 never.
    drop_to_login_after_ms: int = 0
    # The CSS colour the page fills the remote surface with once it draws; "" leaves it.
    paint_desktop: str = ""
    # The page offers Fullscreen again this many ms after the desktop drew; 0 never.
    fullscreen_again_after_ms: int = 0
    # That second offer ignores Cancel: a dialog the adapter cannot dismiss.
    fullscreen_sticks: bool = False
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
                    "drop_to_login_after_ms": self.state.drop_to_login_after_ms,
                    "paint_desktop": self.state.paint_desktop,
                    "fullscreen_again_after_ms": self.state.fullscreen_again_after_ms,
                    "fullscreen_sticks": self.state.fullscreen_sticks,
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


@contextmanager
def serve_portal() -> Iterator[Portal]:
    """Run a fixture portal on a free localhost port until the block ends."""
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
