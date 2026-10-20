"""Run window and retries: a failure is retried inside the window, a late start is skipped."""

from pytest_bdd import given, parsers, scenarios, then

from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Reason
from tests.acceptance.steps.conftest import Scene

scenarios("window_and_retries.feature")


@given(parsers.parse("the first {failures:d} attempts to open the desktop fail"))
def first_attempts_fail(scene: Scene, failures: int) -> None:
    error = HorizonClientError(Reason.DESKTOP_DID_NOT_OPEN)
    scene.scripts.append(lambda world: world.client.fail_on("open_desktop", error, times=failures))


@then(parsers.parse("the desktop was opened {opens:d} times"))
def opened_times(scene: Scene, opens: int) -> None:
    assert scene.ran.client.calls.count("open_desktop") == opens
