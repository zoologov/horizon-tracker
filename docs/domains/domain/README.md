# Domain

Pure decision cores of horizon-tracker. Nothing here performs I/O: no browser,
no network, no wall clock other than the one passed in. Every verdict is
deterministic and unit-tested first.

## Source

`src/horizon_tracker/domain/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `schedule.py` | when a run may go ahead: the daily draw `draw_moments(day, seed, checkin_range, session_length, extra_max, checkout_range)` → `DailyMoments(check_in, check_out)` over `TimeRange`s (hmac-sha256 of the date, so the same date and seed always give the same pair), `window_from(moment, grace)` → the run's `Window`, and the decision for one attempt: `RunKind` (CHECKIN, CHECKOUT), `RetryPolicy`, `FIRST_ATTEMPT` (1, the number the run loop counts from), `decide(now, window, verdict, attempt, policy)` → `Decision` (RUN, RETRY, SKIP_EARLY, SKIP_LATE, SKIP_NON_WORKING_DAY, GIVE_UP, and SKIP_ABSENT, which the run loop decides from the absences and `decide` never answers); `ScheduleError` (a refusal a configured value can reach, its `reason` a `Message`) |
| `calendar.py` | the working-day verdict: `WorkingDayVerdict(is_working, source)` with `VerdictSource` CALENDAR or WEEKDAY_FALLBACK, `weekday_rule(day)`, `resolve(calendar_answer, day)` |
| `session.py` | the states a Horizon session moves through and the two success rules: `SessionState` (NO_SESSION, CONNECTED, DISCONNECTED), `DesktopStatus`, `checkin_succeeded(while_open, after_disconnect)`, `checkout_succeeded(before, after)` |
| `report.py` | the record of one run and its notification text: `RunReport` (with `planned_at`, the drawn moment the run was due at), `Outcome`, `Reason`, `render(report, language)`, `absence_span(absence)` (an absence's days as the notice and the probe name them); the report has no password field by construction |
| `messages.py` | the message catalogue: `Language` (EN, RU), `DEFAULT_LANGUAGE` (EN, Russian being the other language), `MESSAGES` (every text a person reads, keyed, in both languages), `text(key, language, /, **fields)`, `Message(key, fields)` (a text with no language yet, its fields read-only; `in_language(language)`, which reads a field that is a message in the same language), `missing_translations()` |
| `ports.py` | the Protocols the adapters implement: `HorizonClient` (the run's `login`, `desktop_status`, `open_desktop`, `capture_open_desktop`, `disconnect`, `log_off`, where `open_desktop` returns `None`, `capture_open_desktop` and `log_off` answer with a screenshot path or `None`, and the probe's `client_bundles()` and `browser_version()`), `WorkingDayCalendar`, `Notifier` (`send(report)`, the screenshot travels inside the report), `Clock`, `ArtifactStore`, `AbsenceStore` (`load() -> AbsenceBook`, `save(book)`), `BotTransport` (`poll(offset)`, `reply(chat_id, text)`); `HorizonClientError(reason, screenshot)`, `AbsenceStoreError(path, detail)`, `BotTransportError`; the value `IncomingMessage(update_id, chat_id, text)` |
| `absence.py` | the owner's absences and the decisions over a set of them: `AbsenceKind` (VACATION, SICK_LEAVE, DAY_OFF), `Absence(id, kind, first_day, last_day)` (a range of whole days, both ends included; `covers(day)`), `FIRST_ID`, `covering(absences, day)`, `next_after(absences, day)`, `allocate_id(absences, *, last_issued=0)`, `overlaps(first, second)`; `AbsenceBook(absences, last_issued)`, the absences with the highest id ever issued, as the store keeps them (`of(absences)`, `next_id()`) |
| `bot_commands.py` | the bot's text command parser: `parse(text, today)` → `Add(kind, first_day, last_day)`, `List`, `Delete(id)`, `Edit(id, kind, first_day, last_day)`, `Help` (the union `Command`) or `CommandError(problem)`, its problem a `bot.error.*` `Message`; `KIND_WORDS` (the kind words in both languages); dates `dd.mm`, `dd.mm.yyyy`, `yyyy-mm-dd`, a yearless date placed from today |

The domain picks no language: `render(report, language)` and `Message.in_language`
take it as an argument, and the settings read it from `HT_LANGUAGE`. The use cases and the
schedule hand out `Message` values, and the CLI and the notifier render them.

The whole package is the scope of the mutation gate (`scripts/mutation.sh`). The
catalogue's data yields no mutants, because mutmut mutates function bodies only.

## Features

Each feature has a `SPEC.md` (Purpose, How it works, Invariants, API, Testing):

- **[Schedule](features/schedule/SPEC.md)** — `schedule.py`: the day's drawn check-in and
  check-out moments, the window that opens at a moment, and run, retry or skip, given
  the window, the working-day verdict and the retry policy.
- **[Working-day calendar](features/working-day-calendar/SPEC.md)** — `calendar.py`: the
  calendar's answer first, Monday to Friday as the fallback, and the source named.
- **[Session state](features/session-state/SPEC.md)** — `session.py`: the three session
  states and the check-in and check-out success rules.
- **[Run report](features/run-report/SPEC.md)** — `report.py`: the report value of
  closed vocabularies and the notification text in a language.
- **[Messages](features/messages/SPEC.md)** — `messages.py`: the catalogue of every text
  a person reads, in English and Russian, and the check that no key misses a language.
- **[Ports](features/ports/SPEC.md)** — `ports.py`: the seven contracts the adapters
  implement, including the two-method probe contract of `HorizonClient`, the absence
  store and the bot transport.
- **[Absence](features/absence/SPEC.md)** — `absence.py`: the owner's absences as day
  ranges, which one covers a day, which one comes next, the id a new one gets and whether
  two share a day, and the book the store keeps them in.
- **[Bot commands](features/bot-commands/SPEC.md)** — `bot_commands.py`: one message
  from the owner into an absence command with its kind, id and days, or a refusal as a
  catalogue message; a date without a year placed from today.

## Dependencies

- Depends on: (none) — the domain imports nothing from the other layers
- Used by: `application`, `infrastructure`
