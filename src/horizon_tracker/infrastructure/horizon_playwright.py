"""Drives the VMware Horizon HTML Access web client in headless Chrome: the ``HorizonClient`` port.

The path follows a person's: ``#/home`` (login) -> ``#/launchitems`` (desktop tiles) ->
``#/desktop`` (the Blast canvas). Every selector below was read from the compiled
templates of the HTML Access 2312.1 bundle (``app-htmlaccess.4eb7424a56fc03317f06.js``;
RFC HT-001 and BRIEF HT-002). Two readings are inferred from that code, not measured on
a logged-in portal, and say so where they live: the "desktop is open" signal and the
tile's session state.

Secrets: the password is typed into ``#password`` and goes nowhere else. Failure
screenshots are taken only on an allowlist of routes after the login page; Playwright
tracing is never started; a Playwright error is re-raised without its cause and logged by
its type only, so no message text the library composed can carry a value.

One instance per process at a time: the sync Playwright driver refuses a second one in
the same thread, so a client is closed (it is a context manager) before the next starts.
"""

# beadloom:domain=infrastructure

import base64
import logging
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import Literal, Self, TypeVar, cast
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
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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
# A dialog the client shows over the remote surface, read by its buttons: the page holds
# them only inside a dialog. The capture clicks Cancel, never OK, and waits out the rest.
_SHOWN_DIALOG_CANCEL = f"{DIALOG_CANCEL}:visible"
_SHOWN_DIALOG_OK = f"{DIALOG_OK}:visible"
# A tile is ``li#<id>`` with no title; the name is on its launch button, which also holds
# the overflow button and, while it is open, the tile menu.
LAUNCH_BUTTON = "button[id^='launch-']"
ANY_TILE = f"li:has(> {LAUNCH_BUTTON})"
TILE_MENU_BUTTON = "button.overflow-button[aria-haspopup]"
TILE_MENU = ".content-menu .context-menu-container"
# An ``li`` the client hides (the ``hidden`` attribute) when the desktop has no session;
# it is never disabled.
LOGOFF_MENU_ITEM = "#menu-item-logoff-btn"
# The Blast session draws into a canvas it appends to ``#canvas-container``; the service
# ``canvas#canvas`` beside the container is never shown.
DESKTOP_CANVAS = "#canvas-container canvas"
# The remote surface, not the page. The hidden service canvas and video sit beside
# the container and are not part of it. The largest of these is the one a frame is
# read from: a small overlay must not look painted while the desktop is black.
_DESKTOP_SURFACE = "#canvas-container canvas, #canvas-container video"
# The paint rule: a frame of the largest surface drawn onto a 32 by 32 grid, painted once
# at least 8 of its 1024 cells have max(R, G, B) >= 24.
_SAMPLE_SIDE = 32
_LIT_CHANNEL = 24
_LIT_CELLS_REQUIRED = 8
# A bright frame can still be the blank gray repaint. Require either changing luminance
# across cells or chroma within a cell, so both normal windows and solid-colour desktops pass.
_FRAME_VARIATION_REQUIRED = 24
# The least of the capture's bound a sample is started with. A frame and its decode take
# longer than this (about 280 ms and 480 ms for a worst-case 1920 by 1080 frame, measured
# by the review of HT-010), so a sample started with less could only time out.
_SAMPLE_FLOOR_MS = 250
BLAST_PATH_PREFIXES = ("/r/", "/d/")
# Windows gives no DOM signal when Run is ready. Bound that blind wait and pace the text
# so a slow dialog and the Blast delivery do not lose the first characters.
_RUN_DIALOG_WAIT_MS = 2_000
_WINDOWS_TYPE_DELAY_MS = 50
# Live-proven Windows coordinates on the owner's 1280x720 desktop. Every click is scaled
# into the current CSS bounds of the remote surface rather than treated as a page pixel.
_REMOTE_WIDTH = 1280.0
_REMOTE_HEIGHT = 720.0
_START_X = 20.0
_START_Y = 700.0
_RUN_X = 85.0
_RUN_Y = 600.0

