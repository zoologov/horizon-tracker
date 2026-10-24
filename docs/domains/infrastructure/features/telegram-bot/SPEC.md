# Telegram bot transport

The `BotTransport` port over the Telegram Bot API: `getUpdates` long polling for text
messages and `sendMessage` replies. A failure is logged and raised as `BotTransportError`,
and the token never reaches a log or an error.

## Source

`src/horizon_tracker/infrastructure/telegram_bot.py`

## Specification

### Purpose

The owner enters absences by writing to the notification bot. The host has no public
endpoint, so the bot reads its messages by long polling: one `getUpdates` request held
open by the Bot API until a message arrives or the poll times out. The transport carries
those messages to the bot loop and the loop's replies back. It does not decide who is
served or what a text means: a message from any chat is returned, and the loop drops what
is not the owner's.

### How it works

Each call is a `POST` to `https://api.telegram.org/bot<token>/<method>` with a JSON body.

`poll(offset)` posts `getUpdates` with `{"timeout": 30, "allowed_updates": ["message"]}`
and `offset` when there is one, and waits up to 45 seconds, longer than the 30 seconds the
Bot API holds the request. It returns one `IncomingMessage(update_id, chat_id, text)` per
update whose `message` has a `text` string and a whole-number `chat.id`, in the order
received, with the chat id as a string. Any other update (an edited message, a sticker, a
photo, a message without a chat) is skipped, not raised.

A skipped update never reaches the caller, so the caller cannot confirm it by its offset.
The transport therefore remembers the highest update id it has received and raises the
next `offset` it sends past it: `max(offset, highest + 1)`. An update the transport has
received, whether returned or skipped, is never fetched again. A caller's offset that is
already higher is sent as given.

`reply(chat_id, text)` posts `sendMessage` with `{"chat_id": ..., "text": ...}` and waits
up to 20 seconds.

A failure is logged as a warning on `horizon_tracker.infrastructure.telegram_bot` and
raised as `BotTransportError`, whose text names the method:

- a status other than 200: `Telegram getUpdates refused with status 409: <description>`
  in the log, with the token in the API's `description` masked as `<token>`, and
  `getUpdates refused with status 409` raised. A 409 Conflict means another process
  holds `getUpdates` for the same bot;
- a network error: `Telegram getUpdates failed: ConnectError` in the log, the error's type
  only, because httpx's message carries the URL. The error is raised `from None`, so a
  traceback the caller logs does not carry the httpx error either;
- a 200 answer that is not a JSON object with a `result`, a `getUpdates` result that is not
  a list, or an update without a whole-number `update_id`: `getUpdates answered with
  <what>`.

### Token discipline

The token discipline is the notifier's, imported from `telegram.py` rather than
repeated: `BOT_API_URL`, `check_bot_token` (a malformed token is refused at construction
with a `ValueError` that never echoes it), `redact_token` and `mask_token_in_httpx_log`,
which installs one masking filter on the `httpx` logger per process, however many
adapters are built.

## Invariants

- No log line and no raised error carries the token or a URL.
- An update the transport has received is never fetched again.
- The transport answers every chat's text messages, and the loop decides who is served.
- Only `getUpdates` and `sendMessage` are called. Nothing configures a webhook.

## API

Module `src/horizon_tracker/infrastructure/telegram_bot.py`:

- `TelegramBotTransport(token: str, client: httpx.Client)` implements `BotTransport`:
  - `poll(offset: int | None) -> tuple[IncomingMessage, ...]`;
  - `reply(chat_id: str, text: str) -> None`;
  - both raise `BotTransportError` (declared in `domain/ports.py`).
- `POLL_TIMEOUT_SECONDS` is `30`, the long-poll timeout sent to the Bot API.

## Testing

Tests: `tests/unit/infrastructure/test_telegram_bot.py`, on `httpx.MockTransport`; the
live Bot API is never called. They cover the request each method sends, six shapes of
update that are skipped, the offset raised past skipped and received updates, the two
timeouts, a 409 Conflict and five other refusals or network errors per method, a refusal
without a JSON description, seven malformed answers, a `caplog` and traceback check that
the token appears nowhere, and the one masking filter on the `httpx` logger.

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `telegram-notifier`
- Used by: `cli` (`horizon bot`, through `build_bot_transport`)
- External contracts (declared in `.beadloom/_graph/landscape.yml`, not derived): consumes
  `http:telegram-getUpdates` and `http:telegram-sendMessage` from
  [`telegram-bot-api`](../../../external/telegram-bot-api/SPEC.md)

## Parent

`infrastructure` — [infrastructure README](../../README.md)
