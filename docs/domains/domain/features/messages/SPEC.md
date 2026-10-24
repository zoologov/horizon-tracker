# Messages

The message catalogue: every text a person reads, keyed, in English and Russian, the
lookup that fills a text's named fields, and `Message`, a key with its fields that has no
language yet.

## Source

`src/horizon_tracker/domain/messages.py`

## Specification

### Purpose

The owner reads the notifications, the output of `horizon probe` and `--dry-run` and the
bot's replies, and chooses the language they are written in. One catalogue in the domain holds every such
text in every supported language, so no text is a literal inside the logic that decides
when to show it, and a missing translation is found by a test rather than by the owner at
07:43. The catalogue is plain data in code: two languages and 124 keys do not earn gettext.

### How it works

`MESSAGES` maps a dotted key to one text per `Language`. The keys are grouped by the
place a person reads them:

- `report.*` - the lines of the run notification: the headline per run kind and outcome
  (`report.checkin.succeeded`, ...), the time line with and without the planned moment,
  the calendar line, one key per source (`report.calendar.calendar`,
  `report.calendar.weekday_fallback`, `report.calendar.not_asked`), the reason line and
  the reason line with an absence's days (`report.reason_span`);
- `reason.*` - one phrase per `Reason`, keyed by its value, the absence reasons
  (`reason.on_vacation`, `reason.on_sick_leave`, `reason.on_day_off`) included;
- `probe.*` - the settings line of `horizon probe`, the names and statuses of its checks
  and what each check answers, the `absences` check's four answers included
  (`probe.absences.none`, `probe.absences.entered` `{held}`, `probe.absences.entered_next`
  `{held}`, `probe.absences.unreadable`, whose `{reason}` is the store's technical English
  in both languages), the `{held}` field being `probe.absences.held` `{count}` (the
  absences not over) or `probe.absences.held_and_finished` `{count}` `{finished}`;
- `plan.*` - the dry-run plan: its header, verdict, calendar sources and the steps of
  one attempt;
- `bot.*` - the bot's texts (HT-012): the help (`bot.help`); one name per `AbsenceKind`,
  keyed by its value (`bot.kind.vacation`, `bot.kind.sick_leave`, `bot.kind.day_off`); an
  absence's days with the year (`bot.days.single` `{day}`, `bot.days.span` `{first}`
  `{last}`), so a date typed without a year is read back in full; the replies to the
  commands, each naming `{id}`, `{kind}` and `{days}` (`bot.added`, `bot.edited`,
  `bot.deleted`, `bot.list.item`), the list's `bot.list.header` `{count}` (the absences
  not over), `bot.list.none_ahead`, `bot.list.finished` `{count}` (the finished ones,
  counted and not listed) and `bot.list.empty`; the note `bot.note.after_checkin_range` `{start}` (HH:MM), the
  second line of a reply whose absence was moved to start tomorrow because today's
  check-in range had begun, and the whole reply when nothing was left to enter; and the refusals `bot.error.*`: the parser's ten (see the
  `bot-commands` SPEC) and the service's `bot.error.not_found` `{id}`,
  `bot.error.overlap` `{id}` and `bot.error.internal`;
- `config.*` - the line a reader gets for a configuration error (`config.error`) and the
  problem it names after `<VARIABLE>: `. A problem the domain's own check refused carries
  the domain's reason as its `{error}` field, and that reason is itself a message, so it
  reads in the reader's language: `config.invalid_range`, `config.checkout_after_checkin`,
  `config.unusable_session_length` and `config.unusable_grace` take a `schedule.*`
  message, and `config.invalid_range` takes `config.no_such_time` for an hour or a minute
  no clock shows (`25:00`);
- `schedule.*` - the schedule's refusals of a value a setting can reach (`ScheduleError`
  in the `schedule` SPEC): `schedule.range_order`, `schedule.checkout_after_checkin`,
  `schedule.session_length_not_positive`, `schedule.grace_not_positive`,
  `schedule.window_crosses_midnight`.

A Russian configuration error is Russian from end to end. Only what the reader types
stays as written: the variable name, the value they gave and the language codes.