# Finds the remote surface a frame is taken of: the largest canvas or video inside the
# container, by its box. Answers null when no surface has a box, else the surface's index
# among the selector's matches and whether it holds a bitmap yet (a canvas of width 0 or
# a video with no frame holds none, and is not photographed).
_LARGEST_SURFACE = """(selector) => {
    let largest = -1;
    let largestArea = 0;
    const surfaces = Array.from(document.querySelectorAll(selector));
    surfaces.forEach((surface, index) => {
        const box = surface.getBoundingClientRect();
        if (box.width * box.height > largestArea) {
            largest = index;
            largestArea = box.width * box.height;
        }
    });
    if (largest < 0) { return null; }
    const surface = surfaces[largest];
    const isVideo = surface instanceof HTMLVideoElement;
    const width = isVideo ? surface.videoWidth : surface.width;
    const height = isVideo ? surface.videoHeight : surface.height;
    return { index: largest, drawn: Boolean(width && height) };
}"""
# Counts lit cells and measures luminance/chroma variation in a frame the adapter took,
# so no PNG is decoded here. The frame
# arrives as base64 and becomes a Blob and an ImageBitmap: no URL is loaded, so no page
# policy applies, and a Blob never taints the grid. The live surface itself is never
# read, so a WebGL canvas that keeps no drawing buffer is judged by what was composited.
# Smoothing is off: each cell is one pixel of the frame, the same on every rasteriser.
_LIT_CELLS = """async ({ data, side, channel }) => {
    const bytes = Uint8Array.from(atob(data), (character) => character.charCodeAt(0));
    const frame = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
    const grid = document.createElement("canvas");
    grid.width = side;
    grid.height = side;
    const context = grid.getContext("2d");
    context.imageSmoothingEnabled = false;
    context.drawImage(frame, 0, 0, side, side);
    frame.close();
    const cells = context.getImageData(0, 0, side, side).data;
    let lit = 0;
    let minLuminance = 255;
    let maxLuminance = 0;
    let maxChroma = 0;
    for (let offset = 0; offset < cells.length; offset += 4) {
        const luminance = Math.max(cells[offset], cells[offset + 1], cells[offset + 2]);
        const chroma = luminance - Math.min(cells[offset], cells[offset + 1], cells[offset + 2]);
        if (luminance >= channel) { lit += 1; }
        minLuminance = Math.min(minLuminance, luminance);
        maxLuminance = Math.max(maxLuminance, luminance);
        maxChroma = Math.max(maxChroma, chroma);
    }
    return { lit, luminanceRange: maxLuminance - minLuminance, maxChroma };
}"""
# Recognises the standard Run window on the owner's 1280x720 desktop by geometry, not
# by its localised title or by HTML Access DOM. Three independent regions are required:
# the light dialog/title, its white edit field and that field's dark border. This runs
# only on a frame bracketed by the HTML Access dialog guards, never on the web dialog.
_RUN_DIALOG_FRAME = """async (data) => {
    const bytes = Uint8Array.from(atob(data), (character) => character.charCodeAt(0));
    const frame = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
    const canvas = document.createElement("canvas");
    canvas.width = 1280;
    canvas.height = 720;
    const context = canvas.getContext("2d");
    context.imageSmoothingEnabled = false;
    context.drawImage(frame, 0, 0, 1280, 720);
    frame.close();
    const pixels = context.getImageData(0, 0, 1280, 720).data;
    const ratio = (x0, y0, x1, y1, step, accepts) => {
        let accepted = 0;
        let total = 0;
        for (let y = y0; y < y1; y += step) {
            for (let x = x0; x < x1; x += step) {
                const offset = (y * 1280 + x) * 4;
                if (accepts(pixels[offset], pixels[offset + 1], pixels[offset + 2])) {
                    accepted += 1;
                }
                total += 1;
            }
        }
        return total === 0 ? 0 : accepted / total;
    };
    const light = (r, g, b) => (
        Math.min(r, g, b) >= 200 && Math.max(r, g, b) - Math.min(r, g, b) <= 35
    );
    const white = (r, g, b) => Math.min(r, g, b) >= 225;
    const dark = (r, g, b) => Math.max(r, g, b) <= 170;
    const title = ratio(24, 484, 436, 510, 4, light);
    const body = ratio(24, 514, 436, 665, 4, light);
    const input = ratio(84, 552, 416, 578, 2, white);
    const border = Math.min(
        ratio(80, 548, 420, 550, 2, dark),
        ratio(80, 580, 420, 582, 2, dark)
    );
    return title >= 0.75 && body >= 0.65 && input >= 0.85 && border >= 0.40;
}"""
_CANVAS_IS_DRAWN = """(selector) => Array.from(document.querySelectorAll(selector)).some(
    (canvas) => {
        const box = canvas.getBoundingClientRect();
        return box.width > 0 && box.height > 0;
    }
)"""
_CSS_STRING_ESCAPES = str.maketrans(
    {"\\": "\\\\", '"': '\\"', "\n": "\\a ", "\r": "\\d ", "\f": "\\c "}
)
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
    # How long ``capture_open_desktop`` polls for a non-blank remote surface and the
    # evening sign-out waits for one that is safe to send Windows input to.
    # A fixed pause cannot tell a black frame from a painted desktop.
    desktop_paint_ms: int = 60_000


