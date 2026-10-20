"""Morning check-in: the desktop is opened over Blast, held, and let go without a log off."""

from pytest_bdd import given, parsers, scenarios, then

from horizon_tracker.domain.session import SessionState
from tests.acceptance.steps.conftest import Scene

scenarios("morning_checkin.feature")


@given(parsers.parse("the desktop is held open for {seconds:d} seconds"))
def held_open_for(scene: Scene, seconds: int) -> None:
    scene.env_overrides["HT_HOLD_SECONDS"] = str(seconds)


@then("the desktop was opened and then disconnected")
def opened_then_disconnected(scene: Scene) -> None:
    calls = scene.ran.client.calls
    assert "open_desktop" in calls
    assert "disconnect" in calls
    assert calls.index("open_desktop") < calls.index("disconnect")


@then("the Windows session of the desktop is left running without a client")
def session_left_running(scene: Scene) -> None:
    assert scene.ran.client.state is SessionState.DISCONNECTED
