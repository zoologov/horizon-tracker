"""Checks without logging in: the probe and the dry run never open a session on the portal."""

from pytest_bdd import given, parsers, scenarios, then

from tests.acceptance.steps.conftest import Scene
from tests.support.cli_world import World

scenarios("checks_without_login.feature")


@given(parsers.parse('the portal serves the client version "{version}"'))
def portal_version(scene: Scene, version: str) -> None:
    def serve(world: World) -> None:
        world.client.portal_version = version

    scene.scripts.append(serve)


@then("the portal was asked for its version and nothing else")
def only_the_version_asked(scene: Scene) -> None:
    assert scene.ran.client.calls == ["probe"]
