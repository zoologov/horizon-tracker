"""No client dialog in the check-in photo: the real browser adapter on the HTML Access fixture.

Unlike the other features, these scenarios run the check-in over ``PlaywrightHorizonClient``
against the fixture portal of ``tests/support/htmlaccess_portal.py``; the calendar, the
clock and the artifact pruning stay fakes, and the notifier is the real Telegram adapter.
The fixture paints the remote surface one colour and, while the desktop is held, offers
Fullscreen again over it; the Then steps read the photo the owner got, decoded by a
browser of their own, and the portal's record of which answer the offer was given.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from pytest_bdd import given, scenarios, then

from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.infrastructure.horizon_playwright import PlaywrightHorizonClient
from tests.acceptance.steps.conftest import Scene
from tests.support.cli_world import World
from tests.support.htmlaccess_portal import (
    FAST,
    PASSWORD,
    USERNAME,
    Portal,
    RecordingArtifacts,
    chrome_for_tests,
    serve_portal,
    wait_for,
)
from tests.support.photo import colours_unlike

scenarios("client_dialog_in_the_photo.feature")

DESKTOP_BLUE = (0, 120, 215)
# Long after ``open_desktop`` has seen the paint, so the offer comes during the hold.
OFFER_AGAIN_AFTER_MS = 500
# How long the hold may wait, in real time, for the fixture's second offer.
OFFER_WAIT_S = 5.0


class HeldUntilTheClientOffersAgain(PlaywrightHorizonClient):
    """The browser adapter, whose photo waits until the client has offered Fullscreen again.

    The scene's clock is a fake, so the configured hold takes no real time; the fixture's
    second offer comes in real time. Waiting for it before the photo is what a hold long
    enough for the client to show its dialog looks like on a clock that does not run.
    """

    def __init__(self, portal: Portal, offered: str, artifacts: RecordingArtifacts) -> None:
        super().__init__(
            horizon_url=portal.url,
            username=USERNAME,
            password=PASSWORD,
            chrome_path=chrome_for_tests(),
            artifacts=artifacts,
            run_kind=RunKind.CHECKIN,
            timeouts=FAST,
        )
        self._portal = portal
        self._offered = offered

    def capture_open_desktop(self) -> Path | None:
        offered = wait_for(lambda: self._offered in self._portal.state.events, OFFER_WAIT_S)
        assert offered, "the client never offered Fullscreen again during the hold"
        return super().capture_open_desktop()


@pytest.fixture
def fixture_portal() -> Iterator[Portal]:
    with serve_portal() as running:
        yield running


@pytest.fixture
def browser_client() -> Iterator[list[PlaywrightHorizonClient]]:
    """The scenario's browser adapters, closed once it ends; one sync driver per thread."""
    built: list[PlaywrightHorizonClient] = []
    yield built
    for client in built:
        client.close()


# --- Given ----------------------------------------------------------------------------


@given("the check-in drives the browser client on a fixture portal whose desktop has no session")
def drives_the_browser_client(scene: Scene, fixture_portal: Portal) -> None:
    fixture_portal.state.paint_desktop = "rgb({}, {}, {})".format(*DESKTOP_BLUE)
    assert fixture_portal.state.session == "none"


def _offers_again(
    scene: Scene, portal: Portal, built: list[PlaywrightHorizonClient], *, sticks: bool
) -> None:
    portal.state.fullscreen_again_after_ms = OFFER_AGAIN_AFTER_MS
    portal.state.fullscreen_sticks = sticks
    offered = "fullscreen-offered-sticky" if sticks else "fullscreen-offered-again"
    artifacts_dir = scene.root / "browser-artifacts"
    artifacts_dir.mkdir()
    client = HeldUntilTheClientOffersAgain(portal, offered, RecordingArtifacts(artifacts_dir))
    built.append(client)

    def script(world: World) -> None:
        world.horizon = client

    scene.scripts.append(script)


@given("the client offers Fullscreen again while the desktop is held")
def offers_again(
    scene: Scene, fixture_portal: Portal, browser_client: list[PlaywrightHorizonClient]
) -> None:
    _offers_again(scene, fixture_portal, browser_client, sticks=False)


@given("the client offers Fullscreen again while the desktop is held, and the offer ignores Cancel")
def offers_again_and_sticks(
    scene: Scene, fixture_portal: Portal, browser_client: list[PlaywrightHorizonClient]
) -> None:
    _offers_again(scene, fixture_portal, browser_client, sticks=True)


# --- Then -----------------------------------------------------------------------------


@then("the message is a photo of the painted desktop without a client dialog")
def photo_without_a_dialog(scene: Scene, browser_client: list[PlaywrightHorizonClient]) -> None:
    message = scene.only_message()
    assert message.method == "sendPhoto"
    assert message.photo is not None
    for client in browser_client:
        client.close()  # its driver first: one sync Playwright driver per thread
    with sync_playwright() as driver:
        chrome = chrome_for_tests()
        browser = driver.chromium.launch(executable_path=None if chrome is None else str(chrome))
        try:
            unlike = colours_unlike(browser.new_page(), message.photo, DESKTOP_BLUE)
        finally:
            browser.close()
    assert unlike == [], f"the photo carries more than the desktop: {sorted(set(unlike))}"


@then("the client's Fullscreen offer was never accepted")
def offer_never_accepted(fixture_portal: Portal) -> None:
    events = fixture_portal.state.events
    assert "fullscreen-cancelled" in events
    assert "fullscreen-accepted" not in events
