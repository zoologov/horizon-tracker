# The owner's chat

The owner's private Telegram chat with the notification bot. An external system: a
person reading messages and typing commands, not code. This document declares what the
service sends there and what it reads from there.

## Source

None in this repository. The node's `source` in `.beadloom/_graph/landscape.yml` is this
file, so the graph has no sourceless node. The chat's id is the secret `TELEGRAM_CHAT_ID`.
It lives only in the GitHub Environment `horizon-vps` and the host's `.env`.

## Specification

### Purpose

The owner learns from this chat whether each morning's check-in and each evening's
check-out happened, and why not when it did not. It is the only reader of the service's
outcome outside the host's journal. The bot is the notification bot, not the voice of
the neighbouring service on the host.

### Contracts

#### `notification:run-report` — telegram-notifier → owner-chat

Declared from both ends in `landscape.yml`. The portal's map shows it as a dependency
with a presence verdict. The surface is the text the owner reads.

- **One message per run.** A photo with the text as its caption when the run carries a
  screenshot, otherwise the text alone (see the `telegram-bot-api` SPEC). A day skipped
  for itself (a non-working day, an absence) is reported once, by the morning check-in;
  the evening check-out of that day sends nothing (HT-012, the owner's ruling).
- **The text.** Rendered by the domain's `render(report, language)` in the language
  `HT_LANGUAGE` names (`en` by default, `ru`), every word from the message catalogue.
  Three lines, and a fourth when the run did not succeed. A skip for the day itself (a
  non-working day, an absence) has no time line, and an absence skip no calendar line:

| Line | English form |
|------|--------------|
| headline | `Check-in succeeded`, `Check-in failed`, `Check-in skipped`, and the same three for `Check-out` |
| time | `Time: <dd.mm.yyyy HH:MM:SS zone>`, with `, planned for <HH:MM>` when the run had a drawn moment |
| calendar | `Production calendar: isdayoff.ru`, `Production calendar: unavailable, the Mon–Fri rule decided` or `Production calendar: not asked, manual run --force` |
| reason | `Reason: <reason>`, from the closed vocabulary of `Reason` (a non-working day, a missed window, a rejected login, a desktop not found, and the others); an absence adds its days, `Reason: vacation (03.11–14.11)` |

- **What it never carries.** No free text: no exception message, no URL, no account name,
  no password, no token. The screenshot is an attachment and its path is never named.

#### `command:bot-text` — owner-chat → bot-commands

Declared from both ends in `landscape.yml` (HT-012). The surface is the text of one
message the owner types to the bot, read by the domain's `parse(text, today)` (see the
`bot-commands` SPEC):

| Command | Form |
|---------|------|
| enter an absence | `/add <kind> <from>[-<to>]`, e.g. `/add отпуск 03.11-14.11` or `/add vacation 2026-11-03 2026-11-14` |
| list the absences | `/list` |
| change one | `/edit <id> [<kind>] <from>[-<to>]` |
| delete one | `/del <id>` |
| the help | `/help`, and `/start` |

- **Kinds.** `vacation`/`отпуск`, `sick`/`sick_leave`/`больничный`,
  `dayoff`/`day_off`/`отгул`, in any case.
- **Dates.** `dd.mm`, `dd.mm.yyyy`, `yyyy-mm-dd`; a range joined by a dash or as two
  words; a date without a year is placed from the day the message is read.
- **The answer.** Every refusal is a catalogue text (`bot.error.*`) in `HT_LANGUAGE`.
  Only the chat `TELEGRAM_CHAT_ID` names is served; the bot loop (`bot-loop` SPEC) drops
  any other sender's message without logging its text.

## Invariants

- The chat reads the run reports and writes the bot's text commands (`command:bot-text`,
  HT-012); nothing else of the chat is read.

## Dependencies

Declared in `.beadloom/_graph/landscape.yml` as contract edges, not derived from
imports: an external system has no code here.

- Produces: `command:bot-text` to `bot-commands`
- Consumes: `notification:run-report` from `telegram-notifier`

## Parent

None: an external system, not part of `horizon-tracker`. The producer of the run reports
is `telegram-notifier`; the consumer of the commands is `bot-commands`.
