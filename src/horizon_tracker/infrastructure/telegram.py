"""Delivers run reports to the owner's Telegram chat through the Bot API.

Implements the ``Notifier`` port. A report with a screenshot goes out as ``sendPhoto``
captioned with ``render(report, language)``; without one, or when the photo cannot be read or is
refused, as ``sendMessage`` with the same text. A failed delivery is logged and
swallowed: a run never fails on its notification.

The bot token sits in the path of every Bot API URL, so it is kept out of the log on
both sides: this module never logs a URL or an unredacted error, and it installs a
filter on the ``httpx`` logger that masks the token in httpx's own request lines.
"""

# beadloom:domain=infrastructure

import logging
import re

import httpx

from horizon_tracker.domain.messages import Language
from horizon_tracker.domain.report import RunReport, render

logger = logging.getLogger(__name__)

BOT_API_URL = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT_SECONDS = 20.0  # a photo upload; bounded so a hung API cannot hold the run

_TOKEN_SHAPE = re.compile(r"\d+:[A-Za-z0-9_-]+")
_TOKEN_IN_BOT_URL = re.compile(r"(api\.telegram\.org/bot)[^/\s\"']+")
_MASK = "<token>"
# The language the owner has always read; HT-007 BEAD-02 makes it a constructor argument.
_LANGUAGE = Language.RU


class _BotUrlTokenFilter(logging.Filter):
    """Masks the token in any Bot API URL a log record mentions; drops no record."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = _TOKEN_IN_BOT_URL.sub(rf"\1{_MASK}", message)
        if masked != message:
            record.msg, record.args = masked, ()
        return True


_HTTPX_FILTER = _BotUrlTokenFilter()


def _mask_httpx_request_lines() -> None:
    """Attach the masking filter to the ``httpx`` logger once per process."""
    httpx_logger = logging.getLogger("httpx")
    if _HTTPX_FILTER not in httpx_logger.filters:
        httpx_logger.addFilter(_HTTPX_FILTER)


class TelegramNotifier:
    """Sends each run report to one chat as the bot whose token it was built with."""

    def __init__(self, token: str, chat_id: str, client: httpx.Client) -> None:
        if not _TOKEN_SHAPE.fullmatch(token):
            raise ValueError("Telegram bot token is malformed: expected <bot id>:<secret>")
        if not chat_id.strip():
            raise ValueError("Telegram chat id is empty")
        self._token = token
        self._chat_id = chat_id
        self._client = client
        _mask_httpx_request_lines()

    def send(self, report: RunReport) -> None:
        """Send the report; with its screenshot as a photo when one can be delivered."""
        text = render(report, _LANGUAGE)
        if report.screenshot is not None:
            try:
                photo = report.screenshot.read_bytes()
            except OSError as error:
                logger.warning(
                    "Telegram: screenshot unreadable, sending text only: %s",
                    type(error).__name__,
                )
            else:
                files = {"photo": (report.screenshot.name, photo)}
                if self._call("sendPhoto", {"caption": text}, files):
                    return
        self._call("sendMessage", {"text": text})

    def _call(
        self,
        method: str,
        fields: dict[str, str],
        files: dict[str, tuple[str, bytes]] | None = None,
    ) -> bool:
        """POST one Bot API method; ``True`` when delivered, otherwise log and ``False``."""
        url = BOT_API_URL.format(token=self._token, method=method)
        data = {"chat_id": self._chat_id, **fields}
        try:
            response = self._client.post(url, data=data, files=files, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as error:
            logger.warning(
                "Telegram %s failed: %s: %s",
                method,
                type(error).__name__,
                self._redact(str(error)),
            )
            return False
        if response.status_code != httpx.codes.OK:
            logger.warning(
                "Telegram %s refused with status %d: %s",
                method,
                response.status_code,
                self._redact(_description(response)),
            )
            return False
        return True

    def _redact(self, text: str) -> str:
        return text.replace(self._token, _MASK)


def _description(response: httpx.Response) -> str:
    """The Bot API's own explanation of a failure, or a placeholder when it gave none."""
    try:
        payload = response.json()
    except ValueError:
        return "(no description)"
    description = payload.get("description") if isinstance(payload, dict) else None
    return str(description) if description else "(no description)"
