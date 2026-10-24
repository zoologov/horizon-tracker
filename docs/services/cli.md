# CLI — `horizon`

The command-line entry point and the composition root: it reads the settings
from the environment, builds the adapters (one `httpx.Client`, the Playwright
Horizon client, the isdayoff calendar, the Telegram notifier, the system clock,
the artifact store, the absence store, the bot transport) and hands them to the use
cases. Tests replace the adapter
factory through click's context object and drive the commands with `CliRunner`.

**Source:** `src/horizon_tracker/cli.py`

## Commands

| Command | What it does | Exit code |
|---------|--------------|-----------|
| `horizon checkin [--dry-run] [--force]` | the morning check-in: open the desktop, hold it until Windows logs on, then disconnect | 1 only when the run's report is FAILED; 0 for success and for every deliberate skip |
| `horizon checkout [--dry-run] [--force]` | the evening check-out: log the desktop's Windows session off and confirm it ended | same rule |
| `horizon probe` | check the settings, the portal (the HTML Access client bundles it serves, no login), the calendar, and Chrome (found at `HT_CHROME_PATH`, started headless, its version named) and the absences file under `HT_STATE_DIR`; name today's drawn moments last | 1 if the portal, Chrome or absences check FAILED; an unreachable calendar is DEGRADED and keeps 0 |
| `horizon bot` | answer the owner's absence commands (`/add`, `/list`, `/edit`, `/del`, `/help`) in the chat `TELEGRAM_CHAT_ID` names, by long polling, until stopped; every other chat is ignored. The bot loop and the absence service are specified in their SPECs | 1 on a configuration error; 0 when stopped with Ctrl-C; it does not exit on its own |
| `horizon --version`, `horizon --help` | version; the four commands | 0 |

Each run draws today's moments first: `draw_moments` over today's date (the clock's,
in `HT_TIMEZONE`), the seed and the ranges and durations from the settings gives the
check-in and the check-out moment. The run's own moment opens its window, which lasts
`HT_WINDOW_GRACE_MINUTES` (`window_from`). A run started from the start of its range
(`HT_CHECKIN_RANGE` or `HT_CHECKOUT_RANGE`; the timers fire there) and before its moment
waits for the moment in one sleep and then runs; a run started before its range is
skipped as too early; a run started after its window is skipped as too late. The report
names the drawn moment beside the actual time. The same date and settings draw the same
moments in every command, so the probe, a dry run and both runs of a day agree.

`--force` runs now: no wait for the drawn moment, no window and no calendar (a manual
run from the VPS; the report says the calendar was not asked and names no planned
moment). `--dry-run` prints the plan to stdout and exits 0: it never calls login or any
other Horizon method, sends no Telegram report, sleeps for nothing and prunes nothing.
The two flags combine.

A configuration error is logged on stderr as `configuration error: <VAR>: <problem>`
without the credential's value, and every command exits 1. The log line is English
whatever the language. When `HT_LANGUAGE` names another language, the CLI also prints the
error in it on stderr, below the log line (the catalogue's `config.error` text, which
`HT_LANGUAGE=ru` renders in Russian). An English reader gets the log line once. The Russian line is Russian throughout,
the domain's reason for refusing a range, a session length or a grace included. Only the
variable, the value given and the language codes stay as written. The settings did not
load, so the language is read on its own (`language_from_env`). An unknown `HT_LANGUAGE`
is itself the error and is named in English.

The retry policy is a CLI constant, `RETRY_POLICY`: 3 attempts, 30 s apart, still bounded
by the window.

Before a run that is not a dry run, the CLI removes screenshots older than 14 days
from `HT_ARTIFACTS_DIR`. This is best-effort: an `OSError` is logged as
`artifact prune failed, the run goes on: <Type>` and the run goes on. A dry run and
the probe delete nothing.

The use cases, the probe and the dry run are specified in
`docs/domains/application/features/*/SPEC.md`; the settings in
`docs/domains/infrastructure/features/settings/SPEC.md`.

## Output

- stdout: only the dry-run plan and the probe lines, in the language `HT_LANGUAGE` names
  (`en` by default, `ru`). Every text comes from the message catalogue
  (`domain/messages.py`); the use cases hand out keys, the CLI translates them. The
  English lines are shown below; `HT_LANGUAGE=ru` renders the same catalogue keys
  (`probe.settings.ok`, `plan.header`, `plan.steps`, …) in Russian. A probe line's
  check name and status come from the check itself (`Check.label`, `Check.status_label`).
  Identifiers stay as they are in both languages: the run kind (`checkin`), the decision (`run`,
  `skip_late`, …) and a failure reason (`portal_unreachable`). `horizon --help` is
  click's and stays English.
