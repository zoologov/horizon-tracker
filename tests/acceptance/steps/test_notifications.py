"""Notifications: one Telegram message per run, a screenshot on failure, never a credential."""

from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote_plus

from pytest_bdd import given, parsers, scenarios, then

from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Reason
from tests.acceptance.steps.conftest import PASSWORD, USERNAME, Scene
from tests.support.cli_world import World

scenarios("notifications.feature")

SCREENSHOT = b"\x89PNG\r\n\x1a\nthe-captured-launch-items-page"
EVERY_ATTEMPT = 9  # more than the retry policy ever makes


def _refused_login(world: World) -> None:
    world.client.fail_on("login", HorizonClientError(Reason.LOGIN_REJECTED), times=EVERY_ATTEMPT)


def _error_quoting_the_password(world: World) -> None:
    error = RuntimeError(f"typed {USERNAME} / {PASSWORD} into the login form")
    world.client.fail_on("login", error, times=EVERY_ATTEMPT)


def _succeeds(world: World) -> None:
    """The fakes check in successfully when nothing is scripted."""


HOW_IT_GOES: dict[str, Callable[[World], None]] = {
    "succeeds": _succeeds,
    "is refused at the login page": _refused_login,
    "fails with an error quoting the password": _error_quoting_the_password,
}


def _secrets_in(texts: list[str]) -> list[str]:
    """The credentials found in ``texts``, read raw and URL-decoded."""
    found: list[str] = []
    for text in texts:
        for form in (text, unquote_plus(text)):
            found += [secret for secret in (PASSWORD, USERNAME) if secret in form]
    return found


@given("every attempt to open the desktop fails and the adapter captures the page")
def open_fails_with_screenshot(scene: Scene) -> None:
    screenshot: Path = scene.root / "checkin-failure.png"
    screenshot.write_bytes(SCREENSHOT)
    error = HorizonClientError(Reason.DESKTOP_DID_NOT_OPEN, screenshot=screenshot)
    scene.scripts.append(
        lambda world: world.client.fail_on("open_desktop", error, times=EVERY_ATTEMPT)
    )


@given(parsers.parse("the check-in {goes}"))
def the_checkin_goes(scene: Scene, goes: str) -> None:
    scene.scripts.append(HOW_IT_GOES[goes])


@then("the message is a photo of the captured page")
def message_is_the_screenshot(scene: Scene) -> None:
    message = scene.only_message()
    assert message.method == "sendPhoto"
    assert message.photo == SCREENSHOT


@then("nothing sent to Telegram contains the password or the account name")
def telegram_holds_no_credential(scene: Scene) -> None:
    assert scene.bot.requests, "nothing was sent, so nothing was checked"
    assert _secrets_in(scene.bot.raw_bodies()) == []


@then("the service log does not contain the password or the account name")
def log_holds_no_credential(scene: Scene) -> None:
    log = scene.outcome.stderr
    assert "checkin run" in log, f"the run left no log to check:\n{log}"
    assert _secrets_in([log]) == []
