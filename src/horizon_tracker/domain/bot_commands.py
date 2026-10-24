"""The bot's text command parser: one message from the owner into a command, or a refusal.

``parse(text, today)`` reads ``/add <kind> <from>[-<to>]``, ``/list``, ``/del <id>``,
``/edit <id> [<kind>] <from>[-<to>]`` and ``/help`` (``/start`` is help too) and answers
with a ``Command`` value, or a ``CommandError`` whose problem is a catalogue ``Message``, so
the reply is rendered in the owner's language by whoever sends it. A date is ``dd.mm``,
``dd.mm.yyyy`` or ``yyyy-mm-dd``; a range is two dates joined by a dash or apart; a single
date is one day. A date without a year is placed near its anchor: the end of a range is its
next occurrence from today (or from a start written with its year), and the start is its
latest occurrence on or before that end, so a running absence keeps its start. The parser
knows neither the store nor the clock: today's date is an argument, and whether an id
exists or two absences overlap is the service's decision.
"""

# beadloom:domain=domain
# beadloom:feature=bot-commands

import re
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from horizon_tracker.domain.absence import FIRST_ID, AbsenceKind
from horizon_tracker.domain.messages import Message

# The words the owner may name a kind with, in both languages and the short forms.
KIND_WORDS: Final[Mapping[str, AbsenceKind]] = MappingProxyType(
    {
        "vacation": AbsenceKind.VACATION,
        "отпуск": AbsenceKind.VACATION,
        "sick": AbsenceKind.SICK_LEAVE,
        "sick_leave": AbsenceKind.SICK_LEAVE,
        "больничный": AbsenceKind.SICK_LEAVE,
        "dayoff": AbsenceKind.DAY_OFF,
        "day_off": AbsenceKind.DAY_OFF,
        "отгул": AbsenceKind.DAY_OFF,
    }
)

_COMMAND_PREFIX: Final = "/"
_BOT_ADDRESS: Final = "@"  # "/list@<bot name>", as some clients send a command from the menu
# A hyphen, an en dash and an em dash: a phone keyboard turns "--" into one of the last two.
_DASHES: Final = frozenset("-–—")
_DATE: Final = r"[0-9]{1,2}\.[0-9]{1,2}(?:\.[0-9]{4})?|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}"
_JOINED_RANGE: Final = re.compile(rf"({_DATE})(?:[{''.join(sorted(_DASHES))}]({_DATE}))?")
_DOTTED: Final = re.compile(r"([0-9]{1,2})\.([0-9]{1,2})(?:\.([0-9]{4}))?")
_ISO: Final = re.compile(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})")
# An id the owner types: nine digits are more than any chat will issue, and the bound keeps
# int() far from its limit on a pasted wall of digits.
_ID: Final = re.compile(r"[0-9]{1,9}")
_REPLY_DAY_FORMAT: Final = "%d.%m.%Y"


@dataclass(frozen=True)
class Add:
    """Enter a new absence of ``kind`` from ``first_day`` to ``last_day``, both included."""

    kind: AbsenceKind
    first_day: date
    last_day: date


@dataclass(frozen=True)
class List:
    """Show every absence entered."""


@dataclass(frozen=True)
class Delete:
    """Delete the absence with ``id``."""

    id: int


@dataclass(frozen=True)
class Edit:
    """Give the absence with ``id`` new days, and a new kind unless ``kind`` is ``None``."""

    id: int
    kind: AbsenceKind | None
    first_day: date
    last_day: date


@dataclass(frozen=True)
class Help:
    """Show the commands, the kinds and the date formats."""


Command = Add | List | Delete | Edit | Help


@dataclass(frozen=True)
class CommandError:
    """A text that is not a command the bot takes, and the problem to reply with."""

    problem: Message


@dataclass
class _RefusalError(Exception):
    """Raised inside the parser with the problem ``parse`` answers in a ``CommandError``."""

    problem: Message


@dataclass(frozen=True)
class _WrittenDay:
    """A date as the owner wrote it: its text, day and month, and its year if written."""

    text: str
    day: int
    month: int
    year: int | None


def parse(text: str, today: date) -> Command | CommandError:
    """Return the command ``text`` names, or the refusal to reply with; ``today`` places dates."""
    words = text.split()
    if not words or not words[0].startswith(_COMMAND_PREFIX):
        return CommandError(Message("bot.error.not_a_command"))
    command = words[0].lower().partition(_BOT_ADDRESS)[0]
    try:
        return _command(command, words[1:], today)
    except _RefusalError as refusal:
        return CommandError(refusal.problem)


