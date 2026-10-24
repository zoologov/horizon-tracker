"""Production calendar: holidays are skipped, and an unreachable calendar falls back to Mon-Fri.

Every step of this feature is shared and lives in ``conftest.py``.
"""

from pytest_bdd import scenarios

scenarios("production_calendar.feature")
