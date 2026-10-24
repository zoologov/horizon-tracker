# Absence service

The owner's absences on command: `add`, `list`, `delete` and `edit` over the absence store,
each answering with a `Reply` of catalogue messages that the bot sends in the owner's
language.

## Source

`src/horizon_tracker/application/absence_service.py`

## Specification

### Purpose

The owner enters a vacation, a sick leave or a day off by writing to the bot, and later
lists, moves or deletes it. The bot loop parses the text; this service carries the command
out against the store and says what happened. It decides what the store may hold (no two
absences share a day, an id is never issued twice) and how an absence reads back to the
owner (its id, its kind and its days with the year).

### How it works

Each call loads the book from the store afresh and saves it only when the call changes it,
so a refusal leaves the file as it was.

- `add(kind, first_day, last_day)` gives the new absence `book.next_id()`, one above every
  id held or ever issued. When another absence shares a day with it, the call answers
  `bot.error.overlap` with the lowest such id and saves nothing. Otherwise it saves the
  book with the absence appended and `last_issued` raised to its id, and answers
  `bot.added`.
- `list()` answers `bot.list.empty` for an empty book, or `bot.list.header` (the count)
  followed by one `bot.list.item` per absence, ordered by first day and then by id.
- `delete(id)` answers `bot.error.not_found` for an id the book does not hold. Otherwise it
  saves the book without the absence, with `last_issued` unchanged, and answers
  `bot.deleted` naming what was deleted.
- `edit(id, kind, first_day, last_day)` answers `bot.error.not_found` for an unknown id.
  Otherwise the absence keeps its id and position, takes the new days and takes `kind`
  unless it is `None`. An overlap with another absence is refused as in `add`. The days the
  absence itself held do not count as an overlap. The answer is `bot.edited`.

A reply names an absence by `bot.kind.<kind>` and `bot.days.single` (one day) or
`bot.days.span`, with the dates as `dd.mm.yyyy`, so a date typed without a year is read
back in full: `Absence 1 entered: vacation from 03.11.2026 to 14.11.2026`.

### An absence for today once the check-in range has begun

From the start of today's check-in range (`HT_CHECKIN_RANGE`, its start included) the
morning run may already have checked in, so an `add` or `edit` whose days cover today
starts the absence tomorrow: `first_day` becomes tomorrow, the overlap is judged on the
days from tomorrow, and the reply gets a second line, `bot.note.after_checkin_range`:
`Today's check-in range began at 07:30, so an absence starts tomorrow at the earliest;
this evening's check-out runs as usual`. Days that would end today (a one-day absence
for today, or yesterday and today) leave nothing to enter: the call is refused with that
line alone, saves nothing and issues no id.

An `edit` of an absence that already covers today keeps today: the morning run was
skipped for it, so the evening run stays a silent skip, and moving its start to tomorrow
would send the evening run to a desktop never opened. Before the range begins, an
absence for today is entered as written and the morning run skips for it.

With this rule the run loop needs no state for the evening: an absence covering today
was there before the morning run, so a morning logon belongs to a day no absence covers
(CONTEXT, the coordinator's ruling of 2026-10-24).

## Invariants

- Two absences in the store never share a day.
- An id is never issued twice: `delete` keeps `last_issued`, and `add` allocates above it.
- `edit` keeps the absence's id.
- A refused call (overlap, not found, an absence that would end today once the range
  began) saves nothing.
- From the start of today's check-in range, no `add` or `edit` makes an absence cover
  today that did not already.
- Every call loads the store once; a call that changes nothing saves nothing.
- The service picks no language: a `Reply` is messages, rendered by the caller.
- A store that cannot be read or written raises `AbsenceStoreError` to the caller.

## API

Module `src/horizon_tracker/application/absence_service.py`:

- `Reply(lines: tuple[Message, ...])` — frozen, at least one line (`ValueError`
  otherwise); `Reply.of(*lines)`; `in_language(language) -> str`, the lines joined by a
  line break.
- `AbsenceService(store: AbsenceStore, clock: Clock, checkin_range: TimeRange)`:
  - `add(kind: AbsenceKind, first_day: date, last_day: date) -> Reply`;
  - `list() -> Reply`;
  - `delete(absence_id: int) -> Reply`;
  - `edit(absence_id: int, kind: AbsenceKind | None, first_day: date, last_day: date)
    -> Reply`.

The CLI builds it in `horizon bot` as `AbsenceService(adapters.absences, adapters.clock,
settings.checkin_range)`.

## Testing

Tests: `tests/unit/application/test_absence_service.py` (on `FakeAbsenceStore` and
`FakeClock`), `tests/unit/test_cli.py` (the file under `HT_STATE_DIR`).

Scenarios (`tests/acceptance/features/absences.feature`):

- `An absence entered through the bot is confirmed with its dates and an id`
- `The list names every absence with its id, kind and dates`
- `A deleted absence no longer stops a run`
- `An edited absence keeps its id and takes the new dates`

## Dependencies

Derived from the imports on reindex.

- Depends on: `absence`, `messages`, `ports`, `schedule`
- Used by: `bot-loop`, `cli`

## Parent

`application` — [application README](../../README.md)
