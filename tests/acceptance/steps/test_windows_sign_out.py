"""Windows Win+X sign-out through the real adapter on the local HTML Access fixture."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.infrastructure.horizon_playwright import PlaywrightHorizonClient
from tests.support.htmlaccess_portal import (
    FAST,
    PASSWORD,
    USERNAME,
    Portal,
    RecordingArtifacts,
    chrome_for_tests,
    serve_portal,
)

scenarios("windows_sign_out.feature")


@pytest.fixture
def fixture_portal() -> Iterator[Portal]:
    with serve_portal() as running:
        yield running


@pytest.fixture
def windows_client(fixture_portal: Portal, tmp_path: Path) -> Iterator[PlaywrightHorizonClient]:
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
    yield client
    client.close()


@given("the fixture portal's desktop has a disconnected session")
def disconnected_session(fixture_portal: Portal) -> None:
    fixture_portal.state.session = "disconnected"
    fixture_portal.state.paint_desktop = "rgb(0, 120, 215)"


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


@then("no kill-session command reached the broker")
def no_kill_session(fixture_portal: Portal) -> None:
    assert "kill-session" not in fixture_portal.state.events


@then("the desktop has no session on the fixture broker")
def no_session(fixture_portal: Portal) -> None:
    assert fixture_portal.state.session == "none"
