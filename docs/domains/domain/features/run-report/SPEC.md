# Run report

The run report as a value of closed vocabularies, and the notification text rendered
from it in the language the caller names. No field can carry a password.

## Source

`src/horizon_tracker/domain/report.py`

## Specification

### Purpose

Every run ends in exactly one report to the owner. The report must say what happened,
when, on whose working-day verdict and why, and it must be impossible for it to carry
a credential. A value with no free-text field gives both properties by construction.

### How it works

`RunReport` holds the run kind, an `Outcome`, an aware `datetime`, the `VerdictSource`
(or `None` for a run that asks no calendar: a `--force` run or an absence skip), a
`Reason`, an optional screenshot `Path`, `planned_at`, the drawn moment the run was due
at, and `absence`, the [absence](../absence/SPEC.md) a skip was for. `planned_at`
is set for every scheduled run, whether or not it reached its window: a skip on a day
off or a run started after its window names its moment as well. Only a `--force` run
leaves it `None`. `__post_init__` checks the type of every field and refuses a value
of the wrong type with `TypeError`, rather than trusting the caller.

`render(report, language)` builds the message text from the message catalogue
([messages](../messages/SPEC.md)) in `language`. A failure in English, with
`HT_TIMEZONE=Europe/Berlin` as an example zone:

```text
Check-in failed
Time: 21.10.2026 07:39:12 CEST, planned for 07:38
Production calendar: isdayoff.ru
Reason: the desktop did not open
```

`HT_LANGUAGE=ru` renders the same four catalogue keys in Russian. Only the words
change; the times and their format stay as they are. The `ru` text of the headline
above, for instance, is `Вход не удался`; every `ru` text holds Cyrillic, every `en`
text none, and the catalogue's own test keeps it so.

The first line is the run kind and the outcome, one catalogue key per pair
(`report.checkin.failed`). The time line carries the actual time with the abbreviation
of the configured zone (`CEST` for `Europe/Berlin` in summer, for example), followed by the planned
moment (`planned for HH:MM` in English, the `report.time_planned` key) when `planned_at` is set. The calendar
line names the source, one catalogue key per source (`report.calendar.<source>`):
`Production calendar: isdayoff.ru`, `Production calendar: unavailable, the Mon–Fri rule
decided`, or `Production calendar: not asked, manual run --force` for a `--force` run.
The reason line is present only when there is a reason. The formatted times and the days
of an absence are the only values the report puts into the text; every word comes from
the catalogue.

A **day-level skip** (`RunReport.is_day_level_skip`) is a skip for the day itself: the
outcome is `SKIPPED` and the reason is `NON_WORKING_DAY` or an absence reason. Its notice
has no time line, since nothing was going to run that day; `planned_at` stays in the
report. A skipped holiday in Russian:

```text
Вход пропущен
Производственный календарь: isdayoff.ru
Причина: выходной
```

An absence skip has no calendar line either, because the calendar was not asked. Its
reason line carries the absence's first and last day, `dd.mm` without the year, joined by
an en dash (one day when both are the same):

```text
Check-in skipped
Reason: vacation (03.11–14.11)
``` The screenshot never appears in
the text: the notifier attaches it beside the text. A failure carries the screenshot of
the step that failed; a success carries the use case's photo of the step it completed
(the opened desktop, the launch list without the session). Either may be `None`, and
the report then goes out as text.

## Invariants

- No field holds free text: the outcome and the reason come from closed vocabularies,
  so a rendered message cannot quote an exception or a password.
- `RunReport.at` carries a time zone; a naive `datetime` raises `ValueError`.
- A reason is present exactly when the outcome is not `SUCCEEDED`; any other
  combination raises `ValueError`.
- An absence is present exactly when the reason is an absence reason, and then the reason
  names the absence's kind, the outcome is `SKIPPED` and `verdict_source` is `None`; any
  other combination raises `ValueError`.
- Every `Reason` has a phrase in every language; an exception message is never a reason.
- An English notification holds no Cyrillic letter, for every kind, outcome, source,
  reason and planned moment.

## API

Module `src/horizon_tracker/domain/report.py`:

- `Outcome` — `StrEnum`: `SUCCEEDED`, `FAILED`, `SKIPPED`.
- `Reason` — `StrEnum`: `NON_WORKING_DAY`, `TOO_EARLY`, `WINDOW_MISSED`,
  `ALREADY_LOGGED_OFF`, `PORTAL_UNREACHABLE`, `LOGIN_REJECTED`, `DESKTOP_NOT_FOUND`,
  `DESKTOP_DID_NOT_OPEN`, `LOGOFF_NOT_CONFIRMED`, `UNEXPECTED`, and the absence reasons
  `ON_VACATION`, `ON_SICK_LEAVE`, `ON_DAY_OFF`.
- `ABSENCE_REASONS` — read-only mapping `AbsenceKind -> Reason`;
  `absence_reason(kind: AbsenceKind) -> Reason` reads it.
- `absence_span(absence: Absence) -> str` — an absence's days without a year, as the
  reason line gives them: `05.11` for one day, `03.11–14.11` (an en dash) for a range.
  The probe names the next absence with it.
- `RunReport(kind, outcome, at, verdict_source, reason=None, screenshot=None,
  planned_at=None, absence=None)` — frozen; validated at construction as described above.
  `is_day_level_skip: bool` is the property the time line and the morning-only notice
  are decided by.
  `planned_at: time | None` is the drawn moment the run was due at, local wall time,
  set whether or not the run reached its window. It is `None` for a `--force` run. A
  value of any other type is refused with `TypeError`.
- `render(report: RunReport, language: Language) -> str` — the notification text in
  `language`; there is no default, so every caller names the language it renders in.
  When `planned_at` is set, the time line carries it beside the actual time:
  `Time: 20.10.2026 07:56:12 CEST, planned for 07:43`.

## Testing

Tests: `tests/unit/domain/test_report.py`, each text test in both languages. The module
is inside the mutation gate.

Scenarios:

- `tests/acceptance/features/production_calendar.feature`:
  - `A skipped non-working day is reported without a time line`
  - `A day the calendar marks as a holiday is skipped with a notice`
  - `When the calendar is unreachable the weekday rule decides and says so`
- `tests/acceptance/features/notifications.feature`:
  - `A failed run sends the reason and a screenshot`
  - `A notification never contains the password`
- `tests/acceptance/features/morning_checkin.feature`:
  - `Morning check-in reports success with the recorded time`
- `tests/acceptance/features/language.feature`:
  - `A notification is rendered in the configured language`
  - `The default language is English`

## Dependencies

Derived from the imports on reindex.

- Depends on: `absence`, `messages`, `schedule`, `working-day-calendar`
- Used by: `cli`, `evening-checkout`, `horizon-playwright-client`, `morning-checkin`, `ports`, `probe`, `telegram-notifier`, `windowed-run`

## Parent

`domain` — [domain README](../../README.md)
