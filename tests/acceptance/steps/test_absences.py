"""Placeholder steps for the HT-012 absence scenarios: they skip, with the reason, until built.

PRD HT-012 is approved and names these scenarios; the `scenario-coverage` rule requires a
PRD-named scenario to exist in the suite. The behaviour is not built yet, so the only honest
outcome is a SKIP that says so (`pytest -rs` prints it), never a pass. BEAD-05 of HT-012
(ht-fzd) and BEAD-07 (ht-xad) replace this module with real steps over the fakes.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then

scenarios("absences.feature")

_REASON = (
    "HT-012 is approved and not built yet: BEAD-05 (ht-fzd) and BEAD-07 (ht-xad) "
    "implement this scenario"
)


@given("the absences of HT-012 are not built yet")
def _not_built_yet() -> None:
    pytest.skip(_REASON)


@then("the scenario is skipped until HT-012 builds it")
def _skipped() -> None:  # pragma: no cover - never reached, the Given skips first
    pytest.skip(_REASON)
