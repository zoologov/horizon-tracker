"""Unit tests for the Telegram bot transport, over ``httpx.MockTransport``."""

import json
import logging
import traceback
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from horizon_tracker.domain.messages import Language
from horizon_tracker.domain.ports import BotTransport, BotTransportError, IncomingMessage
from horizon_tracker.infrastructure.telegram import TelegramNotifier
from horizon_tracker.infrastructure.telegram_bot import (
    POLL_TIMEOUT_SECONDS,
    TelegramBotTransport,
)

TOKEN = "123456789:AAHsecret-Token_value0123456789abcdefg"
OWNER = 987654321
STRANGER = 555000111

Handler = Callable[[httpx.Request], httpx.Response]
# A Bot API answer is a JSON object of any shape the test needs, malformed ones included.
Payload = dict[str, Any]


def _text_update(update_id: int, text: str, chat_id: int = OWNER) -> Payload:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "chat": {"id": chat_id, "type": "private"},
            "date": 1_793_000_000,
            "text": text,
        },
    }


def _updates(*updates: Payload) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": list(updates)})

    return handler


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


class BotApi:
    """A recording fake of the Bot API: answers each method as configured, else 200."""

    def __init__(self, answers: dict[str, Handler] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self._answers = answers or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        method = request.url.path.rsplit("/", 1)[-1]
        answer = self._answers.get(method)
        if answer is not None:
            return answer(request)
        result: object = [] if method == "getUpdates" else {}
        return httpx.Response(200, json={"ok": True, "result": result})

    def bodies(self) -> list[Payload]:
        return [json.loads(request.content) for request in self.requests]


def _transport(api: BotApi) -> TelegramBotTransport:
    return TelegramBotTransport(TOKEN, httpx.Client(transport=httpx.MockTransport(api)))


# --- poll: getUpdates -----------------------------------------------------------


def test_poll_long_polls_get_updates_for_messages_only() -> None:
    api = BotApi()

    _transport(api).poll(None)

    [request] = api.requests
    assert request.method == "POST"
    assert str(request.url) == f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    assert api.bodies() == [{"timeout": POLL_TIMEOUT_SECONDS, "allowed_updates": ["message"]}]
    assert POLL_TIMEOUT_SECONDS == 30


def test_poll_passes_the_offset_it_is_given() -> None:
    api = BotApi()

    _transport(api).poll(42)

    [body] = api.bodies()
    assert body["offset"] == 42


def test_poll_returns_the_text_messages_in_the_order_received() -> None:
    api = BotApi({"getUpdates": _updates(_text_update(7, "/list"), _text_update(8, "/help"))})

    messages = _transport(api).poll(None)

    assert messages == (
        IncomingMessage(update_id=7, chat_id=str(OWNER), text="/list"),
        IncomingMessage(update_id=8, chat_id=str(OWNER), text="/help"),
    )


def test_poll_returns_a_stranger_s_message_too_the_loop_decides_who_is_served() -> None:
    api = BotApi({"getUpdates": _updates(_text_update(3, "hi", chat_id=STRANGER))})

    [message] = _transport(api).poll(None)

    assert message.chat_id == str(STRANGER)


def test_no_pending_update_is_an_empty_answer() -> None:
    assert _transport(BotApi()).poll(None) == ()


def _without_text(update_id: int) -> Payload:
    update = _text_update(update_id, "")
    del update["message"]["text"]
    update["message"]["sticker"] = {"file_id": "abc"}
    return update


@pytest.mark.parametrize(
    "skipped",
    [
        {"update_id": 5, "edited_message": _text_update(5, "/list")["message"]},
        _without_text(5),
        {"update_id": 5, "message": {**_text_update(5, "")["message"], "text": 17}},
        {"update_id": 5, "message": "not an object"},
        {"update_id": 5, "message": {"text": "/list"}},
        {"update_id": 5, "message": {"text": "/list", "chat": {"id": "not a number"}}},
    ],
    ids=[
        "no-message",
        "no-text",
        "text-not-a-string",
        "message-not-an-object",
        "no-chat",
        "chat-id-not-a-number",
    ],
)
def test_an_update_without_a_text_message_is_skipped_not_raised(skipped: Payload) -> None:
    api = BotApi({"getUpdates": _updates(_text_update(4, "/list"), skipped)})

    messages = _transport(api).poll(None)

    assert [message.update_id for message in messages] == [4]


def test_a_skipped_update_is_confirmed_on_the_next_poll_so_it_never_returns() -> None:
    answers = iter([_updates(_without_text(9)), _updates()])
    api = BotApi({"getUpdates": lambda request: next(answers)(request)})
    transport = _transport(api)

    assert transport.poll(None) == ()
    transport.poll(None)

    assert api.bodies()[1]["offset"] == 10


def test_poll_never_asks_again_for_an_update_it_has_already_received() -> None:
    answers = iter([_updates(_text_update(4, "/list"), _without_text(6)), _updates()])
    api = BotApi({"getUpdates": lambda request: next(answers)(request)})
    transport = _transport(api)

    transport.poll(None)
    transport.poll(5)  # the caller confirmed the text message it was handed

    assert api.bodies()[1]["offset"] == 7


def test_the_next_offset_follows_the_highest_update_id_received_in_any_order() -> None:
    answers = iter([_updates(_without_text(8), _text_update(6, "/list")), _updates()])
    api = BotApi({"getUpdates": lambda request: next(answers)(request)})
    transport = _transport(api)

    transport.poll(None)
    transport.poll(7)

    assert api.bodies()[1]["offset"] == 9


def test_a_caller_s_offset_past_everything_received_is_kept() -> None:
    answers = iter([_updates(_text_update(4, "/list")), _updates()])
    api = BotApi({"getUpdates": lambda request: next(answers)(request)})
    transport = _transport(api)

    transport.poll(None)
    transport.poll(20)

    assert api.bodies()[1]["offset"] == 20


def test_the_poll_waits_longer_than_the_bot_api_holds_the_request() -> None:
    timeouts: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json={"ok": True, "result": []})

    # The client itself never times out: the bound must come from the adapter.
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=None)
    TelegramBotTransport(TOKEN, client).poll(None)

    [timeout] = timeouts
    assert all(
        value is not None and POLL_TIMEOUT_SECONDS < value <= 2 * POLL_TIMEOUT_SECONDS
        for value in timeout.values()
    )


