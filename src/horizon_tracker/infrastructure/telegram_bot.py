"""Receives the owner's messages to the bot by long polling and sends the bot's replies.

Implements the ``BotTransport`` port over the Telegram Bot API: ``poll`` is
``getUpdates`` held open up to ``POLL_TIMEOUT_SECONDS`` for message updates only, and
``reply`` is ``sendMessage``. A refusal, a network error or an answer that is not an
update list is logged (by status or by error type) and raised as ``BotTransportError``;
the caller decides whether to back off. An update that is not a text message is skipped,
and the transport confirms it on its next ``getUpdates`` so it is never fetched again.

The token discipline is the notifier's (``telegram``): the same URL, the same token
check, the same redaction and the same mask on httpx's own request lines. No log line
and no raised error carries the token or a URL.
"""

# beadloom:feature=telegram-bot

import logging

import httpx

from horizon_tracker.domain.ports import BotTransportError, IncomingMessage
from horizon_tracker.infrastructure.telegram import (
    BOT_API_URL,
    bot_api_description,
    check_bot_token,
    mask_token_in_httpx_log,
    redact_token,
)

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = 30  # how long the Bot API holds getUpdates open waiting for a message
_POLL_HTTP_TIMEOUT_SECONDS = POLL_TIMEOUT_SECONDS + 15.0  # the client outwaits the server's hold
_REPLY_TIMEOUT_SECONDS = 20.0  # one short text; bounded so a hung API cannot stall the loop
_ALLOWED_UPDATES = ["message"]


class TelegramBotTransport:
    """Polls one bot's updates and sends its replies, holding the next offset it owes."""

    def __init__(self, token: str, client: httpx.Client) -> None:
        check_bot_token(token)
        self._token = token
        self._client = client
        self._received_through: int | None = None
        mask_token_in_httpx_log()

    def poll(self, offset: int | None) -> tuple[IncomingMessage, ...]:
        """The text messages from ``offset`` on, waiting up to the long-poll timeout."""
        fields: dict[str, object] = {
            "timeout": POLL_TIMEOUT_SECONDS,
            "allowed_updates": _ALLOWED_UPDATES,
        }
        effective = self._offset(offset)
        if effective is not None:
            fields["offset"] = effective
        result = self._call("getUpdates", fields, _POLL_HTTP_TIMEOUT_SECONDS)
        if not isinstance(result, list):
            raise self._malformed("getUpdates", "no update list")
        messages: list[IncomingMessage] = []
        for update in result:
            update_id = _update_id(update)
            if update_id is None:
                raise self._malformed("getUpdates", "an update without an update id")
            if self._received_through is None or update_id > self._received_through:
                self._received_through = update_id
            message = _text_message(update_id, update)
            if message is not None:
                messages.append(message)
        return tuple(messages)

    def reply(self, chat_id: str, text: str) -> None:
        """Send ``text`` to the chat ``chat_id``."""
        self._call("sendMessage", {"chat_id": chat_id, "text": text}, _REPLY_TIMEOUT_SECONDS)

    def _offset(self, offset: int | None) -> int | None:
        """The caller's offset, raised past every update this transport already received."""
        if self._received_through is None:
            return offset
        return max(offset or 0, self._received_through + 1)

    def _call(self, method: str, fields: dict[str, object], timeout: float) -> object:
        """POST one Bot API method as JSON; its ``result``, or log and raise."""
        url = BOT_API_URL.format(token=self._token, method=method)
        try:
            response = self._client.post(url, json=fields, timeout=timeout)
        except httpx.HTTPError as error:
            kind = type(error).__name__
            logger.warning("Telegram %s failed: %s", method, kind)
            raise BotTransportError(f"{method} failed: {kind}") from None
        if response.status_code != httpx.codes.OK:
            logger.warning(
                "Telegram %s refused with status %d: %s",
                method,
                response.status_code,
                redact_token(bot_api_description(response), self._token),
            )
            raise BotTransportError(f"{method} refused with status {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise self._malformed(method, "not JSON") from None
        if not isinstance(payload, dict) or "result" not in payload:
            raise self._malformed(method, "no result")
        return payload["result"]

    @staticmethod
    def _malformed(method: str, what: str) -> BotTransportError:
        logger.warning("Telegram %s answered with %s", method, what)
        return BotTransportError(f"{method} answered with {what}")


def _update_id(update: object) -> int | None:
    """The update's id, or ``None`` when it has no whole-number id (a boolean is not one)."""
    if not isinstance(update, dict):
        return None
    update_id = update.get("update_id")
    return update_id if type(update_id) is int else None


def _text_message(update_id: int, update: object) -> IncomingMessage | None:
    """The update's text message with the chat it came from; ``None`` for anything else."""
    message = update.get("message") if isinstance(update, dict) else None
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    text = message.get("text")
    if type(chat_id) is not int or not isinstance(text, str):
        return None
    return IncomingMessage(update_id=update_id, chat_id=str(chat_id), text=text)
