"""Unit tests for the absence model: its kinds, its range, and the decisions over a set of them."""

import dataclasses
from datetime import date

import pytest

from horizon_tracker.domain.absence import (
    FIRST_ID,
    Absence,
    AbsenceKind,
    allocate_id,
    covering,
    next_after,
    overlaps,
)

VACATION = AbsenceKind.VACATION
SICK_LEAVE = AbsenceKind.SICK_LEAVE
DAY_OFF = AbsenceKind.DAY_OFF


def _absence(
    absence_id: int, first: date, last: date | None = None, kind: AbsenceKind = VACATION
) -> Absence:
    return Absence(id=absence_id, kind=kind, first_day=first, last_day=last or first)


# --- AbsenceKind --------------------------------------------------------------


def test_absence_kind_has_exactly_the_three_kinds_the_owner_enters() -> None:
    assert {kind.value for kind in AbsenceKind} == {"vacation", "sick_leave", "day_off"}


# --- Absence ------------------------------------------------------------------


def test_an_absence_holds_its_id_kind_and_both_days() -> None:
    absence = Absence(
        id=3, kind=SICK_LEAVE, first_day=date(2026, 11, 3), last_day=date(2026, 11, 14)
    )

    assert (absence.id, absence.kind, absence.first_day, absence.last_day) == (
        3,
        SICK_LEAVE,
        date(2026, 11, 3),
        date(2026, 11, 14),
    )


def test_an_absence_is_frozen() -> None:
    absence = _absence(1, date(2026, 11, 3))

    with pytest.raises(dataclasses.FrozenInstanceError):
        absence.id = 2  # type: ignore[misc]  # the assignment is the thing under test


def test_a_one_day_absence_is_allowed() -> None:
    absence = _absence(1, date(2026, 11, 3), date(2026, 11, 3))

    assert absence.first_day == absence.last_day


def test_an_absence_refuses_a_last_day_before_its_first_day() -> None:
    with pytest.raises(ValueError, match=r"last day 2026-11-02 is before the first day 2026-11-03"):
        _absence(1, date(2026, 11, 3), date(2026, 11, 2))


def test_the_first_id_is_one() -> None:
    assert FIRST_ID == 1


def test_an_absence_accepts_the_first_id() -> None:
    assert _absence(FIRST_ID, date(2026, 11, 3)).id == FIRST_ID


def test_an_absence_refuses_an_id_below_the_first_one() -> None:
    with pytest.raises(ValueError, match=r"absence id must be at least 1, got 0"):
        _absence(0, date(2026, 11, 3))


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 11, 2), False),
        (date(2026, 11, 3), True),
        (date(2026, 11, 8), True),
        (date(2026, 11, 14), True),
        (date(2026, 11, 15), False),
    ],
)
def test_an_absence_covers_its_days_both_ends_included(day: date, expected: bool) -> None:
    absence = _absence(1, date(2026, 11, 3), date(2026, 11, 14))

    assert absence.covers(day) is expected


# --- covering -----------------------------------------------------------------


def test_covering_finds_nothing_in_no_absences() -> None:
    assert covering((), date(2026, 11, 3)) is None


def test_covering_finds_nothing_on_a_day_outside_every_absence() -> None:
    absences = (_absence(1, date(2026, 11, 3), date(2026, 11, 14)), _absence(2, date(2026, 12, 1)))

    assert covering(absences, date(2026, 11, 20)) is None


def test_covering_returns_the_absence_the_day_falls_in() -> None:
    december = _absence(2, date(2026, 12, 1), kind=DAY_OFF)
    absences = (_absence(1, date(2026, 11, 3), date(2026, 11, 14)), december)

    assert covering(absences, date(2026, 12, 1)) is december


def test_covering_returns_the_lowest_id_when_several_cover_the_day() -> None:
    later = _absence(7, date(2026, 11, 1), date(2026, 11, 30), kind=SICK_LEAVE)
    earlier = _absence(4, date(2026, 11, 3), date(2026, 11, 14))

    assert covering((later, earlier), date(2026, 11, 5)) is earlier


def test_covering_reads_any_iterable_once() -> None:
    absence = _absence(1, date(2026, 11, 3))

    assert covering(iter([absence]), date(2026, 11, 3)) is absence