# --- reply: sendMessage ---------------------------------------------------------


def test_reply_sends_the_text_to_the_chat_named() -> None:
    api = BotApi()

    _transport(api).reply(str(OWNER), "Vacation 03.11–14.11 added, id 3")

    [request] = api.requests
    assert request.method == "POST"
    assert str(request.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert api.bodies() == [{"chat_id": str(OWNER), "text": "Vacation 03.11–14.11 added, id 3"}]


def test_the_reply_is_bounded_in_time() -> None:
    timeouts: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json={"ok": True, "result": {}})

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=None)
    TelegramBotTransport(TOKEN, client).reply(str(OWNER), "ok")

    [timeout] = timeouts
    assert all(
        value is not None and 0 < value <= POLL_TIMEOUT_SECONDS for value in timeout.values()
    )


# --- the failures: logged by status or type, raised as BotTransportError --------


def test_a_409_conflict_from_another_poller_is_logged_by_status_and_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="horizon_tracker.infrastructure.telegram_bot")
    conflict = "Conflict: terminated by other getUpdates request"
    api = BotApi({"getUpdates": _status(409, conflict)})

    with pytest.raises(BotTransportError, match="409"):
        _transport(api).poll(None)

    assert "getUpdates" in caplog.text
    assert "409" in caplog.text
    assert conflict in caplog.text


@pytest.mark.parametrize("method", ["getUpdates", "sendMessage"])
@pytest.mark.parametrize(
    ("answer", "named"),
    [
        (_status(401, "Unauthorized"), "401"),
        (_status(500), "500"),
        (_status(400, "Bad Request: chat not found"), "400"),
        (_raising(httpx.ConnectError), "ConnectError"),
        (_raising(httpx.ReadTimeout), "ReadTimeout"),
    ],
)
def test_a_refusal_or_a_network_error_is_logged_and_raised_as_a_transport_error(
    method: str, answer: Handler, named: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="horizon_tracker.infrastructure.telegram_bot")
    transport = _transport(BotApi({method: answer}))

    with pytest.raises(BotTransportError, match=named) as raised:
        if method == "getUpdates":
            transport.poll(None)
        else:
            transport.reply(str(OWNER), "ok")

    assert method in str(raised.value)
    assert method in caplog.text
    assert named in caplog.text


