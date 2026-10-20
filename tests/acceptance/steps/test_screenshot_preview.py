"""Placeholder steps for the HT-004 scenarios: they skip, with the reason, until BEAD-03 lands.

PRD HT-004 is approved and names three scenarios; the `scenario-coverage` rule requires a
PRD-named scenario to exist in the suite. The behaviour is not built yet, so the only honest
outcome is a SKIP that says so (`pytest -rs` prints it), never a pass. BEAD-03 of HT-004
(ht-bm9) replaces this module with real steps over the fakes.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then

scenarios("../features/screenshot_preview.feature")

_REASON = "HT-004 is approved and not built yet: BEAD-03 (ht-bm9) implements this scenario"


@given("the screenshot preview of HT-004 is not built yet")
def _not_built_yet() -> None:
    pytest.skip(_REASON)


@then("the scenario is skipped until HT-004 BEAD-03 lands")
def _skipped() -> None:  # pragma: no cover - never reached, the Given skips first
    pytest.skip(_REASON)
