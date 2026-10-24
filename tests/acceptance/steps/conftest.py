"""The steps every feature shares: configure the service, run a command, read what came out.

A scenario builds a ``Scene`` in its Given steps and runs one ``horizon`` command in its
When step, through ``CliRunner`` with the adapter factory replaced: the Horizon client,
the calendar and the clock are fakes, and the notifier is the real Telegram adapter, built
by the composition root's own ``build_notifier`` from the settings the command loaded and
posting to a recording Bot API. ``horizon bot`` polls that same Bot API through the real
Telegram transport, built by ``build_bot_transport``. The Then steps read only what an
observer outside the service could see: the command's exit code and output, the service
log, the messages that reached the chat, and the state of the desktop as the broker shows
it.
"""

import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from click.testing import Result
from pytest_bdd import given, parsers, then, when

from horizon_tracker.cli import build_bot_transport, build_notifier
from horizon_tracker.domain.messages import Language
from horizon_tracker.domain.ports import BotTransport, Notifier
from horizon_tracker.domain.session import SessionState
from horizon_tracker.infrastructure.config import Settings
from tests.support.bot_api import RecordingBotApi, SentMessage
from tests.support.cli_world import World, cli_log_handlers_restored

MOSCOW = ZoneInfo("Europe/Moscow")
USERNAME = "svc.horizon.acceptance"
PASSWORD = "Acceptance-Pa$$w0rd&not=shown"
TOKEN = "123456789:AAH-acceptance_token"
CHAT_ID = "424242"

COMMANDS = {"check-in": "checkin", "check-out": "checkout"}

# The features written before HT-007 quote the Russian notifications the owner has always
# read, beside English command output; a scene pins the notification to that language.
# A scene with no pin builds the notifier in the language HT_LANGUAGE names, as the service.
OWNERS_NOTIFICATION_LANGUAGE = Language.RU

# The schedule every scene runs under: the deployed ranges and day length (the .env contract
# in docs/guides/deployment.md)
# under a seed of the suite's own, so each feature can name the moments a date draws. They
# were computed by an oracle of the RFC formula that imports nothing from the project; the
# dates the features name draw these (check-in / check-out):
#   Wednesday 2026-10-21  07:38 / 16:39     Thursday 2026-10-22  07:37 / 16:38
#   Saturday  2026-10-24  07:40 / 16:50     Thursday 2026-10-29  08:08 / 17:10 (17:12 clipped)
#   Tuesday   2026-11-03  07:30 / 16:40     Wednesday 2026-11-11 08:10 / 17:10
# The four weeks from Monday 2026-10-19 reach both ends of the check-in range and every
# extra minute from 0 to 10, which is why this seed and not another.
SEED = "horizon-acceptance-6"
DEPLOYED_SCHEDULE = {
    "HT_CHECKIN_RANGE": "07:30-08:10",
    "HT_CHECKOUT_RANGE": "16:30-17:10",
    "HT_SESSION_LENGTH_MINUTES": "540",
    "HT_SESSION_EXTRA_MAX_MINUTES": "10",
    "HT_WINDOW_GRACE_MINUTES": "5",
    "HT_JITTER_SEED": SEED,
}

Script = Callable[[World], None]


@dataclass
class Scene:
    """What the Given steps arranged, and what the When steps produced.

    ``world`` and ``result`` are the last command's; ``starts``, ``worlds`` and ``results``
    keep every command of the scenario in order, for the scenarios that run one each day.
    The bot is shared, so ``bot.messages`` holds every message of the scenario.
    ``processes`` holds the commands a scenario ran in an interpreter of their own.
    ``notification_language`` pins the language the notifier is built in; ``None`` leaves
    it to ``HT_LANGUAGE``. ``env_overrides`` may map a variable to ``None`` to unset it.
    """

    root: Path
    desktop: str = "DEV desktop"
    calendar_answer: bool | None = True
    state: SessionState = SessionState.NO_SESSION
    env_overrides: dict[str, str | None] = field(default_factory=dict)
    notification_language: Language | None = OWNERS_NOTIFICATION_LANGUAGE
    scripts: list[Script] = field(default_factory=list)
    bot: RecordingBotApi = field(default_factory=RecordingBotApi)
    world: World | None = None
    result: Result | None = None
    results: list[Result] = field(default_factory=list)
    worlds: list[World] = field(default_factory=list)
    starts: list[datetime] = field(default_factory=list)
    processes: list[subprocess.CompletedProcess[str]] = field(default_factory=list)

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
            **DEPLOYED_SCHEDULE,
            "HT_HOLD_SECONDS": "120",
            "HT_CHROME_PATH": str(chrome),
            "HT_ARTIFACTS_DIR": str(self.root / "artifacts"),
            # The absences file stays inside the scenario, never the host's state directory.
            "HT_STATE_DIR": str(self.root / "state"),
            # Unset whatever the host exports: command output is in the default language.
            "HT_LANGUAGE": None,
            **self.env_overrides,
        }

    def deliver(self, settings: Settings) -> Notifier:
        """The notifier the command delivers through, built as the composition root builds it."""
        if self.notification_language is not None:
            settings = replace(settings, language=self.notification_language)
        return build_notifier(settings, self.bot.client())

    def poll_through(self, settings: Settings) -> BotTransport:
        """The transport ``horizon bot`` polls through, built as the composition root builds it."""
        return build_bot_transport(settings, self.bot.client())

    def run(self, args: list[str], now: datetime) -> None:
        world = World(
            now,
            calendar_answer=self.calendar_answer,
            state=self.state,
            desktop=self.desktop,
            delivery=self.deliver,
            bot_delivery=self.poll_through,
        )
        for script in self.scripts:
            script(world)
        self.world = world
        self.result = world.invoke(args, self.env())
        self.starts.append(now)
        self.worlds.append(world)
        self.results.append(self.result)

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


@then("the message is text without a photo")
def text_without_a_photo(scene: Scene) -> None:
    message = scene.only_message()
    assert message.method == "sendMessage"
    assert message.photo is None


@then(parsers.parse('the message reads "{line}"'))
def message_reads(scene: Scene, line: str) -> None:
    text = scene.only_message().text
    assert line in text.splitlines(), f"{line!r} is not a line of:\n{text}"


@then(parsers.parse('no line of the message starts with "{prefix}"'))
def no_line_starts_with(scene: Scene, prefix: str) -> None:
    text = scene.only_message().text
    assert not [line for line in text.splitlines() if line.startswith(prefix)], text


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
