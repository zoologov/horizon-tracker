"""Placeholder steps for the HT-003 scenarios: they skip, with the reason, until BEAD-06 lands.

PRD HT-003 is approved and names seven scenarios; the `scenario-coverage` rule requires a
PRD-named scenario to exist in the suite. The behaviour is not built yet, so the only honest
outcome is a SKIP that says so (`pytest -rs` prints it), never a pass. BEAD-06 of HT-003
replaces this module with real steps over the fakes.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then

scenarios("../features/randomised_moments.feature")

_REASON = "HT-003 is approved and not built yet: BEAD-06 (ht-slm) implements this scenario"


@given("the randomised schedule of HT-003 is not built yet")
def _not_built_yet() -> None:
    pytest.skip(_REASON)


@then("the scenario is skipped until HT-003 BEAD-06 lands")
def _skipped() -> None:  # pragma: no cover - never reached, the Given skips first
    pytest.skip(_REASON)