# --- next_after ---------------------------------------------------------------


def test_next_after_finds_nothing_in_no_absences() -> None:
    assert next_after((), date(2026, 11, 3)) is None


def test_next_after_finds_nothing_when_every_absence_has_started() -> None:
    absences = (_absence(1, date(2026, 11, 3), date(2026, 11, 14)), _absence(2, date(2026, 10, 1)))

    assert next_after(absences, date(2026, 11, 3)) is None


def test_next_after_returns_the_absence_that_starts_soonest_after_the_day() -> None:
    december = _absence(1, date(2026, 12, 1))
    november = _absence(2, date(2026, 11, 3), date(2026, 11, 14))

    assert next_after((december, november), date(2026, 10, 24)) is november


def test_next_after_skips_an_absence_that_starts_on_the_day_itself() -> None:
    today = _absence(1, date(2026, 11, 3))
    tomorrow = _absence(2, date(2026, 11, 4))

    assert next_after((today, tomorrow), date(2026, 11, 3)) is tomorrow


def test_next_after_breaks_a_tie_on_the_first_day_by_the_lowest_id() -> None:
    higher = _absence(9, date(2026, 11, 3))
    lower = _absence(5, date(2026, 11, 3), date(2026, 11, 4))

    assert next_after((higher, lower), date(2026, 11, 1)) is lower


# --- allocate_id --------------------------------------------------------------


def test_allocate_id_starts_at_the_first_id() -> None:
    assert allocate_id(()) == FIRST_ID


def test_allocate_id_is_one_above_the_highest_id() -> None:
    absences = (_absence(2, date(2026, 11, 3)), _absence(5, date(2026, 11, 4)))

    assert allocate_id(absences) == 6


def test_allocate_id_does_not_fill_a_gap_left_by_a_deletion() -> None:
    absences = (_absence(1, date(2026, 11, 3)), _absence(3, date(2026, 11, 4)))

    assert allocate_id(absences) == 4


def test_allocate_id_never_reuses_an_issued_id_even_when_its_absence_is_gone() -> None:
    survivors = (_absence(1, date(2026, 11, 3)),)

    assert allocate_id(survivors, last_issued=5) == 6


def test_allocate_id_honours_the_last_issued_id_with_no_absences_left() -> None:
    assert allocate_id((), last_issued=5) == 6


def test_allocate_id_takes_the_higher_of_the_ids_and_the_last_issued_one() -> None:
    absences = (_absence(8, date(2026, 11, 3)),)

    assert allocate_id(absences, last_issued=5) == 9


def test_allocate_id_accepts_no_id_issued_yet() -> None:
    assert allocate_id((), last_issued=0) == FIRST_ID


def test_allocate_id_refuses_a_negative_last_issued_id() -> None:
    with pytest.raises(ValueError, match=r"last issued id must not be negative, got -1"):
        allocate_id((), last_issued=-1)


# --- overlaps -----------------------------------------------------------------

_NOVEMBER = _absence(1, date(2026, 11, 3), date(2026, 11, 14))


@pytest.mark.parametrize(
    ("other", "expected"),
    [
        (_absence(2, date(2026, 10, 20), date(2026, 11, 2)), False),
        (_absence(2, date(2026, 10, 20), date(2026, 11, 3)), True),
        (_absence(2, date(2026, 11, 5), date(2026, 11, 6)), True),
        (_absence(2, date(2026, 11, 1), date(2026, 11, 30)), True),
        (_absence(2, date(2026, 11, 14), date(2026, 11, 20)), True),
        (_absence(2, date(2026, 11, 15), date(2026, 11, 20)), False),
    ],
    ids=[
        "ends-the-day-before",
        "ends-on-the-first-day",
        "inside",
        "around",
        "starts-on-the-last-day",
        "starts-the-day-after",
    ],
)
def test_overlaps_is_true_when_the_two_share_a_day_and_symmetric(
    other: Absence, expected: bool
) -> None:
    assert overlaps(_NOVEMBER, other) is expected
    assert overlaps(other, _NOVEMBER) is expected


def test_an_absence_overlaps_itself() -> None:
    assert overlaps(_NOVEMBER, _NOVEMBER) is True
