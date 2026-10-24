"""Changes and reads the owner's absences on the owner's command, answering each with a reply.

``AbsenceService`` is what the bot's commands do to the absence store: ``add`` enters an
absence under a new id, ``list`` names the absences not yet over and counts the finished
ones, ``delete`` removes one and ``edit`` gives one new days (and a new kind) under the
same id. The store keeps every absence, finished or not. The store is loaded afresh for
each call and saved only when the call changes it, so a refusal leaves the file as it was.
Two absences never share a day: an ``add`` or ``edit`` that would is refused, naming the
absence in the way, and the owner edits or deletes it first.

Every call answers with a ``Reply``: catalogue messages, one per line, with no language
yet. A reply names an absence with its id, its kind and its days with the year, so a date
typed without one is read back in full. A store that cannot be read or written raises
``AbsenceStoreError`` to the caller.

Today's morning run may already have checked in once today's check-in range has begun, so
an ``add`` or ``edit`` from then on that would cover today starts the absence tomorrow and
says so in a second line: this evening's check-out runs as usual. An absence that would
have ended today is refused with that line alone. An absence already covering today keeps
today under ``edit``: the morning skipped for it, and the evening stays silent.
"""

# beadloom:domain=application
# beadloom:feature=absence-service

from dataclasses import dataclass
from datetime import date, timedelta

from horizon_tracker.domain.absence import Absence, AbsenceBook, AbsenceKind, overlaps
from horizon_tracker.domain.messages import Language, Message
from horizon_tracker.domain.ports import AbsenceStore, Clock
from horizon_tracker.domain.schedule import TimeRange

_DAY_FORMAT = "%d.%m.%Y"  # a reply gives the year, as the bot.days.* texts expect
_TIME_FORMAT = "%H:%M"
_LINE_BREAK = "\n"
_ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class Reply:
    """The bot's answer to one message: catalogue messages, one per line, no language yet."""

    lines: tuple[Message, ...]

    def __post_init__(self) -> None:
        if not self.lines:
            msg = "a reply has at least one line"
            raise ValueError(msg)

    @classmethod
    def of(cls, *lines: Message) -> "Reply":
        """A reply of ``lines``, in order."""
        return cls(lines)

    def in_language(self, language: Language) -> str:
        """The reply's text in ``language``, its lines one under another."""
        return _LINE_BREAK.join(line.in_language(language) for line in self.lines)