class _Frame(Enum):
    """What one capture sample decided, when it did not save a file."""

    WAIT = "wait"
    DIALOG = "dialog"
    STOP = "stop"


# What the capture logs when its bound runs out on a sample that would have polled again.
_GAVE_UP = {
    _Frame.WAIT: "Horizon desktop still blank",
    _Frame.DIALOG: "Horizon client dialog still open",
}


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
        blast = "seen" if self._blast_socket_open() else "no WebSocket on a Blast path seen"
        logger.info("Horizon desktop open (%s)", blast)

    def capture_open_desktop(self) -> Path | None:
        """Save the first non-blank frame of the open remote surface, or return ``None``.

        Polls an element screenshot of the largest canvas or video inside
        ``#canvas-container``: the page decodes that frame onto a square grid of
        ``_SAMPLE_SIDE`` cells a side, and once at least ``_LIT_CELLS_REQUIRED`` cells have
        ``max(R, G, B) >= _LIT_CHANNEL`` the same frame is saved, so the pixels judged are
        the pixels sent. A frame is taken only while no client dialog shows, and kept only
        if none showed once it was taken: one with a Cancel button is cancelled (never OK,
        which on the Fullscreen offer grants full screen) and the next poll looks again.
        ``desktop_paint_ms`` bounds the whole capture: a sample starts only while at least
        ``_SAMPLE_FLOOR_MS`` of it are left, a pause and the screenshot wait no longer than
        what is left. A blank or dialog-covered timeout, a page closed or outside the
        screenshot allowlist, or a screenshot or decode error answers ``None``. A missing
        photo never fails the step.
        """
        deadline = time.monotonic() + self._timeouts.desktop_paint_ms / 1000
        last = _Frame.WAIT
        try:
            while _remaining_ms(deadline) >= _SAMPLE_FLOOR_MS:
                sample = self._nonblank_frame(deadline)
                if isinstance(sample, Path):
                    return sample
                if sample is _Frame.STOP:
                    return None
                last = sample
                self._pause_between_samples(deadline)
        except (PlaywrightError, OSError, ValueError) as error:
            _log_screenshot_failure(error)
            return None
        logger.warning(_GAVE_UP[last])
        return None

    def _nonblank_frame(self, deadline: float) -> Path | _Frame:
        """One sample: a saved path, ``WAIT`` or ``DIALOG`` to poll again, or ``STOP``."""
        page = self._page
        if page is None or page.is_closed() or _route(page.url) not in _SCREENSHOT_ROUTES:
            return _Frame.STOP
        if self._dialog_in_the_way(page, deadline):
            return _Frame.DIALOG
        surface = _largest_surface(page)
        if surface is None:
            return _Frame.WAIT
        png = surface.screenshot(type="png", timeout=_remaining_ms(deadline))
        if not _frame_is_painted(page, png):
            return _Frame.WAIT
        # A dialog the client showed after the look above is in this frame: discard it.
        if self._dialog_in_the_way(page, deadline):
            return _Frame.DIALOG
        path = self._artifacts.screenshot_path(RunKind.CHECKIN)
        path.write_bytes(png)
        return path

    def _pause_between_samples(self, deadline: float) -> None:
        """Wait one poll interval, or what is left of the bound when that is shorter.

        A page that closed is not waited on: the next sample finds it closed and stops.
        """
        page = self._page
        if page is None or page.is_closed():
            return
        page.wait_for_timeout(min(self._timeouts.poll_ms, _remaining_ms(deadline)))

    def _wait_for_desktop_input(self) -> bool:
        """Wait until a painted remote surface is visible with no client dialog over it."""
        deadline = time.monotonic() + self._timeouts.desktop_paint_ms / 1000
        while _remaining_ms(deadline) >= _SAMPLE_FLOOR_MS:
            ready = self._desktop_input_sample(deadline)
            if ready is True:
                return True
            if ready is _Frame.STOP:
                return False
            self._pause_between_samples(deadline)
        logger.warning("Horizon desktop not ready for Windows input")
        return False

    def _desktop_input_sample(self, deadline: float) -> bool | _Frame:
        """One input-readiness sample, judged on pixels without saving an artifact."""
        page = self._page
        if page is None or page.is_closed() or _route(page.url) != DESKTOP_ROUTE:
            return _Frame.STOP
        if self._dialog_in_the_way(page, deadline):
            return _Frame.DIALOG
        surface = _largest_surface(page)
        if surface is None:
            return _Frame.WAIT
        png = surface.screenshot(type="png", timeout=_remaining_ms(deadline))
        if not _frame_is_painted(page, png):
            return _Frame.WAIT
        return True if not self._dialog_in_the_way(page, deadline) else _Frame.DIALOG

    def _dialog_in_the_way(self, page: Page, deadline: float) -> bool:
        """Cancel a client dialog over the desktop; True while one may still be in the frame.

        The client can show its Fullscreen offer again after ``open_desktop`` cancelled
        it. Cancel is clicked, within what is left of the caller's bound, and the sample
        is not used: the next poll looks again, so a dialog that closes slowly or comes
        straight back is neither photographed nor sent Windows input. A dialog with no
        Cancel is never answered with OK; it stays in the way until it goes or the bound
        runs out.
        """
        cancel = page.locator(_SHOWN_DIALOG_CANCEL)
        if cancel.count() > 0:
            with suppress(PlaywrightTimeoutError):
                cancel.first.click(timeout=_remaining_ms(deadline))
                logger.info("Horizon client dialog cancelled before desktop capture or input")
            return True
        return page.locator(_SHOWN_DIALOG_OK).count() > 0

    def disconnect(self) -> None:
        """Close the browser context: the client lets go, the Windows session keeps running."""
        context = self._release_context()
        if context is None:
            return
        with self._step(Reason.UNEXPECTED):
            context.close()
        logger.info("Horizon client disconnected")

    def _refocus_ready_surface(self, surface: Locator) -> bool:
        """Cancel client dialogs, await painted input and restore focus for the next action."""
        if not self._wait_for_desktop_input():
            return False
        surface.focus()
        # Focus itself can raise Fullscreen; cancel it and leave focus on the surface again.
        if not self._wait_for_desktop_input():
            return False
        surface.focus()
        return True

    def _windows_run_is_open(self, page: Page, surface: Locator) -> bool:
        """Recognise Windows Run in a frame bracketed by HTML Access dialog guards."""
        deadline = time.monotonic() + self._timeouts.desktop_paint_ms / 1000
        if self._dialog_in_the_way(page, deadline):
            return False
        png = surface.screenshot(type="png", timeout=_remaining_ms(deadline))
        if self._dialog_in_the_way(page, deadline):
            return False
        return _run_dialog_in_frame(page, png)

    def _open_windows_run(self, page: Page, surface: Locator) -> bool:
        """Reuse visible Windows Run or open it through the scaled Win+X mouse path."""
        if not self._refocus_ready_surface(surface):
            return False
        if self._windows_run_is_open(page, surface):
            logger.info("Windows Run dialog already open; Win+X skipped")
            return True
        return (
            self._refocus_ready_surface(surface)
            and _click_remote(page, surface, _START_X, _START_Y, "right")
            and self._refocus_ready_surface(surface)
            and _click_remote(page, surface, _RUN_X, _RUN_Y, "left")
            and self._refocus_ready_surface(surface)
        )

    def log_off(self, name: str) -> Path | None:
        """Open the desktop, sign out through Win+X Run, and wait for broker agreement.

        Every confirmation read loads the launch items afresh first; the page is left on that
        fresh list, which is what a ``desktop_status`` after this call reads. Answers with a
        screenshot of that list, or ``None`` when it could not be taken.
        """
        with self._step(Reason.LOGOFF_NOT_CONFIRMED):
            if self._tile_session_state(self._tile(name)) is SessionState.NO_SESSION:
                raise self._failure(Reason.ALREADY_LOGGED_OFF)
            self.open_desktop(name)
            page = self._live_page()
            surface = _largest_surface(page)
            if surface is None or not self._open_windows_run(page, surface):
                raise self._failure(Reason.LOGOFF_NOT_CONFIRMED)
            page.wait_for_timeout(_RUN_DIALOG_WAIT_MS)
            page.keyboard.press("Control+A")
            page.keyboard.type("shutdown /l", delay=_WINDOWS_TYPE_DELAY_MS)
            if not self._refocus_ready_surface(surface):
                raise self._failure(Reason.LOGOFF_NOT_CONFIRMED)
            # Preserve evidence of the fully replaced Run command without making a failed
            # screenshot a new logout failure. No dialog is answered with OK.
            self._screenshot(RunKind.CHECKOUT)
            page.keyboard.press("Enter")
            confirmed = self._poll(
                lambda: self._broker_session_state(name) is SessionState.NO_SESSION or None,
                self._timeouts.logoff_confirm_ms,
            )
        if not confirmed:
            raise self._failure(Reason.LOGOFF_NOT_CONFIRMED)
        logger.info("Horizon desktop logged off")
        return self._screenshot(RunKind.CHECKOUT)

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
        """HYPOTHESIS until the first live ``checkin --force``: is the desktop open?

        Read from the bundle, not measured: a canvas the Blast session appended to
        ``#canvas-container`` has a non-zero size (WMKS keeps its container hidden until
        it connects). ``#sidebar-toggler`` is a secondary sign the RFC names; it is not
        consulted. If the live portal disagrees, this method is the one place to change.
        """
        page = self._page
        if page is None or page.is_closed():
            return False
        return bool(page.evaluate(_CANVAS_IS_DRAWN, DESKTOP_CANVAS))

    def _blast_socket_open(self) -> bool:
        """Whether a WebSocket on a Blast path (``/r/…``, ``/d/…``) is open; logged only.

        The paths are a reading nobody has verified without a login, so the answer never
        decides whether the desktop opened.
        """
        return any(
            not socket.is_closed() and urlsplit(socket.url).path.startswith(BLAST_PATH_PREFIXES)
            for socket in self._websockets
        )

    def _tile_session_state(self, tile: Locator) -> SessionState:
        """HYPOTHESIS until the first live ``checkout --force``: the tile's session state.

        The client binds ``[hidden]`` on ``#menu-item-logoff-btn`` in the tile's menu: the
        item is offered only for a desktop that holds a session (it is never disabled).
        The attribute is read rather than the item's visibility, which the client's own
        stylesheet, not in the bundle, could override. The tile cannot tell whether
        another client is attached, so a session reads as DISCONNECTED; CONNECTED is only
        ever this client's own open desktop. The tile shows the list the page last
        fetched, as the client has since changed it.
        """
        offered = _offered(self._open_tile_menu(tile))
        self._close_tile_menu(tile)
        return SessionState.DISCONNECTED if offered else SessionState.NO_SESSION

    def _broker_session_state(self, name: str) -> SessionState:
        """The named tile's session state on a launch-items list fetched for this read."""
        self._reload_launch_items()
        return self._tile_session_state(self._tile(name))

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
        tile = page.locator(f"li:has(> {LAUNCH_BUTTON}[title={_css_string(name)}])")
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

    def _reload_launch_items(self) -> None:
        """Load ``#/launchitems`` again so its tiles are built from a list the broker sent.

        Windows sign-out changes the broker's session, not this page's in-memory tile
        model. Only a list fetched again shows what the broker holds. A reload that lands
        on the login form logs in afresh, which fetches the list as well.
        """
        page = self._live_page()
        page.reload(timeout=self._timeouts.page_load_ms)
        page.locator(f"{ANY_TILE}, {USERNAME_FIELD}").first.wait_for(
            timeout=self._timeouts.page_load_ms
        )
        if page.locator(USERNAME_FIELD).count() > 0:
            self.login()

    def _open_tile_menu(self, tile: Locator) -> Locator:
        """Open the tile's "…" menu, wait for the menu itself, return its log-off item."""
        tile.locator(TILE_MENU_BUTTON).first.click()
        menu = tile.locator(TILE_MENU)
        menu.wait_for(state="visible")
        return menu.locator(LOGOFF_MENU_ITEM)

    def _close_tile_menu(self, tile: Locator) -> None:
        """Close the tile's menu the way the client does: a click on the document.

        The menu ignores Escape; it listens for a click anywhere outside its trigger.
        """
        self._live_page().locator("body").dispatch_event("click")
        tile.locator(TILE_MENU).wait_for(state="hidden")

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
        return HorizonClientError(reason, self._screenshot(self._run_kind))

    def _screenshot(self, kind: RunKind) -> Path | None:
        """A screenshot of the page, unless it is (or may be) the login page.

        Never raises: the screenshot is evidence, not a condition of the step, so a
        Playwright or disk error is logged by its type only and answers ``None``.
        """
        page = self._page
        if page is None:
            logger.warning("Horizon screenshot skipped: no page")
            return None
        if page.is_closed():
            logger.warning("Horizon screenshot skipped: page closed")
            return None
        try:
            if _route(page.url) not in _SCREENSHOT_ROUTES:
                logger.warning("Horizon screenshot skipped: route outside allowlist")
                return None
            path = self._artifacts.screenshot_path(kind)
            page.screenshot(path=path)
        except (PlaywrightError, OSError) as error:
            _log_screenshot_failure(error)
            return None
        return path


