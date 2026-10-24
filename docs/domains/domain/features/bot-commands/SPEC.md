# Bot commands

The bot's text command parser: one message from the owner into `/add`, `/list`, `/del`,
`/edit` or `/help` with its kind, id and days, or a refusal as a catalogue message.

## Source

`src/horizon_tracker/domain/bot_commands.py`

## Specification

### Purpose

The owner enters, lists, edits and deletes absences with text commands to the bot. This
module turns one message's text into a command value the absence service can act on, or
into the problem the bot replies with. It decides the syntax only: whether an id exists
and whether two absences overlap is the service's decision, over the store the parser does
not know. Today's date is an argument, so the parser reads no clock.

### How it works

`parse(text, today)` splits the text into words on any whitespace. The first word is the
command, read without case and without a trailing `@<bot name>`:

| Command | Arguments | Answer |
|---------|-----------|--------|
| `/add` | `<kind> <from>[-<to>]` | `Add(kind, first_day, last_day)` |
| `/edit` | `<id> [<kind>] <from>[-<to>]` | `Edit(id, kind or None, first_day, last_day)` |
| `/del` | `<id>` | `Delete(id)` |
| `/list` | none read | `List()` |
| `/help`, `/start` | none read | `Help()` |

The words after `/list`, `/help` and `/start` are not read, because Telegram's `/start`
may carry a deep-link payload. In `/edit` the word after the id is a kind unless it
starts with a digit, because every date does and no kind does.

- **Kinds.** `KIND_WORDS`, read without case: `vacation`, `отпуск` (`VACATION`); `sick`,
  `sick_leave`, `больничный` (`SICK_LEAVE`); `dayoff`, `day_off`, `отгул` (`DAY_OFF`).
- **Dates.** `dd.mm`, `dd.mm.yyyy` or `yyyy-mm-dd`, with one or two digits for a day or a
  month and ASCII digits only.
- **Ranges.** Two dates joined by a hyphen, an en dash or an em dash (`03.11-14.11`), two
  dates as two words (`03.11 14.11`), or two words with the dash standing apart
  (`03.11 - 14.11`). A single date is a one-day range.
- **A date without a year** is placed near its anchor. The end of a range is the next
  occurrence on or after today, or on or after a start written with its year. The start
  is the latest occurrence on or before that end. A single date is the next occurrence
  from today, today included. So on 24.10 `23.10-27.10` is the sick leave that started
  yesterday, `28.12-09.01` crosses into next year, and `01.10-05.10` is next October's.
  The occurrence is looked for in the anchor's year and the next (or the previous) one,
  so `29.02` with no leap year in reach is refused.

### Refusals

Every refusal is a `CommandError(problem)` whose problem is a `Message` the catalogue
holds, so the bot replies in `HT_LANGUAGE`. The parser checks in this order: a command at
all, a known command, the number of words, the id, the kind, the date format, the days.

| Key | Fields | When |
|-----|--------|------|
| `bot.error.not_a_command` | - | the text is empty or does not start with `/` |
| `bot.error.unknown_command` | `command` | a command the bot does not take, lower-cased |
| `bot.error.usage.add` | - | `/add` without a kind and dates, or more than two dates |
| `bot.error.usage.del` | - | `/del` without exactly one word |
| `bot.error.usage.edit` | - | `/edit` without an id and dates, or more than two dates |
| `bot.error.bad_id` | `text` | an id that is not a whole number from `FIRST_ID` (1) |
| `bot.error.unknown_kind` | `kind` | a kind outside `KIND_WORDS`, as typed |
| `bot.error.malformed_date` | `text` | a word in none of the three formats; a joined range is named whole |
| `bot.error.no_such_day` | `text` | a day the calendar lacks (`31.02`, `15.13`), or a yearless `29.02` with no leap year in reach |
| `bot.error.reversed_range` | `first`, `last` | a range written with years whose end is before its start, both days as `dd.mm.yyyy` |

## Invariants

- `parse` never raises for any text: it answers a `Command` or a `CommandError`.
- A `Command`'s `first_day` is never after its `last_day`, so the caller can build an
  `Absence` from it without the `ValueError` the absence refuses a reversed range with.
- A yearless end is never before today unless a dated start anchors it, and a yearless
  start is never after its end.
- No function reads the clock, a file or the network.

## API

Module `src/horizon_tracker/domain/bot_commands.py`:

- `parse(text: str, today: date) -> Command | CommandError`.
- `Add(kind: AbsenceKind, first_day: date, last_day: date)` — frozen.
- `List()`, `Help()` — frozen, no fields.
- `Delete(id: int)` — frozen.
- `Edit(id: int, kind: AbsenceKind | None, first_day: date, last_day: date)` — frozen;
  `kind` is `None` when the command keeps the absence's kind.
- `Command = Add | List | Delete | Edit | Help` — a union usable with `isinstance` and
  `match`.
- `CommandError(problem: Message)` — frozen.
- `KIND_WORDS: Mapping[str, AbsenceKind]` — read-only, the lower-case words for each kind.

## Testing

Tests: `tests/unit/domain/test_bot_commands.py`; the bot texts are pinned in the bot
section of `tests/unit/domain/test_messages.py`. The module is inside the mutation gate.

Scenarios: the PRD HT-012 scenarios of the bot (`tests/acceptance/features/absences.feature`)
drive the parser through the bot loop and the real Telegram transport, among them
`An absence with a malformed date is refused with the expected format`.

## Dependencies

Derived from the imports on reindex.

- Depends on: `absence`, `messages`
- Used by: `bot-loop`

## Contracts

- Consumes `command:bot-text` from `owner-chat` (declared in `.beadloom/_graph/landscape.yml`).

## Parent

`domain` — [domain README](../../README.md)
