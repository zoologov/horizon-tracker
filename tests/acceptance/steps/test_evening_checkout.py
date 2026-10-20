"""Evening check-out: the Windows session is logged off, or reported as already gone."""

from pytest_bdd import scenarios, then

from tests.acceptance.steps.conftest import Scene

scenarios("evening_checkout.feature")


@then("the desktop was logged off")
def logged_off(scene: Scene) -> None:
    assert "log_off" in scene.ran.client.calls