class AbsenceService:
    """Adds, lists, deletes and edits the absences in ``store``, answering each with a reply."""

    def __init__(self, store: AbsenceStore, clock: Clock, checkin_range: TimeRange) -> None:
        self._store = store
        self._clock = clock
        self._checkin_range = checkin_range

    def add(self, kind: AbsenceKind, first_day: date, last_day: date) -> Reply:
        """Enter an absence under a new id, unless another one holds any of its days."""
        book = self._store.load()
        first = self._first_day_to_enter(first_day, last_day, held=None)
        if first > last_day:
            return Reply.of(self._note())
        entered = Absence(book.next_id(), kind, first, last_day)
        clash = _first_overlap(book.absences, entered)
        if clash is not None:
            return _overlap(clash)
        self._store.save(AbsenceBook((*book.absences, entered), last_issued=entered.id))
        return self._answer(_naming("bot.added", entered), moved=first != first_day)

    def list(self) -> Reply:
        """Name the absences not yet over, earliest first, and count the finished ones."""
        held = self._store.load().absences
        if not held:
            return Reply.of(Message("bot.list.empty"))
        today = self._clock.now().date()
        ahead = sorted(not_over(held, today), key=_by_first_day_then_id)
        lines = [_list_header(len(ahead))]
        lines.extend(_naming("bot.list.item", absence) for absence in ahead)
        finished = len(held) - len(ahead)
        if finished:
            lines.append(Message("bot.list.finished", {"count": finished}))
        return Reply(tuple(lines))

    def delete(self, absence_id: int) -> Reply:
        """Remove the absence with ``absence_id``; its id is never issued again."""
        book = self._store.load()
        deleted = _find(book.absences, absence_id)
        if deleted is None:
            return _not_found(absence_id)
        kept = tuple(absence for absence in book.absences if absence.id != absence_id)
        self._store.save(AbsenceBook(kept, last_issued=book.last_issued))
        return Reply.of(_naming("bot.deleted", deleted))

    def edit(
        self, absence_id: int, kind: AbsenceKind | None, first_day: date, last_day: date
    ) -> Reply:
        """Give the absence new days, and ``kind`` unless it is ``None``, under the same id."""
        book = self._store.load()
        held = _find(book.absences, absence_id)
        if held is None:
            return _not_found(absence_id)
        first = self._first_day_to_enter(first_day, last_day, held=held)
        if first > last_day:
            return Reply.of(self._note())
        edited = Absence(absence_id, kind or held.kind, first, last_day)
        others = tuple(absence for absence in book.absences if absence.id != absence_id)
        clash = _first_overlap(others, edited)
        if clash is not None:
            return _overlap(clash)
        changed = tuple(
            edited if absence.id == absence_id else absence for absence in book.absences
        )
        self._store.save(AbsenceBook(changed, last_issued=book.last_issued))
        return self._answer(_naming("bot.edited", edited), moved=first != first_day)

    def _first_day_to_enter(self, first_day: date, last_day: date, *, held: Absence | None) -> date:
        """``first_day``, or tomorrow when the days cover today and today's range has begun.

        ``held`` is the absence an edit changes: one that already covers today keeps today.
        """
        now = self._clock.now()
        today = now.date()
        if held is not None and held.covers(today):
            return first_day
        if first_day <= today <= last_day and now.time() >= self._checkin_range.start:
            return today + _ONE_DAY
        return first_day

    def _answer(self, line: Message, *, moved: bool) -> Reply:
        """``line``, and the note under it when the absence was moved to start tomorrow."""
        return Reply.of(line, self._note()) if moved else Reply.of(line)

    def _note(self) -> Message:
        start = f"{self._checkin_range.start:{_TIME_FORMAT}}"
        return Message("bot.note.after_checkin_range", {"start": start})


def _find(absences: tuple[Absence, ...], absence_id: int) -> Absence | None:
    return next((absence for absence in absences if absence.id == absence_id), None)


def _first_overlap(absences: tuple[Absence, ...], candidate: Absence) -> Absence | None:
    """The absence with the lowest id that shares a day with ``candidate``, else ``None``."""
    clashing = (absence for absence in absences if overlaps(absence, candidate))
    return min(clashing, key=lambda absence: absence.id, default=None)


def not_over(absences: tuple[Absence, ...], today: date) -> tuple[Absence, ...]:
    """The absences whose last day is ``today`` or later: the ones a run may still meet.

    ``list`` and the probe name these; the finished ones stay in the store and are counted.
    """
    return tuple(absence for absence in absences if absence.last_day >= today)


def _list_header(count: int) -> Message:
    if not count:
        return Message("bot.list.none_ahead")
    return Message("bot.list.header", {"count": count})


def _by_first_day_then_id(absence: Absence) -> tuple[date, int]:
    return absence.first_day, absence.id


def _naming(key: str, absence: Absence) -> Message:
    """The message ``key`` filled with the absence's id, its kind and its days."""
    return Message(key, {"id": absence.id, "kind": _kind(absence.kind), "days": _days(absence)})


def _kind(kind: AbsenceKind) -> Message:
    return Message(f"bot.kind.{kind.value}")


def _days(absence: Absence) -> Message:
    first = f"{absence.first_day:{_DAY_FORMAT}}"
    if absence.first_day == absence.last_day:
        return Message("bot.days.single", {"day": first})
    return Message("bot.days.span", {"first": first, "last": f"{absence.last_day:{_DAY_FORMAT}}"})


def _overlap(clash: Absence) -> Reply:
    return Reply.of(Message("bot.error.overlap", {"id": clash.id}))


def _not_found(absence_id: int) -> Reply:
    return Reply.of(Message("bot.error.not_found", {"id": absence_id}))
