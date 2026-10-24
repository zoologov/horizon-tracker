"""Tests for the bot loop: the owner's chat only, one reply per message, and a loop that goes on."""

import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.application.absence_service import AbsenceService
from horizon_tracker.application.bot_loop import (
    BACKOFF_FIRST_SECONDS,
    BACKOFF_MAX_SECONDS,
    BotLoop,
)
from horizon_tracker.domain.absence import Absence, AbsenceBook, AbsenceKind
from horizon_tracker.domain.messages import Language
from horizon_tracker.domain.ports import BotTransportError, IncomingMessage
from horizon_tracker.domain.schedule import TimeRange
from tests.support.fakes import FakeAbsenceStore, FakeBotTransport, FakeClock

MSK = ZoneInfo("Europe/Moscow")
NOON = datetime(2026, 10, 24, 12, 0, tzinfo=MSK)
OWNER = "424242"
STRANGER = "1000"
SECRET_TEXT = "/add vacation 03.11-14.11 my-private-words"
CHECKIN_RANGE = TimeRange(start=time(7, 30), end=time(8, 10))
ADDED = "Absence 1 entered: vacation from 03.11.2026 to 14.11.2026"
INTERNAL = "Something went wrong; the details are in the journal"


class World:
    """A loop over a fake transport, store and clock, in English unless told otherwise."""

    def __init__(self, language: Language = Language.EN, now: datetime = NOON) -> None:
        self.transport = FakeBotTransport()
        self.store = FakeAbsenceStore()
        self.clock = FakeClock(now)
        service = AbsenceService(self.store, self.clock, CHECKIN_RANGE)
        self.loop = BotLoop(self.transport, service, OWNER, language, self.clock)

    def receive(self, *messages: IncomingMessage) -> None:
        self.transport.deliver(messages)

    def texts(self) -> list[str]:
        return [text for _, text in self.transport.replies]


def message(update_id: int, text: str, chat_id: str = OWNER) -> IncomingMessage:
    return IncomingMessage(update_id=update_id, chat_id=chat_id, text=text)


# --- run_once: the owner's commands --------------------------------------------------------


def test_the_owners_command_is_answered_in_the_owners_chat() -> None:
    world = World()
    world.receive(message(7, "/add vacation 03.11-14.11"))

    world.loop.run_once(None)

    assert world.transport.replies == [(OWNER, ADDED)]
    assert world.store.book.absences == (
        Absence(1, AbsenceKind.VACATION, date(2026, 11, 3), date(2026, 11, 14)),
    )


def test_run_once_polls_from_the_offset_it_is_given_and_returns_the_next_one() -> None:
    world = World()
    world.receive(message(7, "/list"), message(9, "/list"))

    assert world.loop.run_once(5) == 10
    assert world.transport.offsets == [5]


@pytest.mark.parametrize("offset", [None, 5])
def test_a_poll_with_no_message_returns_the_offset_it_was_given(offset: int | None) -> None:
    world = World()
    world.receive()

    assert world.loop.run_once(offset) == offset
    assert world.transport.replies == []


def test_every_message_gets_exactly_one_reply_in_order() -> None:
    world = World()
    world.receive(
        message(1, "/add vacation 03.11-14.11"),
        message(2, "/list"),
        message(3, "/del 1"),
    )

    world.loop.run_once(None)

    assert world.texts() == [
        ADDED,
        "Absences entered: 1\nAbsence 1: vacation from 03.11.2026 to 14.11.2026",
        "Absence 1 deleted: vacation from 03.11.2026 to 14.11.2026",
    ]


def test_an_edit_and_a_listing_reach_the_service() -> None:
    world = World()
    world.receive(message(1, "/add vacation 03.11-14.11"), message(2, "/edit 1 dayoff 05.11"))

    world.loop.run_once(None)

    assert world.texts()[1] == "Absence 1 changed: day off on 05.11.2026"


def test_a_text_the_parser_refuses_is_answered_with_its_problem() -> None:
    world = World()
    world.receive(message(1, "/add vacation 3 November"))

    world.loop.run_once(None)

    assert world.texts() == [
        "Not a date '3': expected 03.11, 03.11.2026 or 2026-11-03; a range is written 03.11-14.11"
    ]
    assert world.store.saved == []


@pytest.mark.parametrize("command", ["/help", "/start"])
def test_help_and_start_answer_with_the_commands(command: str) -> None:
    world = World()
    world.receive(message(1, command))

    world.loop.run_once(None)

    assert world.texts()[0].startswith("Commands:\n/add <kind> <from>[-<to>]")


def test_the_reply_is_in_the_configured_language() -> None:
    world = World(Language.RU)
    world.receive(message(1, "/add отпуск 03.11-14.11"), message(2, "привет"))

    world.loop.run_once(None)

    assert world.texts() == [
        "Отсутствие 1 внесено: отпуск, дни 03.11.2026–14.11.2026",
        "Это не команда; список команд покажет /help",
    ]


def test_a_date_without_a_year_is_placed_from_the_clocks_today() -> None:
    world = World(now=datetime(2026, 11, 5, 12, 0, tzinfo=MSK))
    world.receive(message(1, "/add dayoff 03.11"))

    world.loop.run_once(None)

    assert world.texts() == ["Absence 1 entered: day off on 03.11.2027"]


# --- run_once: any other chat ----------------------------------------------------------------


def test_a_message_from_another_chat_gets_no_reply_and_changes_nothing() -> None:
    world = World()
    world.receive(message(4, "/add vacation 03.11-14.11", chat_id=STRANGER))

    assert world.loop.run_once(None) == 5
    assert world.transport.replies == []
    assert world.store.loads == 0


