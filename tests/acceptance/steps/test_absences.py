"""Absences through the bot: the owner writes commands to the bot, the bot answers in the chat.

The bot scenarios run ``horizon bot`` over the real Telegram transport, posting to the
scene's recording Bot API: each message a Given step writes is handed out by one
``getUpdates``, and once all of them are, the operator stops the bot. A Then step reads
what an observer could see: the replies in the chat, the absences file on the disk and the
service log. The scenarios of the runs enter their absence straight into the absences file,
the state the bot leaves behind, and run the check-in or the check-out over it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pytest_bdd import given, parsers, scenarios, then, when

from horizon_tracker.domain.absence import Absence, AbsenceBook, AbsenceKind
from horizon_tracker.infrastructure.absence_store import JsonAbsenceStore
from tests.acceptance.steps.conftest import CHAT_ID, Scene, moment
from tests.support.bot_api import SentMessage

scenarios("absences.feature")

_ABSENCES_FILE = "absences.json"
_KINDS = {"vacation": AbsenceKind.VACATION, "sick leave": AbsenceKind.SICK_LEAVE}


def _store(scene: Scene) -> JsonAbsenceStore:
    return JsonAbsenceStore(Path(scene.env()["HT_STATE_DIR"] or "") / _ABSENCES_FILE)


def _absence(id_: int, kind: str, first_day: str, last_day: str) -> Absence:
    return Absence(id_, _KINDS[kind], date.fromisoformat(first_day), date.fromisoformat(last_day))


def _replies(scene: Scene) -> list[SentMessage]:
    return [message for message in scene.bot.messages if message.method == "sendMessage"]


# --- Given ----------------------------------------------------------------------------


@given(parsers.parse('the owner writes "{text}" to the bot'))
def owner_writes(scene: Scene, text: str) -> None:
    scene.bot.write(CHAT_ID, text)


@given(parsers.parse('the chat {chat_id} writes "{text}" to the bot'))
def stranger_writes(scene: Scene, chat_id: str, text: str) -> None:
    scene.bot.write(chat_id, text)


@given(parsers.parse("a {kind} from {first_day} to {last_day} is entered as absence {id_:d}"))
def absence_entered(scene: Scene, kind: str, first_day: str, last_day: str, id_: int) -> None:
    entered = _absence(id_, kind, first_day, last_day)
    _store(scene).save(AbsenceBook.of((entered,)))


# --- When -----------------------------------------------------------------------------


@when(parsers.parse("the bot runs at {clock} on {weekday} {day}"))
def bot_runs(scene: Scene, clock: str, weekday: str, day: str) -> None:
    scene.run(["bot"], moment(clock, weekday, day))


# --- Then -----------------------------------------------------------------------------


@then(parsers.parse('the bot\'s last reply reads "{text}"'))
def last_reply_reads(scene: Scene, text: str) -> None:
    replies = _replies(scene)
    assert replies, f"the bot sent no reply; log: {scene.outcome.stderr}"
    assert replies[-1].text == text
    assert replies[-1].chat_id == CHAT_ID


@then("the bot's last reply reads:")
def last_reply_reads_lines(scene: Scene, docstring: str) -> None:
    last_reply_reads(scene, docstring)


@then("the bot sends no reply")
def no_reply(scene: Scene) -> None:
    assert _replies(scene) == []


@then(
    parsers.parse(
        "the absences file holds a {kind} from {first_day} to {last_day} as absence {id_:d}"
    )
)
def file_holds(scene: Scene, kind: str, first_day: str, last_day: str, id_: int) -> None:
    expected = _absence(id_, kind, first_day, last_day)
    assert _store(scene).load().absences == (expected,)


@then("the absences file holds no absence")
def file_holds_none(scene: Scene) -> None:
    assert _store(scene).load().absences == ()


@then(parsers.parse("the service log names the chat {chat_id} and not the text it wrote"))
def log_names_the_chat_only(scene: Scene, chat_id: str) -> None:
    log = scene.outcome.stderr
    assert chat_id in log
    assert "/add" not in log
    assert "03.11" not in log


@then("the check-in opened the desktop")
def checkin_opened_the_desktop(scene: Scene) -> None:
    assert "open_desktop" in scene.ran.client.calls


@then("the production calendar was never asked")
def calendar_never_asked(scene: Scene) -> None:
    assert scene.ran.calendar.asked == []
