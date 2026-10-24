"""Integration tests of the bot loop over the real Telegram transport and the real absences file.

The loop, the absence service, ``TelegramBotTransport`` and ``JsonAbsenceStore`` run as the
``horizon bot`` service wires them; only the Bot API is a local stand-in, answering each
``getUpdates`` from a script and stopping the loop once the script is spent. These pin the
risks the unit tests cannot reach through fakes: another poller's 409 Conflict, a corrupt
absences file on disk, a date typed without a year around New Year, and a stranger's text
kept out of every log record, the HTTP client's included.
"""

import json
import logging
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from horizon_tracker.application.absence_service import AbsenceService
from horizon_tracker.application.bot_loop import BACKOFF_FIRST_SECONDS, BotLoop
from horizon_tracker.domain.absence import Absence, AbsenceKind
from horizon_tracker.domain.messages import Language
from horizon_tracker.domain.schedule import TimeRange
from horizon_tracker.infrastructure.absence_store import JsonAbsenceStore
from horizon_tracker.infrastructure.telegram_bot import TelegramBotTransport
from tests.support.fakes import FakeClock

MSK = ZoneInfo("Europe/Moscow")
TOKEN = "123456789:AAHsecret-Token_value0123456789abcdefg"
OWNER = 987654321
STRANGER = 1000
CHECKIN_RANGE = TimeRange(start=time(7, 30), end=time(8, 10))
NOON = datetime(2026, 10, 24, 12, 0, tzinfo=MSK)
CONFLICT = "Conflict: terminated by other getUpdates request"
INTERNAL = "Something went wrong; the details are in the journal"
NOTE = (
    "Today's check-in range began at 07:30, so an absence starts tomorrow at the earliest; "
    "this evening's check-out runs as usual"
)


class ScriptedBotApi:
    """Answers each ``getUpdates`` with the next scripted answer, every other call with 200.

    Once the script is spent the next ``getUpdates`` raises ``KeyboardInterrupt``, the stop
    an operator gives ``horizon bot``.
    """

    def __init__(self) -> None:
        self.script: list[httpx.Response] = []
        self.poll_bodies: list[dict[str, object]] = []
        self.replies: list[tuple[str, str]] = []

    def write(self, update_id: int, text: str, chat_id: int = OWNER) -> None:
        """Hand out one text message from ``chat_id`` as the answer to the next poll."""
        update = {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}
        self.script.append(httpx.Response(200, json={"ok": True, "result": [update]}))

    def refuse(self, status: int, description: str) -> None:
        """Refuse the next poll with ``status``, as the Bot API does while another poller polls."""
        body = {"ok": False, "error_code": status, "description": description}
        self.script.append(httpx.Response(status, json=body))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        if request.url.path.endswith("/getUpdates"):
            self.poll_bodies.append(body)
            if not self.script:
                raise KeyboardInterrupt
            return self.script.pop(0)
        self.replies.append((str(body["chat_id"]), str(body["text"])))
        return httpx.Response(200, json={"ok": True, "result": {}})

    def texts(self) -> list[str]:
        return [text for _, text in self.replies]


class Bot:
    """``horizon bot`` as the CLI wires it: the scripted Bot API, the file under ``root``."""

    def __init__(self, root: Path, now: datetime = NOON) -> None:
        self.api = ScriptedBotApi()
        self.absences_file = root / "state" / "absences.json"
        self.clock = FakeClock(now)
        transport = TelegramBotTransport(
            TOKEN, httpx.Client(transport=httpx.MockTransport(self.api))
        )
        service = AbsenceService(JsonAbsenceStore(self.absences_file), self.clock, CHECKIN_RANGE)
        self.loop = BotLoop(transport, service, str(OWNER), Language.EN, self.clock)

    def run_until_stopped(self) -> None:
        with pytest.raises(KeyboardInterrupt):
            self.loop.run_forever()

    def held(self) -> tuple[Absence, ...]:
        return JsonAbsenceStore(self.absences_file).load().absences


# --- another poller holds getUpdates: 409 Conflict ----------------------------------------


def test_a_conflict_from_another_poller_is_waited_out_and_the_owner_then_answered(
    tmp_path: Path,
) -> None:
    bot = Bot(tmp_path)
    bot.api.refuse(409, CONFLICT)
    bot.api.write(1, "/list")

    bot.run_until_stopped()

    assert bot.clock.sleeps == [BACKOFF_FIRST_SECONDS]
    assert bot.api.replies == [(str(OWNER), "No absences entered")]