def test_another_chats_text_is_never_logged_and_its_chat_id_is(
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = World()
    world.receive(message(4, SECRET_TEXT, chat_id=STRANGER))

    with caplog.at_level(logging.DEBUG):
        world.loop.run_once(None)

    assert any(STRANGER in record.getMessage() for record in caplog.records)
    for record in caplog.records:
        assert "my-private-words" not in record.getMessage()
        assert "/add" not in record.getMessage()
    assert "my-private-words" not in caplog.text


def test_a_chat_id_that_only_starts_like_the_owners_is_another_chat() -> None:
    world = World()
    world.receive(
        message(1, "/list", chat_id=OWNER + "0"), message(2, "/list", chat_id=" " + OWNER)
    )

    world.loop.run_once(None)

    assert world.transport.replies == []


def test_the_owner_is_answered_beside_a_stranger_in_the_same_poll() -> None:
    world = World()
    world.receive(message(1, "/list", chat_id=STRANGER), message(2, "/list"))

    assert world.loop.run_once(None) == 3
    assert world.transport.replies == [(OWNER, "No absences entered")]


def test_the_owners_text_is_not_logged_either(caplog: pytest.LogCaptureFixture) -> None:
    world = World()
    world.receive(message(1, SECRET_TEXT))

    with caplog.at_level(logging.DEBUG):
        world.loop.run_once(None)

    assert "my-private-words" not in caplog.text


# --- run_once: what goes wrong inside one message -----------------------------------------


def test_an_internal_error_is_answered_as_one_and_the_next_message_still_is(
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = World()
    world.store.broken = True
    world.receive(message(1, "/list"), message(2, "/help"))

    with caplog.at_level(logging.ERROR):
        assert world.loop.run_once(None) == 3

    assert world.texts()[0] == INTERNAL
    assert world.texts()[1].startswith("Commands:")
    assert [record.levelno for record in caplog.records] == [logging.ERROR]
    assert "update 1" in caplog.records[0].getMessage()
    assert caplog.records[0].exc_info is not None


def test_an_unexpected_exception_is_answered_as_internal_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()

    def a_bug() -> AbsenceBook:
        raise RuntimeError("a bug")

    monkeypatch.setattr(world.store, "load", a_bug)
    world.receive(message(1, "/list"))

    world.loop.run_once(None)

    assert world.texts() == [INTERNAL]


def test_the_internal_error_reads_in_the_configured_language() -> None:
    world = World(Language.RU)
    world.store.broken = True
    world.receive(message(1, "/list"))

    world.loop.run_once(None)

    assert world.texts() == ["Что-то пошло не так; подробности в журнале"]


def test_a_reply_that_cannot_be_sent_is_logged_and_the_next_message_is_answered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = World()
    world.transport.fail_replies = True
    world.receive(message(1, "/list"), message(2, "/help"))

    with caplog.at_level(logging.WARNING):
        assert world.loop.run_once(None) == 3

    assert len(world.transport.replies) == 2
    warnings = [record.getMessage() for record in caplog.records]
    assert warnings == [
        "reply to update 1 was not sent: BotTransportError",
        "reply to update 2 was not sent: BotTransportError",
    ]


def test_a_failed_poll_is_left_to_the_caller() -> None:
    world = World()
    world.transport.script(BotTransportError("getUpdates failed: ConnectError"))

    with pytest.raises(BotTransportError):
        world.loop.run_once(None)


# --- run_forever -----------------------------------------------------------------------


def failure() -> BotTransportError:
    return BotTransportError("getUpdates failed: ConnectError")


def test_run_forever_survives_three_transport_errors_in_a_row(
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = World()
    world.transport.script(failure(), failure(), failure(), (message(1, "/list"),))

    with caplog.at_level(logging.WARNING), pytest.raises(KeyboardInterrupt):
        world.loop.run_forever()

    assert world.texts() == ["No absences entered"]
    assert world.clock.sleeps == [
        BACKOFF_FIRST_SECONDS,
        BACKOFF_FIRST_SECONDS * 2,
        BACKOFF_FIRST_SECONDS * 4,
    ]
    assert [record.getMessage() for record in caplog.records] == [
        f"poll failed (BotTransportError), retrying in {BACKOFF_FIRST_SECONDS * 2**n:g} s"
        for n in range(3)
    ]


def test_the_backoff_starts_over_after_a_poll_that_succeeds() -> None:
    world = World()
    world.transport.script(failure(), failure(), (), failure())

    with pytest.raises(KeyboardInterrupt):
        world.loop.run_forever()

    assert world.clock.sleeps == [
        BACKOFF_FIRST_SECONDS,
        BACKOFF_FIRST_SECONDS * 2,
        BACKOFF_FIRST_SECONDS,
    ]


def test_the_backoff_never_exceeds_its_ceiling() -> None:
    world = World()
    world.transport.script(*(failure() for _ in range(12)))

    with pytest.raises(KeyboardInterrupt):
        world.loop.run_forever()

    assert max(world.clock.sleeps) == BACKOFF_MAX_SECONDS
    assert world.clock.sleeps[-1] == BACKOFF_MAX_SECONDS
    assert world.clock.sleeps == sorted(world.clock.sleeps)


def test_run_forever_polls_again_at_once_and_from_the_next_offset() -> None:
    world = World()
    world.transport.script((message(7, "/list"),), (), (message(8, "/list"),))

    with pytest.raises(KeyboardInterrupt):
        world.loop.run_forever()

    assert world.transport.offsets == [None, 8, 8, 9]
    assert world.clock.sleeps == []


def test_a_failed_poll_keeps_the_offset_already_reached() -> None:
    world = World()
    world.transport.script((message(7, "/list"),), failure())

    with pytest.raises(KeyboardInterrupt):
        world.loop.run_forever()

    assert world.transport.offsets == [None, 8, 8]
