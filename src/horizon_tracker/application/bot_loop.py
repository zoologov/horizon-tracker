"""Serves the owner's chat with the bot: poll the messages, answer each one, and keep going.

``BotLoop.run_once`` polls the transport once and handles what came back. The chat filter
comes first: a message from any chat but the owner's is dropped unread, and the log names
its chat id and never its text. The owner's text is parsed against the clock's today and
the command it names is carried out by the absence service; whatever the outcome, the
owner gets exactly one reply, in the configured language. An exception while handling one
message, the rendering of its reply included, is logged with its traceback and answered
as an internal error, and the next message is handled as if nothing happened; a reply the
transport cannot send is logged by error type and the loop goes on. ``run_once`` returns
the offset the next poll starts from.

``run_forever`` never returns: it polls again at once after each poll (the transport's long
poll is the wait), and after a poll that fails with ``BotTransportError`` it waits through
the clock, ``BACKOFF_FIRST_SECONDS`` and twice as long after each further failure in a row,
up to ``BACKOFF_MAX_SECONDS``. A poll that succeeds starts the backoff over. Nothing here
logs a message's text.
"""

# beadloom:domain=application
# beadloom:feature=bot-loop

import logging

from horizon_tracker.application.absence_service import AbsenceService, Reply
from horizon_tracker.domain.bot_commands import (
    Add,
    Command,
    CommandError,
    Delete,
    Edit,
    Help,
    List,
    parse,
)
from horizon_tracker.domain.messages import Language, Message
from horizon_tracker.domain.ports import BotTransport, BotTransportError, Clock, IncomingMessage

logger = logging.getLogger(__name__)

# A poll that fails is retried after 5 s, then 10, 20, ... and at most every 5 minutes: soon
# enough to answer the owner after a short outage, rare enough not to hammer the Bot API
# (or another poller holding getUpdates) through a long one.
BACKOFF_FIRST_SECONDS = 5.0
BACKOFF_MAX_SECONDS = 300.0
_BACKOFF_FACTOR = 2.0


class BotLoop:
    """Answers the owner's messages to the bot, one reply each, and ignores every other chat."""

    def __init__(
        self,
        transport: BotTransport,
        service: AbsenceService,
        owner_chat_id: str,
        language: Language,
        clock: Clock,
    ) -> None:
        self._transport = transport
        self._service = service
        self._owner_chat_id = owner_chat_id
        self._language = language
        self._clock = clock

    def run_forever(self) -> None:
        """Poll and answer until the process is stopped; back off on a failed poll."""
        offset: int | None = None
        delay = BACKOFF_FIRST_SECONDS
        while True:
            try:
                offset = self.run_once(offset)
            except BotTransportError as error:
                logger.warning("poll failed (%s), retrying in %g s", type(error).__name__, delay)
                self._clock.sleep(delay)
                delay = min(delay * _BACKOFF_FACTOR, BACKOFF_MAX_SECONDS)
            else:
                delay = BACKOFF_FIRST_SECONDS

    def run_once(self, offset: int | None) -> int | None:
        """Poll once from ``offset``, answer the owner's messages; the next poll's offset.

        The next offset is one past the highest update id received, the dropped ones
        included, or ``offset`` itself when the poll brought nothing.
        """
        messages = self._transport.poll(offset)
        for message in messages:
            if message.chat_id != self._owner_chat_id:
                logger.info(
                    "ignored update %d from chat %s: not the owner's",
                    message.update_id,
                    message.chat_id,
                )
                continue
            self._answer(message)
        if not messages:
            return offset
        return max(message.update_id for message in messages) + 1

    def _answer(self, message: IncomingMessage) -> None:
        """Reply to one of the owner's messages; a reply that cannot be sent is logged."""
        text = self._reply_text(message)
        try:
            self._transport.reply(self._owner_chat_id, text)
        except BotTransportError as error:
            logger.warning(
                "reply to update %d was not sent: %s", message.update_id, type(error).__name__
            )

    def _reply_text(self, message: IncomingMessage) -> str:
        """The reply's text in the language; any exception, rendering included, is internal."""
        try:
            reply = self._carry_out(parse(message.text, self._clock.now().date()))
            return reply.in_language(self._language)
        except Exception:
            # The boundary of one message: whatever went wrong, the rendering of the reply
            # included, is the journal's to show, and the loop answers the owner and goes on.
            logger.exception("update %d could not be handled", message.update_id)
            return Message("bot.error.internal").in_language(self._language)

    def _carry_out(self, parsed: Command | CommandError) -> Reply:
        """Carry out the command ``parsed`` names, or answer with the parser's refusal."""
        match parsed:
            case CommandError(problem=problem):
                return Reply.of(problem)
            case Add(kind=kind, first_day=first_day, last_day=last_day):
                return self._service.add(kind, first_day, last_day)
            case List():
                return self._service.list()
            case Delete(id=absence_id):
                return self._service.delete(absence_id)
            case Edit(id=absence_id, kind=kind, first_day=first_day, last_day=last_day):
                return self._service.edit(absence_id, kind, first_day, last_day)
            case Help():
                return Reply.of(Message("bot.help"))
