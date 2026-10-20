"""Placeholder steps for the HT-007 scenarios: they skip, with the reason, until BEAD-03 lands.

PRD HT-007 is approved and names four scenarios; the `scenario-coverage` rule requires a
PRD-named scenario to exist in the suite. The behaviour is not built yet, so the only honest
outcome is a SKIP that says so. BEAD-03 of HT-007 (ht-bsc) replaces this module with real steps.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then

scenarios("../features/language.feature")

_REASON = "HT-007 is approved and not built yet: BEAD-03 (ht-bsc) implements this scenario"


@given("the message catalogue of HT-007 is not built yet")
def _not_built_yet() -> None:
    pytest.skip(_REASON)


@then("the scenario is skipped until HT-007 BEAD-03 lands")
def _skipped() -> None:  # pragma: no cover - never reached, the Given skips first
    pytest.skip(_REASON)
