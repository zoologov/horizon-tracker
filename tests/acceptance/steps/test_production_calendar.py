"""Production calendar: holidays are skipped, and an unreachable calendar falls back to Mon-Fri.

The shared steps live in ``conftest.py``; the one step below reads the absence of a line,
which only the notice of a day-level skip needs (PRD HT-012 US-4).
"""

from __future__ import annotations

from pytest_bdd import parsers, scenarios, then

from tests.acceptance.steps.conftest import Scene

scenarios("production_calendar.feature")


@then(parsers.parse('no line of the message starts with "{prefix}"'))
def no_line_starts_with(scene: Scene, prefix: str) -> None:
    text = scene.only_message().text
    assert not [line for line in text.splitlines() if line.startswith(prefix)], text