def test_a_conflict_loses_no_update_and_repeats_none(tmp_path: Path) -> None:
    bot = Bot(tmp_path)
    bot.api.write(1, "/help")
    bot.api.refuse(409, CONFLICT)
    bot.api.write(2, "/list")

    bot.run_until_stopped()

    # The poll after the conflict asks again from where the refused one did.
    assert [body.get("offset") for body in bot.api.poll_bodies] == [None, 2, 2, 3]
    assert len(bot.api.replies) == 2


def test_a_conflict_is_logged_by_its_status_and_never_with_the_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bot = Bot(tmp_path)
    bot.api.refuse(409, f"{CONFLICT} for bot{TOKEN}")

    with caplog.at_level(logging.DEBUG):
        bot.run_until_stopped()

    assert "refused with status 409" in caplog.text
    assert "poll failed (BotTransportError)" in caplog.text
    assert TOKEN not in caplog.text


# --- a corrupt absences file ---------------------------------------------------------------


@pytest.mark.parametrize(
    "command", ["/add vacation 03.11-14.11", "/edit 1 05.11-16.11", "/del 1", "/list"]
)
def test_a_corrupt_absences_file_is_answered_as_an_internal_error_and_left_as_it_was(
    tmp_path: Path, command: str
) -> None:
    bot = Bot(tmp_path)
    bot.absences_file.parent.mkdir()
    corrupt = b'{"last_issued": 1, "absences": [{"id": 1, "kind": "vacat'
    bot.absences_file.write_bytes(corrupt)
    bot.api.write(1, command)

    bot.run_until_stopped()

    assert bot.api.texts() == [INTERNAL]
    assert bot.absences_file.read_bytes() == corrupt


# --- the file the refusals leave -----------------------------------------------------------


def test_an_overlap_is_refused_naming_the_absence_and_the_file_keeps_the_first(
    tmp_path: Path,
) -> None:
    bot = Bot(tmp_path)
    bot.api.write(1, "/add vacation 03.11-14.11")
    bot.api.write(2, "/add dayoff 14.11")

    bot.run_until_stopped()

    assert bot.api.texts()[1] == "These days overlap absence 1; change or delete it first"
    assert bot.held() == (Absence(1, AbsenceKind.VACATION, date(2026, 11, 3), date(2026, 11, 14)),)


# --- a date without a year around New Year ---------------------------------------------------


def test_a_yearless_range_across_new_year_is_echoed_and_kept_with_both_years(
    tmp_path: Path,
) -> None:
    bot = Bot(tmp_path, now=datetime(2026, 12, 29, 12, 0, tzinfo=MSK))
    bot.api.write(1, "/add vacation 30.12-02.01")

    bot.run_until_stopped()

    assert bot.api.texts() == ["Absence 1 entered: vacation from 30.12.2026 to 02.01.2027"]
    assert bot.held() == (Absence(1, AbsenceKind.VACATION, date(2026, 12, 30), date(2027, 1, 2)),)


def test_a_running_range_across_new_year_entered_on_new_years_eve_starts_on_new_years_day(
    tmp_path: Path,
) -> None:
    bot = Bot(tmp_path, now=datetime(2026, 12, 31, 9, 0, tzinfo=MSK))
    bot.api.write(1, "/add vacation 30.12-02.01")

    bot.run_until_stopped()

    assert bot.api.texts() == ["Absence 1 entered: vacation from 01.01.2027 to 02.01.2027\n" + NOTE]
    assert bot.held() == (Absence(1, AbsenceKind.VACATION, date(2027, 1, 1), date(2027, 1, 2)),)


# --- a stranger --------------------------------------------------------------------------------


def test_a_strangers_text_reaches_no_log_record_and_no_reply_even_at_debug(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bot = Bot(tmp_path)
    bot.api.write(1, "/add vacation 03.11-14.11 my-private-words", chat_id=STRANGER)

    with caplog.at_level(logging.DEBUG):
        bot.run_until_stopped()

    assert bot.api.replies == []
    assert not bot.absences_file.exists()
    assert f"chat {STRANGER}" in caplog.text
    assert all("my-private-words" not in record.getMessage() for record in caplog.records)
