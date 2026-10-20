"""Unit tests for the isdayoff.ru calendar adapter, over ``httpx.MockTransport``."""

import logging
from collections.abc import Callable
from datetime import date

import httpx
import pytest

from horizon_tracker.domain.ports import WorkingDayCalendar
from horizon_tracker.infrastructure.isdayoff import IsDayOffCalendar

TUESDAY = date(2026, 10, 20)

Handler = Callable[[httpx.Request], httpx.Response]


def _calendar(handler: Handler) -> IsDayOffCalendar:
    return IsDayOffCalendar(httpx.Client(transport=httpx.MockTransport(handler)))


def _answering(status: int, body: str) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body)

    return handler


def _raising(error: type[httpx.TransportError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("simulated", request=request)

    return handler


# --- the request ----------------------------------------------------------------


def test_the_calendar_asks_isdayoff_for_the_day_in_its_compact_date_form() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="0")

    _calendar(handler).is_working_day(date(2026, 1, 7))

    assert [(r.method, str(r.url)) for r in seen] == [("GET", "https://isdayoff.ru/20260107")]


def test_the_calendar_gives_isdayoff_five_seconds_and_no_more() -> None:
    timeouts: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, text="0")

    # The client's own default is a minute: the five seconds must come from the adapter.
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=60.0)
    IsDayOffCalendar(client).is_working_day(TUESDAY)

    assert timeouts == [{"connect": 5.0, "read": 5.0, "write": 5.0, "pool": 5.0}]


# --- the answers ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "working"),
    [
        ("0", True),  # a working day
        ("2", True),  # a shortened pre-holiday day is still a working day
        ("1", False),  # a weekend or a public holiday
    ],
)
def test_the_calendar_reads_the_isdayoff_day_code(body: str, working: bool) -> None:
    assert _calendar(_answering(200, body)).is_working_day(TUESDAY) is working


# --- the failures: None, logged, never raised -----------------------------------


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, httpx.RemoteProtocolError],
)
def test_a_network_failure_is_no_answer(
    error: type[httpx.TransportError], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="horizon_tracker.infrastructure.isdayoff")

    assert _calendar(_raising(error)).is_working_day(TUESDAY) is None
    assert "isdayoff.ru" in caplog.text


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (500, "0"),
        (503, ""),
        (400, "100"),  # isdayoff: malformed date
        (404, "101"),  # isdayoff: no data for that date
        (400, "1"),  # a valid-looking code is still no answer when the status says error
    ],
)
def test_an_error_status_is_no_answer(
    status: int, body: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="horizon_tracker.infrastructure.isdayoff")

    assert _calendar(_answering(status, body)).is_working_day(TUESDAY) is None
    assert str(status) in caplog.text


@pytest.mark.parametrize("body", ["", "4", "199", "true", "<html>maintenance</html>", "01"])
def test_an_unexpected_body_is_no_answer(body: str, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="horizon_tracker.infrastructure.isdayoff")

    assert _calendar(_answering(200, body)).is_working_day(TUESDAY) is None
    assert "unexpected" in caplog.text


def test_the_adapter_satisfies_the_working_day_calendar_port() -> None:
    calendar: WorkingDayCalendar = _calendar(_answering(200, "0"))

    assert calendar.is_working_day(TUESDAY) is True
