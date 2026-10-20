"""Unit tests for the Telegram notifier, over ``httpx.MockTransport``."""

import dataclasses
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.ports import Notifier
from horizon_tracker.domain.report import Outcome, Reason, RunReport, render
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.infrastructure.telegram import TelegramNotifier

TOKEN = "123456789:AAHsecret-Token_value0123456789abcdefg"
CHAT_ID = "987654321"
PNG = b"\x89PNG\r\n\x1a\nfake-screenshot-bytes"
MOSCOW = ZoneInfo("Europe/Moscow")

SUCCESS = RunReport(
    kind=RunKind.CHECKIN,
    outcome=Outcome.SUCCEEDED,
    at=datetime(2026, 10, 20, 7, 56, 12, tzinfo=MOSCOW),
    verdict_source=VerdictSource.CALENDAR,
)

Handler = Callable[[httpx.Request], httpx.Response]
OK = {"ok": True, "result": {}}


class BotApi:
    """A recording fake of the Bot API: answers each method as configured."""

    def __init__(self, answers: dict[str, Handler] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self._answers = answers or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        method = request.url.path.rsplit("/", 1)[-1]
        answer = self._answers.get(method)
        return answer(request) if answer else httpx.Response(200, json=OK)

    @property
    def methods(self) -> list[str]:
        return [request.url.path.rsplit("/", 1)[-1] for request in self.requests]


def _notifier(api: BotApi) -> TelegramNotifier:
    return TelegramNotifier(TOKEN, CHAT_ID, httpx.Client(transport=httpx.MockTransport(api)))


def _failure_with_screenshot(path: Path) -> RunReport:
    return dataclasses.replace(
        SUCCESS, outcome=Outcome.FAILED, reason=Reason.DESKTOP_DID_NOT_OPEN, screenshot=path
    )


def _status(code: int, description: str = "") -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            code, json={"ok": False, "error_code": code, "description": description}
        )

    return handler


def _raising(error: type[httpx.TransportError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error(f"simulated failure for {request.url}", request=request)

    return handler


@pytest.fixture
def screenshot(tmp_path: Path) -> Path:
    path = tmp_path / "checkin-failed.png"
    path.write_bytes(PNG)
    return path


# --- the text message -----------------------------------------------------------


def test_a_report_without_a_screenshot_goes_out_as_a_text_message() -> None:
    api = BotApi()

    _notifier(api).send(SUCCESS)

    [request] = api.requests
    assert request.method == "POST"
    assert str(request.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert httpx.QueryParams(request.content.decode()) == httpx.QueryParams(
        {"chat_id": CHAT_ID, "text": render(SUCCESS)}
    )


# --- the photo ------------------------------------------------------------------


def test_a_report_with_a_screenshot_goes_out_as_a_photo_captioned_with_the_text(
    screenshot: Path,
) -> None:
    api = BotApi()
    report = _failure_with_screenshot(screenshot)

    _notifier(api).send(report)

    [request] = api.requests
    assert str(request.url) == f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    body = request.content
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="chat_id"\r\n\r\n' + CHAT_ID.encode() in body
    assert b'name="caption"\r\n\r\n' + render(report).encode() in body
    assert b'name="photo"; filename="checkin-failed.png"' in body
    assert PNG in body


def test_an_unreadable_screenshot_still_delivers_the_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    api = BotApi()
    report = _failure_with_screenshot(tmp_path / "never-written.png")

    _notifier(api).send(report)

    assert api.methods == ["sendMessage"]
    assert "screenshot" in caplog.text


def test_a_photo_the_bot_api_rejects_still_delivers_the_text(screenshot: Path) -> None:
    api = BotApi({"sendPhoto": _status(400, "Bad Request: PHOTO_INVALID_DIMENSIONS")})
    report = _failure_with_screenshot(screenshot)

    _notifier(api).send(report)

    assert api.methods == ["sendPhoto", "sendMessage"]
    assert httpx.QueryParams(api.requests[1].content.decode())["text"] == render(report)


# --- the failures: logged, never raised -----------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        _status(500, "Internal Server Error"),
        _status(401, "Unauthorized"),
        _status(400, "Bad Request: chat not found"),
        _raising(httpx.ConnectError),
        _raising(httpx.ReadTimeout),
    ],
)
def test_a_failed_send_is_logged_and_never_fails_the_run(
    answer: Handler, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="horizon_tracker.infrastructure.telegram")
    api = BotApi({"sendMessage": answer})

    _notifier(api).send(SUCCESS)

    assert api.methods == ["sendMessage"]
    assert "sendMessage" in caplog.text


def test_the_bot_api_description_of_a_failure_reaches_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = BotApi({"sendMessage": _status(403, "Forbidden: bot was blocked by the user")})

    _notifier(api).send(SUCCESS)

    assert "403" in caplog.text
    assert "bot was blocked by the user" in caplog.text


def test_the_notifier_gives_the_bot_api_a_bounded_time() -> None:
    timeouts: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json=OK)

    # The client itself never times out: the bound must come from the adapter.
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=None)
    TelegramNotifier(TOKEN, CHAT_ID, client).send(SUCCESS)

    [timeout] = timeouts
    assert all(value is not None and 0 < value <= 30 for value in timeout.values())


# --- the token stays out of the log ---------------------------------------------


def _every_record_text(caplog: pytest.LogCaptureFixture) -> str:
    """Everything a handler could write: the message, its arguments and any traceback."""
    parts = []
    for record in caplog.records:
        parts.append(record.getMessage())
        parts.append(repr(record.args))
        parts.append(record.exc_text or "")
        if record.exc_info and record.exc_info[1] is not None:
            parts.append(str(record.exc_info[1]))
    return "\n".join(parts)


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"sendPhoto": _status(400, "Bad Request"), "sendMessage": _status(500)},
        {"sendPhoto": _raising(httpx.ConnectError), "sendMessage": _raising(httpx.ReadTimeout)},
        {"sendPhoto": _status(401, f"Unauthorized: {TOKEN}")},
    ],
    ids=["delivered", "rejected", "network-down", "description-echoes-token"],
)
def test_no_log_record_from_any_logger_carries_the_token_or_the_chat_id(
    answers: dict[str, Handler], screenshot: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)  # every logger, httpx's own request line included
    api = BotApi(answers)

    _notifier(api).send(_failure_with_screenshot(screenshot))

    assert caplog.records, "the scenario logged nothing, so the check would be vacuous"
    logged = _every_record_text(caplog)
    assert TOKEN not in logged
    assert TOKEN.split(":", 1)[1] not in logged
    assert CHAT_ID not in logged


def test_httpx_request_lines_still_name_the_bot_method(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="httpx")

    _notifier(BotApi()).send(SUCCESS)

    assert "api.telegram.org" in caplog.text
    assert "sendMessage" in caplog.text


# --- construction ---------------------------------------------------------------


@pytest.mark.parametrize(
    "token", ["", "not-a-token", "123456789:", f"{TOKEN}\n", f" {TOKEN}", "123:abc/../x"]
)
def test_a_malformed_token_is_refused_without_echoing_it(token: str) -> None:
    with pytest.raises(ValueError, match="token") as refused:
        TelegramNotifier(token, CHAT_ID, httpx.Client())

    if token.strip():
        assert token.strip() not in str(refused.value)


def test_an_empty_chat_id_is_refused() -> None:
    with pytest.raises(ValueError, match="chat"):
        TelegramNotifier(TOKEN, "", httpx.Client())


def test_the_adapter_satisfies_the_notifier_port() -> None:
    notifier: Notifier = _notifier(BotApi())

    notifier.send(SUCCESS)
