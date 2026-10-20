"""Implements the ``Clock`` port on the system's wall clock, in the service's time zone."""

# beadloom:domain=infrastructure

import time
from datetime import datetime
from zoneinfo import ZoneInfo


class SystemClock:
    """The real clock: aware ``now()`` in one zone, and a blocking ``sleep()``."""

    def __init__(self, tz: ZoneInfo) -> None:
        self._tz = tz

    def now(self) -> datetime:
        """The current instant as wall time in the configured zone."""
        return datetime.now(self._tz)

    def sleep(self, seconds: float) -> None:
        """Block for ``seconds``; a negative wait raises ``ValueError``, as ``time.sleep`` does."""
        time.sleep(seconds)
