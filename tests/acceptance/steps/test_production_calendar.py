"""Production calendar: holidays are skipped, and an unreachable calendar falls back to Mon-Fri.

The scenario `A skipped non-working day is reported without a time line` is named by PRD
HT-012 and not built yet: its steps below SKIP with the reason until BEAD-03 of HT-012
(ht-4um) replaces them with real ones.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then

scenarios("production_calendar.feature")

_HT012_REASON = "HT-012 is approved and not built yet: BEAD-03 (ht-4um) implements this scenario"


@given("the day-level skip notice of HT-012 is not built yet")
def _not_built_yet() -> None:
    pytest.skip(_HT012_REASON)


@then("the scenario is skipped until HT-012 BEAD-03 lands")
def _skipped() -> None:  # pragma: no cover - never reached, the Given skips first
    pytest.skip(_HT012_REASON)
