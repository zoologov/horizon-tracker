# Absence

The owner's absences (vacation, sick leave, day off) as day ranges, and the decisions over
a set of them: which covers a day, which comes next, the id a new one gets, whether two
share a day; and the book the store keeps them in.

## Source

`src/horizon_tracker/domain/absence.py`

## Specification

### Purpose

The production calendar does not know that the owner is on leave. An absence is the second
kind of day the service does not work on: the owner enters it through the bot, and a run on
a day it covers does not go ahead. This module holds the absence value and the four
decisions the store, the bot and the runs take over a set of absences. It knows neither the
file the absences are kept in nor today's date: every function takes the day as an argument.

### How it works

- `AbsenceKind` names what the owner is absent for: `VACATION`, `SICK_LEAVE`, `DAY_OFF`.
- `Absence(id, kind, first_day, last_day)` is one range of whole days, both ends included;
  a one-day absence has `first_day == last_day`. `covers(day)` answers whether a day falls
  inside it.
- `covering(absences, day)` returns the absence that covers the day, or `None`. When
  several cover it, the lowest id wins, so the answer does not depend on the order the
  store returned them in.
- `next_after(absences, day)` returns the absence that starts soonest after the day, not
  on it, or `None`. A tie on the first day goes to the lowest id. An absence that has
  started already is not "next": `covering` answers for the day itself.
- `allocate_id(absences, *, last_issued=0)` returns the id of a new absence: one above
  both the highest id held and `last_issued`, the highest id ever handed out. The ids stay
  small integers the owner can type in a chat. With `last_issued` kept beside the
  absences, an id whose absence was deleted never comes back under a new meaning. With the
  default `0`, the answer is the highest id held plus one, which reuses the id of a deleted
  absence that held the highest one.
- `overlaps(first, second)` is true when the two share at least one day, and the order of
  the arguments does not matter. Overlapping absences are refused by the caller, not
  merged.
- `AbsenceBook(absences, last_issued)` is what the `AbsenceStore` port loads and saves:
  the absences in the order they were saved, and the highest id ever issued. The empty
  book, `AbsenceBook()`, holds nothing and has issued nothing. `AbsenceBook.of(absences)`
  builds a book whose `last_issued` is the highest id held, which is how a file written
  without the field reads. `next_id()` is `allocate_id(absences,
  last_issued=last_issued)`, the id the next absence entered gets.

## Invariants

- An absence's `last_day` is never before its `first_day`, and its id is at least
  `FIRST_ID` (1); the constructor raises `ValueError` otherwise.
- `covering` and `next_after` are deterministic over a set: the lowest id breaks every tie.
- `allocate_id` never returns an id at or below `last_issued` or any id held, and refuses
  a negative `last_issued` with `ValueError`.
- `overlaps(a, b) == overlaps(b, a)`, and an absence overlaps itself.
- An `AbsenceBook` holds no id twice, and its `last_issued` is neither negative nor below
  an id it holds; the constructor raises `ValueError` otherwise, so a book that could
  reissue an id cannot be built.
- No function reads the clock, a file or the network.

## API

Module `src/horizon_tracker/domain/absence.py`:

- `FIRST_ID = 1` — the id the first absence gets.
- `AbsenceKind` — `StrEnum`: `VACATION` (`"vacation"`), `SICK_LEAVE` (`"sick_leave"`),
  `DAY_OFF` (`"day_off"`).
- `Absence(id: int, kind: AbsenceKind, first_day: date, last_day: date)` — frozen;
  `covers(day: date) -> bool`.
- `covering(absences: Iterable[Absence], day: date) -> Absence | None`.
- `next_after(absences: Iterable[Absence], day: date) -> Absence | None`.
- `allocate_id(absences: Iterable[Absence], *, last_issued: int = 0) -> int`.
- `overlaps(first: Absence, second: Absence) -> bool`.
- `AbsenceBook(absences: tuple[Absence, ...] = (), last_issued: int = 0)` — frozen;
  classmethod `of(absences: Iterable[Absence]) -> AbsenceBook`; `next_id() -> int`.

## Testing

Tests: `tests/unit/domain/test_absence.py`. The module is inside the mutation gate.

Scenarios: `tests/acceptance/features/absences.feature` names the PRD HT-012 scenarios of
the bot and the runs; until HT-012 BEAD-05 and BEAD-07 build them, they skip with that
reason.

## Dependencies

Derived from the imports on reindex.

- Depends on: (none)
- Used by: `absence-service`, `absence-store`, `ports`, `probe`, `run-report`

## Parent

`domain` — [domain README](../../README.md)
