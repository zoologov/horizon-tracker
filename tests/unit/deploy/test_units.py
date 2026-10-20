"""Tests for the systemd units: each timer starts its run as `horizon` at its range's start.

The units are the only caller of the CLI in production, so the facts the service relies on
are asserted on the parsed files: the user, the environment file, the exact command, a
timer that fires once, on time, at the start of the range the moment is drawn from, and
never catches up a missed run, and a timeout long enough for the wait for that moment.
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
    pytest.param("checkin", "07:30", id="checkin"),
    pytest.param("checkout", "16:30", id="checkout"),
]
RANGE_VARIABLE = {"checkin": "HT_CHECKIN_RANGE", "checkout": "HT_CHECKOUT_RANGE"}
# One run after its timer fires: the wait for the drawn moment (at most the whole range),
# the window of attempts from that moment, then the attempts themselves - the 120 s hold
# of the opened desktop or the log off, and the browser's teardown. RUN_ALLOWANCE is that
# last part with margin; it is what the 15-minute timeout of HT-001 held beside its window.
RUN_ALLOWANCE_MINUTES = 10
TIMEOUT = "60min"

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


def runbook_minutes(text: str, variable: str) -> int:
    """The whole minutes RUNBOOK §2.2 gives ``variable``."""
    values = re.findall(rf"^{variable}=(\d+)$", text, re.M)
    assert len(values) == 1, f"{variable}: expected one line in the RUNBOOK, got {values}"
    return int(values[0])


def runbook_range(text: str, variable: str) -> tuple[int, int]:
    """The range RUNBOOK §2.2 gives ``variable``, as minutes since midnight."""
    found = re.findall(rf"^{variable}=(\d\d):(\d\d)-(\d\d):(\d\d)$", text, re.M)
    assert len(found) == 1, f"{variable}: expected one line in the RUNBOOK, got {found}"
    sh, sm, eh, em = (int(part) for part in found[0])
    return sh * 60 + sm, eh * 60 + em


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
    assert only(service(run), "Service", "TimeoutStartSec") == TIMEOUT


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_service_timeout_covers_the_wait_the_window_and_the_run(run: str, start: str) -> None:
    runbook = (DEPLOY_DIR / "RUNBOOK.md").read_text(encoding="utf-8")
    range_start, range_end = runbook_range(runbook, RANGE_VARIABLE[run])
    grace = runbook_minutes(runbook, "HT_WINDOW_GRACE_MINUTES")
    timeout = only(service(run), "Service", "TimeoutStartSec")
    minutes = re.fullmatch(r"(\d+)min", timeout)
    assert minutes, timeout
    needed = (range_end - range_start) + grace + RUN_ALLOWANCE_MINUTES
    assert needed <= int(minutes.group(1)), f"{timeout} < {needed} min"


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_service_waits_for_the_network(run: str, start: str) -> None:
    unit = service(run)
    assert "network-online.target" in only(unit, "Unit", "After").split()
    assert "network-online.target" in only(unit, "Unit", "Wants").split()


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_service_is_started_only_by_its_timer(run: str, start: str) -> None:
    assert "Install" not in service(run)


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_timer_fires_at_the_range_start_in_moscow(run: str, start: str) -> None:
    unit = timer(run)
    assert only(unit, "Timer", "OnCalendar") == f"*-*-* {start}:00 Europe/Moscow"
    assert only(unit, "Timer", "Unit") == f"horizon-{run}.service"
    assert only(unit, "Install", "WantedBy") == "timers.target"


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_timer_never_catches_up_a_missed_run(run: str, start: str) -> None:
    assert only(timer(run), "Timer", "Persistent") == "no"


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_timer_is_not_coalesced_into_the_range(run: str, start: str) -> None:
    unit = timer(run)
    assert only(unit, "Timer", "AccuracySec") == "1s"
    assert "RandomizedDelaySec" not in unit["Timer"]


@pytest.mark.parametrize(("run", "start"), RUNS)
def test_runbook_range_opens_when_the_timer_fires(run: str, start: str) -> None:
    # A timer later than the range start skips every moment drawn before it as missed;
    # one earlier skips the run as too early. Only the start itself waits for the moment.
    runbook = (DEPLOY_DIR / "RUNBOOK.md").read_text(encoding="utf-8")
    range_start, _ = runbook_range(runbook, RANGE_VARIABLE[run])
    assert f"{range_start // 60:02d}:{range_start % 60:02d}" == start


def test_runbook_names_no_retired_window_variable() -> None:
    # Settings refuses HT_CHECKIN_WINDOW / HT_CHECKOUT_WINDOW: a .env copied from a
    # RUNBOOK that still shows them would stop every run with a configuration error.
    runbook = (DEPLOY_DIR / "RUNBOOK.md").read_text(encoding="utf-8")
    assert not re.search(r"^HT_CHECK(IN|OUT)_WINDOW=", runbook, re.M)


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


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze absent")
def test_systemd_verifies_the_units_without_a_warning(tmp_path: Path) -> None:
    # The CLI exists only on the VPS, so ExecStart is pointed at a binary that exists here;
    # everything else is the shipped text. verify exits 0 on a value it ignores
    # ("Failed to parse TimeoutStartSec=..., ignoring"), so its output must be empty too.
    executable = shutil.which("true")
    assert executable is not None
    paths = []
    for name in sorted(p.name for p in DEPLOY_DIR.iterdir() if p.suffix in {".service", ".timer"}):
        text = (DEPLOY_DIR / name).read_text(encoding="utf-8")
        copy = tmp_path / name
        copy.write_text(text.replace(f"{HOME}/.venv/bin/horizon", executable), encoding="utf-8")
        paths.append(str(copy))
    result = subprocess.run(
        ["systemd-analyze", "verify", *paths],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout + result.stderr == ""