- stderr: logging at INFO on the `horizon_tracker` logger, always in English; under
  systemd the journal captures it, so there is no log file and no rotation code.

### `horizon probe`

The probe never logs in. It prints one line per check, `<check>: <status> - <detail>`,
after the settings line, and then the day's drawn moments as `schedule: today HH:MM /
HH:MM` (check-in / check-out; the same draw a run makes today, so it can be compared on
the VPS without a login):

| Line | `ok` | Otherwise |
|------|------|-----------|
| `settings:` | `ok - portal <HORIZON_URL>, desktop '<HORIZON_DESKTOP>', check-in <HT_CHECKIN_RANGE>, check-out <HT_CHECKOUT_RANGE>, <zone>, language <HT_LANGUAGE>`; no credential and no seed is named | no probe lines; `configuration error: ...` on stderr, exit 1 |
| `portal:` | `ok - client bundles: <file names>` | `failed - no answer: portal_unreachable` (no answer, or a status other than 200) or `failed - no answer: unexpected` (no bundle named) |
| `calendar:` | `ok - isdayoff.ru: <date> is a working day` or `... is a day off` | `degraded - isdayoff.ru did not answer for <date>; runs fall back to the Mon-Fri rule` |
| `chrome:` | `ok - Chrome <version> started from <path>` | `failed - not found at <path>` (nothing is started) or `failed - found at <path> but did not start: unexpected` |
| `absences:` | `ok - none (<path>)`, `ok - <n> current or upcoming[, <m> finished], none ahead (<path>)` or `ok - <n> current or upcoming[, <m> finished], next: vacation 03.11–14.11 (<path>)` | `failed - <path>: <reason>`, exit 1: the file cannot be read or is not the store's layout (`<reason>` is the store's technical English, e.g. `not valid JSON: ...`) |
| `schedule:` | `today <check-in HH:MM> / <check-out HH:MM>`, no status: information, never a failure | — |

The probe reads no portal version: the portal is asked for the client bundles it
serves and Chrome for the version it reports once started.

The `absences:` line reads `HT_STATE_DIR/absences.json` once and never writes it. `<n>`
counts the absences whose last day is today or later, the ones `/list` names, and
`, <m> finished` follows when the file also holds absences that are over. `next:` names the
earliest absence that starts after today, its kind as the notice words it (`vacation`,
`sick leave`, `day off taken`) and its days without the year. An absence under way is
counted and never named as next. A missing file is `none`. In Russian the line reads
`отсутствия: в порядке - текущих и предстоящих: 2, ближайшее: отпуск 03.11–14.11 (<path>)`.

### `horizon bot`

`horizon bot` serves the bot chat named by `TELEGRAM_CHAT_ID` until it is stopped. On the
host it runs as `horizon-bot.service`, which is the only caller of the bot's `getUpdates`:
a second `horizon bot` started while the service runs makes Telegram refuse one of the two
with status 409. Stop the service before running the command by hand
(`docs/guides/deployment.md`, section 6.5). It prints nothing to stdout. Its log lines go
to stderr in English:

- `bot started: answering one chat, absences in <HT_STATE_DIR>/absences.json`;
- `ignored update <n> from chat <id>: not the owner's` for any other chat, whose message
  gets no reply and whose text is never logged;
- `update <n> could not be handled` with a traceback, after which the owner gets
  `Something went wrong; the details are in the journal`;
- `reply to update <n> was not sent: <ErrorType>`;
- `poll failed (<ErrorType>), retrying in <s> s`, after 5 s, then 10, 20, and at most
  every 300 s;
- `bot stopped`, after Ctrl-C or `systemctl stop` (the unit stops it with `SIGINT`), and
  exit 0.

The owner writes one command per message. A reply is in `HT_LANGUAGE`, and every message
from the owner gets exactly one:

| Command | What it does |
|---------|--------------|
| `/add <kind> <from>[-<to>]` | enters an absence under a new id |
| `/list` | names the current and upcoming absences, earliest first, and counts the finished ones |
| `/edit <id> [<kind>] <from>[-<to>]` | gives an absence new days, and a new kind when one is named; the id stays |
| `/del <id>` | deletes an absence; its id is never issued again |
| `/help`, `/start` | the commands, the kinds and the date formats |