def test_a_refusal_without_a_json_description_is_logged_as_having_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway = BotApi({"getUpdates": lambda request: httpx.Response(502, text="<html>502</html>")})

    with pytest.raises(BotTransportError, match="502"):
        _transport(gateway).poll(None)

    assert "(no description)" in caplog.text
    assert "<html>" not in caplog.text


def test_a_network_error_is_logged_by_its_type_only(caplog: pytest.LogCaptureFixture) -> None:
    transport = _transport(BotApi({"getUpdates": _raising(httpx.ConnectError)}))

    with pytest.raises(BotTransportError):
        transport.poll(None)

    assert "simulated failure" not in caplog.text


@pytest.mark.parametrize(
    "answer",
    [
        lambda request: httpx.Response(200, text="<html>bad gateway</html>"),
        lambda request: httpx.Response(200, json=["not", "an", "object"]),
        lambda request: httpx.Response(200, json={"ok": True}),
        lambda request: httpx.Response(200, json={"ok": True, "result": {"update_id": 1}}),
        lambda request: httpx.Response(200, json={"ok": True, "result": ["not an update"]}),
        lambda request: httpx.Response(200, json={"ok": True, "result": [{"message": {}}]}),
        lambda request: httpx.Response(
            200, json={"ok": True, "result": [{"update_id": True, "message": {}}]}
        ),
    ],
    ids=[
        "not-json",
        "not-an-object",
        "no-result",
        "result-not-a-list",
        "update-not-an-object",
        "no-update-id",
        "update-id-a-boolean",
    ],
)
def test_an_answer_that_is_not_an_update_list_is_raised(answer: Handler) -> None:
    with pytest.raises(BotTransportError, match="getUpdates"):
        _transport(BotApi({"getUpdates": answer})).poll(None)


# --- the token stays out of the log and out of the error ------------------------


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
        {"getUpdates": _updates(_text_update(1, "/list"))},
        {"getUpdates": _status(409, "Conflict"), "sendMessage": _status(403, "Forbidden")},
        {"getUpdates": _raising(httpx.ConnectError), "sendMessage": _raising(httpx.ReadTimeout)},
        {
            "getUpdates": _status(401, f"Unauthorized: {TOKEN}"),
            "sendMessage": _status(400, f"bot{TOKEN} said no"),
        },
    ],
    ids=["delivered", "refused", "network-down", "description-echoes-token"],
)
def test_no_log_record_and_no_error_carries_the_token(
    answers: dict[str, Handler], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)  # every logger, httpx's own request line included
    transport = _transport(BotApi(answers))
    raised: list[BotTransportError] = []

    for call in (lambda: transport.poll(None), lambda: transport.reply(str(OWNER), "ok")):
        try:
            call()
        except BotTransportError as error:
            raised.append(error)
            logging.getLogger("bot-loop-stand-in").exception("the loop logs what it caught")

    assert caplog.records, "the scenario logged nothing, so the check would be vacuous"
    shown = _every_record_text(caplog)
    shown += "".join("".join(traceback.format_exception(error)) for error in raised)
    assert TOKEN not in shown
    assert TOKEN.split(":", 1)[1] not in shown


def test_httpx_request_lines_still_name_the_bot_method(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="httpx")

    _transport(BotApi()).poll(None)

    assert "api.telegram.org" in caplog.text
    assert "getUpdates" in caplog.text
    assert TOKEN not in caplog.text


def test_the_httpx_logger_carries_one_masking_filter_however_many_adapters_are_built() -> None:
    client = httpx.Client(transport=httpx.MockTransport(BotApi()))
    before = list(logging.getLogger("httpx").filters)

    TelegramBotTransport(TOKEN, client)
    TelegramBotTransport(TOKEN, client)
    TelegramNotifier(TOKEN, str(OWNER), client, Language.EN)

    after = logging.getLogger("httpx").filters
    assert len(after) == max(len(before), 1)


# --- construction ---------------------------------------------------------------


@pytest.mark.parametrize(
    "token", ["", "not-a-token", "123456789:", f"{TOKEN}\n", f" {TOKEN}", "123:abc/../x"]
)
def test_a_malformed_token_is_refused_without_echoing_it(token: str) -> None:
    with pytest.raises(ValueError, match="token") as refused:
        TelegramBotTransport(token, httpx.Client())

    if token.strip():
        assert token.strip() not in str(refused.value)


def test_the_adapter_satisfies_the_bot_transport_port() -> None:
    transport: BotTransport = _transport(BotApi())

    assert transport.poll(None) == ()
