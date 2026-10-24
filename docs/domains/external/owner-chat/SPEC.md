# The owner's chat

The owner's private Telegram chat with the notification bot. An external system: a
person reading messages, not code. This document declares what the service sends there.

## Source

None in this repository. The node's `source` in `.beadloom/_graph/landscape.yml` is this
file, so the graph has no sourceless node. The chat's id is the secret `TELEGRAM_CHAT_ID`;
it lives only in the GitHub Environment `horizon-vps` and the host's `.env`.

## Specification

### Purpose

The owner learns from this chat whether each morning's check-in and each evening's
check-out happened, and why not when it did not. It is the only reader of the service's
outcome outside the host's journal. The bot is the notification bot, not the voice of
the neighbouring service on the host.

### Contracts

#### `notification:run-report` — telegram-notifier → owner-chat

Declared from both ends in `landscape.yml`; the portal's map shows it as a dependency
with a presence verdict. The surface is the text the owner reads.

- **One message per run.** A photo with the text as its caption when the run carries a
  screenshot, otherwise the text alone (see the `telegram-bot-api` SPEC).
- **The text.** Rendered by the domain's `render(report, language)` in the language
  `HT_LANGUAGE` names (`en` by default, `ru`), every word from the message catalogue.
  Three lines, and a fourth when the run did not succeed:

| Line | English form |
|------|--------------|
| headline | `Check-in succeeded`, `Check-in failed`, `Check-in skipped`, and the same three for `Check-out` |
| time | `Time: <dd.mm.yyyy HH:MM:SS zone>`, with `, planned for <HH:MM>` when the run had a drawn moment |
| calendar | `Calendar: the isdayoff.ru production calendar`, `Calendar: unreachable, the Mon-Fri rule decided` or `Calendar: not asked, manual run --force` |
| reason | `Reason: <reason>`, from the closed vocabulary of `Reason` (a non-working day, a missed window, a rejected login, a desktop not found, and the others) |

- **What it never carries.** No free text: no exception message, no URL, no account name,
  no password, no token. The screenshot is an attachment and its path is never named.

## Invariants

- The chat only reads today. HT-012 makes it a writer of commands too and declares that
  contract (`command:bot-text`) then, together with the change to this text.

## Dependencies

Declared in `.beadloom/_graph/landscape.yml` as contract edges, not derived from
imports: an external system has no code here.

- Produces: (none today; HT-012 adds `command:bot-text`)
- Consumes: `notification:run-report` from `telegram-notifier`

## Parent

None: an external system, not part of `horizon-tracker`. The producer is
`telegram-notifier`.
