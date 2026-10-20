"""Tests for the systemd units: each timer starts its run as `horizon` at the window's start.

The units are the only caller of the CLI in production, so the facts the service relies on
are asserted on the parsed files: the user, the environment file, the exact command, and
a timer that fires once, on time, and never catches up a missed run.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support.repository_root import repository_root

DEPLOY_DIR = repository_root() / "deploy"
HOME = "/opt/horizon-tracker"
RUNS = [
    pytest.param("checkin", "07:55", id="checkin"),
    pytest.param("checkout", "17:00", id="checkout"),
]
WINDOW_VARIABLE = {"checkin": "HT_CHECKIN_WINDOW", "checkout": "HT_CHECKOUT_WINDOW"}

Unit = dict[str, dict[str, list[str]]]


def parse_unit(path: Path) -> Unit:
    """Read a systemd unit into section -> key -> values (a key may repeat)."""
    sections: Unit = {}
    current: dict[str, list[str]] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
            continue
        assert current is not None, f"{path.name}: key outside a section: {line!r}"
        key, sep, value = line.partition("=")
        assert sep, f"{path.name}: not a key=value line: {line!r}"
        current.setdefault(key.strip(), []).append(value.strip())
    return sections


def only(unit: Unit, section: str, key: str) -> str:
    """The single value of `key` in `section`; a missing or repeated key fails the test."""
    values = unit.get(section, {}).get(key, [])
    assert len(values) == 1, f"[{section}] {key}: expected one value, got {values}"
    return values[0]


def service(run: str) -> Unit:
    return parse_unit(DEPLOY_DIR / f"horizon-{run}.service")


def timer(run: str) -> Unit:
    return parse_unit(DEPLOY_DIR / f"horizon-{run}.timer")


def test_deploy_ships_exactly_the_four_units() -> None:
    units = {p.name for p in DEPLOY_DIR.iterdir() if p.suffix in {".service", ".timer"}}
    assert units == {
        "horizon-checkin.service",
        "horizon-checkin.timer",
        "horizon-checkout.service",
        "horizon-checkout.timer",
    }


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_service_runs_the_cli_command_once_as_horizon(run: str, start: str) -> None:
    unit = service(run)
    assert only(unit, "Service", "Type") == "oneshot"
    assert only(unit, "Service", "User") == "horizon"
    assert only(unit, "Service", "Group") == "horizon"
    assert only(unit, "Service", "WorkingDirectory") == HOME
    assert only(unit, "Service", "EnvironmentFile") == f"{HOME}/.env"
    assert only(unit, "Service", "ExecStart") == f"{HOME}/.venv/bin/horizon {run}"


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_service_cannot_hang_until_the_next_run(run: str, start: str) -> None:
    timeout = only(service(run), "Service", "TimeoutStartSec")
    assert re.fullmatch(r"\d+(s|min)", timeout), timeout


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_service_waits_for_the_network(run: str, start: str) -> None:
    unit = service(run)
    assert "network-online.target" in only(unit, "Unit", "After").split()
    assert "network-online.target" in only(unit, "Unit", "Wants").split()


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_service_is_started_only_by_its_timer(run: str, start: str) -> None:
    assert "Install" not in service(run)


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_timer_fires_at_the_window_start_in_moscow(run: str, start: str) -> None:
    unit = timer(run)
    assert only(unit, "Timer", "OnCalendar") == f"*-*-* {start}:00 Europe/Moscow"
    assert only(unit, "Timer", "Unit") == f"horizon-{run}.service"
    assert only(unit, "Install", "WantedBy") == "timers.target"


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_timer_never_catches_up_a_missed_run(run: str, start: str) -> None:
    assert only(timer(run), "Timer", "Persistent") == "no"


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_timer_is_not_coalesced_into_the_window(run: str, start: str) -> None:
    unit = timer(run)
    assert only(unit, "Timer", "AccuracySec") == "1s"
    assert "RandomizedDelaySec" not in unit["Timer"]


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_runbook_window_opens_when_the_timer_fires(run: str, start: str) -> None:
    runbook = (DEPLOY_DIR / "RUNBOOK.md").read_text(encoding="utf-8")
    windows = re.findall(rf"^{WINDOW_VARIABLE[run]}=(\d\d:\d\d)-\d\d:\d\d$", runbook, re.M)
    assert windows == [start]


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze absent")
@pytest.mark.parametrize(("run", "start"), RUNS)
def test_systemd_accepts_the_calendar_expression(run: str, start: str) -> None:
    expression = only(timer(run), "Timer", "OnCalendar")
    result = subprocess.run(
        ["systemd-analyze", "calendar", expression],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert f"{start}:00 Europe/Moscow" in result.stdout
