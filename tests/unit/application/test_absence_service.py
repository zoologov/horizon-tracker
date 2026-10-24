"""Tests for the absence service: add, list, delete and edit over the store, each with its reply."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.application.absence_service import AbsenceService, Reply
from horizon_tracker.domain.absence import Absence, AbsenceBook, AbsenceKind
from horizon_tracker.domain.messages import Language, Message
from horizon_tracker.domain.ports import AbsenceStoreError
from horizon_tracker.domain.schedule import TimeRange
from tests.support.fakes import FakeAbsenceStore, FakeClock

MSK = ZoneInfo("Europe/Moscow")
CHECKIN_RANGE = TimeRange(start=time(7, 30), end=time(8, 10))
NOON = datetime(2026, 10, 24, 12, 0, tzinfo=MSK)  # Saturday, long after the check-in range
NOV_3, NOV_14, NOV_20 = date(2026, 11, 3), date(2026, 11, 14), date(2026, 11, 20)

VACATION = Absence(1, AbsenceKind.VACATION, NOV_3, NOV_14)
DAY_OFF = Absence(2, AbsenceKind.DAY_OFF, NOV_20, NOV_20)


def service(
    book: AbsenceBook | None = None, now: datetime = NOON
) -> tuple[AbsenceService, FakeAbsenceStore]:
    store = FakeAbsenceStore(book=book if book is not None else AbsenceBook())
    return AbsenceService(store, FakeClock(now), CHECKIN_RANGE), store


def english(reply: Reply) -> str:
    return reply.in_language(Language.EN)


# --- the reply ------------------------------------------------------------------------


def test_a_reply_reads_its_lines_in_order_one_per_line() -> None:
    reply = Reply.of(Message("bot.list.header", {"count": 2}), Message("bot.list.empty"))

    assert reply.in_language(Language.EN) == "Absences entered: 2\nNo absences entered"
    assert reply.in_language(Language.RU).splitlines() == [
        "Внесено отсутствий: 2",
        "Отсутствий не внесено",
    ]


def test_a_reply_has_at_least_one_line() -> None:
    with pytest.raises(ValueError, match="at least one line"):
        Reply(())


# --- add ------------------------------------------------------------------------------


def test_add_enters_the_first_absence_as_id_one_and_echoes_its_full_dates() -> None:
    absences, store = service()

    reply = absences.add(AbsenceKind.VACATION, NOV_3, NOV_14)

    assert english(reply) == "Absence 1 entered: vacation from 03.11.2026 to 14.11.2026"
    assert store.saved == [AbsenceBook((VACATION,), last_issued=1)]


def test_a_one_day_absence_is_echoed_as_one_day() -> None:
    absences, _ = service()

    reply = absences.add(AbsenceKind.DAY_OFF, NOV_20, NOV_20)

    assert english(reply) == "Absence 1 entered: day off on 20.11.2026"


def test_add_replies_in_russian_with_the_russian_kind() -> None:
    absences, _ = service()

    reply = absences.add(AbsenceKind.SICK_LEAVE, NOV_3, NOV_14)

    assert reply.in_language(Language.RU) == (
        "Отсутствие 1 внесено: больничный, дни 03.11.2026–14.11.2026"
    )


def test_add_never_reissues_the_id_of_a_deleted_absence() -> None:
    absences, store = service(AbsenceBook((VACATION,), last_issued=3))

    reply = absences.add(AbsenceKind.DAY_OFF, NOV_20, NOV_20)

    assert english(reply).startswith("Absence 4 entered")
    assert store.book == AbsenceBook(
        (VACATION, Absence(4, AbsenceKind.DAY_OFF, NOV_20, NOV_20)), last_issued=4
    )


def test_add_refuses_days_another_absence_holds_and_names_it() -> None:
    absences, store = service(AbsenceBook.of((VACATION,)))

    reply = absences.add(AbsenceKind.DAY_OFF, NOV_14, NOV_20)

    assert reply == Reply.of(Message("bot.error.overlap", {"id": 1}))
    assert store.saved == []


def test_an_overlap_with_several_absences_names_the_lowest_id() -> None:
    absences, _ = service(AbsenceBook.of((DAY_OFF, VACATION)))

    reply = absences.add(AbsenceKind.SICK_LEAVE, NOV_3, NOV_20)

    assert reply == Reply.of(Message("bot.error.overlap", {"id": 1}))


def test_an_absence_that_ends_the_day_before_another_starts_is_entered() -> None:
    absences, store = service(AbsenceBook.of((VACATION,)))

    absences.add(AbsenceKind.DAY_OFF, date(2026, 11, 15), date(2026, 11, 15))

    assert len(store.book.absences) == 2


def test_add_leaves_a_store_error_to_the_caller() -> None:
    absences, store = service()
    store.broken = True

    with pytest.raises(AbsenceStoreError):
        absences.add(AbsenceKind.VACATION, NOV_3, NOV_14)


# --- an absence for today once the check-in range has begun ------------------------------
# The morning run may already have checked in, so an absence entered from the start of the
# check-in range on starts tomorrow, and the evening check-out runs as usual (HT-012).

TODAY = date(2026, 10, 26)  # Monday
TOMORROW = date(2026, 10, 27)
OCT_28 = date(2026, 10, 28)


def at(hour: int, minute: int) -> datetime:
    return datetime.combine(TODAY, time(hour, minute), tzinfo=MSK)


NOTE = (
    "Today's check-in range began at 07:30, so an absence starts tomorrow at the earliest; "
    "this evening's check-out runs as usual"
)


@pytest.mark.parametrize("now", [at(7, 30), at(8, 11), at(23, 59)])
def test_an_absence_covering_today_entered_once_the_range_began_starts_tomorrow(
    now: datetime,
) -> None:
    absences, store = service(now=now)

    reply = absences.add(AbsenceKind.SICK_LEAVE, TODAY, OCT_28)

    assert english(reply).splitlines() == [
        "Absence 1 entered: sick leave from 27.10.2026 to 28.10.2026",
        NOTE,
    ]
    assert store.book.absences == (Absence(1, AbsenceKind.SICK_LEAVE, TOMORROW, OCT_28),)


def test_the_note_reads_in_russian() -> None:
    absences, _ = service(now=at(12, 0))

    reply = absences.add(AbsenceKind.DAY_OFF, TODAY, OCT_28)

    assert reply.in_language(Language.RU).splitlines()[1] == (
        "Диапазон входа на сегодня начался в 07:30, поэтому отсутствие начнётся "
        "не раньше завтрашнего дня; вечерний выход сегодня пройдёт как обычно"
    )


def test_an_absence_started_yesterday_and_covering_today_starts_tomorrow_too() -> None:
    absences, store = service(now=at(12, 0))

    reply = absences.add(AbsenceKind.SICK_LEAVE, date(2026, 10, 25), OCT_28)

    assert english(reply).splitlines() == [
        "Absence 1 entered: sick leave from 27.10.2026 to 28.10.2026",
        NOTE,
    ]
    assert store.book.absences[0].first_day == TOMORROW


@pytest.mark.parametrize(
    "first_day", [TODAY, date(2026, 10, 25)], ids=["today alone", "yesterday and today"]
)
def test_an_absence_that_would_end_today_is_refused_with_the_note(first_day: date) -> None:
    absences, store = service(now=at(12, 0))

    reply = absences.add(AbsenceKind.DAY_OFF, first_day, TODAY)

    assert english(reply) == NOTE
    assert store.saved == []
    # The refusal issues no id: the next absence entered is still the first.
    assert english(absences.add(AbsenceKind.DAY_OFF, NOV_20, NOV_20)).startswith("Absence 1 ")


@pytest.mark.parametrize("now", [at(0, 0), at(7, 0), at(7, 29)])
def test_an_absence_for_today_entered_before_the_range_begins_keeps_today(
    now: datetime,
) -> None:
    absences, store = service(now=now)

    reply = absences.add(AbsenceKind.DAY_OFF, TODAY, TODAY)

    assert english(reply) == "Absence 1 entered: day off on 26.10.2026"
    assert store.book.absences == (Absence(1, AbsenceKind.DAY_OFF, TODAY, TODAY),)


@pytest.mark.parametrize(
    ("first_day", "last_day"),
    [(TOMORROW, TOMORROW), (date(2026, 10, 25), date(2026, 10, 25))],
    ids=["starts tomorrow", "ended yesterday"],
)
def test_an_absence_off_today_is_entered_as_written_without_the_note(
    first_day: date, last_day: date
) -> None:
    absences, store = service(now=at(12, 0))

    reply = absences.add(AbsenceKind.DAY_OFF, first_day, last_day)

    assert len(reply.lines) == 1
    assert store.book.absences == (Absence(1, AbsenceKind.DAY_OFF, first_day, last_day),)


def test_the_overlap_is_judged_on_the_days_from_tomorrow() -> None:
    today_off = Absence(1, AbsenceKind.DAY_OFF, TODAY, TODAY)
    absences, store = service(AbsenceBook.of((today_off,)), now=at(12, 0))

    reply = absences.add(AbsenceKind.VACATION, TODAY, OCT_28)

    assert english(reply).splitlines()[0] == (
        "Absence 2 entered: vacation from 27.10.2026 to 28.10.2026"
    )
    assert store.book.absences[1] == Absence(2, AbsenceKind.VACATION, TOMORROW, OCT_28)


def test_an_edit_onto_today_once_the_range_began_starts_tomorrow() -> None:
    absences, store = service(AbsenceBook.of((VACATION,)), now=at(9, 0))

    reply = absences.edit(1, None, TODAY, NOV_14)

    assert english(reply).splitlines() == [
        "Absence 1 changed: vacation from 27.10.2026 to 14.11.2026",
        NOTE,
    ]
    assert store.book.absences == (Absence(1, AbsenceKind.VACATION, TOMORROW, NOV_14),)


def test_an_edit_onto_today_alone_once_the_range_began_is_refused_with_the_note() -> None:
    absences, store = service(AbsenceBook.of((VACATION,)), now=at(9, 0))

    reply = absences.edit(1, None, TODAY, TODAY)

    assert english(reply) == NOTE
    assert store.saved == []


def test_an_edit_of_an_absence_already_covering_today_keeps_today() -> None:
    # Today's morning run was skipped for this absence, so the evening must stay silent:
    # moving its start to tomorrow would send the evening run to a desktop never opened.
    running = Absence(1, AbsenceKind.VACATION, date(2026, 10, 20), OCT_28)
    absences, store = service(AbsenceBook.of((running,)), now=at(12, 0))

    reply = absences.edit(1, None, date(2026, 10, 20), NOV_14)

    assert english(reply) == "Absence 1 changed: vacation from 20.10.2026 to 14.11.2026"
    assert store.book.absences == (Absence(1, AbsenceKind.VACATION, date(2026, 10, 20), NOV_14),)


def test_an_edit_ending_an_absence_already_covering_today_on_today_is_kept() -> None:
    # The owner is back early: the absence ends today, and today stays in it, so the
    # evening run stays silent for the morning that was skipped.
    running = Absence(1, AbsenceKind.SICK_LEAVE, date(2026, 10, 20), OCT_28)
    absences, store = service(AbsenceBook.of((running,)), now=at(12, 0))

    reply = absences.edit(1, None, date(2026, 10, 20), TODAY)

    assert english(reply) == "Absence 1 changed: sick leave from 20.10.2026 to 26.10.2026"
    assert store.book.absences == (Absence(1, AbsenceKind.SICK_LEAVE, date(2026, 10, 20), TODAY),)


# --- list -----------------------------------------------------------------------------


def test_list_of_nothing_says_none_is_entered() -> None:
    absences, _ = service()

    assert english(absences.list()) == "No absences entered"


def test_list_names_every_absence_with_its_id_kind_and_dates_by_first_day() -> None:
    later = Absence(3, AbsenceKind.SICK_LEAVE, date(2026, 12, 1), date(2026, 12, 2))
    same_day = Absence(4, AbsenceKind.VACATION, date(2026, 10, 1), date(2026, 10, 1))
    first = Absence(5, AbsenceKind.DAY_OFF, date(2026, 10, 1), date(2026, 10, 1))
    absences, store = service(AbsenceBook.of((later, DAY_OFF, first, VACATION, same_day)))

    reply = absences.list()

    assert english(reply).splitlines() == [
        "Absences entered: 5",
        "Absence 4: vacation on 01.10.2026",
        "Absence 5: day off on 01.10.2026",
        "Absence 1: vacation from 03.11.2026 to 14.11.2026",
        "Absence 2: day off on 20.11.2026",
        "Absence 3: sick leave from 01.12.2026 to 02.12.2026",
    ]
    assert store.saved == []


def test_list_reads_in_russian() -> None:
    absences, _ = service(AbsenceBook.of((VACATION,)))

    assert absences.list().in_language(Language.RU).splitlines() == [
        "Внесено отсутствий: 1",
        "Отсутствие 1: отпуск, дни 03.11.2026–14.11.2026",
    ]


# --- delete ---------------------------------------------------------------------------


def test_delete_removes_the_absence_names_it_and_keeps_the_last_issued_id() -> None:
    absences, store = service(AbsenceBook.of((VACATION, DAY_OFF)))

    reply = absences.delete(2)

    assert english(reply) == "Absence 2 deleted: day off on 20.11.2026"
    assert store.saved == [AbsenceBook((VACATION,), last_issued=2)]


def test_delete_of_an_unknown_id_answers_not_found_and_saves_nothing() -> None:
    absences, store = service(AbsenceBook.of((VACATION,)))

    reply = absences.delete(7)

    assert reply == Reply.of(Message("bot.error.not_found", {"id": 7}))
    assert english(reply) == "No absence 7; /list shows the ones entered"
    assert store.saved == []


# --- edit -----------------------------------------------------------------------------


def test_edit_keeps_the_id_and_the_kind_and_takes_the_new_days() -> None:
    absences, store = service(AbsenceBook.of((VACATION, DAY_OFF)))

    reply = absences.edit(1, None, date(2026, 11, 5), date(2026, 11, 16))

    assert english(reply) == "Absence 1 changed: vacation from 05.11.2026 to 16.11.2026"
    moved = Absence(1, AbsenceKind.VACATION, date(2026, 11, 5), date(2026, 11, 16))
    assert store.saved == [AbsenceBook((moved, DAY_OFF), last_issued=2)]


def test_edit_with_a_kind_changes_the_kind() -> None:
    absences, store = service(AbsenceBook.of((VACATION,)))

    reply = absences.edit(1, AbsenceKind.SICK_LEAVE, NOV_3, NOV_14)

    assert english(reply) == "Absence 1 changed: sick leave from 03.11.2026 to 14.11.2026"
    assert store.book.absences == (Absence(1, AbsenceKind.SICK_LEAVE, NOV_3, NOV_14),)


def test_edit_may_overlap_the_days_the_absence_itself_held() -> None:
    absences, store = service(AbsenceBook.of((VACATION,)))

    absences.edit(1, None, date(2026, 11, 10), date(2026, 11, 18))

    assert store.book.absences[0].first_day == date(2026, 11, 10)


def test_edit_refuses_days_another_absence_holds_and_names_it() -> None:
    absences, store = service(AbsenceBook.of((VACATION, DAY_OFF)))

    reply = absences.edit(1, None, NOV_3, NOV_20)

    assert reply == Reply.of(Message("bot.error.overlap", {"id": 2}))
    assert store.saved == []


def test_edit_of_an_unknown_id_answers_not_found_and_saves_nothing() -> None:
    absences, store = service(AbsenceBook.of((VACATION,)))

    reply = absences.edit(9, None, NOV_3, NOV_14)

    assert reply == Reply.of(Message("bot.error.not_found", {"id": 9}))
    assert store.saved == []


def test_every_call_loads_the_store_afresh() -> None:
    absences, store = service()

    absences.add(AbsenceKind.VACATION, NOV_3, NOV_14)
    absences.list()

    assert store.loads == 2
