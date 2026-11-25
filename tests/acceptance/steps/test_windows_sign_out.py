"""Windows Win+X sign-out through the real adapter on the local HTML Access fixture."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from pytest_bdd import given, parsers, scenarios, then, when

from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.infrastructure.horizon_playwright import PlaywrightHorizonClient
from tests.support.htmlaccess_portal import (
    FAST,
    FRESH_LIST_CLICK_INTERCEPT_DELAY_MS,
    FRESH_LIST_DIALOG_DELAY_MS,
    PASSWORD,
    USERNAME,
    Portal,
    RecordingArtifacts,
    chrome_for_tests,
    offer_fullscreen,
    serve_portal,
)

RUN_WAIT_MS = 2_000

scenarios("windows_sign_out.feature")


@pytest.fixture
def fixture_portal() -> Iterator[Portal]:
    with serve_portal() as running:
        yield running


@pytest.fixture
def windows_client(
    fixture_portal: Portal, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[PlaywrightHorizonClient]:
    artifacts = RecordingArtifacts(tmp_path / "artifacts")
    artifacts.root.mkdir()
    client = PlaywrightHorizonClient(
        horizon_url=fixture_portal.url,
        username=USERNAME,
        password=PASSWORD,
        chrome_path=chrome_for_tests(),
        artifacts=artifacts,
        run_kind=RunKind.CHECKOUT,
        timeouts=FAST,
    )
    real_wait = Page.wait_for_timeout
    real_screenshot = Page.screenshot
    real_click = Locator.click
    fresh_list_click_held = False

    def wait_then_offer_fullscreen(page: Page, timeout: float) -> None:
        real_wait(page, timeout)
        if timeout == RUN_WAIT_MS and fixture_portal.state.fullscreen_after_run_wait:
            fixture_portal.state.fullscreen_after_run_wait = False
            offer_fullscreen(page, fixture_portal.state, "fullscreen-offered-post-run-wait")

    def screenshot_then_offer_fullscreen(page: Page, *args: Any, **kwargs: Any) -> bytes:
        png = real_screenshot(page, *args, **kwargs)
        if fixture_portal.state.fullscreen_on_pre_enter_screenshot:
            fixture_portal.state.fullscreen_on_pre_enter_screenshot = False
            offer_fullscreen(page, fixture_portal.state, "fullscreen-offered-pre-enter")
        return png

    def click_with_fresh_list_interception(locator: Locator, *args: Any, **kwargs: Any) -> None:
        nonlocal fresh_list_click_held
        classes = locator.get_attribute("class") or ""
        should_hold = (
            not fresh_list_click_held
            and "overflow-button" in classes
            and fixture_portal.state.fullscreen_on_fresh_list_delay_ms > 0
            and "windows-sign-out" in fixture_portal.state.events
        )
        if should_hold:
            fresh_list_click_held = True
            locator.page.locator("#logoffDialog").wait_for(state="visible", timeout=1_000)
            try:
                real_click(locator, *args, **kwargs)
            except PlaywrightTimeoutError:
                fixture_portal.state.record("fresh-list-overflow-click-blocked")
                raise
            raise AssertionError("Fullscreen did not intercept the fresh-list overflow click")
        real_click(locator, *args, **kwargs)

    monkeypatch.setattr(Page, "wait_for_timeout", wait_then_offer_fullscreen)
    monkeypatch.setattr(Page, "screenshot", screenshot_then_offer_fullscreen)
    monkeypatch.setattr(Locator, "click", click_with_fresh_list_interception)
    yield client
    client.close()


@given("the fixture portal's desktop has a disconnected session")
def disconnected_session(fixture_portal: Portal) -> None:
    fixture_portal.state.session = "disconnected"
    fixture_portal.state.paint_desktop = "rgb(0, 120, 215)"


@given("the fixture Windows Run dialog is already open at the v1.1.6 production geometry")
def run_already_open(fixture_portal: Portal) -> None:
    fixture_portal.state.run_already_open = True


@given("the fixture offers Fullscreen over the fresh broker list")
def fullscreen_over_fresh_list(fixture_portal: Portal) -> None:
    fixture_portal.state.fullscreen_on_fresh_list = True


@given("the fixture offers Fullscreen asynchronously over the fresh broker list")
def delayed_fullscreen_over_fresh_list(fixture_portal: Portal) -> None:
    fullscreen_over_fresh_list(fixture_portal)
    fixture_portal.state.fullscreen_on_fresh_list_delay_ms = FRESH_LIST_DIALOG_DELAY_MS


@given("the fixture offers Fullscreen beyond the old fresh-list observation window")
def click_intercepting_fullscreen_over_fresh_list(fixture_portal: Portal) -> None:
    fullscreen_over_fresh_list(fixture_portal)
    fixture_portal.state.fullscreen_on_fresh_list_delay_ms = FRESH_LIST_CLICK_INTERCEPT_DELAY_MS


@given("the fixture offers Fullscreen during the post-Run wait")
def fullscreen_after_run_wait(fixture_portal: Portal) -> None:
    fixture_portal.state.fullscreen_after_run_wait = True


@given("the fixture offers Fullscreen during the pre-Enter screenshot")
def fullscreen_on_pre_enter_screenshot(fixture_portal: Portal) -> None:
    fixture_portal.state.fullscreen_on_pre_enter_screenshot = True


@when(parsers.parse('the Playwright client logs off "{desktop}"'))
def log_off(windows_client: PlaywrightHorizonClient, desktop: str) -> None:
    windows_client.login()
    windows_client.log_off(desktop)


@then("the desktop was opened before Windows signed out")
def opened_before_sign_out(fixture_portal: Portal) -> None:
    events = fixture_portal.state.events
    assert events.index("blast-open") < events.index("windows-sign-out")


@then('Windows received Start right-click, Run, "shutdown /l" and Enter in order')
def mouse_and_keyboard_sign_out(fixture_portal: Portal) -> None:
    sequence = "Win+X@20,700|Run@85,600|shutdown /l|Enter"
    assert f"windows-input:{sequence}" in fixture_portal.state.events


@then('Windows received the existing Run field, "shutdown /l" and Enter in order')
def existing_run_sign_out(fixture_portal: Portal) -> None:
    assert "windows-input:Existing Run|shutdown /l|Enter" in fixture_portal.state.events


@then("no Win+X mouse sequence reached Windows")
def no_winx_sequence(fixture_portal: Portal) -> None:
    assert not [event for event in fixture_portal.state.events if "Win+X@" in event]


@then("the fresh-list Fullscreen offer was cancelled without OK")
def fresh_list_fullscreen_cancelled(fixture_portal: Portal) -> None:
    events = fixture_portal.state.events
    assert "fullscreen-cancelled-fresh-list" in events
    assert "fullscreen-accepted-fresh-list" not in events


@then("the blocked fresh-list overflow click was retried after Cancel without OK")
def blocked_fresh_list_click_retried(fixture_portal: Portal) -> None:
    events = fixture_portal.state.events
    assert "fresh-list-overflow-click-blocked" in events
    assert "fullscreen-cancelled-fresh-list" in events
    assert "fullscreen-accepted-fresh-list" not in events


@then("both gap Fullscreen offers were cancelled without OK")
def gap_fullscreen_cancelled(fixture_portal: Portal) -> None:
    events = fixture_portal.state.events
    for offered in ("fullscreen-offered-post-run-wait", "fullscreen-offered-pre-enter"):
        assert offered in events
        assert "fullscreen-cancelled" in events[events.index(offered) :]
    assert "fullscreen-accepted" not in events


@then("Windows received Enter exactly once")
def exactly_one_windows_enter(fixture_portal: Portal) -> None:
    enters = [
        event
        for event in fixture_portal.state.events
        if event.startswith("windows-input:") and event.endswith("|Enter")
    ]
    assert len(enters) == 1


@then("no kill-session command reached the broker")
def no_kill_session(fixture_portal: Portal) -> None:
    assert "kill-session" not in fixture_portal.state.events


@then("the desktop has no session on the fixture broker")
def no_session(fixture_portal: Portal) -> None:
    assert fixture_portal.state.session == "none"
