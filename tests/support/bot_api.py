"""A recording stand-in for the Telegram Bot API, read back as the messages the owner got.

The real ``TelegramNotifier`` posts to it through ``httpx.MockTransport``, so a test sees
what would have reached the chat: the method, the text or caption, the attached photo.
It also keeps every raw request body, for the checks that a secret never left the run.
"""

from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import HTTP
from urllib.parse import parse_qs

import httpx

OK = {"ok": True, "result": {}}


@dataclass(frozen=True)
class SentMessage:
    """One delivered Bot API call: its method, its text (or caption) and its photo bytes."""

    method: str
    text: str
    photo: bytes | None


@dataclass
class RecordingBotApi:
    """Answers every Bot API call with 200 and records what was posted."""

    requests: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        return httpx.Response(200, json=OK)

    def client(self) -> httpx.Client:
        """An HTTP client whose every request lands here."""
        return httpx.Client(transport=httpx.MockTransport(self))

    @property
    def messages(self) -> list[SentMessage]:
        """The calls in the order they were made, parsed into what the chat shows."""
        return [_parse(request) for request in self.requests]

    def raw_bodies(self) -> list[str]:
        """Every request's URL and body as text, for searching a secret in what was sent."""
        return [
            f"{request.url}\n{request.content.decode('utf-8', errors='replace')}"
            for request in self.requests
        ]


def _parse(request: httpx.Request) -> SentMessage:
    method = request.url.path.rsplit("/", 1)[-1]
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        return _multipart(method, content_type, request.content)
    fields = parse_qs(request.content.decode("utf-8"))
    return SentMessage(method, fields.get("text", [""])[0], None)


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
