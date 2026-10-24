# RFC: HT-012 — Absences through the bot, and one notice for a skipped day

> **Status:** Approved
> **Created:** 2026-10-24

---

## Overview

The service gains a second kind of day it does not work on: an **absence** the owner
enters through the Telegram bot (a vacation, a sick leave, a day off), each a range of
dates from one day up. A new long-running process, `horizon bot`, polls the Bot API,
accepts text commands from the owner's chat only, and keeps the absences in a JSON file in
the service's state directory on the host. The morning and evening runs read that file
through a port before they ask the calendar; a day inside an absence is skipped with the
kind named. On any day-level skip (a calendar day off or an absence) only the morning run
notifies; the notice carries no time line, and the calendar line of every report is
renamed.

## Motivation

### Problem
See the PRD: an unintended logon during leave, and two uninformative weekend notices.

### Solution
A pure domain of absences and bot commands, two new ports (the store, the bot transport),
two adapters (a JSON file, Telegram long polling), one new use case pair (the absence
service and the bot loop), the verdict in `WindowedRun` extended, a `horizon bot` command
and a `horizon-bot.service` unit installed by the deploy.

## Technical Context

### Constraints
- Python 3.12, `click`, `httpx`; tests pytest; ruff; mypy --strict (STACK section).
- Clean architecture: `cli` → `infrastructure` → `application` → `domain`; ports are
  Protocols in `domain/ports.py`; `domain` reads no clock, network or file.
- The pure domain is inside the mutation gate (`domain/`), so every decision below that
  lands in `domain` arrives with tests that kill its mutants.
- Secrets: the bot token sits in every Bot API URL and must not reach the journal; the
  existing notifier's redaction is reused, not re-invented. From CI and the sandbox the
  live Bot API is never called: `httpx.MockTransport` only.
- One Telegram bot, one poller: `getUpdates` may be held by one process at a time, and
  the timers only send, so the bot service is the one poller. No webhook.
- The host: a single service user `horizon`, home `/opt/horizon-tracker`; the deploy
  rewrites `.env` and the units on every release; what must survive a deploy lives outside
  the checkout.

### Affected Areas
Derived below. The deploy directory has no graph node (the derivation says so), so its
rows are authored from the deploy guide and marked as such.

## Axes

Derived, never authored. Three runs of `beadloom impact` (Explore, 2026-10-24), each with
seed `none` under rule `reaches-an-effect-sink`, so every axis is unresolved rather than
empty; the branches rows are collapsed to one per node. The nodes this work item creates
cannot appear in a derivation over the tree before it exists; they are listed after the
table and declared in the graph by the beads that create them.

