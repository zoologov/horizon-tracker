# PRD: HT-012 — Absences through the bot, and one notice for a skipped day

> **Status:** Approved
> **Created:** 2026-10-24

---

## Problem

The service decides whether to check in by the production calendar alone. A vacation, a
sick day or a day off is a working day to the calendar, so on such a day the service logs
on to the desktop as usual and records an attendance the owner did not intend. Today the
only way to stop it is to disable the timers by hand over SSH, and to remember to enable
them again.

The notification of a day skipped by the calendar (2026-10-24, a Saturday) also reads
badly:

```
Вход пропущен
Время: 24.10.2026 07:30:01 MSK, назначено на 07:40
Календарь: производственный календарь isdayoff.ru
Причина: выходной
```

The time line reports when the timer fired and a drawn moment for a day on which nothing
was going to run, and the calendar line names its source in a roundabout way. The evening
run then sends the same notice a second time.

## Impact

The owner. An unintended logon during leave is the one outcome the service exists to
avoid producing by mistake; the noise of two uninformative notices on every weekend is
the thing that makes the owner stop reading them.

## Goals

- [ ] The owner enters, lists, edits and deletes **absences** — a vacation, a sick leave or
      a day off, each a range from one day to many — with text commands to the bot from
      their own chat, and the bot answers in `HT_LANGUAGE`.
- [ ] On a day inside an absence the morning run skips, names the kind of absence as the
      reason, and notifies once; the evening run skips silently.
- [ ] On a day the calendar marks non-working the morning run notifies once and the evening
      run skips silently; the notice carries no time line.
- [ ] The calendar line of every report names its source as
      `Production calendar: isdayoff.ru` / `Производственный календарь: isdayoff.ru`, and
      for the weekday fallback `Production calendar: unavailable, the Mon–Fri rule decided` /
      `Производственный календарь: недоступен, решило правило Пн–Пт`.
- [ ] Absences survive a deploy, a restart and a reboot of the host.
- [ ] Only the configured chat (`TELEGRAM_CHAT_ID`) is served; a message from anyone else is
      ignored and logged without its content.
- [ ] The bot runs as its own systemd service, installed and enabled by the deploy; its
      failure never touches the timers, and a timer run never waits on it.

## Non-goals

- Inline keyboards, menus or a conversation state machine: text commands only.
- Several users or chats.
- A database, a webhook or a public endpoint on the host: long polling and a file.
- Half days, hours, or editing the production calendar itself.
- Reminders or a daily digest from the bot.

## User Stories

### US-1: Enter an absence
**As** the owner, **I want** to tell the bot `/add отпуск 03.11-14.11` (or `/add vacation
2026-11-03 2026-11-14`), **so that** the service does not log on during those days.

**Acceptance criteria** (each references a scenario in `tests/acceptance/features/`):
- [ ] Scenario: `An absence entered through the bot is confirmed with its dates and an id`
- [ ] Scenario: `An absence with a malformed date is refused with the expected format`
- [ ] Scenario: `A message from another chat is ignored`

### US-2: See and change what is entered
**As** the owner, **I want** `/list`, `/edit <id> …` and `/del <id>`, **so that** a changed
plan is reflected without SSH.

**Acceptance criteria**:
- [ ] Scenario: `The list names every absence with its id, kind and dates`
- [ ] Scenario: `A deleted absence no longer stops a run`
- [ ] Scenario: `An edited absence keeps its id and takes the new dates`

### US-3: The runs respect an absence
**As** the owner, **I want** the morning run on a day of absence to skip and say why,
**so that** I get one line and no logon.

**Acceptance criteria**:
- [ ] Scenario: `A morning run on a day of vacation is skipped with the kind named`
- [ ] Scenario: `An evening run on a skipped day sends nothing`
- [ ] Scenario: `A day after the absence ends is a working day again`

### US-4: One readable notice for a skipped day
**As** the owner, **I want** the weekend notice to say only what matters, **so that** I keep
reading the notices.

**Acceptance criteria**:
- [ ] Scenario: `A skipped non-working day is reported without a time line`
- [ ] Scenario: `A day the calendar marks as a holiday is skipped with a notice`
- [ ] Scenario: `When the calendar is unreachable the weekday rule decides and says so`

The last two scenarios exist and keep their names; their expected text changes.

## Acceptance Criteria (overall)

Behaviour-bearing criteria are scenarios; the suite holds their text and this list references
them by name. `beadloom lint` reports a referenced scenario the suite does not contain.

- [ ] Scenario: `An absence entered through the bot is confirmed with its dates and an id`
- [ ] Scenario: `An absence with a malformed date is refused with the expected format`
- [ ] Scenario: `A message from another chat is ignored`
- [ ] Scenario: `The list names every absence with its id, kind and dates`
- [ ] Scenario: `A deleted absence no longer stops a run`
- [ ] Scenario: `An edited absence keeps its id and takes the new dates`
- [ ] Scenario: `A morning run on a day of vacation is skipped with the kind named`
- [ ] Scenario: `An evening run on a skipped day sends nothing`
- [ ] Scenario: `A day after the absence ends is a working day again`
- [ ] Scenario: `A skipped non-working day is reported without a time line`

**Non-behavioural criteria**:

- [ ] `horizon-bot.service` is installed and enabled by the deploy; `horizon probe` names
      the absence store and the next absence — non-behavioural: a property of the deploy
      and a probe line, observed in the deploy summary
- [ ] The absences file lives outside the code checkout, under the service user, mode 0600
      — non-behavioural: a property of the host, observed with `ls -l`
- [ ] The first absence entered by the owner through the bot on the host stops the next
      morning run with one notice — non-behavioural: the observer is the owner's chat
