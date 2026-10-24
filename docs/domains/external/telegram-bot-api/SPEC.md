# Telegram Bot API

The Telegram Bot API at `api.telegram.org`, the HTTP interface a bot is driven through. An
external system: this repository holds no code of it and declares only the methods the
service calls.

## Source

None in this repository. The node's `source` in `.beadloom/_graph/landscape.yml` is this
file, so the graph has no sourceless node.

## Specification

### Purpose

Every run sends one report to the owner's chat as the notification bot whose token the
service holds, and the owner writes absences to the same bot. The Bot API is how that
report leaves the host and how the owner's messages reach it. `telegram-notifier` sends
the reports, and `telegram-bot` reads the owner's messages and replies to them.

### Contracts

Three contracts, one per method, each declared from both ends in `landscape.yml`. The
portal's map shows each as a dependency with a presence verdict. `sendMessage` has two
consumers, `telegram-notifier` and `telegram-bot`.

Common to both:

- **URL.** `POST https://api.telegram.org/bot<token>/<method>`. The token
  (`TELEGRAM_BOT_TOKEN`, `<bot id>:<secret>`) sits in the path of every URL, so the
  notifier never logs a URL and masks the token as `<token>` in httpx's own log lines and
  in every error it logs.
- **Body.** The notifier posts a form with `chat_id` (`TELEGRAM_CHAT_ID`) and the
  method's own fields. The bot transport posts a JSON object.
- **Timeout.** 20 seconds, so a hung API cannot hold the run, except `getUpdates`, which
  waits 45 seconds for the Bot API's 30-second hold.
- **Answer.** For the notifier: status 200 is delivered. A status other than 200 is logged with the API's
  `description` field (or `(no description)`). A network error has no response, so it is
  logged by the error's type and its redacted message. Either answers `False` and is never
  raised, so a run never fails on its notification. For the bot transport, a status other
  than 200 is logged by status with the redacted `description`, a network error by its
  type only, and either is raised as `BotTransportError` to the bot loop.

#### `http:telegram-sendPhoto` — telegram-bot-api → telegram-notifier

- **Fields.** `chat_id`, `caption` (the rendered report) and a multipart file `photo`:
  the run's screenshot, a PNG, under its own file name.
- **When.** A report that carries a screenshot. A screenshot that cannot be read, or a
  `sendPhoto` that is refused, falls back to `sendMessage` with the same text.
- **The caption limit.** The Bot API accepts a caption of up to 1024 characters. The
  notifier does not truncate: the report is at most four short lines from a closed
  message catalogue, far under the limit, and a caption the API refused would fall back
  to `sendMessage`.

#### `http:telegram-sendMessage` — telegram-bot-api → telegram-notifier, telegram-bot

- **Fields.** `chat_id` and `text`: the rendered report from the notifier, the reply from
  the bot transport.
- **When.** For the notifier, a report without a screenshot, and every fallback from
  `sendPhoto`. A refused `sendMessage` is logged and the report is lost. Nothing retries
  it. For the bot transport, one reply per owner's command, to the chat it came from.

#### `http:telegram-getUpdates` — telegram-bot-api → telegram-bot

- **Fields.** `timeout` (30, the long-poll hold in seconds), `allowed_updates`
  (`["message"]`) and `offset` once an update has been received.
- **Answer.** `{"ok": true, "result": [<update>, ...]}`. An update with a `message` that
  holds a `text` and a `chat.id` is returned to the bot loop; any other update is skipped
  and confirmed by the next `offset`.
- **One poller.** The Bot API serves `getUpdates` to one caller at a time and answers a
  second with 409 Conflict. `telegram-bot` is the service's only caller. No webhook is
  configured.

## Invariants

- The token never reaches a log, a bead comment or a document. This SPEC names only its
  shape.
- No other method is called, and no webhook is configured.
- Tests never reach the Bot API: the unit tests run on `httpx.MockTransport`, and the
  acceptance suite on a recording Bot API (`tests/support/bot_api.py`).

## Dependencies

Declared in `.beadloom/_graph/landscape.yml` as contract edges, not derived from
imports: an external system has no code here.

- Produces: `http:telegram-sendMessage` and `http:telegram-sendPhoto` for
  `telegram-notifier`; `http:telegram-getUpdates` and `http:telegram-sendMessage` for
  `telegram-bot`
- Consumes: (none)

## Parent

None: an external system, not part of `horizon-tracker`. The consumers are
`telegram-notifier` and `telegram-bot`.