Every refusal of a setting has the same shape, `<VARIABLE>: <problem>`, the bot token's
included: `TELEGRAM_BOT_TOKEN: is malformed: expected <bot id>:<secret>`. A range with an
hour or a minute no clock shows is refused with the catalogue's own reason,
`not a valid range '25:00-26:00': no such time of day`, and never with the text of the
exception the standard library raised. The probe's settings line names the language last
(`, language en`). The English text of a `schedule.*` key is the `str()` of the
`ScheduleError` that carries it, so the English log line of a configuration error and the
domain's exception say the same thing.

`text(key, language, /, **fields)` returns the text of `key` in `language` with its named
fields filled by `str.format`; a field may carry a conversion (`{desktop!r}`). `key` and
`language` are positional, so a text may name a field `language` (the probe's settings
line does). A text is always formatted, so a text with a field the caller did not pass is
never returned half-filled.

`Message(key, fields)` is what the use cases and the settings hand out instead of a
string: the probe's check details and labels, the steps of a dry run, the problem of a
configuration error, the reason of a schedule refusal. Whoever shows it to a person calls
`in_language(language)`; a field whose value is itself a `Message` is read in the same
language first. A key the catalogue does not hold is refused when the message is made, so
a typo fails where it is written. The fields are copied into a read-only mapping when the
message is made: neither the caller's mapping changing later nor a reader can change it.

`missing_translations(catalogue=MESSAGES)` returns every `(key, language)` pair whose text
is absent or blank, sorted by key and then in `Language` order. For the shipped catalogue
the answer is an empty list, and a test holds it there.

Logs are not in the catalogue: the operator reads the journal in English whatever
language `HT_LANGUAGE` picks. English is the default language, Russian the other one.

## Invariants

- Every key has a non-blank text in every `Language`.
- Every translation of a key names the same set of fields, so a field cannot be missing
  in one language only.
- No English text contains a Cyrillic letter, and every Russian text contains one: a
  Russian entry copied from English is caught.
- An unknown key and an unfilled field raise `KeyError` naming the key or the field; a
  `Message` with an unknown key is refused when it is made.
- A `config.*` or `schedule.*` text in Russian holds no Latin letter outside its fields
  and the environment variables it names.
- A `Message`'s fields cannot change after it is made.
- The module performs no I/O and imports nothing outside the standard library.

## API

Module `src/horizon_tracker/domain/messages.py`:

- `Language` - `StrEnum`: `EN = "en"`, `RU = "ru"`; `Language("de")` raises `ValueError`.
- `DEFAULT_LANGUAGE` - `Language.EN`.
- `MESSAGES: Mapping[str, Mapping[Language, str]]` - the catalogue.
- `text(key: str, language: Language, /, **fields: object) -> str` - the filled text.
- `Message(key: str, fields: Mapping[str, object] = {})` - frozen; `fields` is a read-only
  copy (`MappingProxyType`); `in_language(language) -> str` reads a `Message`-valued field
  in the same language. Equal messages hash alike (the hash reads the key only).
- `missing_translations(catalogue=MESSAGES) -> list[tuple[str, Language]]` - the pairs
  without a text.

## Testing

Tests: `tests/unit/domain/test_messages.py`. The functions are inside the mutation gate.
The catalogue's data is outside it by construction, because mutmut mutates function
bodies only. The texts are pinned elsewhere: the render tests in
`tests/unit/domain/test_report.py` pin `report.*` and `reason.*` in both languages, and
`tests/unit/test_cli.py`, `tests/unit/infrastructure/test_config.py`,
`tests/unit/domain/test_moments.py` and the language scenarios pin `plan.*`, `probe.*`,
`config.*` and `schedule.*`; `tests/unit/domain/test_bot_commands.py` and the bot section of
`test_messages.py` pin `bot.*`.

Scenarios (`tests/acceptance/features/language.feature`):

- `Every message key has a text in every supported language`
- `A configuration error reaches a Russian reader in Russian beside the English log line`
- `A value the schedule refuses reaches a Russian reader with its reason in Russian`
- `A configuration error is said once to an English reader`

## Dependencies

Derived from the imports on reindex.

- Depends on: (none)
- Used by: `schedule`, `run-report`, `bot-commands`, `morning-checkin`, `evening-checkout`,
  `windowed-run`, `probe`, `settings`, `telegram-notifier`, `absence-service`, `bot-loop`,
  `cli`

## Parent

`domain` - [domain README](../../README.md)