> **Derived by:** `beadloom impact resolve` (run 1, the working-day verdict), `beadloom impact src/horizon_tracker/infrastructure/telegram.py` (run 2), `beadloom impact deploy/` (run 3), over `src/horizon_tracker` and `deploy`
> **Seed:** none in all three runs
> **Unresolved:** run 1: 1 no-seed; run 2: 2 name-defined-more-than-once, 1 no-seed, 4 unresolved-terminator-name; run 3: 1 no-seed, 1 sweep-narrower-than-the-project, no node for `deploy/`

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved in all three runs | — | no | nothing the derivation could see is written through; the new store is the first writer and is created here |
| callers | windowed-run | `src/horizon_tracker/application/windowed_run.py:175` (run 1), `:125` (run 2) | none | yes | the verdict gains the absence check before the calendar, and the rule "a day-level skip notifies in the morning only" |
| branches | working-day-calendar | `resolve`, `weekday_rule` | none | no | the calendar's own rules do not change; the absence verdict is a separate decision that runs first |
| branches | telegram-notifier | `send`, `_call`, `_redact`, `_mask_httpx_request_lines`, `filter`, `_description`, `__init__` | none | yes | the token redaction and the `_call` shape are shared with the new transport: the redaction moves to a module both adapters import |
| callers | ports | `src/horizon_tracker/domain/ports.py:26` | none | yes | two new Protocols: `AbsenceStore`, `BotTransport` |
| callers | settings | `src/horizon_tracker/infrastructure/config.py:92` | none | yes | `state_dir` (`HT_STATE_DIR`, default `/opt/horizon-tracker/state`) |
| callers | schedule | `src/horizon_tracker/domain/schedule.py:48` | none | yes | ruled out at first (the draw does not change); BEAD-05 added `Decision.SKIP_ABSENT`, which `decide()` never returns, so that the dry run prints the absence decision — one enum member, no change to the draw |
| — (authored) | run-report | `render`, `_time_line` (HT-011's derivation, run over `render`) | none | yes | no time line for a day-level skip; the calendar line renamed; the absence reason with its span |
| — (authored) | messages | the catalogue (HT-011's derivation) | none | yes | new keys `report.reason.vacation/sick_leave/day_off`, `report.calendar.*` renamed, `bot.*` replies |
| — (authored) | probe | `probe.py` (the run-report derivation's caller list) | none | yes | a fifth check line `absences:` |
| — (authored) | cli | `cli.py` | none | yes | `horizon bot`; the notify-skips flag per command |
| — (authored) | telegram-bot-api | `docs/domains/external/telegram-bot-api/SPEC.md` (HT-013's node) | none | yes | gains the contracts `http:telegram-getUpdates` and `http:telegram-sendMessage` towards the new `telegram-bot` node |
| — (authored) | owner-chat | `docs/domains/external/owner-chat/SPEC.md` (HT-013's node) | none | yes | gains `command:bot-text` towards `bot-commands`; the notice it reads changes |
| — (authored) | vps-host | `docs/domains/external/vps-host/SPEC.md` (HT-013's node) | none | yes | gains `file:absences` towards `absence-store` and the new unit under `systemd:units` |
| — (authored) | deploy (no node) | `deploy/bootstrap.sh`, `deploy/*.service`, `.github/workflows/release.yml:457-463`, `tests/unit/deploy/*` | the whole directory: no Python, no node | yes | a new unit installed and enabled, the state directory created |

New nodes this work item declares in `.beadloom/_graph/` (each with a SPEC under
`docs/domains/`): `absence` (domain), `bot-commands` (domain), `absence-store`
(infrastructure), `telegram-bot` (infrastructure), `absence-service` (application),
`bot-loop` (application).

Kept axes name more than one node: the full flow carries the change.

## Proposed Solution

### Approach

**Domain (pure, mutation-gated).**

- `domain/absence.py` — `AbsenceKind` (`VACATION`, `SICK_LEAVE`, `DAY_OFF`);
  `Absence(id: int, kind, first_day: date, last_day: date)` frozen, refuses
  `last_day < first_day`; `covering(absences, day) -> Absence | None` (the first match by
  id); `next_after(absences, day)`; `allocate_id(absences) -> int` (max + 1, never
  reused); `overlaps(a, b)`. Nothing here knows the file or the clock.
- `domain/bot_commands.py` — `parse(text: str, today: date) -> Command | CommandError`.
  Commands: `/add <kind> <from>[-<to>]`, `/list`, `/del <id>`, `/edit <id> [<kind>]
  <from>[-<to>]`, `/help` (and `/start` = help). Dates `dd.mm`, `dd.mm.yyyy`,
  `yyyy-mm-dd`; a range as `a-b` or `a b`; a single date is a one-day range; `dd.mm`
  without a year is the next occurrence from `today` (this year, or next year when it
  already passed). Kinds in both languages and short forms: `vacation|отпуск`,
  `sick|sick_leave|больничный`, `dayoff|day_off|отгул`. Errors are `Message`s from the
  catalogue (`bot.error.*`) so the reply is rendered in `HT_LANGUAGE`. The parser is a
  pure function and lives in the mutation gate.
- `domain/report.py` — `Reason` gains `ON_VACATION`, `ON_SICK_LEAVE`, `ON_DAY_OFF`;
  `RunReport` gains `absence: Absence | None` (set with those reasons only, validated in
  `__post_init__`). `render`: no time line when the outcome is `SKIPPED` and the reason
  is `NON_WORKING_DAY` or one of the absence reasons (a *day-level skip*); the calendar
  line becomes `Production calendar: isdayoff.ru` / `Production calendar: unavailable,
  the Mon–Fri rule decided` (`ru`: `Производственный календарь: isdayoff.ru` /
  `Производственный календарь: недоступен, решило правило Пн–Пт`); an absence skip has
  `verdict_source=None` (the calendar was not asked) and so no calendar line, and its
  reason line carries the span: `Reason: vacation (03.11–14.11)` / `Причина: отпуск
  (03.11–14.11)`.
- `domain/messages.py` — the keys above and the `bot.*` replies (added, listed, deleted,
  edited, not found, help, the errors), both languages; the completeness test holds.
- `domain/ports.py` — `AbsenceStore` (`load() -> AbsenceBook`, `save(book: AbsenceBook) -> None`,
  where `AbsenceBook(absences: tuple[Absence, ...], last_issued: int)` is a frozen domain
  value: BEAD-01 found that "max + 1 over the absences held" would re-issue a deleted top
  id, so the book carries the highest id ever issued and `allocate_id(absences,
  last_issued=...)` takes it; the JSON file holds `{"last_issued": N, "absences": [...]}`)
  and `BotTransport`
  (`poll(offset: int | None) -> tuple[IncomingMessage, ...]`, `reply(chat_id: str, text:
  str) -> None`); `IncomingMessage(update_id: int, chat_id: str, text: str)` frozen.

**Application.**

- `application/windowed_run.py` — before the calendar, `covering(store.load(), today)`;
  a hit decides `SKIP_ABSENT` with the absence and no calendar call (the store is read
  once per run; a store that raises is logged and treated as empty, so a broken file never
  stops a working day — and that is reported by `probe`). `WindowedRun` gains
  `notify_day_skips: bool` (default `True`): when `False`, a day-level skip builds and
  logs its report and does not call the notifier. The other skips (`TOO_EARLY`,
  `WINDOW_MISSED`) always notify: they are anomalies. A forced run ignores absences as it
  ignores the calendar.
- `application/absence_service.py` — `AbsenceService(store)`: `add`, `list`, `delete`,
  `edit`, each returning a `Message` reply; the store is loaded and saved per call.
- `application/bot_loop.py` — `BotLoop(transport, service, owner_chat_id, language,
  clock)`: `run_once(offset) -> int` polls, drops messages from any other chat (logs the
  chat id, never the text), parses, dispatches, replies in `language`, returns the next
  offset; `run_forever()` loops with the transport's long-poll timeout and a backoff on
  transport errors (logged by type). Any exception inside one message's handling becomes
  a `bot.error.internal` reply and the loop goes on.
- `application/probe.py` — a fifth check `absences`: `ok - <n> entered, next: vacation
  03.11–14.11 (<path>)`, `ok - none (<path>)`, `failed - <path>: <reason>` when the
  file cannot be read or parsed.

**Infrastructure.**

- `infrastructure/absence_store.py` — `JsonAbsenceStore(path)`: reads `{"absences":
  [...]}`; a missing file is empty; writes atomically (temp file + `os.replace`), mode
  0600, parent created 0700. ISO dates in the file.
- `infrastructure/telegram.py` — the token redaction (`_redact`, the httpx log filter)
  moves to `infrastructure/telegram_redaction.py` (or stays and is imported; the dev
  decides and records it); `TelegramBotTransport(token, client)` in
  `infrastructure/telegram_bot.py`: `poll` = `getUpdates` with `timeout=30`,
  `allowed_updates=["message"]`, `offset`; `reply` = `sendMessage`. A non-200 or a
  transport error raises `BotTransportError` (type only in the log).
- `infrastructure/config.py` — `state_dir: Path` from `HT_STATE_DIR`, default
  `/opt/horizon-tracker/state`; the absences file is `state_dir / "absences.json"`.

**CLI.** `horizon bot` (runs `BotLoop.run_forever()`; exit 1 on a configuration error as
the others); `horizon checkin` builds its `WindowedRun` with `notify_day_skips=True`,
`horizon checkout` with `False`; both pass the store. `--dry-run` names the absence check
as a step.

**Deploy.** `deploy/horizon-bot.service` (`Type=simple`, `User=horizon`,
`ExecStart=/opt/horizon-tracker/.venv/bin/horizon bot`, `EnvironmentFile=.env`,
`Restart=always`, `RestartSec=10`, `After=network-online.target`); `bootstrap.sh` lists
it among the units and creates `/opt/horizon-tracker/state` (0700, `horizon`);
`release.yml`'s deploy installs the five units, `daemon-reload`, `enable --now
horizon-bot.service`, `try-restart` it on every release, and the summary shows its
status. The contract tests in `tests/unit/deploy/` pin the unit, the bootstrap lines and
the workflow lines.

### Changes

| File / Module | Change |
|---------------|--------|
| `src/horizon_tracker/domain/absence.py` | new: kinds, `Absence`, `covering`, `next_after`, `allocate_id` |
| `src/horizon_tracker/domain/bot_commands.py` | new: the text command parser |
| `src/horizon_tracker/domain/report.py` | reasons, `absence` field, `render` rules |
| `src/horizon_tracker/domain/messages.py` | keys for the reasons, the calendar line, the bot replies |
| `src/horizon_tracker/domain/ports.py` | `AbsenceStore`, `BotTransport`, `IncomingMessage` |
| `src/horizon_tracker/application/windowed_run.py` | absence verdict first; `notify_day_skips` |
| `src/horizon_tracker/application/absence_service.py` | new |
| `src/horizon_tracker/application/bot_loop.py` | new |
| `src/horizon_tracker/application/probe.py` | the `absences` check |
| `src/horizon_tracker/infrastructure/absence_store.py` | new: the JSON file |
| `src/horizon_tracker/infrastructure/telegram_bot.py` | new: long polling + reply |
| `src/horizon_tracker/infrastructure/telegram.py` | redaction shared |
| `src/horizon_tracker/infrastructure/config.py` | `state_dir` |
| `src/horizon_tracker/cli.py` | `horizon bot`; the flag per command; the store wired |
| `deploy/horizon-bot.service`, `deploy/bootstrap.sh`, `.github/workflows/release.yml` | the unit, the state dir, install + enable |
| `tests/**` | unit tests per module; `tests/unit/deploy/*`; the 10 scenarios in `tests/acceptance/features/absences.feature` and `production_calendar.feature` |
| `.beadloom/_graph/*.yml`, `docs/domains/**` | six new nodes and SPECs; the changed SPECs |
| `docs/services/cli.md`, `docs/guides/deployment.md`, `deploy/RUNBOOK.md`, `README.md`, `CHANGELOG.md` | the command, the unit, the variable, the behaviour |

### API Changes

Public surface (the `horizon` command, the environment, the deploy contract):

- new command `horizon bot`; new unit `horizon-bot.service`;
- new optional variable `HT_STATE_DIR` (default `/opt/horizon-tracker/state`);
- the notification text changes: the calendar line, the time line of a day-level skip,
  the new reasons; the evening run sends nothing on a day-level skip;
- `horizon probe` prints one more line (`absences:`); exit codes unchanged.

Minor version: `1.1.0`.

## Alternatives Considered

### Option A: poll `getUpdates` only inside the morning run
No new process. Rejected: a command entered at noon would be read the next morning, and
`/list` could not answer at all.

### Option B: a webhook
Rejected: it needs a public HTTPS endpoint on the host, a certificate and a port; the
long poll needs nothing the host does not already have.

### Option C: absences as lines in `.env`
Rejected: the deploy rewrites `.env`, and editing it needs SSH, which is what the owner
wants to stop doing.

### Option D: inline keyboards
Rejected by the owner: text commands only.

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| The bot process holds `getUpdates` while a developer polls the same bot from a laptop | Low | Medium (409 Conflict, both stall) | documented: one poller; the service is the poller; stop it before polling by hand |
| A corrupt `absences.json` | Low | Medium | the run treats it as empty and logs; `probe` reports it `failed`; the store writes atomically |
| A date without a year read in the wrong year around New Year | Medium | Low | the rule "next occurrence from today" is pinned by tests across the year boundary; the reply echoes the full dates |
| An absence entered for today after the morning run already logged on | Medium | Low | the reply says so when the range starts today and the time is past the check-in range; the evening run still logs off |
| The bot replies to a stranger | Low | High | the chat id filter is the first step of `run_once` and is pinned by a scenario; nothing is replied |
| `Restart=always` loops on a configuration error | Low | Low | `RestartSec=10`; the journal shows the error; `probe` names it |

## Open Questions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Does a weekend day inside an absence report the absence or the calendar? | Decided: the absence (checked first, no calendar call) |
| Q2 | Does `/add` with a range already covered by another absence merge or refuse? | Decided: refuse with the overlapping id named; the owner edits or deletes |
| Q3 | Are the three calendar-skip anomalies (`TOO_EARLY`, `WINDOW_MISSED`) silenced in the evening too? | Decided: no, they always notify |
