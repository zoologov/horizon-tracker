"""Application layer: use cases (morning check-in, evening check-out) over ports.

A use case orders domain decisions and port calls; it owns no transport and no
browser detail. Both use cases run through ``WindowedRun``, the shared loop that
asks the calendar, retries inside the window and sends one report per run.
"""

from horizon_tracker.application.checkin import MorningCheckin
from horizon_tracker.application.checkout import EveningCheckout
from horizon_tracker.application.windowed_run import AttemptResult, WindowedRun

__all__ = ["AttemptResult", "EveningCheckout", "MorningCheckin", "WindowedRun"]
