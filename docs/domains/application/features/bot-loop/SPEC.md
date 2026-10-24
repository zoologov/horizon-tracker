# Bot loop

Serves the owner's chat with the bot: polls the transport, drops every other chat unread,
parses the owner's text, carries the command out through the absence service and sends
exactly one reply per message; on a failed poll it backs off and goes on.

## Source

`src/horizon_tracker/application/bot_loop.py`

## Specification

### Purpose

`horizon bot` runs this loop for as long as `horizon-bot.service` runs. It is the only
caller of `getUpdates` for the bot. The loop decides who is served (the one chat
`TELEGRAM_CHAT_ID` names) and that a message always gets an answer, and it keeps running
through a bad message or an unreachable Bot API.

### How it works

`run_once(offset)` polls the transport once from `offset`. For each message, in order:

1. **The chat filter comes first.** A message whose chat id is not exactly the owner's is
   dropped: no parse, no store access, no reply. The log names its update id and chat id
   at `INFO` and never its text.
2. The owner's text is parsed with `parse(text, today)`, today being the clock's date in
   the service's time zone.
3. The command is carried out: `Add`, `List`, `Delete` and `Edit` through the absence
   service, `Help` (and `/start`) as `bot.help`, and a `CommandError` as its problem.
4. The reply is rendered in the configured language, inside the same boundary as steps
   2 and 3, and sent to the owner's chat.

An exception raised while handling one message (a store that cannot be read, a bug, a
reply whose catalogue text names a field the code did not pass) is logged at `ERROR`
with its traceback, and the reply becomes `bot.error.internal`
(`Something went wrong; the details are in the journal`). A reply the transport cannot
send is logged as a warning by error type (`reply to update 4 was not sent:
BotTransportError`). In both cases the next message is handled.

`run_once` returns one past the highest update id it received, the dropped messages
included, or the `offset` it was given when the poll brought nothing. The transport also
raises its own offset past every update it received (see the telegram-bot SPEC), so a
message handed out is never fetched again, whether or not its reply was sent.

`run_forever()` never returns. It polls again at once after each poll, because the
transport's long poll is the wait. A poll that raises `BotTransportError` is logged as a
warning by error type (`poll failed (BotTransportError), retrying in 5 s`), followed by a
`Clock.sleep` of `BACKOFF_FIRST_SECONDS` (5 s) that doubles with each further failure in a
row, up to `BACKOFF_MAX_SECONDS` (300 s). A poll that succeeds resets the delay to 5 s. Any
other exception from the transport leaves the loop, and systemd restarts the service.

## Invariants

- The chat filter is the first step for every message: another chat gets no reply, and
  nothing of its text reaches the store or the log.
- The owner gets exactly one reply per message, whatever the command came to.
- An exception inside one message's handling, the rendering of its reply included, never
  stops the loop.
- A failed poll never stops `run_forever`; three or more in a row are ridden out with a
  growing, bounded wait.
- No log line carries a message's text, the owner's included.

## API

Module `src/horizon_tracker/application/bot_loop.py`:

- `BotLoop(transport: BotTransport, service: AbsenceService, owner_chat_id: str,
  language: Language, clock: Clock)`:
  - `run_once(offset: int | None) -> int | None` — raises the transport's
    `BotTransportError` from the poll;
  - `run_forever() -> None` — returns only by an exception that is not a
    `BotTransportError` (`KeyboardInterrupt`, which the CLI treats as a clean stop).
- `BACKOFF_FIRST_SECONDS = 5.0`, `BACKOFF_MAX_SECONDS = 300.0`.

The CLI builds it in `horizon bot` as `BotLoop(adapters.bot, service,
settings.telegram_chat_id, settings.language, adapters.clock)`.

## Testing

Tests: `tests/unit/application/test_bot_loop.py` (on `FakeBotTransport`, whose spent
script raises `KeyboardInterrupt`, and `FakeClock`; `caplog` for the stranger's text and
the warnings), `tests/unit/test_cli.py` (`horizon bot` end to end on the fakes). The live
Bot API is never called.

Scenarios (`tests/acceptance/features/absences.feature`, over the real Telegram transport
and a recording Bot API):

- `An absence entered through the bot is confirmed with its dates and an id`
- `An absence with a malformed date is refused with the expected format`
- `A message from another chat is ignored`

## Dependencies

Derived from the imports on reindex.

- Depends on: `absence-service`, `bot-commands`, `messages`, `ports`
- Used by: `cli`

## Parent

`application` — [application README](../../README.md)