def _log_screenshot_failure(error: BaseException) -> None:
    """Log a screenshot failure by the error's type, never by its message."""
    logger.warning("Horizon screenshot failed: %s", type(error).__name__)


def _remaining_ms(deadline: float) -> int:
    """Milliseconds left until ``deadline``, at least 1: Playwright reads 0 as no timeout."""
    return max(1, round((deadline - time.monotonic()) * 1000))


def _click_remote(
    page: Page,
    surface: Locator,
    remote_x: float,
    remote_y: float,
    button: Literal["left", "right"],
) -> bool:
    """Click one 1280x720 Windows point scaled into the remote surface's CSS bounds."""
    bounds = surface.bounding_box()
    if bounds is None or bounds["width"] <= 0 or bounds["height"] <= 0:
        return False
    x = bounds["x"] + remote_x * bounds["width"] / _REMOTE_WIDTH
    y = bounds["y"] + remote_y * bounds["height"] / _REMOTE_HEIGHT
    page.mouse.click(x, y, button=button)
    return True


def _largest_surface(page: Page) -> Locator | None:
    """The largest remote surface once it holds a bitmap, else ``None``.

    Raises ``ValueError`` when the page answers something other than the reading.
    """
    reading = page.evaluate(_LARGEST_SURFACE, _DESKTOP_SURFACE)
    if reading is None:
        return None
    if not isinstance(reading, dict):
        raise ValueError("surface reading")
    fields = cast(dict[str, object], reading)
    index, drawn = fields.get("index"), fields.get("drawn")
    if not isinstance(index, int) or not isinstance(drawn, bool):
        raise ValueError("surface reading")
    return page.locator(_DESKTOP_SURFACE).nth(index) if drawn else None


