# Telegram notifier

The `Notifier` port over the Telegram Bot API: a photo with a caption or a text
message. A failed delivery is logged and never raised, and the token never reaches a
log.

## Source

`src/horizon_tracker/infrastructure/telegram.py`

## Specification

### Purpose

Every run sends one message to the configured chat (`TELEGRAM_CHAT_ID`) from the
Telegram bot whose token the service holds (`TELEGRAM_BOT_TOKEN`).
A report that carries a screenshot, of a confirmed success or of a failure, goes out as
that photo with the text as its caption. A run must never fail because its notification
failed, and the bot token, which sits in the path of every Bot API URL, must not leak
into the journal.

### How it works

`send(report)` renders the text with `render(report, language)` from the domain, in the
language the notifier was built with (the CLI passes `Settings.language`, read from
`HT_LANGUAGE`, English by default), and then:

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

- `TelegramNotifier(token: str, chat_id: str, client: httpx.Client, language: Language)`
  — implements `Notifier`; `send(report: RunReport) -> None`. The language has no default,
  so no caller gets English by forgetting it.
- `BOT_API_URL` — `"https://api.telegram.org/bot{token}/{method}"`.
- `TIMEOUT_SECONDS` — `20.0`.

The token discipline is public because the bot transport (`telegram-bot`) calls the same
API with the same token and imports it from here instead of repeating it:

- `check_bot_token(token: str) -> None` — raises `ValueError` for a token not shaped
  `<bot id>:<secret>`, without echoing it;
- `redact_token(text: str, token: str) -> str` — the text with the token masked as
  `<token>`;
- `mask_token_in_httpx_log() -> None` — installs the masking filter on the `httpx`
  logger, once per process;
- `bot_api_description(response: httpx.Response) -> str` — the API's `description` of a
  failure, or `(no description)`.

## Testing

Tests: `tests/unit/infrastructure/test_telegram.py`, on `httpx.MockTransport`.

The acceptance suite runs the real notifier over a recording Bot API
(`tests/support/bot_api.py`), built by the CLI's own `build_notifier` from the settings
the command loaded. Most feature files quote the notification in Russian, so the
acceptance scene builds the notifier in `ru`. The scenarios of `language.feature` leave
the language to `HT_LANGUAGE`, so their notifier is built the way the service builds it.
Scenarios (`tests/acceptance/features/notifications.feature`):

- `A failed run sends the reason and a screenshot`
- `A notification never contains the password`

Scenarios (`tests/acceptance/features/screenshot_preview.feature`), on a fake Horizon
client:

- `A successful check-in sends a screenshot of the opened desktop`
- `A successful check-out sends a screenshot of the launch list without a session`
- `A check-in whose screenshot failed still reports success as text`

Scenarios (`tests/acceptance/features/language.feature`):

- `A notification is rendered in the configured language`
- `The default language is English`
- `A blank HT_LANGUAGE reads as the default English`

## Dependencies

Derived from the imports on reindex.

- Depends on: `messages`, `run-report`
- Used by: `cli`, `telegram-bot`
- External contracts (declared in `.beadloom/_graph/landscape.yml`, not derived): consumes
  `http:telegram-sendMessage` and `http:telegram-sendPhoto` from
  [`telegram-bot-api`](../../../external/telegram-bot-api/SPEC.md), and produces
  `notification:run-report` for [`owner-chat`](../../../external/owner-chat/SPEC.md)

## Parent

`infrastructure` — [infrastructure README](../../README.md)
