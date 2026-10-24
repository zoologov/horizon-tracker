"""Screenshot preview: a success reports with the photo the client took, or as text without one.

The Horizon fake answers ``capture_open_desktop`` and ``log_off`` with the path of a photo
the Given steps wrote, as the adapter answers with the screenshot it took of that step;
``None`` plays a screenshot that could not be taken. ``open_desktop`` returns nothing.
The Then steps read the chat through the real Telegram notifier: whether the message is a
photo, which bytes it carries and what its caption says. One check-in scenario also reads
the fake's call order: the photograph follows the hold and precedes the disconnect, while
the caption's time stays the moment the desktop opened. That the adapter photographs the
launch list only once the broker has ended the session is the adapter's contract, pinned
on the HTML Access fixture in the adapter's integration tests; here the fake keeps it by
construction.
"""

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from pytest_bdd import given, parsers, scenarios, then

from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Reason
from tests.acceptance.steps.conftest import Scene, Script
from tests.support.cli_world import World

scenarios("screenshot_preview.feature")

OPENED_DESKTOP = b"\x89PNG\r\n\x1a\nthe-drawn-dev-desktop"
LAUNCH_LIST = b"\x89PNG\r\n\x1a\nthe-launch-list-without-a-session"
LOST_CONFIRMATION = b"\x89PNG\r\n\x1a\nthe-launch-list-while-the-log-off-went-unconfirmed"


def _photo(scene: Scene, name: str, content: bytes) -> Path:
    """A photo file of the client's, written where the scenario's artifacts live."""
    path = scene.root / name
    path.write_bytes(content)
    return path


def _answers_with(shot: Path | None) -> Script:
    """The client answers a completed capture or log off with ``shot``."""

    def script(world: World) -> None:
        world.client.success_screenshot = shot

    return script


# --- Given ----------------------------------------------------------------------------


@given("the client photographs the opened desktop")
def photographs_the_desktop(scene: Scene) -> None:
    scene.scripts.append(_answers_with(_photo(scene, "checkin-desktop.png", OPENED_DESKTOP)))


@given("the client cannot photograph the opened desktop")
def cannot_photograph_the_desktop(scene: Scene) -> None:
    scene.scripts.append(_answers_with(None))


@given("the client photographs the launch list after its log off")
def photographs_the_launch_list(scene: Scene) -> None:
    scene.scripts.append(_answers_with(_photo(scene, "checkout-launch-list.png", LAUNCH_LIST)))


@given("the Windows session ends when the client lets go")
def session_ends_on_disconnect(scene: Scene) -> None:
    def script(world: World) -> None:
        world.client.disconnect_keeps_session = False

    scene.scripts.append(script)


def _log_off_not_confirmed(scene: Scene) -> Script:
    """The log off takes effect, then the client answers with its failure screenshot."""
    shot = _photo(scene, "checkout-failure.png", LOST_CONFIRMATION)
    error = HorizonClientError(Reason.LOGOFF_NOT_CONFIRMED, screenshot=shot)
    return lambda world: world.client.lose_on("log_off", error)


def _read_after_log_off_fails(scene: Scene) -> Script:
    """The log off answers with its photo, then the read that would confirm it fails."""
    error = HorizonClientError(Reason.UNEXPECTED)
    return lambda world: world.client.fail_on("desktop_status", error, after=1)


LOSSES: dict[str, Callable[[Scene], Script]] = {
    "the client answers that the log off was not confirmed": _log_off_not_confirmed,
    "reading the session state fails": _read_after_log_off_fails,
}


@given(parsers.parse("after the first log off {loss}"))
def first_confirmation_lost(scene: Scene, loss: str) -> None:
    scene.scripts.append(LOSSES[loss](scene))


# --- Then -----------------------------------------------------------------------------


@then("the opened desktop was photographed after the hold, before the disconnect")
def photographed_after_the_hold(scene: Scene) -> None:
    """The photograph follows the configured hold and still precedes the disconnect."""
    client = scene.ran.client
    calls = client.calls
    assert calls.count("open_desktop") == 1
    assert calls.count("capture_open_desktop") == 1
    assert calls.count("disconnect") == 1
    opened = calls.index("open_desktop")
    captured = calls.index("capture_open_desktop")
    disconnected = calls.index("disconnect")
    assert opened < captured < disconnected
    hold = timedelta(seconds=scene.ran.opened[-1][0].hold_seconds)
    gap = client.called_at[captured] - client.called_at[opened]
    assert gap == hold, f"the photograph was {gap} after the open; the hold is {hold}"


@then("the message is the photo of the opened desktop")
def photo_of_the_desktop(scene: Scene) -> None:
    message = scene.only_message()
    assert message.method == "sendPhoto"
    assert message.photo == OPENED_DESKTOP


@then("the message is the photo of the launch list")
def photo_of_the_launch_list(scene: Scene) -> None:
    message = scene.only_message()
    assert message.method == "sendPhoto"
    assert message.photo == LAUNCH_LIST


@then(parsers.re(r"the desktop was opened (?P<count>\d+) times?"), converters={"count": int})
def opened_times(scene: Scene, count: int) -> None:
    assert scene.ran.client.calls.count("open_desktop") == count


@then(parsers.re(r"the desktop was logged off (?P<count>\d+) times?"), converters={"count": int})
def logged_off_times(scene: Scene, count: int) -> None:
    assert scene.ran.client.calls.count("log_off") == count