- **Kinds**, in any case: `vacation` or `отпуск`; `sick`, `sick_leave` or `больничный`;
  `dayoff`, `day_off` or `отгул`.
- **Dates**: `03.11`, `03.11.2026` or `2026-11-03`. A range is two dates joined by a dash
  (`03.11-14.11`) or written as two words (`2026-11-03 2026-11-14`). One date is one day.
- **A date without a year** is placed near today: the end of a range is its next
  occurrence on or after today, and the start is the latest occurrence on or before that
  end. On 24.10, `23.10-27.10` is a sick leave that began yesterday (entered before the
  check-in range begins; later, the rule below applies), and `28.12-09.01` ends in the next
  year.

A session in English, on 24.10.2026:

```text
/add vacation 03.11-14.11
Absence 1 entered: vacation from 03.11.2026 to 14.11.2026
/add dayoff 20.11
Absence 2 entered: day off on 20.11.2026
/list
Current and upcoming absences: 2
Absence 1: vacation from 03.11.2026 to 14.11.2026
Absence 2: day off on 20.11.2026
/edit 1 05.11-16.11
Absence 1 changed: vacation from 05.11.2026 to 16.11.2026
/del 2
Absence 2 deleted: day off on 20.11.2026
/add vacation 10.11-12.11
These days overlap absence 1; change or delete it first
/add sick 31.02
No such day '31.02' in the calendar
```

The same session with `HT_LANGUAGE=ru`:

```text
/add отпуск 03.11-14.11
Отсутствие 1 внесено: отпуск, дни 03.11.2026–14.11.2026
/add отгул 20.11
Отсутствие 2 внесено: отгул, день 20.11.2026
/list
Текущих и предстоящих отсутствий: 2
Отсутствие 1: отпуск, дни 03.11.2026–14.11.2026
Отсутствие 2: отгул, день 20.11.2026
```

A reply always gives the days with the year, so a date typed without one is read back in
full. When the file holds finished absences, `/list` ends with
`Finished absences, not listed: <m>`, and a file holding only finished ones answers
`No current or upcoming absences` above that line. An empty file answers
`No absences entered`. Two absences never share a day: an `/add` or `/edit` that would
make them is refused, naming the absence in the way. An unknown id is answered
`No absence <id>; /list shows the ones entered`.

**An absence for today after the morning range began.** From the start of today's
`HT_CHECKIN_RANGE`, the morning run may already have checked in. An `/add` or `/edit` whose
days cover today then starts the absence tomorrow, and the reply has a second line:
`Today's check-in range began at 07:30, so an absence starts tomorrow at the earliest;
this evening's check-out runs as usual`. An absence that would have ended today is not
entered, and that line is the whole reply. An `/edit` of an absence that already covers
today keeps today, because that morning was already skipped for it.

### `horizon checkin --dry-run`, `horizon checkout --dry-run`

With `HT_TIMEZONE=Europe/Berlin` as an example:

```text
dry run: checkin at 2026-10-21 07:30:00 CEST
would run now: yes (run)
would wait until: 07:41
calendar: isdayoff.ru
schedule: today 07:41 / 16:43
steps of one attempt:
  1. log in to the Horizon portal
  ...
```

`would run now` is the decision the run loop would take on its first attempt: now, or,
when the run would first wait for its drawn moment, at that moment. `would wait until`
appears only then. Under `--force` the parenthesis reads
`(run, forced: window and calendar ignored)` and nothing is waited for. The calendar
line is `isdayoff.ru`, `isdayoff.ru unreachable, Mon-Fri rule`, `not asked (forced)` or,
on a day an absence covers, `not asked (an absence covers today)` beside
`would run now: no (skip_absent)`.
`schedule:` names the day's drawn check-in and check-out moments, as the probe does.
The steps are the use case's own list followed by the loop's: the absence check, the wait
for the moment, the retries and the one Telegram report, which the check-out names as
`send one report to Telegram, unless the day is skipped: the morning reports it`.

## Environment

