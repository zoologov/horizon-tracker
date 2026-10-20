"""The steps every feature shares: configure the service, run a command, read what came out.

A scenario builds a ``Scene`` in its Given steps and runs one ``horizon`` command in its
When step, through ``CliRunner`` with the adapter factory replaced: the Horizon client,
the calendar and the clock are fakes, and the notifier is the real Telegram adapter
posting to a recording Bot API. The Then steps read only what an observer outside the
service could see: the command's exit code and output, the service log, the messages
that reached the chat, and the state of the desktop as the broker shows it.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from click.testing import Result
from pytest_bdd import given, parsers, then, when

from horizon_tracker.domain.session import SessionState
from horizon_tracker.infrastructure.telegram import TelegramNotifier
from tests.support.bot_api import RecordingBotApi, SentMessage
from tests.support.cli_world import World, cli_log_handlers_restored

MOSCOW = ZoneInfo("Europe/Moscow")
USERNAME = "svc.horizon.acceptance"
PASSWORD = "Acceptance-Pa$$w0rd&not=shown"
TOKEN = "123456789:AAH-acceptance_token"
CHAT_ID = "424242"

COMMANDS = {"check-in": "checkin", "check-out": "checkout"}

Script = Callable[[World], None]


@dataclass
class Scene:
    """What the Given steps arranged, and what the When step produced."""

    root: Path
    desktop: str = "DEV desktop"
    calendar_answer: bool | None = True
    state: SessionState = SessionState.NO_SESSION
    env_overrides: dict[str, str] = field(default_factory=dict)
    scripts: list[Script] = field(default_factory=list)
    bot: RecordingBotApi = field(default_factory=RecordingBotApi)
    world: World | None = None
    result: Result | None = None

    def env(self) -> dict[str, str | None]:
        chrome = self.root / "google-chrome"
        chrome.write_text("")
        return {
            "HORIZON_URL": "https://portal.example.invalid/portal/webclient/",
            "HORIZON_USERNAME": USERNAME,
            "HORIZON_PASSWORD": PASSWORD,
            "HORIZON_DESKTOP": self.desktop,
            "TELEGRAM_BOT_TOKEN": TOKEN,
            "TELEGRAM_CHAT_ID": CHAT_ID,
            "HT_TIMEZONE": "Europe/Moscow",
            "HT_CHECKIN_RANGE": "07:30-08:10",
            "HT_CHECKOUT_RANGE": "16:30-17:10",
            "HT_SESSION_LENGTH_MINUTES": "540",
            "HT_SESSION_EXTRA_MAX_MINUTES": "10",
            "HT_WINDOW_GRACE_MINUTES": "5",
            "HT_HOLD_SECONDS": "120",
            "HT_CHROME_PATH": str(chrome),
            "HT_ARTIFACTS_DIR": str(self.root / "artifacts"),
            **self.env_overrides,
        }

    def run(self, args: list[str], now: datetime) -> None:
        notifier = TelegramNotifier(TOKEN, CHAT_ID, self.bot.client())
        world = World(
            now,
            calendar_answer=self.calendar_answer,
            state=self.state,
            desktop=self.desktop,
            delivery=notifier,
        )
        for script in self.scripts:
            script(world)
        self.world = world
        self.result = world.invoke(args, self.env())

    @property
    def ran(self) -> World:
        assert self.world is not None, "no command ran in this scenario"
        return self.world

    @property
    def outcome(self) -> Result:
        assert self.result is not None, "no command ran in this scenario"
        return self.result

    def only_message(self) -> SentMessage:
        messages = self.bot.messages
        assert len(messages) == 1, f"expected one message, the chat got {len(messages)}"
        return messages[0]


@pytest.fixture
def scene(tmp_path: Path) -> Iterator[Scene]:
    with cli_log_handlers_restored():
        yield Scene(root=tmp_path)


def moment(clock: str, weekday: str, day: str) -> datetime:
    """The Moscow wall time named by a step; the weekday must agree with the date."""
    on = date.fromisoformat(day)
    assert on.strftime("%A") == weekday, f"{day} is a {on:%A}, not a {weekday}"
    return datetime.combine(on, time.fromisoformat(clock), tzinfo=MOSCOW)


_BINDING_TAGS = ("bead:", "node:")


def pytest_bdd_apply_tag(tag: str, function: Callable[..., object]) -> bool | None:
    """Keep the binding tags off pytest's marks; beadloom reads them from the feature file."""
    if tag.startswith(_BINDING_TAGS):
        return True
    return None


# --- Given ----------------------------------------------------------------------------


@given(parsers.parse('the service is configured for the desktop "{desktop}"'))
def configured_for(scene: Scene, desktop: str) -> None:
    scene.desktop = desktop


@given("the calendar marks the day as a working day")
def working_day(scene: Scene) -> None:
    scene.calendar_answer = True


@given("the calendar marks the day as a day off")
def day_off(scene: Scene) -> None:
    scene.calendar_answer = False


@given("the calendar cannot be reached")
def calendar_unreachable(scene: Scene) -> None:
    scene.calendar_answer = None


@given("the desktop has no session")
def no_session(scene: Scene) -> None:
    scene.state = SessionState.NO_SESSION


@given("the desktop has a session no client is attached to")
def disconnected_session(scene: Scene) -> None:
    scene.state = SessionState.DISCONNECTED


# --- When -----------------------------------------------------------------------------


@when(parsers.parse("the {run} runs at {clock} on {weekday} {day}"))
def scheduled_run(scene: Scene, run: str, clock: str, weekday: str, day: str) -> None:
    scene.run([COMMANDS[run]], moment(clock, weekday, day))


@when(parsers.parse('the owner runs "horizon {args}" at {clock} on {weekday} {day}'))
def owner_runs(scene: Scene, args: str, clock: str, weekday: str, day: str) -> None:
    scene.run(args.split(), moment(clock, weekday, day))


# --- Then -----------------------------------------------------------------------------


@then(parsers.parse("the command exits with {code:d}"))
def exits_with(scene: Scene, code: int) -> None:
    assert scene.outcome.exit_code == code, scene.outcome.output


@then("exactly one message reaches the owner")
def one_message(scene: Scene) -> None:
    scene.only_message()


@then("no message reaches the owner")
def no_message(scene: Scene) -> None:
    assert scene.bot.messages == []


@then(parsers.parse('the message reads "{line}"'))
def message_reads(scene: Scene, line: str) -> None:
    text = scene.only_message().text
    assert line in text.splitlines(), f"{line!r} is not a line of:\n{text}"


@then("the portal was never contacted")
def portal_untouched(scene: Scene) -> None:
    assert scene.ran.client.calls == []


@then(parsers.re(r"the portal was logged in to (?P<count>\d+) times?"), converters={"count": int})
def logged_in_times(scene: Scene, count: int) -> None:
    assert scene.ran.client.calls.count("login") == count


@then("the desktop was never logged off")
def never_logged_off(scene: Scene) -> None:
    assert "log_off" not in scene.ran.client.calls


@then("the desktop has no session")
def has_no_session(scene: Scene) -> None:
    assert scene.ran.client.state is SessionState.NO_SESSION


@then(parsers.parse('the output reads "{text}"'))
def output_reads(scene: Scene, text: str) -> None:
    assert text in scene.outcome.stdout, scene.outcome.stdout
