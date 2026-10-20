"""Drives the VMware Horizon HTML Access web client in headless Chrome: the ``HorizonClient`` port.

The path follows a person's: ``#/home`` (login) -> ``#/launchitems`` (desktop tiles) ->
``#/desktop`` (the Blast canvas). Every selector below was read from the HTML Access 2312
bundle (RFC HT-001, "The path through the web client"), except the tile's "…" button, which the RFC
names only by its glyph. Two readings are hypotheses until the first ``horizon probe`` on
the VPS and say so where they live: the "desktop is open" signal and the tile's session
state.

Secrets: the password is typed into ``#password`` and goes nowhere else. Failure
screenshots are taken only on an allowlist of routes after the login page; Playwright
tracing is never started; a Playwright error is re-raised without its cause and logged by
its type only, so no message text the library composed can carry a value.

One instance per process at a time: the sync Playwright driver refuses a second one in
the same thread, so a client is closed (it is a context manager) before the next starts.
"""

# beadloom:domain=infrastructure

import json
import logging
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self, TypeVar
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    WebSocket,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError

from horizon_tracker.domain.ports import ArtifactStore, HorizonClientError
from horizon_tracker.domain.report import Reason
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import DesktopStatus, SessionState

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

LOGIN_ROUTE = "#/home"
LAUNCH_ITEMS_ROUTE = "#/launchitems"
DESKTOP_ROUTE = "#/desktop"
# An allowlist, not a denylist: a page on any other route (the login page, a bare portal
# URL that renders the login form) is never photographed.
_SCREENSHOT_ROUTES = (LAUNCH_ITEMS_ROUTE, DESKTOP_ROUTE)

USERNAME_FIELD = "#username"
PASSWORD_FIELD = "#password"
LOGIN_BUTTON = "#loginButton"
DIALOG_OK = "#okDialogBtn"
DIALOG_CANCEL = "#cancelDialogBtn"
ANY_TILE = "li[title]"
LAUNCH_BUTTON = "[id^='launch-']"
# Unmeasured: the RFC names the tile menu button only by its glyph "…".
TILE_MENU_BUTTON = "button[aria-haspopup], button:has-text('…')"
LOGOFF_MENU_ITEM = "#menu-item-logoff-btn"
DESKTOP_CANVAS = "#canvas-container #canvas"
BLAST_PATH_PREFIXES = ("/r/", "/d/")

_CANVAS_IS_DRAWN = """(selector) => {
    const canvas = document.querySelector(selector);
    if (canvas === null) { return false; }
    const box = canvas.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
}"""
_BUNDLE_SCRIPT = re.compile(r"<script[^>]*\bsrc=[\"']([^\"']+\.js)[\"']", re.IGNORECASE)
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/{major}.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class HorizonTimeouts:
    """How long each step may take, in milliseconds; the defaults are for the live portal."""

    page_load_ms: int = 30_000
    action_ms: int = 15_000
    login_ms: int = 30_000
    desktop_open_ms: int = 90_000
    logoff_confirm_ms: int = 60_000
    poll_ms: int = 1_000


