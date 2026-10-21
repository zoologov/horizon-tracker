# Telegram notifier

The `Notifier` port over the Telegram Bot API: a photo with a caption or a text
message. A failed delivery is logged and never raised, and the token never reaches a
log.

## Source

`src/horizon_tracker/infrastructure/telegram.py`

## Specification

### Purpose

Every run sends one message to the owner's private chat from the service bot the notification bot.
A report that carries a screenshot, of a confirmed success or of a failure, goes out as
that photo with the text as its caption. A run must never fail because its notification
failed, and the bot token, which sits in the path of every Bot API URL, must not leak
into the journal.

### How it works

`send(report)` renders the text with `render(report)` from the domain and then:

1. if the report has a screenshot, reads it and posts `sendPhoto` with the text as the
   caption;
2. if there is no screenshot, the file cannot be read, or `sendPhoto` fails or is
   refused, posts `sendMessage` with the same text.

Each call is a `POST` to `https://api.telegram.org/bot<token>/<method>` with a 20-second
timeout, bounded so a hung API cannot hold the run. A network error or a status other
than 200 is logged with the error's text or the API's `description`, with the token
replaced by `<token>`, and the call answers `False`.

The constructor installs a filter on the `httpx` logger, once per process, that masks
the token in any Bot API URL a log record mentions, so httpx's own request lines carry
`bot<token>` instead of the token.

## Invariants

- `send()` never raises for a delivery failure.
- The module never logs a URL or an unredacted error.
- The screenshot is an attachment; the text never names its path.
- A malformed token (not `<bot id>:<secret>`) or an empty chat id is refused at
  construction with `ValueError`, whose message never echoes the token. The CLI turns
  that refusal into a configuration error for `TELEGRAM_BOT_TOKEN`.

## API

Module `src/horizon_tracker/infrastructure/telegram.py`:

- `TelegramNotifier(token: str, chat_id: str, client: httpx.Client)` — implements
  `Notifier`; `send(report: RunReport) -> None`.
- `BOT_API_URL` — `"https://api.telegram.org/bot{token}/{method}"`.
- `TIMEOUT_SECONDS` — `20.0`.

## Testing

Tests: `tests/unit/infrastructure/test_telegram.py`, on `httpx.MockTransport`.

The acceptance suite runs the real notifier over a recording Bot API
(`tests/support/bot_api.py`). Scenarios
(`tests/acceptance/features/notifications.feature`):

- `A failed run sends the reason and a screenshot`
- `A notification never contains the password`

Scenarios (`tests/acceptance/features/screenshot_preview.feature`), on a fake Horizon
client:

- `A successful check-in sends a screenshot of the opened desktop`
- `A successful check-out sends a screenshot of the launch list without a session`
- `A check-in whose screenshot failed still reports success as text`

## Dependencies

Derived from the imports on reindex.

- Depends on: `run-report`
- Used by: `cli`

## Parent

`infrastructure` — [infrastructure README](../../README.md)