| Variable | Meaning |
|----------|---------|
| `HORIZON_URL` | the HTML Access portal, e.g. `https://horizon.example.com/portal/webclient/` (required) |
| `HORIZON_USERNAME`, `HORIZON_PASSWORD` | the AD account (secret; masked in every repr and log) |
| `HORIZON_DESKTOP` | the launch item's title, e.g. `DEV desktop` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | the Telegram bot's token, and the chat its reports go to and the only chat `horizon bot` answers (secret) |
| `HT_TIMEZONE` | the IANA zone of every wall time: the ranges, the drawn moments and the report, e.g. `Europe/Berlin`; the code's default is `Europe/Moscow` |
| `HT_CHECKIN_RANGE` | `HH:MM-HH:MM` the check-in moment is drawn from, default `07:30-08:10`; the check-in timer fires at its start |
| `HT_CHECKOUT_RANGE` | `HH:MM-HH:MM` the check-out moment is clipped to, default `16:30-17:10`; the check-out timer fires at its start |
| `HT_SESSION_LENGTH_MINUTES` | the check-out moment is at least this long after the check-in one when the range allows, default `540` |
| `HT_SESSION_EXTRA_MAX_MINUTES` | up to this many minutes drawn on top of the session, default `10` |
| `HT_WINDOW_GRACE_MINUTES` | how long a run's window stays open from its moment, default `5` |
| `HT_JITTER_SEED` | optional seed of the daily draw (masked in every repr, never printed); unset or blank: `HORIZON_USERNAME` in UTF-8 |
| `HT_HOLD_SECONDS` | how long the opened desktop is held in the morning, default `120` |
| `HT_CHROME_PATH` | the Chrome binary, `/usr/bin/google-chrome` on the VPS |
| `HT_ARTIFACTS_DIR` | where screenshots are written and pruned (older than 14 days) |
| `HT_STATE_DIR` | where the service keeps what outlives a run, default `/opt/horizon-tracker/state`: the absences in `absences.json` (0600, written atomically; a missing directory is created 0700 by the first write). `horizon bot` writes the file; the runs and the probe read it |
| `HT_LANGUAGE` | the language of the notification, the probe, the dry run and a configuration error: `en` (default) or `ru`; anything else is refused at start with `configuration error: HT_LANGUAGE: expected one of en, ru, got '<value>'`. The logs stay English |

`HT_CHECKIN_WINDOW` and `HT_CHECKOUT_WINDOW` are retired: either one present in the
environment, even blank, makes every command exit 1 with
`configuration error: HT_CHECKIN_WINDOW: ...` naming its successors.

## Source

`src/horizon_tracker/cli.py`

The composition root builds the notifier with `build_notifier(settings, http)`: a
`TelegramNotifier` in `settings.language`, and a token the adapter refuses becomes a
configuration error for `TELEGRAM_BOT_TOKEN`. The acceptance suite builds its notifier
through the same function.

`horizon checkin` and `horizon checkout` build their `WindowedRun` with
`absences=adapters.absences` and `notify_day_skips` `True` for the check-in, `False` for
the check-out: a day skipped for an absence or by the calendar is reported once, by the
morning run, and the evening run logs it and sends nothing. `TOO_EARLY`,
`WINDOW_MISSED` and every run that made an attempt still reach the chat in the evening.
An unreadable absences file is logged by type and the run goes on as if none were entered.

`open_adapters` also builds the absence store, `JsonAbsenceStore(settings.absences_file)`,
and the bot transport, `build_bot_transport(settings, http)`: a `TelegramBotTransport` over
the same HTTP client, its long poll setting its own longer timeout per request, and a
refused token is the same configuration error. Every command gets both in `Adapters`
(`absences`, `bot`), so the store is built in one place: the probe reads it, and `horizon
bot` builds `AbsenceService(adapters.absences, adapters.clock, settings.checkin_range)` and
`BotLoop(adapters.bot, service, settings.telegram_chat_id, settings.language,
adapters.clock)` and runs `run_forever()`. A `KeyboardInterrupt` ends it with `bot
stopped` in the log and exit 0. The acceptance suite builds its bot transport through
`build_bot_transport` too.

## Testing

Tests: `tests/unit/test_cli.py`. The acceptance scenarios drive the commands through
`CliRunner` (`tests/support/cli_world.py`). The language of the output, of the
notification and of a configuration error is held by
`tests/acceptance/features/language.feature`.

## Dependencies

- Depends on: `application`, `infrastructure`, and from the domain `messages` (the CLI
  renders every message in `HT_LANGUAGE`), `schedule`, `ports`, `run-report` and
  `working-day-calendar`
- Used by: the systemd timers on the VPS, and `horizon-bot.service`
- External contract (declared in `.beadloom/_graph/landscape.yml`): consumes `systemd:units`
  from [`vps-host`](../domains/external/vps-host/SPEC.md)