def _run_dialog_in_frame(page: Page, png: bytes) -> bool:
    """Whether a composited frame has the owner desktop's Windows Run geometry."""
    reading = page.evaluate(_RUN_DIALOG_FRAME, base64.b64encode(png).decode("ascii"))
    if not isinstance(reading, bool):
        raise ValueError("Run dialog reading")
    return reading


def _frame_is_painted(page: Page, png: bytes) -> bool:
    """Whether enough cells are lit and show luminance or chroma variation.

    Raises ``ValueError`` when the page answers something other than the paint metrics,
    and a Playwright error when the page cannot decode the frame.
    """
    reading = page.evaluate(
        _LIT_CELLS,
        {
            "data": base64.b64encode(png).decode("ascii"),
            "side": _SAMPLE_SIDE,
            "channel": _LIT_CHANNEL,
        },
    )
    if not isinstance(reading, dict):
        raise ValueError("paint reading")
    fields = cast(dict[str, object], reading)
    lit = fields.get("lit")
    luminance_range = fields.get("luminanceRange")
    max_chroma = fields.get("maxChroma")
    for value in (lit, luminance_range, max_chroma):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("paint reading")
    return cast(int, lit) >= _LIT_CELLS_REQUIRED and (
        cast(int, luminance_range) >= _FRAME_VARIATION_REQUIRED
        or cast(int, max_chroma) >= _FRAME_VARIATION_REQUIRED
    )


def _close_quietly(part: str, close: Callable[[], None]) -> None:
    """Close one part of the browser; a Playwright error is logged by its type only."""
    try:
        close()
    except PlaywrightError as error:
        logger.warning("Horizon %s did not close: %s", part, type(error).__name__)


def _offered(menu_item: Locator) -> bool:
    """Whether the tile menu offers this item: the client hides it, it never disables it."""
    return menu_item.get_attribute("hidden") is None


def _css_string(value: str) -> str:
    """``value`` as a double-quoted CSS string, for an attribute selector."""
    return '"' + value.translate(_CSS_STRING_ESCAPES) + '"'


def _route(url: str) -> str:
    """The client's hash route of a URL (``#/desktop``), without any query part."""
    fragment = urlsplit(url).fragment.split("?", 1)[0]
    return f"#{fragment}" if fragment else ""