class PlaywrightHorizonClient:
    """The ``HorizonClient`` port over Playwright and a Chrome binary.

    One instance serves one run. ``login`` starts the browser on first use and opens a
    fresh context; ``disconnect`` closes the context (the Blast connection goes with it,
    the Windows session stays); ``close`` stops the browser. Use it as a context manager
    so the browser is stopped whatever happens.
    """

    def __init__(
        self,
        *,
        horizon_url: str,
        username: str,
        password: str,
        chrome_path: Path | None,
        artifacts: ArtifactStore,
        run_kind: RunKind,
        timeouts: HorizonTimeouts | None = None,
    ) -> None:
        self._base_url = horizon_url if horizon_url.endswith("/") else horizon_url + "/"
        self._username = username
        self._password = password
        self._chrome_path = chrome_path
        self._artifacts = artifacts
        self._run_kind = run_kind
        self._timeouts = timeouts or HorizonTimeouts()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._websockets: list[WebSocket] = []
        self._opened_desktop: str | None = None

    def __repr__(self) -> str:
        return f"PlaywrightHorizonClient(horizon_url={self._base_url!r}, run_kind={self._run_kind})"

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # --- the port -------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate on ``#/home``; returns on ``#/launchitems``, fails on the error dialog."""
        with self._step(Reason.PORTAL_UNREACHABLE):
            page = self._new_page()
            page.goto(self._url(LOGIN_ROUTE), timeout=self._timeouts.page_load_ms)
            page.locator(USERNAME_FIELD).wait_for(timeout=self._timeouts.page_load_ms)
        with self._step(Reason.UNEXPECTED):
            page.locator(USERNAME_FIELD).fill(self._username)
            page.locator(PASSWORD_FIELD).fill(self._password)
            page.locator(LOGIN_BUTTON).click()
            accepted = self._poll(self._login_verdict, self._timeouts.login_ms)
        if accepted is None:
            raise self._failure(Reason.UNEXPECTED)
        if not accepted:
            raise self._failure(Reason.LOGIN_REJECTED)
        logger.info("Horizon login accepted")

    def desktop_status(self, name: str) -> DesktopStatus:
        """The named desktop's state: CONNECTED while this client holds it open, else its tile's.

        A client that has disconnected (or never logged in) logs in again to read the tile.
        """
        if self._opened_desktop == name and self._desktop_is_open():
            return DesktopStatus(name, SessionState.CONNECTED)
        with self._step(Reason.UNEXPECTED):
            tile = self._tile(name)
            return DesktopStatus(name, self._tile_session_state(tile))

    def open_desktop(self, name: str) -> None:
        """Launch the tile, cancel the Fullscreen offer, return once the desktop is open."""
        with self._step(Reason.DESKTOP_DID_NOT_OPEN):
            self._tile(name).locator(LAUNCH_BUTTON).first.click()
            self._opened_desktop = name
            opened = self._poll(self._settle_desktop, self._timeouts.desktop_open_ms)
        if not opened:
            raise self._failure(Reason.DESKTOP_DID_NOT_OPEN)
        logger.info("Horizon desktop open")

    def disconnect(self) -> None:
        """Close the browser context: the client lets go, the Windows session keeps running."""
        context = self._release_context()
        if context is None:
            return
        with self._step(Reason.UNEXPECTED):
            context.close()
        logger.info("Horizon client disconnected")

    def log_off(self, name: str) -> None:
        """Log off from the tile's "…" menu, confirm the dialog, wait for the tile to agree."""
        with self._step(Reason.LOGOFF_NOT_CONFIRMED):
            tile = self._tile(name)
            logoff = self._open_tile_menu(tile)
            if not logoff.is_enabled():
                self._close_tile_menu()
                raise self._failure(Reason.ALREADY_LOGGED_OFF)
            logoff.click()
            self._live_page().locator(DIALOG_OK).click()
            confirmed = self._poll(
                lambda: self._tile_session_state(tile) is SessionState.NO_SESSION or None,
                self._timeouts.logoff_confirm_ms,
            )
        if not confirmed:
            raise self._failure(Reason.LOGOFF_NOT_CONFIRMED)
        logger.info("Horizon desktop logged off")

    def client_bundles(self) -> tuple[str, ...]:
        """The client bundles the portal serves in ``index.html``, read without logging in."""
        with self._step(Reason.PORTAL_UNREACHABLE, screenshot=False):
            request = self._driver().request.new_context()
            try:
                response = request.get(
                    urljoin(self._base_url, "index.html"), timeout=self._timeouts.page_load_ms
                )
                status, html = response.status, response.text()
            finally:
                request.dispose()
        if status != 200:
            raise HorizonClientError(Reason.PORTAL_UNREACHABLE)
        bundles = tuple(Path(urlsplit(src).path).name for src in _BUNDLE_SCRIPT.findall(html))
        if not bundles:
            raise HorizonClientError(Reason.UNEXPECTED)
        return bundles

    def browser_version(self) -> str:
        """Start headless Chrome at ``chrome_path``, read its version, close it; no page opens.

        A browser of its own, so the deploy smoke finds a Chrome that Playwright can no
        longer drive without touching the portal or the run's browser.
        """
        with self._step(Reason.UNEXPECTED, screenshot=False):
            browser = self._launch()
            try:
                return browser.version
            finally:
                browser.close()

    def close(self) -> None:
        """Stop the context, the browser and the driver; safe to call more than once.

        Best-effort: by now the run has reported, so a context or browser that fails to
        close is logged by its error's type and never raised -- a run that SUCCEEDED
        must not exit 1 on the way out. The driver is stopped whatever happened before.
        """
        context, browser, driver = self._release_context(), self._browser, self._playwright
        self._browser = None
        self._playwright = None
        try:
            if context is not None:
                _close_quietly("context", context.close)
            if browser is not None:
                _close_quietly("browser", browser.close)
        finally:
            if driver is not None:
                driver.stop()

    # --- the two hypotheses -----------------------------------------------------------

    def _desktop_is_open(self) -> bool:
        """HYPOTHESIS until the first ``horizon probe`` on the VPS: is the desktop open?

        Read from the bundle, not measured: ``#canvas`` inside ``#canvas-container`` has a
        non-zero size AND a WebSocket on a Blast path (``/r/…`` or ``/d/…``) is still open.
        ``#sidebar-toggler`` is a secondary sign the RFC names; it is not consulted. If the
        live portal disagrees, this method is the one place to change.
        """
        page = self._page
        if page is None or page.is_closed():
            return False
        blast_open = any(
            not socket.is_closed() and urlsplit(socket.url).path.startswith(BLAST_PATH_PREFIXES)
            for socket in self._websockets
        )
        return blast_open and bool(page.evaluate(_CANVAS_IS_DRAWN, DESKTOP_CANVAS))

    def _tile_session_state(self, tile: Locator) -> SessionState:
        """HYPOTHESIS until the first ``horizon probe`` on the VPS: the tile's session state.

        The tile's "…" menu offers an enabled ``#menu-item-logoff-btn`` only when Windows
        holds a session. The tile cannot tell whether another client is attached, so a
        session reads as DISCONNECTED; CONNECTED is only ever this client's own open desktop.
        """
        enabled = self._open_tile_menu(tile).is_enabled()
        self._close_tile_menu()
        return SessionState.DISCONNECTED if enabled else SessionState.NO_SESSION

    # --- steps ------------------------------------------------------------------------

    def _login_verdict(self) -> bool | None:
        """True once the launch items show, False once the error dialog does, else None."""
        page = self._live_page()
        if _route(page.url) == LAUNCH_ITEMS_ROUTE:
            return True
        if page.locator(DIALOG_OK).is_visible():
            return False
        return None

    def _settle_desktop(self) -> bool | None:
        """Cancel the Fullscreen offer if it is showing; True once the desktop is open."""
        page = self._live_page()
        cancel = page.locator(DIALOG_CANCEL)
        if _route(page.url) == DESKTOP_ROUTE and cancel.is_visible():
            cancel.click()
        return self._desktop_is_open() or None

    def _tile(self, name: str) -> Locator:
        """The named desktop's tile on ``#/launchitems``; logs in first when no page is live."""
        page = self._launch_items_page()
        page.locator(ANY_TILE).first.wait_for(timeout=self._timeouts.page_load_ms)
        tile = page.locator(f"li[title={json.dumps(name)}]")
        if tile.count() == 0:
            raise self._failure(Reason.DESKTOP_NOT_FOUND)
        return tile.first

    def _launch_items_page(self) -> Page:
        if self._page is None or self._page.is_closed():
            self.login()
        page = self._live_page()
        if _route(page.url) != LAUNCH_ITEMS_ROUTE:
            page.goto(self._url(LAUNCH_ITEMS_ROUTE), timeout=self._timeouts.page_load_ms)
            self._opened_desktop = None
        return page

    def _open_tile_menu(self, tile: Locator) -> Locator:
        tile.locator(TILE_MENU_BUTTON).first.click()
        logoff = self._live_page().locator(LOGOFF_MENU_ITEM)
        logoff.wait_for(state="visible")
        return logoff

    def _close_tile_menu(self) -> None:
        self._live_page().keyboard.press("Escape")

    # --- browser lifecycle ------------------------------------------------------------

    def _driver(self) -> Playwright:
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        return self._playwright

    def _launch(self) -> Browser:
        """Start headless Chrome at ``chrome_path`` (Playwright's own Chromium when unset)."""
        executable = str(self._chrome_path) if self._chrome_path is not None else None
        return self._driver().chromium.launch(executable_path=executable, headless=True)

    def _new_page(self) -> Page:
        """A fresh context and page on the shared browser, with WebSockets recorded."""
        self.disconnect()
        if self._browser is None:
            self._browser = self._launch()
        major = self._browser.version.split(".", 1)[0]
        self._context = self._browser.new_context(user_agent=_USER_AGENT.format(major=major))
        self._context.set_default_timeout(self._timeouts.action_ms)
        page = self._context.new_page()
        page.on("websocket", self._record_websocket)
        self._page = page
        return page

    def _release_context(self) -> BrowserContext | None:
        """Forget the context, its page and what was seen on it; return it to be closed."""
        context = self._context
        self._context = None
        self._page = None
        self._websockets = []
        self._opened_desktop = None
        return context

    def _record_websocket(self, socket: WebSocket) -> None:
        self._websockets.append(socket)

    def _live_page(self) -> Page:
        if self._page is None or self._page.is_closed():
            raise self._failure(Reason.UNEXPECTED)
        return self._page

    def _url(self, route: str) -> str:
        return self._base_url + route

    def _poll(self, check: Callable[[], _T | None], timeout_ms: int) -> _T | None:
        """Ask ``check`` until it answers (not None) or ``timeout_ms`` runs out."""
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            answer = check()
            if answer is not None or time.monotonic() >= deadline:
                return answer
            self._live_page().wait_for_timeout(self._timeouts.poll_ms)

    # --- failures ---------------------------------------------------------------------

    @contextmanager
    def _step(self, reason: Reason, *, screenshot: bool = True) -> Iterator[None]:
        """Turn a Playwright error inside the block into ``HorizonClientError(reason)``.

        The Playwright error is dropped as a cause (``from None``) and logged by its type
        only; the domain error carries the reason and nothing else.
        """
        try:
            yield
        except PlaywrightError as error:
            logger.warning("Horizon step failed (%s): %s", reason.value, type(error).__name__)
            failure = self._failure(reason) if screenshot else HorizonClientError(reason)
            raise failure from None

    def _failure(self, reason: Reason) -> HorizonClientError:
        return HorizonClientError(reason, self._screenshot())

    def _screenshot(self) -> Path | None:
        """A screenshot of the current page, unless it is (or may be) the login page."""
        page = self._page
        if page is None or page.is_closed() or _route(page.url) not in _SCREENSHOT_ROUTES:
            return None
        path = self._artifacts.screenshot_path(self._run_kind)
        try:
            page.screenshot(path=path)
        except PlaywrightError as error:
            logger.warning("Horizon screenshot failed: %s", type(error).__name__)
            return None
        return path


def _close_quietly(part: str, close: Callable[[], None]) -> None:
    """Close one part of the browser; a Playwright error is logged by its type only."""
    try:
        close()
    except PlaywrightError as error:
        logger.warning("Horizon %s did not close: %s", part, type(error).__name__)


def _route(url: str) -> str:
    """The client's hash route of a URL (``#/desktop``), without any query part."""
    fragment = urlsplit(url).fragment.split("?", 1)[0]
    return f"#{fragment}" if fragment else ""
