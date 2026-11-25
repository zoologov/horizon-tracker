"""Tests of the Playwright Horizon client against a local HTML Access fixture, never the portal.

The fixture portal (``tests/support/htmlaccess_portal.py``) serves the fixture pages and
plays the broker and the Blast handshake; the tests below steer it through its state.
"""

import http.client
import json
import logging
import re
import struct
import time
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    FloatRect,
    Keyboard,
    Locator,
    Mouse,
    Page,
    sync_playwright,
)
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
from tests.support.htmlaccess_portal import (
    DESKTOP,
    FAST,
    PASSWORD,
    QUOTED_DESKTOP,
    USERNAME,
    Portal,
    RecordingArtifacts,
    chrome_for_tests,
    closed_port_url,
    serve_portal,
    wait_for,
)
from tests.support.photo import colours_unlike

# The fixture page falls back to the login page this long after the desktop drew.
DROP_TO_LOGIN_AFTER_MS = 300


# --- the fixture portal ---------------------------------------------------------------


@pytest.fixture
def portal() -> Iterator[Portal]:
    with serve_portal() as running:
        yield running


# --- the client under test ------------------------------------------------------------


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
        timeouts: HorizonTimeouts = FAST,
    ) -> PlaywrightHorizonClient:
        client = PlaywrightHorizonClient(
            horizon_url=url or portal.url,
            username=USERNAME,
            password=password,
            chrome_path=chrome_path or chrome_for_tests(),
            artifacts=artifacts,
            run_kind=run_kind,
            timeouts=timeouts,
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


@pytest.fixture
def photographed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The hash route of the page at each screenshot the adapter takes, in order."""
    routes: list[str] = []
    real_page = Page.screenshot
    real_locator = Locator.screenshot

    def spy_page(page: Page, *args: Any, **kwargs: Any) -> bytes:
        routes.append("#" + urlsplit(page.url).fragment)
        return real_page(page, *args, **kwargs)

    def spy_locator(locator: Locator, *args: Any, **kwargs: Any) -> bytes:
        routes.append("#" + urlsplit(locator.page.url).fragment)
        return real_locator(locator, *args, **kwargs)

    monkeypatch.setattr(Page, "screenshot", spy_page)
    monkeypatch.setattr(Locator, "screenshot", spy_locator)
    return routes


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
    real_driver = sync_playwright  # the object the adapter imports; mypy sees no re-export
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
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    client = make_client(password="wrong")

    error = fails_with(Reason.LOGIN_REJECTED, client.login)

    assert portal.state.events == ["login-rejected"]
    assert error.screenshot is None
    assert artifacts.asked == []
    assert list(artifacts.root.iterdir()) == []
    assert "Horizon screenshot skipped: route outside allowlist" in caplog.text
    assert PASSWORD not in caplog.text


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


def test_windows_sign_out_event_records_input_before_ending_the_session(portal: Portal) -> None:
    sequence = "Win+X@20,700|Run@85,600|shutdown /l|Enter"
    with closing(http.client.HTTPConnection(urlsplit(portal.url).netloc)) as connection:
        connection.request(
            "POST",
            "/fixture/event",
            body=json.dumps({"name": "windows-sign-out", "input": sequence}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        response.read()

    assert response.status == 200
    assert portal.state.events == [f"windows-input:{sequence}", "windows-sign-out"]


def test_log_off_opens_the_desktop_and_signs_out_through_scaled_winx_mouse(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()
    real_open = client.open_desktop

    def open_on_a_scaled_surface(name: str) -> None:
        real_open(name)
        page = client._page
        assert page is not None
        page.evaluate(
            """() => {
                const surface = document.querySelector('#canvas-container .wmks');
                surface.style.left = '100px';
                surface.style.top = '50px';
                const canvas = surface.querySelector('canvas');
                canvas.style.width = '640px';
                canvas.style.height = '360px';
            }"""
        )

    clicks: list[tuple[float, float, str | None]] = []
    click_bounds: list[FloatRect] = []
    presses: list[str] = []
    focused_at_select_all: list[bool] = []
    typed_delays: list[float | int | None] = []
    run_waits: list[float] = []
    page_screenshots = 0
    screenshots_at_enter: list[int] = []
    real_click = Mouse.click
    real_press = Keyboard.press
    real_type = Keyboard.type
    real_wait = Page.wait_for_timeout
    real_screenshot = Page.screenshot

    def click(mouse: Mouse, x: float, y: float, *args: Any, **kwargs: Any) -> None:
        page = client._page
        assert page is not None
        bounds = page.locator("#mainCanvas").bounding_box()
        assert bounds is not None
        click_bounds.append(bounds)
        clicks.append((x, y, kwargs.get("button")))
        real_click(mouse, x, y, *args, **kwargs)

    def press(keyboard: Keyboard, key: str, *args: Any, **kwargs: Any) -> None:
        presses.append(key)
        page = client._page
        assert page is not None
        if key == "Control+A":
            focused_at_select_all.append(
                page.evaluate(
                    "document.activeElement === document.querySelector('#canvas-container canvas')"
                )
            )
        if key == "Enter":
            screenshots_at_enter.append(page_screenshots)
        real_press(keyboard, key, *args, **kwargs)

    def type_text(keyboard: Keyboard, text: str, *args: Any, **kwargs: Any) -> None:
        if text == "shutdown /l":
            typed_delays.append(kwargs.get("delay"))
        real_type(keyboard, text, *args, **kwargs)

    def wait(page: Page, timeout: float) -> None:
        if timeout == 2_000:
            run_waits.append(timeout)
        real_wait(page, timeout)

    def screenshot(page: Page, *args: Any, **kwargs: Any) -> bytes:
        nonlocal page_screenshots
        page_screenshots += 1
        return real_screenshot(page, *args, **kwargs)

    monkeypatch.setattr(client, "open_desktop", open_on_a_scaled_surface)
    monkeypatch.setattr(Mouse, "click", click)
    monkeypatch.setattr(Keyboard, "press", press)
    monkeypatch.setattr(Keyboard, "type", type_text)
    monkeypatch.setattr(Page, "wait_for_timeout", wait)
    monkeypatch.setattr(Page, "screenshot", screenshot)

    client.log_off(DESKTOP)

    assert len(click_bounds) == 2
    start, run = click_bounds
    assert (start["width"], start["height"]) != (1280.0, 720.0)
    assert clicks == [
        (
            start["x"] + 20.0 * start["width"] / 1280.0,
            start["y"] + 700.0 * start["height"] / 720.0,
            "right",
        ),
        (
            run["x"] + 85.0 * run["width"] / 1280.0,
            run["y"] + 600.0 * run["height"] / 720.0,
            "left",
        ),
    ]
    assert presses == ["Control+A", "Enter"], "Meta+R or a second Enter was sent"
    assert focused_at_select_all == [True], "Run input was not refocused before replacement"
    assert run_waits == [2_000], "the command was typed before Run could accept input"
    assert typed_delays == [50], "Windows input was not paced"
    assert screenshots_at_enter == [1], "the Run command was not captured before Enter"
    events = portal.state.events
    windows_input = "windows-input:Win+X@20,700|Run@85,600|shutdown /l|Enter"
    assert [
        event for event in events if event in {"blast-open", windows_input, "windows-sign-out"}
    ] == [
        "blast-open",
        windows_input,
        "windows-sign-out",
    ]
    assert "kill-session" not in events
    assert artifacts.asked == [RunKind.CHECKOUT, RunKind.CHECKOUT]
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_log_off_reuses_an_already_open_run_without_winx(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    portal.state.run_already_open = True
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()
    clicks: list[tuple[float, float, str | None]] = []
    presses: list[str] = []
    real_click = Mouse.click
    real_press = Keyboard.press

    def click(mouse: Mouse, x: float, y: float, *args: Any, **kwargs: Any) -> None:
        clicks.append((x, y, kwargs.get("button")))
        real_click(mouse, x, y, *args, **kwargs)

    def press(keyboard: Keyboard, key: str, *args: Any, **kwargs: Any) -> None:
        presses.append(key)
        real_press(keyboard, key, *args, **kwargs)

    monkeypatch.setattr(Mouse, "click", click)
    monkeypatch.setattr(Keyboard, "press", press)

    client.log_off(DESKTOP)

    assert clicks == [], "an existing Windows Run dialog was reopened through Win+X"
    assert presses == ["Control+A", "Enter"]
    events = portal.state.events
    assert "windows-input:Existing Run|shutdown /l|Enter" in events
    assert not [event for event in events if "Win+X@" in event]
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_log_off_waits_for_a_painted_desktop_before_sending_windows_input(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portal.state.session = "disconnected"
    client = make_client(
        run_kind=RunKind.CHECKOUT, timeouts=replace(FAST, desktop_paint_ms=PAINT_WAIT_MS)
    )
    client.login()
    real_open = client.open_desktop

    def open_on_a_black_desktop(name: str) -> None:
        real_open(name)
        paint_remote_surface(client, "rgb(0, 0, 0)")
        paint_remote_surface_later(client, "rgb(0, 120, 215)", PAINTED_AFTER_MS)

    painted_at_input: list[bool] = []
    real_click = Mouse.click

    def click(mouse: Mouse, x: float, y: float, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("button") == "right":
            page = client._page
            assert page is not None
            surface = horizon_playwright._largest_surface(page)
            assert surface is not None
            painted_at_input.append(
                horizon_playwright._frame_is_painted(page, surface.screenshot(type="png"))
            )
        real_click(mouse, x, y, *args, **kwargs)

    monkeypatch.setattr(client, "open_desktop", open_on_a_black_desktop)
    monkeypatch.setattr(Mouse, "click", click)

    client.log_off(DESKTOP)

    assert painted_at_input == [True], "Win+X reached Windows while its desktop was black"


def test_log_off_waits_for_a_real_repaint_after_focus(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    client = make_client(
        run_kind=RunKind.CHECKOUT, timeouts=replace(FAST, desktop_paint_ms=PAINT_WAIT_MS)
    )
    client.login()
    focused = 0
    real_focus = Locator.focus

    def gray_on_first_focus(locator: Locator, *args: Any, **kwargs: Any) -> None:
        nonlocal focused
        if focused == 0:
            paint_remote_surface(client, "rgb(220, 220, 220)")
            paint_remote_surface_later(client, "rgb(0, 120, 215)", PAINTED_AFTER_MS)
        focused += 1
        real_focus(locator, *args, **kwargs)

    colours_at_input: list[list[int]] = []
    real_click = Mouse.click

    def click(mouse: Mouse, x: float, y: float, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("button") == "right":
            page = client._page
            assert page is not None
            colours_at_input.append(
                page.evaluate(
                    "Array.from(document.querySelector('#canvas-container canvas')"
                    ".getContext('2d').getImageData(0, 0, 1, 1).data.slice(0, 3))"
                )
            )
        real_click(mouse, x, y, *args, **kwargs)

    monkeypatch.setattr(Locator, "focus", gray_on_first_focus)
    monkeypatch.setattr(Mouse, "click", click)

    client.log_off(DESKTOP)

    assert focused >= 2, "focus was not restored after the readiness check"
    assert colours_at_input == [[0, 120, 215]], "Win+X was sent on the gray repaint"


def test_log_off_without_surface_bounds_sends_no_windows_input(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()
    monkeypatch.setattr(Locator, "bounding_box", lambda _locator: None)

    error = fails_with(Reason.LOGOFF_NOT_CONFIRMED, lambda: client.log_off(DESKTOP))

    assert not [event for event in portal.state.events if event.startswith("windows-input:")]
    assert "kill-session" not in portal.state.events
    assert artifacts.asked == [RunKind.CHECKOUT]
    assert error.screenshot is not None


def test_log_off_after_reading_the_state_ends_the_session(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    # The check-out's own order: read the state, then log off. The menu the read opened
    # must be closed by then, and the client's menu ignores Escape.
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    assert client.desktop_status(DESKTOP).state is SessionState.DISCONNECTED
    client.log_off(DESKTOP)

    assert "windows-sign-out" in portal.state.events
    assert "kill-session" not in portal.state.events
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_a_log_off_the_portal_never_confirms_fails_with_a_screenshot(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    portal.state.ignore_logoff = True
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    error = fails_with(Reason.LOGOFF_NOT_CONFIRMED, lambda: client.log_off(DESKTOP))

    assert "windows-sign-out" in portal.state.events
    assert artifacts.asked == [RunKind.CHECKOUT, RunKind.CHECKOUT]
    assert error.screenshot is not None
    assert client.desktop_status(DESKTOP).state is SessionState.DISCONNECTED


def test_a_log_off_is_confirmed_only_once_a_fresh_list_shows_the_session_gone(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    # A broker that ends the session a few lists after the Windows command must be waited
    # for: the open desktop's disappearance is not the broker confirmation.
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
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
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    portal.state.login_survives_reload = False
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    assert "windows-sign-out" in portal.state.events
    assert portal.state.events.count("login-accepted") == 2
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def test_a_desktop_that_never_becomes_ready_receives_no_windows_input(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
) -> None:
    portal.state.session = "disconnected"
    client = make_client(
        run_kind=RunKind.CHECKOUT,
        timeouts=replace(FAST, desktop_paint_ms=SHORTER_THAN_A_SAMPLE_MS),
    )
    client.login()

    error = fails_with(Reason.LOGOFF_NOT_CONFIRMED, lambda: client.log_off(DESKTOP))

    assert not [event for event in portal.state.events if event.startswith("windows-input:")]
    assert "kill-session" not in portal.state.events
    assert artifacts.asked == [RunKind.CHECKOUT]
    assert error.screenshot is not None


def test_a_black_desktop_times_out_without_receiving_windows_input(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 0, 0)"
    client = make_client(
        run_kind=RunKind.CHECKOUT,
        timeouts=replace(FAST, desktop_paint_ms=SHORT_PAINT_MS),
    )
    client.login()

    fails_with(Reason.LOGOFF_NOT_CONFIRMED, lambda: client.log_off(DESKTOP))

    assert not [event for event in portal.state.events if event.startswith("windows-input:")]
    assert "Horizon desktop not ready for Windows input" in caplog.text


def test_log_off_cancels_a_dialog_before_sending_windows_input(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 0, 0)"
    portal.state.repaint_desktop = "rgb(0, 120, 215)"
    portal.state.repaint_desktop_after_ms = PAINTED_AFTER_MS * 2
    portal.state.fullscreen_again_after_ms = PAINTED_AFTER_MS
    client = make_client(
        run_kind=RunKind.CHECKOUT, timeouts=replace(FAST, desktop_paint_ms=PAINT_WAIT_MS)
    )
    client.login()

    client.log_off(DESKTOP)

    events = portal.state.events
    cancelled_at = [index for index, event in enumerate(events) if event == "fullscreen-cancelled"]
    assert len(cancelled_at) == 2, "the second Fullscreen offer was not cancelled"
    windows_input = "windows-input:Win+X@20,700|Run@85,600|shutdown /l|Enter"
    assert cancelled_at[-1] < events.index(windows_input)
    assert "fullscreen-accepted" not in events


def test_log_off_recancels_fullscreen_after_the_start_right_click(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    portal.state.fullscreen_on_start_click = True
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    events = portal.state.events
    offered = events.index("fullscreen-offered-again")
    cancelled = events.index("fullscreen-cancelled", offered)
    windows_input = "windows-input:Win+X@20,700|Run@85,600|shutdown /l|Enter"
    assert cancelled < events.index(windows_input)
    assert "fullscreen-accepted" not in events


def test_log_off_recancels_fullscreen_after_focusing_the_surface(
    make_client: Callable[..., PlaywrightHorizonClient], portal: Portal
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    portal.state.fullscreen_on_surface_click = True
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    client.log_off(DESKTOP)

    events = portal.state.events
    offered = events.index("fullscreen-offered-focus")
    cancelled = events.index("fullscreen-cancelled", offered)
    assert cancelled < events.index("windows-input:Win+X@20,700|Run@85,600|shutdown /l|Enter")
    assert "fullscreen-accepted" not in events


def test_log_off_without_a_session_is_already_logged_off(
    client: PlaywrightHorizonClient, portal: Portal
) -> None:
    client.login()

    fails_with(Reason.ALREADY_LOGGED_OFF, lambda: client.log_off(DESKTOP))

    assert "kill-session" not in portal.state.events
    assert not [event for event in portal.state.events if event.startswith("windows-input:")]


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


# --- the success screenshot ------------------------------------------------------------

DESKTOP_BLUE = (0, 120, 215)
# The side of the grid the capture reads a surface on.
PAINT_GRID_SIDE = 32
# A remote surface the page paints this long after the capture's first sample.
PAINTED_AFTER_MS = 300
# A bound long enough for several samples after that paint.
PAINT_WAIT_MS = 5_000
# A bound shorter than a poll interval set to twice it, and the time one sample, the
# start and the return may add on this machine.
SHORT_PAINT_MS = 1_500
SAMPLE_SLACK_MS = 500


def png_size(data: bytes) -> tuple[int, int]:
    """The width and height stored in a PNG's IHDR."""
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", data[16:24])


def paint_remote_surface(
    client: PlaywrightHorizonClient,
    color: str,
    *,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Fill the Blast canvas. A width and height replace its bitmap, which clears it first."""
    page = client._page
    assert page is not None
    page.evaluate(
        """({ color, width, height }) => {
            const canvas = document.querySelector("#canvas-container canvas");
            if (width !== null) { canvas.width = width; }
            if (height !== null) { canvas.height = height; }
            const context = canvas.getContext("2d");
            context.fillStyle = color;
            context.fillRect(0, 0, canvas.width, canvas.height);
        }""",
        {"color": color, "width": width, "height": height},
    )


def add_small_bright_canvas(client: PlaywrightHorizonClient) -> None:
    """A 64 by 64 red canvas ahead of the remote surface, smaller than the Blast canvas.

    It is the container's first child, so the first surface in document order is the
    small one: a capture that read the first surface instead of the largest would see red.
    """
    page = client._page
    assert page is not None
    page.evaluate(
        """() => {
            const canvas = document.createElement("canvas");
            canvas.width = 64;
            canvas.height = 64;
            const context = canvas.getContext("2d");
            context.fillStyle = "rgb(255, 0, 0)";
            context.fillRect(0, 0, 64, 64);
            const container = document.querySelector("#canvas-container");
            container.insertBefore(canvas, container.firstChild);
        }"""
    )


def light_the_first_row(client: PlaywrightHorizonClient, pixels: int, channel: int) -> None:
    """A black 32 by 32 Blast canvas whose first ``pixels`` of row 0 are rgb(channel, 0, 0).

    At 32 by 32 the paint grid is the bitmap itself, so the count is exact.
    """
    paint_remote_surface(client, "rgb(0, 0, 0)", width=PAINT_GRID_SIDE, height=PAINT_GRID_SIDE)
    page = client._page
    assert page is not None
    page.evaluate(
        """({ pixels, channel }) => {
            const canvas = document.querySelector("#canvas-container canvas");
            const context = canvas.getContext("2d");
            context.fillStyle = `rgb(${channel}, 0, 0)`;
            context.fillRect(0, 0, pixels, 1);
        }""",
        {"pixels": pixels, "channel": channel},
    )


def paint_remote_surface_later(client: PlaywrightHorizonClient, color: str, after_ms: int) -> None:
    """Fill the Blast canvas with ``color`` once ``after_ms`` have passed, from a page timer."""
    page = client._page
    assert page is not None
    page.evaluate(
        """({ color, afterMs }) => {
            setTimeout(() => {
                const canvas = document.querySelector("#canvas-container canvas");
                const context = canvas.getContext("2d");
                context.fillStyle = color;
                context.fillRect(0, 0, canvas.width, canvas.height);
            }, afterMs);
        }""",
        {"color": color, "afterMs": after_ms},
    )


def test_open_desktop_returns_no_success_screenshot(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
    photographed: list[str],
) -> None:
    client.login()

    # mypy will not let a caller read a None return. This proves the call gives no path.
    opened = client.open_desktop(DESKTOP)  # type: ignore[func-returns-value]
    assert opened is None

    assert artifacts.asked == []
    assert photographed == []
    assert list(artifacts.root.iterdir()) == []
    assert client.desktop_status(DESKTOP).state is SessionState.CONNECTED


def test_a_black_remote_surface_is_not_saved(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Each sample takes a frame to judge it; a black one is judged and never saved.
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(0, 0, 0)")

    assert client.capture_open_desktop() is None

    assert artifacts.asked == []
    assert list(artifacts.root.iterdir()) == []
    assert "Horizon desktop still blank" in caplog.text


def test_a_uniform_bright_gray_surface_is_not_saved(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(220, 220, 220)")

    assert client.capture_open_desktop() is None
    assert artifacts.asked == []


def test_a_normal_windows_desktop_is_saved(
    client: PlaywrightHorizonClient,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(0, 120, 215)")
    page = client._page
    assert page is not None
    page.evaluate(
        """() => {
            const context = document.querySelector("#canvas-container canvas").getContext("2d");
            context.fillStyle = "rgb(240, 240, 240)";
            context.fillRect(180, 100, 600, 400);
            context.fillStyle = "rgb(45, 45, 45)";
            context.fillRect(180, 100, 600, 48);
            context.fillStyle = "rgb(255, 255, 255)";
            context.fillRect(210, 180, 300, 220);
        }"""
    )

    assert client.capture_open_desktop() is not None


def test_a_painted_remote_surface_is_saved(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
    photographed: list[str],
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(220, 30, 30)", width=200, height=100)

    shot = client.capture_open_desktop()

    assert shot is not None
    assert png_size(shot.read_bytes()) == (200, 100)
    assert artifacts.asked == [RunKind.CHECKIN]
    assert photographed == ["#/desktop"]


def test_a_smaller_bright_canvas_does_not_paint_a_black_desktop(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(0, 0, 0)")
    add_small_bright_canvas(client)

    assert client.capture_open_desktop() is None

    assert artifacts.asked == []
    assert list(artifacts.root.iterdir()) == []
    assert "Horizon desktop still blank" in caplog.text


@pytest.mark.parametrize(
    ("pixels", "channel", "painted"),
    [(7, 24, False), (8, 23, False), (8, 24, True)],
    ids=["seven-lit-cells", "a-channel-below-24", "eight-cells-at-24"],
)
def test_a_surface_is_painted_from_eight_lit_cells_of_its_grid(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
    pixels: int,
    channel: int,
    painted: bool,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    light_the_first_row(client, pixels, channel)

    shot = client.capture_open_desktop()

    assert (shot is not None) is painted
    assert artifacts.asked == ([RunKind.CHECKIN] if painted else [])


def test_a_surface_lit_only_past_its_top_left_corner_is_painted(
    client: PlaywrightHorizonClient,
) -> None:
    # 64 by 32, black on the left and red on the right: a 32 by 32 crop of the top-left
    # corner is black, a grid spread across the whole surface reaches the lit half.
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(0, 0, 0)", width=2 * PAINT_GRID_SIDE, height=PAINT_GRID_SIDE)
    page = client._page
    assert page is not None
    page.evaluate(
        """(side) => {
            const canvas = document.querySelector("#canvas-container canvas");
            const context = canvas.getContext("2d");
            context.fillStyle = "rgb(255, 0, 0)";
            context.fillRect(side, 0, side, side);
        }""",
        PAINT_GRID_SIDE,
    )

    assert client.capture_open_desktop() is not None


def test_the_photo_is_of_the_largest_surface_not_the_first(
    client: PlaywrightHorizonClient,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb({}, {}, {})".format(*DESKTOP_BLUE), width=200, height=100)
    add_small_bright_canvas(client)

    shot = client.capture_open_desktop()

    assert shot is not None
    assert png_size(shot.read_bytes()) == (200, 100)


def test_a_surface_with_no_frame_yet_is_not_photographed(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
    photographed: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A video larger than the painted Blast canvas that has received no frame: the page
    # shows only what lies behind it, which is not the desktop.
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb({}, {}, {})".format(*DESKTOP_BLUE))
    page = client._page
    assert page is not None
    page.evaluate(
        """() => {
            const video = document.createElement("video");
            video.style.width = "1600px";
            video.style.height = "900px";
            document.querySelector("#canvas-container").appendChild(video);
        }"""
    )

    assert client.capture_open_desktop() is None

    assert photographed == [], "a surface with no frame was photographed"
    assert artifacts.asked == []
    assert "Horizon desktop still blank" in caplog.text


def paint_a_webgl_surface(client: PlaywrightHorizonClient, colour: tuple[int, int, int]) -> bool:
    """Replace the Blast canvas with a 200 by 100 WebGL one cleared to ``colour``.

    The context keeps no drawing buffer (the WebGL default), so once the page has
    composited the frame the canvas's own bitmap reads blank: only the composited pixels
    show the colour. Answers False when the browser offers no WebGL context.
    """
    page = client._page
    assert page is not None
    created = page.evaluate(
        """async ([red, green, blue]) => {
            const canvas = document.createElement("canvas");
            canvas.width = 200;
            canvas.height = 100;
            const gl = canvas.getContext("webgl", { preserveDrawingBuffer: false });
            if (gl === null) { return false; }
            document.querySelector("#canvas-container canvas").replaceWith(canvas);
            gl.clearColor(red / 255, green / 255, blue / 255, 1);
            gl.clear(gl.COLOR_BUFFER_BIT);
            // Two frames: the clear is composited, then the drawing buffer is discarded.
            await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
            return true;
        }""",
        list(colour),
    )
    return bool(created)


def test_a_webgl_surface_that_keeps_no_drawing_buffer_is_photographed(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    if not paint_a_webgl_surface(client, DESKTOP_BLUE):
        pytest.skip("this browser offers no WebGL context, so the case cannot be built")

    shot = client.capture_open_desktop()

    assert shot is not None, "the paint was read from the surface's bitmap, which WebGL discarded"
    assert png_size(shot.read_bytes()) == (200, 100)
    page = client._page
    assert page is not None
    assert colours_unlike(page, shot.read_bytes(), DESKTOP_BLUE) == []
    assert artifacts.asked == [RunKind.CHECKIN]


def test_the_paint_is_judged_on_the_composited_frame_not_the_surfaces_bitmap(
    client: PlaywrightHorizonClient,
) -> None:
    # A surface whose own bitmap is empty (transparent black) while the page shows it
    # painted, here by its CSS background: the photo a person would see is not blank.
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgba(0, 0, 0, 0)", width=200, height=100)
    page = client._page
    assert page is not None
    page.evaluate(
        """(colour) => {
            document.querySelector("#canvas-container canvas").style.background = colour;
        }""",
        "rgb({}, {}, {})".format(*DESKTOP_BLUE),
    )

    shot = client.capture_open_desktop()

    assert shot is not None, "the paint was read from the surface's bitmap, not the frame"
    assert colours_unlike(page, shot.read_bytes(), DESKTOP_BLUE) == []


def test_a_frame_a_dialog_came_into_is_discarded_and_sampled_again(
    client: PlaywrightHorizonClient,
    portal: Portal,
    artifacts: RecordingArtifacts,
    photographed: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb({}, {}, {})".format(*DESKTOP_BLUE))
    real_screenshot = Locator.screenshot
    offered: list[bool] = []

    def offer_then_take(locator: Locator, *args: Any, **kwargs: Any) -> bytes:
        # The client shows its dialog after the sample looked for one and before the
        # frame is taken, once: the frame carries it.
        if not offered:
            offered.append(True)
            locator.page.evaluate("() => { document.querySelector('#dialog').hidden = false; }")
        return real_screenshot(locator, *args, **kwargs)

    monkeypatch.setattr(Locator, "screenshot", offer_then_take)

    shot = client.capture_open_desktop()

    assert shot is not None
    page = client._page
    assert page is not None
    assert colours_unlike(page, shot.read_bytes(), DESKTOP_BLUE) == [], "the dialog is in the frame"
    assert photographed == ["#/desktop", "#/desktop"]
    assert artifacts.asked == [RunKind.CHECKIN]
    assert wait_for(lambda: portal.state.events.count("fullscreen-cancelled") == 2)
    assert "fullscreen-accepted" not in portal.state.events


def test_a_frame_the_page_cannot_decode_leaves_no_photo_and_raises_nothing(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(220, 30, 30)", width=200, height=100)

    def a_frame_no_browser_decodes(*_args: object, **_kwargs: object) -> bytes:
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    monkeypatch.setattr(Locator, "screenshot", a_frame_no_browser_decodes)

    assert client.capture_open_desktop() is None

    assert artifacts.asked == []
    assert list(artifacts.root.iterdir()) == []
    assert "Horizon screenshot failed: Error" in caplog.text
    assert "Horizon desktop still blank" not in caplog.text
    assert client.desktop_status(DESKTOP).state is SessionState.CONNECTED


# Less than any sample takes on this machine (a frame and its decode), and under the
# floor of 250 ms the capture needs left to start one.
SHORTER_THAN_A_SAMPLE_MS = 100


def test_a_capture_with_less_left_than_a_sample_takes_starts_none(
    make_client: Callable[..., PlaywrightHorizonClient],
    artifacts: RecordingArtifacts,
    photographed: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = make_client(timeouts=replace(FAST, desktop_paint_ms=SHORTER_THAN_A_SAMPLE_MS))
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(220, 30, 30)", width=200, height=100)

    assert client.capture_open_desktop() is None

    assert photographed == [], "a sample was started that could only time out"
    assert artifacts.asked == []
    assert "Horizon desktop still blank" in caplog.text
    assert "Horizon screenshot failed" not in caplog.text


def test_a_surface_black_at_the_first_sample_and_painted_later_is_photographed(
    make_client: Callable[..., PlaywrightHorizonClient],
    artifacts: RecordingArtifacts,
) -> None:
    client = make_client(timeouts=replace(FAST, desktop_paint_ms=PAINT_WAIT_MS))
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(0, 0, 0)")
    paint_remote_surface_later(client, "rgb({}, {}, {})".format(*DESKTOP_BLUE), PAINTED_AFTER_MS)

    shot = client.capture_open_desktop()

    assert shot is not None, "the capture gave up after its first, black, sample"
    page = client._page
    assert page is not None
    assert colours_unlike(page, shot.read_bytes(), DESKTOP_BLUE) == []
    assert artifacts.asked == [RunKind.CHECKIN]


def test_a_pause_between_samples_never_outlasts_the_capture_bound(
    make_client: Callable[..., PlaywrightHorizonClient],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A poll interval twice the bound: a pause that is not cut to what is left of the
    # bound starts one more sample long after it.
    timeouts = replace(FAST, desktop_paint_ms=SHORT_PAINT_MS, poll_ms=2 * SHORT_PAINT_MS)
    client = make_client(timeouts=timeouts)
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(0, 0, 0)")
    started = time.monotonic()

    assert client.capture_open_desktop() is None

    elapsed_ms = (time.monotonic() - started) * 1000
    assert elapsed_ms < SHORT_PAINT_MS + SAMPLE_SLACK_MS, f"the capture took {elapsed_ms:.0f} ms"
    assert "Horizon desktop still blank" in caplog.text


def test_the_photo_waits_no_longer_than_the_capture_has_left(
    client: PlaywrightHorizonClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(220, 30, 30)", width=200, height=100)
    timeouts: list[object] = []
    real_screenshot = Locator.screenshot

    def spy(locator: Locator, *args: Any, **kwargs: Any) -> bytes:
        timeouts.append(kwargs.get("timeout"))
        return real_screenshot(locator, *args, **kwargs)

    monkeypatch.setattr(Locator, "screenshot", spy)

    assert client.capture_open_desktop() is not None

    assert len(timeouts) == 1
    timeout = timeouts[0]
    assert isinstance(timeout, int | float), "the photo waits on the action timeout instead"
    assert 0 < timeout <= FAST.desktop_paint_ms


def test_a_page_closed_after_a_blank_sample_stops_the_capture_without_a_failure(
    client: PlaywrightHorizonClient,
    artifacts: RecordingArtifacts,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(0, 0, 0)")
    real_evaluate = Page.evaluate
    closed_after: list[object] = []

    def close_once_the_frame_is_read(page: Page, expression: str, *args: Any) -> Any:
        # The page goes away only once a sample has read its frame's lit cells, so that
        # sample judges the black frame and waits. The pause and the next sample are the
        # ones that find the page closed.
        answer = real_evaluate(page, expression, *args)
        if expression == horizon_playwright._LIT_CELLS:
            closed_after.append(answer)
            page.close()
        return answer

    monkeypatch.setattr(Page, "evaluate", close_once_the_frame_is_read)

    assert client.capture_open_desktop() is None

    assert closed_after == [{"lit": 0, "luminanceRange": 0, "maxChroma": 0}], (
        "the page did not close after a blank sample"
    )
    assert artifacts.asked == []
    assert list(artifacts.root.iterdir()) == []
    assert "Horizon screenshot failed" not in caplog.text
    assert "Horizon desktop still blank" not in caplog.text


def test_capture_on_the_login_page_saves_nothing(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
    photographed: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    portal.state.drop_to_login_after_ms = DROP_TO_LOGIN_AFTER_MS
    client = make_client()
    client.login()
    client.open_desktop(DESKTOP)
    page = client._page
    assert page is not None
    # The page's timer only runs while Playwright is polling, so wait on the page.
    page.wait_for_function("() => location.hash.split('?')[0] === '#/home'", timeout=3_000)

    assert client.capture_open_desktop() is None

    assert photographed == []
    assert artifacts.asked == []
    assert list(artifacts.root.iterdir()) == []
    assert "Horizon desktop still blank" not in caplog.text


# Long after open_desktop has seen the paint (it polls every FAST.poll_ms), so the second
# offer comes while the desktop is held, as on the live portal.
FULLSCREEN_AGAIN_AFTER_MS = 500


def open_a_desktop_the_client_offers_fullscreen_on_again(
    client: PlaywrightHorizonClient, portal: Portal, *, sticks: bool = False
) -> None:
    """Open a painted desktop, then wait until the client shows its Fullscreen offer again."""
    portal.state.fullscreen_again_after_ms = FULLSCREEN_AGAIN_AFTER_MS
    portal.state.fullscreen_sticks = sticks
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb({}, {}, {})".format(*DESKTOP_BLUE))
    offered = "fullscreen-offered-sticky" if sticks else "fullscreen-offered-again"
    assert wait_for(lambda: offered in portal.state.events), "the client never offered again"
    page = client._page
    assert page is not None
    assert page.locator(horizon_playwright.DIALOG_CANCEL).is_visible()


def test_a_dialog_the_client_shows_after_the_paint_is_cancelled_before_the_frame(
    client: PlaywrightHorizonClient,
    portal: Portal,
    artifacts: RecordingArtifacts,
    photographed: list[str],
) -> None:
    open_a_desktop_the_client_offers_fullscreen_on_again(client, portal)

    shot = client.capture_open_desktop()

    assert shot is not None
    page = client._page
    assert page is not None
    assert colours_unlike(page, shot.read_bytes(), DESKTOP_BLUE) == [], "the dialog is in the frame"
    assert portal.state.events.count("fullscreen-cancelled") == 2
    assert "fullscreen-accepted" not in portal.state.events
    assert photographed == ["#/desktop"]
    assert artifacts.asked == [RunKind.CHECKIN]
    assert client.desktop_status(DESKTOP).state is SessionState.CONNECTED


def test_a_dialog_that_cannot_be_dismissed_leaves_no_photo_and_is_never_accepted(
    client: PlaywrightHorizonClient,
    portal: Portal,
    artifacts: RecordingArtifacts,
    photographed: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    open_a_desktop_the_client_offers_fullscreen_on_again(client, portal, sticks=True)
    started = time.monotonic()

    assert client.capture_open_desktop() is None

    elapsed_ms = (time.monotonic() - started) * 1000
    assert elapsed_ms < FAST.desktop_paint_ms + FAST.action_ms, "the capture overran its bound"
    assert "fullscreen-cancel-ignored" in portal.state.events, "Cancel was never tried"
    assert "fullscreen-accepted" not in portal.state.events
    assert photographed == [], "a frame was taken while the dialog showed"
    assert artifacts.asked == []
    assert "Horizon client dialog still open" in caplog.text
    assert "Horizon desktop still blank" not in caplog.text
    assert client.desktop_status(DESKTOP).state is SessionState.CONNECTED


def test_a_dialog_with_only_ok_is_never_answered_and_leaves_no_photo(
    client: PlaywrightHorizonClient,
    portal: Portal,
    artifacts: RecordingArtifacts,
    photographed: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    open_a_desktop_the_client_offers_fullscreen_on_again(client, portal)
    page = client._page
    assert page is not None
    # A dialog the client shows with OK alone: an answer the adapter must never give.
    page.evaluate("() => { document.querySelector('#cancelDialogBtn').hidden = true; }")

    assert client.capture_open_desktop() is None

    assert "fullscreen-accepted" not in portal.state.events
    assert photographed == [], "a frame was taken while the dialog showed"
    assert artifacts.asked == []
    assert "Horizon client dialog still open" in caplog.text


def test_a_log_off_answers_with_a_screenshot_of_the_list_without_the_session(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
    photographed: list[str],
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    shot = client.log_off(DESKTOP)

    assert shot is not None
    assert shot.read_bytes().startswith(b"\x89PNG")
    assert artifacts.asked == [RunKind.CHECKOUT, RunKind.CHECKOUT]
    # Readiness samples save nothing. The last desktop photo precedes Enter; the final
    # artifact is the freshly loaded launch-items list after broker confirmation.
    assert photographed[-2:] == ["#/desktop", "#/launchitems"]
    assert set(photographed[:-2]) == {"#/desktop"}
    assert portal.state.session == "none"


def test_a_log_off_is_finally_photographed_only_once_the_broker_has_ended_the_session(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A broker that ends the session two lists after the Windows command distinguishes
    # the final confirmation photo from the pre-Enter evidence on the desktop.
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    portal.state.logoff_lag_lists = 2
    broker_at_photo: list[str] = []
    real_screenshot = Page.screenshot

    def spy(page: Page, *args: Any, **kwargs: Any) -> bytes:
        broker_at_photo.append(portal.state.session)
        return real_screenshot(page, *args, **kwargs)

    monkeypatch.setattr(Page, "screenshot", spy)
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()

    shot = client.log_off(DESKTOP)

    assert shot is not None
    assert broker_at_photo == ["connected", "none"]


def refuse_the_screenshot(monkeypatch: pytest.MonkeyPatch, artifacts: RecordingArtifacts) -> None:
    """Playwright fails the screenshot, with the password in its message."""

    def refuse(*_args: object, **_kwargs: object) -> bytes:
        raise PlaywrightError(f"Target crashed {PASSWORD}")

    monkeypatch.setattr(Page, "screenshot", refuse)


def refuse_the_disk(monkeypatch: pytest.MonkeyPatch, artifacts: RecordingArtifacts) -> None:
    """The store hands out paths under a file, so writing the screenshot fails (an OSError)."""
    blocked = artifacts.root / "not-a-directory"
    blocked.write_bytes(b"")
    monkeypatch.setattr(artifacts, "root", blocked)


@pytest.mark.parametrize(
    ("fault", "error_types"),
    [
        (refuse_the_screenshot, ("Error",)),
        (refuse_the_disk, ("FileExistsError", "NotADirectoryError")),
    ],
)
def test_a_log_off_screenshot_that_fails_is_logged_by_type_and_the_step_still_succeeds(
    make_client: Callable[..., PlaywrightHorizonClient],
    portal: Portal,
    artifacts: RecordingArtifacts,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    fault: Callable[[pytest.MonkeyPatch, RecordingArtifacts], None],
    error_types: tuple[str, ...],
) -> None:
    portal.state.session = "disconnected"
    portal.state.paint_desktop = "rgb(0, 120, 215)"
    client = make_client(run_kind=RunKind.CHECKOUT)
    client.login()
    fault(monkeypatch, artifacts)

    shot = client.log_off(DESKTOP)

    assert shot is None
    assert artifacts.asked == [RunKind.CHECKOUT, RunKind.CHECKOUT], (
        "the pre-Enter or final screenshot was never attempted"
    )
    assert any(
        f"Horizon screenshot failed: {error_type}" in caplog.text for error_type in error_types
    )
    assert PASSWORD not in caplog.text
    assert client.desktop_status(DESKTOP).state is SessionState.NO_SESSION


def refuse_the_element_screenshot(
    monkeypatch: pytest.MonkeyPatch, artifacts: RecordingArtifacts
) -> None:
    """The element screenshot fails, with the password in its message."""

    def refuse(*_args: object, **_kwargs: object) -> bytes:
        raise PlaywrightError(f"Target crashed {PASSWORD}")

    monkeypatch.setattr(Locator, "screenshot", refuse)


@pytest.mark.parametrize(
    ("fault", "error_type"),
    [(refuse_the_element_screenshot, "Error"), (refuse_the_disk, "NotADirectoryError")],
)
def test_a_capture_whose_screenshot_fails_returns_none(
    make_client: Callable[..., PlaywrightHorizonClient],
    artifacts: RecordingArtifacts,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    fault: Callable[[pytest.MonkeyPatch, RecordingArtifacts], None],
    error_type: str,
) -> None:
    client = make_client()
    client.login()
    client.open_desktop(DESKTOP)
    paint_remote_surface(client, "rgb(220, 30, 30)", width=200, height=100)
    fault(monkeypatch, artifacts)

    assert client.capture_open_desktop() is None

    assert f"Horizon screenshot failed: {error_type}" in caplog.text
    assert "Horizon desktop still blank" not in caplog.text
    assert PASSWORD not in caplog.text
    assert client.desktop_status(DESKTOP).state is SessionState.CONNECTED


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