def _command(command: str, arguments: Sequence[str], today: date) -> Command:
    match command:
        case "/add":
            return _add(arguments, today)
        case "/edit":
            return _edit(arguments, today)
        case "/del":
            return Delete(_id(_only(arguments, Message("bot.error.usage.del"))))
        case "/list":
            return List()
        case "/help" | "/start":
            return Help()
    raise _RefusalError(Message("bot.error.unknown_command", {"command": command}))


def _add(arguments: Sequence[str], today: date) -> Add:
    usage = Message("bot.error.usage.add")
    if len(arguments) < 2:
        raise _RefusalError(usage)
    kind = _kind(arguments[0])
    first_day, last_day = _days(arguments[1:], today, usage)
    return Add(kind, first_day, last_day)


def _edit(arguments: Sequence[str], today: date) -> Edit:
    usage = Message("bot.error.usage.edit")
    if len(arguments) < 2:
        raise _RefusalError(usage)
    absence_id = _id(arguments[0])
    rest = arguments[1:]
    kind = None
    if rest[0][0] not in string.digits:  # every date starts with a digit, no kind does
        kind = _kind(rest[0])
        rest = rest[1:]
    first_day, last_day = _days(rest, today, usage)
    return Edit(absence_id, kind, first_day, last_day)


def _only(arguments: Sequence[str], usage: Message) -> str:
    if len(arguments) != 1:
        raise _RefusalError(usage)
    return arguments[0]


def _id(word: str) -> int:
    if _ID.fullmatch(word) is None or int(word) < FIRST_ID:
        raise _RefusalError(Message("bot.error.bad_id", {"text": word}))
    return int(word)


def _kind(word: str) -> AbsenceKind:
    kind = KIND_WORDS.get(word.lower())
    if kind is None:
        raise _RefusalError(Message("bot.error.unknown_kind", {"kind": word}))
    return kind


def _days(words: Sequence[str], today: date, usage: Message) -> tuple[date, date]:
    if len(words) == 3 and words[1] in _DASHES:  # "03.11 - 14.11": the dash stands apart
        words = [words[0], words[2]]
    if len(words) == 1:
        first, last = _split(words[0])
    elif len(words) == 2:
        first, last = words
    else:
        raise _RefusalError(usage)
    return _place(_read(first), _read(last), today)


def _split(joined: str) -> tuple[str, str]:
    """The two dates of ``03.11-14.11``; a single date is both ends of a one-day range."""
    match = _JOINED_RANGE.fullmatch(joined)
    if match is None:
        raise _malformed(joined)
    first, last = match.groups()
    return first, last or first


def _read(word: str) -> _WrittenDay:
    if dotted := _DOTTED.fullmatch(word):
        day, month, year = dotted.groups()
        return _WrittenDay(word, int(day), int(month), None if year is None else int(year))
    if iso := _ISO.fullmatch(word):
        year, month, day = iso.groups()
        return _WrittenDay(word, int(day), int(month), int(year))
    raise _malformed(word)


def _malformed(word: str) -> _RefusalError:
    return _RefusalError(Message("bot.error.malformed_date", {"text": word}))


def _place(first: _WrittenDay, last: _WrittenDay, today: date) -> tuple[date, date]:
    """The range's days: a yearless end follows its start or today, a yearless start its end."""
    start = None if first.year is None else _exact(first, first.year)
    end = _on_or_after(last, start or today) if last.year is None else _exact(last, last.year)
    if start is None:
        start = _on_or_before(first, end)
    if end < start:
        fields = {"first": f"{start:{_REPLY_DAY_FORMAT}}", "last": f"{end:{_REPLY_DAY_FORMAT}}"}
        raise _RefusalError(Message("bot.error.reversed_range", fields))
    return start, end


def _exact(written: _WrittenDay, year: int) -> date:
    day = _in_year(written, year)
    if day is None:
        raise _no_such_day(written)
    return day


def _on_or_after(written: _WrittenDay, anchor: date) -> date:
    """The first ``written`` day on or after ``anchor``, in its year or the next one."""
    for year in (anchor.year, anchor.year + 1):
        day = _in_year(written, year)
        if day is not None and day >= anchor:
            return day
    raise _no_such_day(written)


def _on_or_before(written: _WrittenDay, anchor: date) -> date:
    """The last ``written`` day on or before ``anchor``, in its year or the one before."""
    for year in (anchor.year, anchor.year - 1):
        day = _in_year(written, year)
        if day is not None and day <= anchor:
            return day
    raise _no_such_day(written)


def _in_year(written: _WrittenDay, year: int) -> date | None:
    try:
        return date(year, written.month, written.day)
    except ValueError:  # 31.02, 15.13, 29.02 outside a leap year, or a year out of range
        return None


def _no_such_day(written: _WrittenDay) -> _RefusalError:
    return _RefusalError(Message("bot.error.no_such_day", {"text": written.text}))
