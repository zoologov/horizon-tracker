"""A recording stand-in for the Telegram Bot API, read back as the messages the owner got.

The real ``TelegramNotifier`` and ``TelegramBotTransport`` post to it through
``httpx.MockTransport``, so a test sees what would have reached the chat: the method, the
chat, the text or caption, the attached photo. It also keeps every raw request body, for
the checks that a secret never left the run.

A test writes to the bot with ``write``: each message written is the answer to one
``getUpdates``, in order. Once every message has been handed out, the next ``getUpdates``
raises ``KeyboardInterrupt``: the operator stops the bot, which is how a scenario of a
long-running ``horizon bot`` comes to an end.
"""

import json
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import HTTP
from urllib.parse import parse_qs

import httpx

OK = {"ok": True, "result": {}}
_GET_UPDATES = "getUpdates"
_FIRST_UPDATE_ID = 1


@dataclass(frozen=True)
class SentMessage:
    """One delivered Bot API call: its method, its text (or caption) and its photo bytes."""

    method: str
    text: str
    photo: bytes | None
    chat_id: str | None = None


@dataclass
class RecordingBotApi:
    """Answers every Bot API call with 200 and records what was posted.

    ``getUpdates`` hands out the messages written with ``write``, one per call, and then
    stops the bot (see the module docstring).
    """

    requests: list[httpx.Request] = field(default_factory=list)
    incoming: list[dict[str, object]] = field(default_factory=list)
    _next_update_id: int = _FIRST_UPDATE_ID

    def write(self, chat_id: str, text: str) -> None:
        """Queue a text message from ``chat_id`` for the bot's next ``getUpdates``."""
        message = {"chat": {"id": int(chat_id)}, "text": text}
        self.incoming.append({"update_id": self._next_update_id, "message": message})
        self._next_update_id += 1

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if _method(request) == _GET_UPDATES:
            return self._updates()
        return httpx.Response(200, json=OK)

    def _updates(self) -> httpx.Response:
        if not self.incoming:
            raise KeyboardInterrupt  # the operator stops the bot: nothing is left to hand out
        return httpx.Response(200, json={"ok": True, "result": [self.incoming.pop(0)]})

    def client(self) -> httpx.Client:
        """An HTTP client whose every request lands here."""
        return httpx.Client(transport=httpx.MockTransport(self))

    @property
    def messages(self) -> list[SentMessage]:
        """The calls that reached a chat, in order, parsed into what the chat shows.

        A ``getUpdates`` shows nothing in a chat, so it is not among them.
        """
        return [_parse(request) for request in self.requests if _method(request) != _GET_UPDATES]

    def raw_bodies(self) -> list[str]:
        """Every request's URL and body as text, for searching a secret in what was sent."""
        return [
            f"{request.url}\n{request.content.decode('utf-8', errors='replace')}"
            for request in self.requests
        ]


def _method(request: httpx.Request) -> str:
    return request.url.path.rsplit("/", 1)[-1]


def _parse(request: httpx.Request) -> SentMessage:
    method = _method(request)
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        return _multipart(method, content_type, request.content)
    if content_type.startswith("application/json"):
        body = json.loads(request.content)
        return SentMessage(method, str(body.get("text", "")), None, str(body.get("chat_id")))
    fields = parse_qs(request.content.decode("utf-8"))
    return SentMessage(method, fields.get("text", [""])[0], None, fields.get("chat_id", [""])[0])


def _multipart(method: str, content_type: str, body: bytes) -> SentMessage:
    head = f"Content-Type: {content_type}\r\n\r\n".encode()
    message = BytesParser(policy=HTTP).parsebytes(head + body)
    text = ""
    photo: bytes | None = None
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        payload = part.get_payload(decode=True)
        assert isinstance(payload, bytes)
        if name == "photo":
            photo = payload
        elif name == "caption":
            text = payload.decode("utf-8")
    return SentMessage(method, text, photo)
