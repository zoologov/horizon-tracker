"""Asks the isdayoff.ru production calendar whether a date is a working day.

Implements the ``WorkingDayCalendar`` port. The service answers a ``GET`` of
``https://isdayoff.ru/YYYYMMDD`` with a one-character day code. Anything that is not a
clean answer -- a network failure, a timeout, an error status, an unknown code -- is
``None``: logged here and never raised, so the domain falls back to the weekday rule.
"""

# beadloom:domain=infrastructure

import logging
from datetime import date

import httpx

logger = logging.getLogger(__name__)

ISDAYOFF_URL = "https://isdayoff.ru/{day:%Y%m%d}"
TIMEOUT_SECONDS = 5.0

# isdayoff day codes: 0 working, 1 non-working, 2 shortened pre-holiday (still working).
_DAY_CODES = {"0": True, "1": False, "2": True}


class IsDayOffCalendar:
    """The production calendar of isdayoff.ru, asked over a client the caller owns."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def is_working_day(self, day: date) -> bool | None:
        """``True``/``False`` by the calendar, ``None`` when it gave no clean answer."""
        try:
            response = self._client.get(ISDAYOFF_URL.format(day=day), timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as error:
            logger.warning(
                "isdayoff.ru unreachable for %s: %s: %s", day, type(error).__name__, error
            )
            return None
        if response.status_code != httpx.codes.OK:
            logger.warning("isdayoff.ru answered status %d for %s", response.status_code, day)
            return None
        working = _DAY_CODES.get(response.text)
        if working is None:
            logger.warning(
                "isdayoff.ru gave an unexpected body for %s: %r", day, response.text[:40]
            )
        return working
