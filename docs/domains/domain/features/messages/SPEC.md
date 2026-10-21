# Messages

The message catalogue: every text a person reads, keyed, in English and Russian, the
lookup that fills a text's named fields, and `Message`, a key with its fields that has no
language yet.

## Source

`src/horizon_tracker/domain/messages.py`

## Specification

### Purpose

The owner reads the notifications and the output of `horizon probe` and `--dry-run`, and
chooses the language they are written in. One catalogue in the domain holds every such
text in every supported language, so no text is a literal inside the logic that decides
when to show it, and a missing translation is found by a test rather than by the owner at
07:43. The catalogue is plain data in code: two languages and 77 keys do not earn gettext.

### How it works

`MESSAGES` maps a dotted key to one text per `Language`. The keys are grouped by the
place a person reads them:

- `report.*` - the lines of the run notification: the headline per run kind and outcome
  (`report.checkin.succeeded`, ...), the time line with and without the planned moment,
  the calendar line and its three sources, the reason line;
- `reason.*` - one phrase per `Reason`, keyed by its value;
- `probe.*` - the settings line of `horizon probe`, the names and statuses of its checks
  and what each check answers;
- `plan.*` - the dry-run plan: its header, verdict, calendar sources and the steps of
  one attempt;
- `config.*` - the line a reader gets for a configuration error (`config.error`) and the
  problem it names after `<VARIABLE>: `; a problem the domain's own check refused carries
  the domain's English reason as its `{error}` field.

The English texts of `plan.*`, `config.*` and the probe's checks are the strings those
commands printed before HT-007, byte for byte, with two deliberate changes: the probe's
settings line ends with `, language <code>`, and a refused bot token reads
`TELEGRAM_BOT_TOKEN: is malformed: expected <bot id>:<secret>` like every other refusal.

`text(key, language, /, **fields)` returns the text of `key` in `language` with its named
fields filled by `str.format`; a field may carry a conversion (`{desktop!r}`). `key` and
`language` are positional, so a text may name a field `language` (the probe's settings
line does). A text is always formatted, so a text with a field the caller did not pass is
never returned half-filled.

`Message(key, fields)` is what the use cases and the settings hand out instead of a
string: the probe's check details, the steps of a dry run, the problem of a configuration
error. Whoever shows it to a person calls `in_language(language)`. A key the catalogue
does not hold is refused when the message is made, so a typo fails where it is written.

`missing_translations(catalogue=MESSAGES)` returns every `(key, language)` pair whose text
is absent or blank, sorted by key and then in `Language` order. For the shipped catalogue
the answer is an empty list, and a test holds it there.

Logs are not in the catalogue: the operator reads the journal in English whatever
language the owner reads.

## Invariants

- Every key has a non-blank text in every `Language`.
- Every translation of a key names the same set of fields, so a field cannot be missing
  in one language only.
- No English text contains a Cyrillic letter, and every Russian text contains one: a
  Russian entry copied from English is caught.
- An unknown key and an unfilled field raise `KeyError` naming the key or the field; a
  `Message` with an unknown key is refused when it is made.
- The module performs no I/O and imports nothing outside the standard library.

## API

Module `src/horizon_tracker/domain/messages.py`:

- `Language` - `StrEnum`: `EN = "en"`, `RU = "ru"`; `Language("de")` raises `ValueError`.
- `DEFAULT_LANGUAGE` - `Language.EN`.
- `MESSAGES: Mapping[str, Mapping[Language, str]]` - the catalogue.
- `text(key: str, language: Language, /, **fields: object) -> str` - the filled text.
- `Message(key: str, fields: Mapping[str, object] = {})` - frozen; `in_language(language)
  -> str`. Equal messages hash alike (the hash reads the key only).
- `missing_translations(catalogue=MESSAGES) -> list[tuple[str, Language]]` - the pairs
  without a text.

## Testing

Tests: `tests/unit/domain/test_messages.py`. The functions are inside the mutation gate;
mutmut mutates function bodies only, so the catalogue's data is outside it, and the
render tests in `tests/unit/domain/test_report.py` pin the `report.*` and `reason.*`
texts in both languages.

Scenarios (HT-007 BEAD-03): `tests/acceptance/features/language.feature`.

## Dependencies

Derived from the imports on reindex.

- Depends on: (none)
- Used by: `run-report`, `morning-checkin`, `evening-checkout`, `windowed-run`, `probe`,
  `settings`, `telegram-notifier`, `cli`

## Parent

`domain` - [domain README](../../README.md)
