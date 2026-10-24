"""Checks without logging in: the probe and the dry run never open a session on the portal."""

import json
from pathlib import Path

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


# --- the absences file the probe reads ---------------------------------------------------

ABSENCES_FILE = "absences.json"
FILE_TOKEN = "{file}"


def _absences_file(scene: Scene) -> Path:
    return Path(scene.env()["HT_STATE_DIR"] or "") / ABSENCES_FILE


def _enter(scene: Scene, kind: str, first_day: str, last_day: str) -> None:
    """Add one absence to the file on the disk, in the shape the store writes."""
    path = _absences_file(scene)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = json.loads(path.read_text()) if path.exists() else {"absences": []}
    absences = document["absences"]
    absences.append(
        {"id": len(absences) + 1, "kind": kind, "first_day": first_day, "last_day": last_day}
    )
    document["last_issued"] = len(absences)
    path.write_text(json.dumps(document))


@given(parsers.parse("the absences file holds a day off on {day}"))
def day_off_entered(scene: Scene, day: str) -> None:
    _enter(scene, "day_off", day, day)


@given(parsers.parse("the absences file holds a vacation from {first_day} to {last_day}"))
def vacation_entered(scene: Scene, first_day: str, last_day: str) -> None:
    _enter(scene, "vacation", first_day, last_day)


@given("the absences file holds text that is not JSON")
def absences_file_malformed(scene: Scene) -> None:
    path = _absences_file(scene)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("vacation from Monday")


@then(parsers.parse('the output reads "{text}" with the absences file for {{file}}'))
def output_reads_with_the_file(scene: Scene, text: str) -> None:
    expected = text.replace(FILE_TOKEN, str(_absences_file(scene)))
    assert expected in scene.outcome.stdout, scene.outcome.stdout
