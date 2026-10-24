"""The owner's absences: their kinds, their day ranges, and the decisions over a set of them.

An absence is a vacation, a sick leave or a day off, entered by the owner as a range of
whole days, ends included. A run on a day an absence covers does not go ahead. This module
decides which absence covers a day, which one comes next, which id a new one gets, and
whether two of them share a day; it knows neither the file they are kept in nor today's
date, which every function takes as an argument. ``AbsenceBook`` is what the store keeps:
the absences together with the highest id ever issued, so a deleted id is never reissued.
"""

# beadloom:domain=domain
# beadloom:feature=absence

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

FIRST_ID = 1  # the id the first absence gets: small integers, typeable in a chat


class AbsenceKind(StrEnum):
    """What the owner is absent for; the notice names it as the reason of a skipped run."""

    VACATION = "vacation"
    SICK_LEAVE = "sick_leave"
    DAY_OFF = "day_off"


@dataclass(frozen=True)
class Absence:
    """One absence: its id, its kind and the first and last day it covers, both included."""

    id: int
    kind: AbsenceKind
    first_day: date
    last_day: date

    def __post_init__(self) -> None:
        if self.id < FIRST_ID:
            msg = f"absence id must be at least {FIRST_ID}, got {self.id}"
            raise ValueError(msg)
        if self.last_day < self.first_day:
            msg = f"absence last day {self.last_day} is before the first day {self.first_day}"
            raise ValueError(msg)

    def covers(self, day: date) -> bool:
        """Return whether ``day`` falls inside the absence, both ends included."""
        return self.first_day <= day <= self.last_day


def _by_id(absence: Absence) -> int:
    return absence.id


def covering(absences: Iterable[Absence], day: date) -> Absence | None:
    """Return the absence that covers ``day``, the lowest id when several do, else ``None``."""
    return min((absence for absence in absences if absence.covers(day)), key=_by_id, default=None)


def _by_start_then_id(absence: Absence) -> tuple[date, int]:
    return absence.first_day, absence.id


def next_after(absences: Iterable[Absence], day: date) -> Absence | None:
    """Return the absence that starts soonest after ``day`` (not on it), else ``None``.

    A tie on the first day goes to the lowest id. An absence that started on or before
    ``day`` is not next, whether it still covers ``day`` or is over: ``covering`` answers
    for the day itself.
    """
    upcoming = (absence for absence in absences if absence.first_day > day)
    return min(upcoming, key=_by_start_then_id, default=None)


def allocate_id(absences: Iterable[Absence], *, last_issued: int = 0) -> int:
    """Return the id a new absence gets: one above every id held or ever issued.

    ``last_issued`` is the highest id ever handed out, kept beside the absences by the
    caller, so an id whose absence was deleted never comes back under a new meaning. Without
    it the answer is the highest id held plus one, which reuses the id of a deleted absence
    that had the highest one.
    """
    _refuse_negative(last_issued)
    return max(_highest_id(absences), last_issued) + 1


def _refuse_negative(last_issued: int) -> None:
    if last_issued < 0:
        msg = f"last issued id must not be negative, got {last_issued}"
        raise ValueError(msg)


def _highest_id(absences: Iterable[Absence]) -> int:
    return max((absence.id for absence in absences), default=0)


def overlaps(first: Absence, second: Absence) -> bool:
    """Return whether the two absences share at least one day; the order does not matter."""
    return first.first_day <= second.last_day and second.first_day <= first.last_day


@dataclass(frozen=True)
class AbsenceBook:
    """The absences the owner entered and the highest id ever issued, kept together.

    The book is what the store loads and saves. ``last_issued`` is never below an id held,
    and no id is held twice, so an id names one absence and a deleted one is not reissued.
    """

    absences: tuple[Absence, ...] = ()
    last_issued: int = 0

    def __post_init__(self) -> None:
        _refuse_negative(self.last_issued)
        counts = Counter(absence.id for absence in self.absences)
        twice = next((id_ for id_, count in counts.items() if count > 1), None)
        if twice is not None:
            msg = f"absence id {twice} is held twice"
            raise ValueError(msg)
        highest = _highest_id(self.absences)
        if self.last_issued < highest:
            msg = f"last issued id {self.last_issued} is below the id {highest} held"
            raise ValueError(msg)

    @classmethod
    def of(cls, absences: Iterable[Absence]) -> "AbsenceBook":
        """A book of ``absences`` whose last issued id is the highest one held."""
        held = tuple(absences)
        return cls(absences=held, last_issued=_highest_id(held))

    def next_id(self) -> int:
        """The id the next absence entered gets: one above every id held or ever issued."""
        return allocate_id(self.absences, last_issued=self.last_issued)
