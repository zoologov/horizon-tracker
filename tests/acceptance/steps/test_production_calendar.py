"""Production calendar: holidays are skipped, and an unreachable calendar falls back to Mon-Fri."""

from pytest_bdd import scenarios

scenarios("production_calendar.feature")
