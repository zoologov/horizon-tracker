"""Checks without logging in: the probe and the dry run never open a session on the portal."""

from pytest_bdd import given, parsers, scenarios, then

from tests.acceptance.steps.conftest import Scene
from tests.support.cli_world import World

scenarios("checks_without_login.feature")


@given(parsers.parse('the portal serves the client bundle "{bundle}"'))
def client_bundle(scene: Scene, bundle: str) -> None:
    def serve(world: World) -> None:
        world.client.bundles = (bundle,)

    scene.scripts.append(serve)


@given(parsers.parse('the installed Chrome reports the version "{version}"'))
def chrome_version(scene: Scene, version: str) -> None:
    def install(world: World) -> None:
        world.client.browser = version

    scene.scripts.append(install)


@then("the portal was asked for its client bundles, Chrome for its version, and nothing else")
def only_bundles_and_version_asked(scene: Scene) -> None:
    assert scene.ran.client.calls == ["client_bundles", "browser_version"]
