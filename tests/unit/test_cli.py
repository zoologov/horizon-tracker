"""Tests for the ``horizon`` commands: wiring, flags, exit codes, and what never leaves the run.

Every command runs through ``CliRunner`` with the adapter factory replaced by fakes, so
nothing here reaches the portal, the calendar or Telegram. The few tests that use the
real factory exercise only the paths that open no connection.
"""

import logging
import re
import tomllib
from collections.abc import Iterator
from datetime import date, datetime, time
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from click.testing import CliRunner

from horizon_tracker import __version__
from horizon_tracker.cli import build_bot_transport, build_notifier, main, open_adapters
from horizon_tracker.domain.absence import Absence, AbsenceBook, AbsenceKind
from horizon_tracker.domain.ports import (
    BotTransportError,
    HorizonClientError,
    IncomingMessage,
    Notifier,
)
from horizon_tracker.domain.report import Outcome, Reason
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import SessionState
from horizon_tracker.infrastructure.absence_store import JsonAbsenceStore
from horizon_tracker.infrastructure.artifacts import DirectoryArtifactStore
from horizon_tracker.infrastructure.clock import SystemClock
from horizon_tracker.infrastructure.config import ConfigError, Settings
from horizon_tracker.infrastructure.horizon_playwright import PlaywrightHorizonClient
from horizon_tracker.infrastructure.isdayoff import IsDayOffCalendar
from horizon_tracker.infrastructure.telegram import TelegramNotifier
from horizon_tracker.infrastructure.telegram_bot import TelegramBotTransport
from tests.support.bot_api import RecordingBotApi
from tests.support.cli_world import DESKTOP, World, cli_log_handlers_restored
from tests.support.repository_root import repository_root

MSK = ZoneInfo("Europe/Moscow")
USERNAME = "svc.horizon.user"
PASSWORD = "Pa$$w0rd-never-shown"
TOKEN = "123456:SECRET-token_never-shown"
CHAT_ID = "987654321"

ONE_CHECKIN = [
    "login",
    "open_desktop",
    "capture_open_desktop",
    "desktop_status",
    "disconnect",
    "login",
    "desktop_status",
]
ONE_CHECKOUT = ["login", "desktop_status", "log_off", "desktop_status"]

# The day's draw, computed by an oracle independent of the code (the RFC's formula over
# hmac-sha256): under SEED, Wednesday 2026-10-21 draws 07:41 / 16:43 and Thursday
# 2026-10-22 draws 07:59 / 17:03; seeded by USERNAME, 2026-10-21 draws 08:03 / 17:10.
SEED = "horizon-test-seed"
CHECK_IN = (7, 41)
CHECK_OUT = (16, 43)
HOLD_SECONDS = 120.0
CYRILLIC = re.compile("[\u0400-\u04ff]")


def at(hour: int, minute: int, day: int = 21) -> datetime:
    """A moment on Wednesday 2026-10-21 (or another October day), Moscow time."""
    return datetime(2026, 10, day, hour, minute, tzinfo=MSK)


def package_logger() -> logging.Logger:
    return logging.getLogger("horizon_tracker")


@pytest.fixture(autouse=True)
def _detach_cli_log_handler() -> Iterator[None]:
    """Take off the handler an invocation left behind, so it never outlives its stream."""
    with cli_log_handlers_restored():
        yield


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str | None]:
    """A complete environment: every variable set, Chrome present in a temporary file."""
    chrome = tmp_path / "google-chrome"
    chrome.write_text("")
    return {
        "HORIZON_URL": "https://portal.example.invalid/portal/webclient/",
        "HORIZON_USERNAME": USERNAME,
        "HORIZON_PASSWORD": PASSWORD,
        "HORIZON_DESKTOP": DESKTOP,
        "TELEGRAM_BOT_TOKEN": TOKEN,
        "TELEGRAM_CHAT_ID": CHAT_ID,
        "HT_TIMEZONE": "Europe/Moscow",
        "HT_CHECKIN_RANGE": "07:30-08:10",
        "HT_CHECKOUT_RANGE": "16:30-17:10",
        "HT_SESSION_LENGTH_MINUTES": "540",
        "HT_SESSION_EXTRA_MAX_MINUTES": "10",
        "HT_WINDOW_GRACE_MINUTES": "5",
        "HT_JITTER_SEED": SEED,
        "HT_HOLD_SECONDS": "120",
        "HT_CHROME_PATH": str(chrome),
        "HT_ARTIFACTS_DIR": str(tmp_path / "artifacts"),
        # The absences file stays in the test's directory, never the host's state directory.
        "HT_STATE_DIR": str(tmp_path / "state"),
        # Unset whatever the host exports: the default language is what these tests read.
        "HT_LANGUAGE": None,
    }


# --- the group ------------------------------------------------------------------------


def test_version_is_reported() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_the_version_reported_is_the_one_pyproject_declares() -> None:
    # pyproject.toml is the one source a release sets; the package carries no copy of it.
    manifest = tomllib.loads((repository_root() / "pyproject.toml").read_text(encoding="utf-8"))
    declared = manifest["project"]["version"]

    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"horizon, version {declared}\n"


def test_help_lists_the_four_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    commands = result.output.split("Commands:")[1]
    assert {line.split()[0] for line in commands.strip().splitlines()} == {
        "bot",
        "checkin",
        "checkout",
        "probe",
    }


@pytest.mark.parametrize("command", ["checkin", "checkout"])
def test_run_commands_offer_both_flags(command: str) -> None:
    result = CliRunner().invoke(main, [command, "--help"])

    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--force" in result.output


# --- checkin ----------------------------------------------------------------------------


def test_checkin_at_its_drawn_moment_checks_in_and_exits_zero(
    env: dict[str, str | None],
) -> None:
    world = World(at(*CHECK_IN))

    result = world.invoke(["checkin"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == ONE_CHECKIN
    assert [report.outcome for report in world.notifier.sent] == [Outcome.SUCCEEDED]
    assert world.notifier.sent[0].kind is RunKind.CHECKIN
    assert [kind for _, kind in world.opened] == [RunKind.CHECKIN]
    assert world.closed == 1


def test_checkin_holds_the_desktop_for_the_configured_seconds(
    env: dict[str, str | None],
) -> None:
    world = World(at(*CHECK_IN))

    world.invoke(["checkin"], {**env, "HT_HOLD_SECONDS": "7"})

    assert world.clock.sleeps[0] == 7


def test_a_failed_checkin_exits_one(env: dict[str, str | None]) -> None:
    world = World(at(*CHECK_IN))
    world.client.fail_on("open_desktop", HorizonClientError(Reason.DESKTOP_DID_NOT_OPEN), times=9)

    result = world.invoke(["checkin"], env)

    assert result.exit_code == 1
    (report,) = world.notifier.sent
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.DESKTOP_DID_NOT_OPEN


def test_checkin_retries_inside_its_window(env: dict[str, str | None]) -> None:
    world = World(at(*CHECK_IN))
    world.client.fail_on("open_desktop", HorizonClientError(Reason.DESKTOP_DID_NOT_OPEN))

    result = world.invoke(["checkin"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls.count("open_desktop") == 2
    assert [report.outcome for report in world.notifier.sent] == [Outcome.SUCCEEDED]


def test_checkin_outside_its_window_skips_without_logging_in_and_exits_zero(
    env: dict[str, str | None],
) -> None:
    world = World(at(17, 0))

    result = world.invoke(["checkin"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == []
    (report,) = world.notifier.sent
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.WINDOW_MISSED


def test_checkin_on_a_day_off_skips_and_exits_zero(env: dict[str, str | None]) -> None:
    world = World(at(7, 55, day=24), calendar_answer=False)

    result = world.invoke(["checkin"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == []
    assert world.notifier.sent[0].reason is Reason.NON_WORKING_DAY


def test_forced_checkin_ignores_window_and_calendar(env: dict[str, str | None]) -> None:
    world = World(at(12, 0, day=24), calendar_answer=False)

    result = world.invoke(["checkin", "--force"], env)

    assert result.exit_code == 0, result.output
    assert world.calendar.asked == []
    assert world.client.calls == ONE_CHECKIN
    (report,) = world.notifier.sent
    assert report.outcome is Outcome.SUCCEEDED
    assert report.verdict_source is None


def test_checkin_dry_run_lists_the_plan_and_never_logs_in(env: dict[str, str | None]) -> None:
    world = World(at(*CHECK_IN))

    result = world.invoke(["checkin", "--dry-run"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == []
    assert world.notifier.sent == []
    assert "dry run: checkin" in result.stdout
    assert "would run now: yes (run)" in result.stdout
    assert "calendar: isdayoff.ru" in result.stdout
    assert "open desktop 'DEV desktop'" in result.stdout
    assert "hold the desktop open for 120 s" in result.stdout


def test_checkin_dry_run_outside_the_window_says_it_would_not_run(
    env: dict[str, str | None],
) -> None:
    world = World(at(12, 0))

    result = world.invoke(["checkin", "--dry-run"], env)

    assert result.exit_code == 0, result.output
    assert "would run now: no (skip_late)" in result.stdout
    assert world.client.calls == []


def test_forced_dry_run_names_the_force_and_asks_no_calendar(
    env: dict[str, str | None],
) -> None:
    world = World(at(12, 0, day=24), calendar_answer=False)

    result = world.invoke(["checkin", "--dry-run", "--force"], env)

    assert result.exit_code == 0, result.output
    assert world.calendar.asked == []
    assert world.client.calls == []
    assert world.notifier.sent == []
    assert "would run now: yes (run, forced: window and calendar ignored)" in result.stdout
    assert "calendar: not asked" in result.stdout


# --- checkout ---------------------------------------------------------------------------


def test_checkout_at_its_drawn_moment_logs_off_and_exits_zero(
    env: dict[str, str | None],
) -> None:
    world = World(at(*CHECK_OUT), state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == ONE_CHECKOUT
    (report,) = world.notifier.sent
    assert report.kind is RunKind.CHECKOUT
    assert report.outcome is Outcome.SUCCEEDED
    assert [kind for _, kind in world.opened] == [RunKind.CHECKOUT]


def test_an_unconfirmed_checkout_exits_one(env: dict[str, str | None]) -> None:
    world = World(at(*CHECK_OUT), state=SessionState.DISCONNECTED)
    world.client.log_off_takes_effect = False

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 1
    assert world.notifier.sent[-1].reason is Reason.LOGOFF_NOT_CONFIRMED


def test_checkout_with_no_session_reports_the_skip_and_exits_zero(
    env: dict[str, str | None],
) -> None:
    world = World(at(*CHECK_OUT), state=SessionState.NO_SESSION)

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 0, result.output
    assert world.notifier.sent[0].reason is Reason.ALREADY_LOGGED_OFF


def test_checkout_uses_the_check_out_moment_not_the_check_in_one(
    env: dict[str, str | None],
) -> None:
    world = World(at(*CHECK_IN), state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == []
    assert world.notifier.sent[0].outcome is Outcome.SKIPPED


def test_forced_checkout_ignores_window_and_calendar(env: dict[str, str | None]) -> None:
    world = World(at(12, 0, day=24), calendar_answer=False, state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout", "--force"], env)

    assert result.exit_code == 0, result.output
    assert world.calendar.asked == []
    assert world.client.calls == ONE_CHECKOUT


def test_checkout_dry_run_lists_the_plan_and_never_logs_in(env: dict[str, str | None]) -> None:
    world = World(at(*CHECK_OUT), state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout", "--dry-run"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == []
    assert world.notifier.sent == []
    assert "dry run: checkout" in result.stdout
    assert "log off from the tile menu" in result.stdout
    assert "hold" not in result.stdout


# --- absences, and the evening's silence on a skipped day --------------------------------

VACATION = Absence(1, AbsenceKind.VACATION, date(2026, 10, 19), date(2026, 10, 23))


def enter(env: dict[str, str | None], *absences: Absence) -> JsonAbsenceStore:
    """Enter ``absences`` in the file the command reads, as the bot would have left it."""
    store = JsonAbsenceStore(Path(env["HT_STATE_DIR"] or "") / "absences.json")
    store.save(AbsenceBook.of(absences))
    return store


def test_checkin_on_an_absence_day_skips_names_the_absence_and_asks_no_calendar(
    env: dict[str, str | None],
) -> None:
    enter(env, VACATION)
    world = World(at(*CHECK_IN))

    result = world.invoke(["checkin"], env)

    assert result.exit_code == 0, result.output
    assert world.calendar.asked == []
    assert world.client.calls == []
    (report,) = world.notifier.sent
    assert (report.outcome, report.reason, report.absence) == (
        Outcome.SKIPPED,
        Reason.ON_VACATION,
        VACATION,
    )


def test_checkout_on_an_absence_day_sends_nothing_and_exits_zero(
    env: dict[str, str | None],
) -> None:
    enter(env, VACATION)
    world = World(at(*CHECK_OUT), state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == []
    assert world.calendar.asked == []
    assert world.notifier.sent == []


def test_checkout_on_a_day_off_sends_nothing(env: dict[str, str | None]) -> None:
    world = World(at(16, 30, day=24), calendar_answer=False, state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == []
    assert world.notifier.sent == []


@pytest.mark.parametrize(
    ("start", "reason"),
    [(at(16, 0), Reason.TOO_EARLY), (at(18, 0), Reason.WINDOW_MISSED)],
    ids=["too early", "window missed"],
)
def test_an_anomalous_checkout_skip_still_reaches_the_owner(
    env: dict[str, str | None], start: datetime, reason: Reason
) -> None:
    world = World(start, state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 0, result.output
    (report,) = world.notifier.sent
    assert report.reason is reason


def test_forced_checkin_ignores_an_absence(env: dict[str, str | None]) -> None:
    enter(env, VACATION)
    world = World(at(12, 0))

    result = world.invoke(["checkin", "--force"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == ONE_CHECKIN


def test_an_unreadable_absences_file_does_not_stop_the_checkin(
    env: dict[str, str | None],
) -> None:
    state = Path(env["HT_STATE_DIR"] or "")
    state.mkdir()
    (state / "absences.json").write_text("{not json", encoding="utf-8")
    world = World(at(*CHECK_IN))

    result = world.invoke(["checkin"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == ONE_CHECKIN
    assert "absences could not be read (AbsenceStoreError)" in result.stderr


def test_a_dry_run_on_an_absence_day_says_it_would_skip_and_asks_no_calendar(
    env: dict[str, str | None],
) -> None:
    enter(env, VACATION)
    world = World(at(*CHECK_IN))

    result = world.invoke(["checkin", "--dry-run"], env)

    assert result.exit_code == 0, result.output
    assert world.calendar.asked == []
    assert "would run now: no (skip_absent)" in result.stdout
    assert "calendar: not asked (an absence covers today)" in result.stdout


@pytest.mark.parametrize(
    ("command", "report_step"),
    [
        ("checkin", "send one report to Telegram\n"),
        (
            "checkout",
            "send one report to Telegram, unless the day is skipped: the morning reports it\n",
        ),
    ],
)
def test_a_dry_run_names_the_absence_check_and_which_reports_it_sends(
    env: dict[str, str | None], command: str, report_step: str
) -> None:
    result = World(at(*CHECK_IN)).invoke([command, "--dry-run"], env)

    assert result.exit_code == 0, result.output
    assert "skip the day if an absence entered through the bot covers it" in result.stdout
    assert result.stdout.endswith(report_step)


# --- the day's drawn moments -----------------------------------------------------------


def test_a_checkin_started_at_its_range_start_waits_for_the_drawn_moment(
    env: dict[str, str | None],
) -> None:
    world = World(at(7, 30))

    result = world.invoke(["checkin"], env)

    assert result.exit_code == 0, result.output
    assert world.clock.sleeps == [11 * 60.0, HOLD_SECONDS]
    assert world.client.calls == ONE_CHECKIN
    (report,) = world.notifier.sent
    assert report.outcome is Outcome.SUCCEEDED
    assert report.planned_at == time(*CHECK_IN)


def test_a_checkout_started_at_its_range_start_waits_for_the_drawn_moment(
    env: dict[str, str | None],
) -> None:
    world = World(at(16, 30), state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 0, result.output
    assert world.clock.sleeps == [13 * 60.0]
    assert world.client.calls == ONE_CHECKOUT
    (report,) = world.notifier.sent
    assert report.planned_at == time(*CHECK_OUT)


@pytest.mark.parametrize(("command", "start"), [("checkin", at(7, 29)), ("checkout", at(16, 29))])
def test_a_run_started_before_its_own_range_is_skipped_without_waiting(
    command: str, start: datetime, env: dict[str, str | None]
) -> None:
    world = World(start, state=SessionState.DISCONNECTED)

    result = world.invoke([command], env)

    assert result.exit_code == 0, result.output
    assert world.clock.sleeps == []
    assert world.client.calls == []
    (report,) = world.notifier.sent
    assert report.outcome is Outcome.SKIPPED
    assert report.reason is Reason.TOO_EARLY


@pytest.mark.parametrize(("grace", "succeeded"), [("5", False), ("10", True)])
def test_the_window_lasts_the_configured_grace_from_the_moment(
    grace: str, succeeded: bool, env: dict[str, str | None]
) -> None:
    world = World(at(7, 47))

    world.invoke(["checkin"], {**env, "HT_WINDOW_GRACE_MINUTES": grace})

    (report,) = world.notifier.sent
    assert (report.outcome is Outcome.SUCCEEDED) is succeeded


def test_each_day_draws_its_own_moments(env: dict[str, str | None]) -> None:
    world = World(at(7, 30, day=22))

    world.invoke(["checkin"], env)

    assert world.clock.sleeps[0] == 29 * 60.0
    assert world.notifier.sent[0].planned_at == time(7, 59)


@pytest.mark.parametrize("command", ["checkin", "checkout"])
def test_a_forced_run_does_not_wait_for_the_drawn_moment(
    command: str, env: dict[str, str | None]
) -> None:
    world = World(at(7, 30), state=SessionState.DISCONNECTED)

    result = world.invoke([command, "--force"], env)

    assert result.exit_code == 0, result.output
    assert world.clock.sleeps == ([HOLD_SECONDS] if command == "checkin" else [])
    (report,) = world.notifier.sent
    assert report.outcome is Outcome.SUCCEEDED
    assert report.planned_at is None


def test_a_forced_run_just_before_midnight_still_runs(env: dict[str, str | None]) -> None:
    world = World(datetime(2026, 10, 21, 23, 58, 30, tzinfo=MSK))

    result = world.invoke(["checkin", "--force"], env)

    assert result.exit_code == 0, result.output
    assert [report.outcome for report in world.notifier.sent] == [Outcome.SUCCEEDED]


@pytest.mark.parametrize("args", [["checkin", "--dry-run"], ["checkout", "--dry-run", "--force"]])
def test_a_dry_run_names_both_of_the_days_moments(
    args: list[str], env: dict[str, str | None]
) -> None:
    world = World(at(12, 0))

    result = world.invoke(args, env)

    assert result.exit_code == 0, result.output
    assert "schedule: today 07:41 / 16:43" in result.stdout.splitlines()


def test_a_dry_run_before_the_moment_names_the_wait(env: dict[str, str | None]) -> None:
    world = World(at(7, 30))

    result = world.invoke(["checkin", "--dry-run"], env)

    assert result.exit_code == 0, result.output
    assert "would wait until: 07:41" in result.stdout.splitlines()
    assert "would run now: yes (run)" in result.stdout
    assert world.clock.sleeps == []


@pytest.mark.parametrize("now", [at(7, 41), at(12, 0)])
def test_a_dry_run_that_would_not_wait_names_no_wait(
    now: datetime, env: dict[str, str | None]
) -> None:
    result = World(now).invoke(["checkin", "--dry-run"], env)

    assert "would wait" not in result.stdout


# --- artifacts --------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["checkin", "checkout"])
def test_a_run_prunes_old_artifacts_once(command: str, env: dict[str, str | None]) -> None:
    world = World(at(7, 55))

    world.invoke([command], env)

    assert world.artifacts.prunes == 1


@pytest.mark.parametrize(
    ("command", "state"),
    [("checkin", SessionState.NO_SESSION), ("checkout", SessionState.DISCONNECTED)],
)
def test_an_artifact_directory_that_cannot_be_pruned_does_not_stop_the_run(
    command: str, state: SessionState, env: dict[str, str | None]
) -> None:
    world = World(at(*(CHECK_IN if command == "checkin" else CHECK_OUT)), state=state)
    world.artifacts.prune_error = PermissionError(13, "Permission denied", "/opt/x/artifacts")

    result = world.invoke([command], env)

    assert result.exit_code == 0
    assert [report.outcome for report in world.notifier.sent] == [Outcome.SUCCEEDED]
    assert "PermissionError" in result.stderr
    assert "/opt/x/artifacts" not in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("args", [["checkin", "--dry-run"], ["checkout", "--dry-run"], ["probe"]])
def test_a_dry_run_and_a_probe_delete_nothing(args: list[str], env: dict[str, str | None]) -> None:
    world = World(at(7, 55))

    world.invoke(args, env)

    assert world.artifacts.prunes == 0


# --- probe ------------------------------------------------------------------------------


def test_probe_reports_every_check_and_exits_zero(env: dict[str, str | None]) -> None:
    world = World(at(12, 0))

    result = world.invoke(["probe"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == ["client_bundles", "browser_version"]
    lines = result.stdout.splitlines()
    assert [line.split(":")[0] for line in lines] == [
        "settings",
        "portal",
        "calendar",
        "chrome",
        "absences",
        "schedule",
    ]
    assert lines[0].startswith("settings: ok")
    assert lines[1] == "portal: ok - client bundles: app-htmlaccess.fake-2312.js"
    assert lines[3] == f"chrome: ok - Chrome 131.0.6778.85 started from {env['HT_CHROME_PATH']}"
    assert lines[4] == f"absences: ok - none ({env['HT_STATE_DIR']}/absences.json)"
    assert lines[5] == "schedule: today 07:41 / 16:43"
    assert world.notifier.sent == []


def test_probe_names_the_ranges_of_the_draw_among_the_settings(
    env: dict[str, str | None],
) -> None:
    result = World(at(12, 0)).invoke(["probe"], env)

    settings_line = result.stdout.splitlines()[0]
    assert "check-in 07:30-08:10, check-out 16:30-17:10, Europe/Moscow" in settings_line


@pytest.mark.parametrize(
    ("seed", "day", "line"),
    [
        (SEED, 22, "schedule: today 07:59 / 17:03"),
        (None, 21, "schedule: today 08:03 / 17:10"),
        ("", 21, "schedule: today 08:03 / 17:10"),
    ],
    ids=["another-day", "seed-unset-username", "seed-blank-username"],
)
def test_probe_names_the_moments_drawn_for_today_from_the_configured_seed(
    seed: str | None, day: int, line: str, env: dict[str, str | None]
) -> None:
    result = World(at(12, 0, day=day)).invoke(["probe"], {**env, "HT_JITTER_SEED": seed})

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[5] == line


def test_the_probe_never_shows_the_seed_of_the_draw(env: dict[str, str | None]) -> None:
    result = World(at(12, 0)).invoke(["probe"], env)

    assert SEED not in result.output


def test_probe_with_an_unreachable_portal_exits_one(env: dict[str, str | None]) -> None:
    world = World(at(12, 0))
    world.client.fail_on("client_bundles", HorizonClientError(Reason.PORTAL_UNREACHABLE))

    result = world.invoke(["probe"], env)

    assert result.exit_code == 1
    assert "portal: failed - no answer: portal_unreachable" in result.stdout


def test_probe_without_chrome_exits_one(env: dict[str, str | None], tmp_path: Path) -> None:
    world = World(at(12, 0))
    missing = tmp_path / "no-chrome-here"

    result = world.invoke(["probe"], {**env, "HT_CHROME_PATH": str(missing)})

    assert result.exit_code == 1
    assert f"chrome: failed - not found at {missing}" in result.stdout


def test_probe_with_the_calendar_down_is_degraded_but_exits_zero(
    env: dict[str, str | None],
) -> None:
    world = World(at(12, 0), calendar_answer=None)

    result = world.invoke(["probe"], env)

    assert result.exit_code == 0, result.output
    assert "calendar: degraded" in result.stdout


def test_probe_reads_the_absences_file_under_the_state_directory(
    env: dict[str, str | None],
) -> None:
    absences = Path(env["HT_STATE_DIR"] or "") / "absences.json"
    absences.parent.mkdir()
    absences.write_text(
        '{"last_issued": 1, "absences": [{"id": 1, "kind": "vacation", '
        '"first_day": "2026-11-03", "last_day": "2026-11-14"}]}'
    )

    result = World(at(12, 0)).invoke(["probe"], env)

    assert result.exit_code == 0, result.output
    assert f"absences: ok - 1 entered, next: vacation 03.11\u201314.11 ({absences})" in (
        result.stdout.splitlines()
    )


def test_probe_with_an_unreadable_absences_file_exits_one(env: dict[str, str | None]) -> None:
    absences = Path(env["HT_STATE_DIR"] or "") / "absences.json"
    absences.parent.mkdir()
    absences.write_text("[]")

    result = World(at(12, 0)).invoke(["probe"], env)

    assert result.exit_code == 1
    assert f"absences: failed - {absences}: " in result.stdout
    assert "schedule: today 07:41 / 16:43" in result.stdout.splitlines()


# --- the bot ----------------------------------------------------------------------------


def owner_writes(update_id: int, text: str, chat_id: str = CHAT_ID) -> IncomingMessage:
    return IncomingMessage(update_id=update_id, chat_id=chat_id, text=text)


def absences_in(env: dict[str, str | None]) -> tuple[Absence, ...]:
    return JsonAbsenceStore(Path(env["HT_STATE_DIR"] or "") / "absences.json").load().absences


def test_the_bot_answers_the_owner_and_exits_zero_when_stopped(
    env: dict[str, str | None],
) -> None:
    world = World(at(12, 0))
    world.bot.deliver([owner_writes(1, "/add vacation 03.11-14.11")])

    result = world.invoke(["bot"], env)

    assert result.exit_code == 0, result.output
    assert world.bot.replies == [
        (CHAT_ID, "Absence 1 entered: vacation from 03.11.2026 to 14.11.2026")
    ]
    assert "bot started" in result.stderr
    assert "bot stopped" in result.stderr
    assert result.stdout == ""


def test_the_bot_keeps_the_absence_in_the_file_under_the_state_directory(
    env: dict[str, str | None],
) -> None:
    world = World(at(12, 0))
    world.bot.deliver([owner_writes(1, "/add dayoff 20.11")])

    world.invoke(["bot"], env)

    assert absences_in(env) == (
        Absence(1, AbsenceKind.DAY_OFF, date(2026, 11, 20), date(2026, 11, 20)),
    )
    probe = World(at(12, 0)).invoke(["probe"], env)
    assert "absences: ok - 1 entered, next: day off taken 20.11" in probe.stdout


def test_the_bot_serves_only_the_configured_chat(env: dict[str, str | None]) -> None:
    world = World(at(12, 0))
    world.bot.deliver([owner_writes(1, "/add vacation 03.11-14.11", chat_id="1000")])

    result = world.invoke(["bot"], env)

    assert result.exit_code == 0
    assert world.bot.replies == []
    assert absences_in(env) == ()
    assert "chat 1000" in result.stderr
    assert "/add" not in result.stderr


def test_the_bot_replies_in_the_configured_language(env: dict[str, str | None]) -> None:
    world = World(at(12, 0))
    world.bot.deliver([owner_writes(1, "/list")])

    world.invoke(["bot"], {**env, "HT_LANGUAGE": "ru"})

    assert world.bot.replies == [(CHAT_ID, "Отсутствий не внесено")]


def test_the_bot_starts_an_absence_tomorrow_once_the_configured_check_in_range_began(
    env: dict[str, str | None],
) -> None:
    world = World(at(9, 0))
    world.bot.deliver([owner_writes(1, "/add sick 21.10-23.10")])

    world.invoke(["bot"], {**env, "HT_CHECKIN_RANGE": "09:00-09:30"})

    [(_, text)] = world.bot.replies
    assert text.splitlines() == [
        "Absence 1 entered: sick leave from 22.10.2026 to 23.10.2026",
        "Today's check-in range began at 09:00, so an absence starts tomorrow at the earliest; "
        "this evening's check-out runs as usual",
    ]


def test_the_bot_rides_out_a_failed_poll(env: dict[str, str | None]) -> None:
    world = World(at(12, 0))
    world.bot.script(BotTransportError("getUpdates failed: ConnectError"))
    world.bot.deliver([owner_writes(1, "/list")])

    result = world.invoke(["bot"], env)

    assert result.exit_code == 0
    assert world.bot.replies == [(CHAT_ID, "No absences entered")]
    assert world.clock.sleeps == [5.0]
    assert "poll failed (BotTransportError)" in result.stderr


def test_the_bot_never_prints_a_secret(env: dict[str, str | None]) -> None:
    world = World(at(12, 0))
    world.bot.deliver([owner_writes(1, "/list"), owner_writes(2, "/help", chat_id="1000")])

    result = world.invoke(["bot"], env)

    for secret in (PASSWORD, TOKEN, USERNAME):
        assert secret not in result.output


# --- configuration ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "args", [["checkin"], ["checkin", "--dry-run"], ["checkout", "--force"], ["probe"], ["bot"]]
)
def test_a_missing_variable_is_named_and_exits_one(
    args: list[str], env: dict[str, str | None]
) -> None:
    world = World(at(7, 55))

    result = world.invoke(args, {**env, "HORIZON_URL": None})

    assert result.exit_code == 1
    assert "configuration error: HORIZON_URL: is required and not set" in result.stderr
    assert "Traceback" not in result.output
    assert world.opened == []
    assert world.notifier.sent == []


def test_a_malformed_variable_is_named_and_exits_one(env: dict[str, str | None]) -> None:
    world = World(at(7, 55))

    result = world.invoke(["checkin"], {**env, "HT_CHECKIN_RANGE": "8am"})

    assert result.exit_code == 1
    assert "configuration error: HT_CHECKIN_RANGE" in result.stderr


def test_a_configuration_error_names_the_variable_but_not_its_value(
    env: dict[str, str | None],
) -> None:
    world = World(at(7, 55))

    result = world.invoke(["checkin"], {**env, "HORIZON_PASSWORD": " "})

    assert result.exit_code == 1
    assert "HORIZON_PASSWORD" in result.stderr


# --- logging and secrets ----------------------------------------------------------------


def test_a_run_logs_to_stderr_and_prints_nothing(env: dict[str, str | None]) -> None:
    world = World(at(*CHECK_IN))

    result = world.invoke(["checkin"], env)

    assert result.stdout == ""
    assert "checkin run succeeded" in result.stderr


@pytest.mark.parametrize("args", [["checkin"], ["checkout"], ["checkin", "--dry-run"], ["probe"]])
def test_no_secret_reaches_the_output_even_on_failure(
    args: list[str], env: dict[str, str | None]
) -> None:
    world = World(at(7, 55), state=SessionState.DISCONNECTED)
    for method in ("login", "client_bundles", "browser_version"):
        world.client.fail_on(method, HorizonClientError(Reason.LOGIN_REJECTED), times=9)

    result = world.invoke(args, env)

    for secret in (PASSWORD, TOKEN, USERNAME, CHAT_ID):
        assert secret not in result.output


def test_repeated_invocations_keep_one_cli_handler(env: dict[str, str | None]) -> None:
    World(at(*CHECK_IN)).invoke(["checkin"], env)
    result = World(at(*CHECK_IN)).invoke(["checkin"], env)

    assert result.stderr.count("checkin run succeeded") == 1
    assert len(package_logger().handlers) == 1


# --- the real factory -------------------------------------------------------------------


def settings_from(env: dict[str, str | None]) -> Settings:
    return Settings.from_env({key: value for key, value in env.items() if value is not None})


@pytest.fixture
def requests_sent(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Every HTTP request the real wiring makes, answered locally so none leaves the host.

    A test that expects the wiring to stay offline asserts this list is empty, so a
    regression shows as a failed assertion instead of a call to Telegram or isdayoff.ru.
    """
    sent: list[httpx.Request] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(503)

    monkeypatch.setattr(
        httpx, "Client", partial(httpx.Client, transport=httpx.MockTransport(refuse))
    )
    return sent


def test_the_real_factory_builds_the_production_adapters(
    env: dict[str, str | None], requests_sent: list[httpx.Request]
) -> None:
    with open_adapters(settings_from(env), RunKind.CHECKOUT) as adapters:
        assert isinstance(adapters.clock, SystemClock)
        assert isinstance(adapters.calendar, IsDayOffCalendar)
        assert isinstance(adapters.notifier, TelegramNotifier)
        assert isinstance(adapters.horizon, PlaywrightHorizonClient)
        assert isinstance(adapters.artifacts, DirectoryArtifactStore)
        assert isinstance(adapters.absences, JsonAbsenceStore)
        assert isinstance(adapters.bot, TelegramBotTransport)
        assert "run_kind=checkout" in repr(adapters.horizon)
    assert requests_sent == []


def test_the_bot_transport_refuses_a_malformed_token_as_configuration(
    env: dict[str, str | None],
) -> None:
    settings = settings_from({**env, "TELEGRAM_BOT_TOKEN": "nonsense"})

    with pytest.raises(ConfigError) as caught, httpx.Client() as http:
        build_bot_transport(settings, http)

    assert caught.value.variable == "TELEGRAM_BOT_TOKEN"
    assert "nonsense" not in str(caught.value)


def test_the_real_factory_refuses_a_malformed_token_as_configuration(
    env: dict[str, str | None],
) -> None:
    settings = settings_from({**env, "TELEGRAM_BOT_TOKEN": TOKEN + "\n"})

    with pytest.raises(ConfigError) as caught, open_adapters(settings, RunKind.CHECKIN):
        pass

    assert caught.value.variable == "TELEGRAM_BOT_TOKEN"
    assert TOKEN not in str(caught.value)


def test_the_default_wiring_turns_a_malformed_token_into_exit_one(
    env: dict[str, str | None], requests_sent: list[httpx.Request]
) -> None:
    result = CliRunner().invoke(main, ["checkin"], env={**env, "TELEGRAM_BOT_TOKEN": "nonsense"})

    assert result.exit_code == 1
    assert "configuration error: TELEGRAM_BOT_TOKEN" in result.stderr
    assert "nonsense" not in result.output
    assert requests_sent == []


def test_the_default_wiring_runs_a_forced_dry_run_offline(
    env: dict[str, str | None], requests_sent: list[httpx.Request]
) -> None:
    result = CliRunner().invoke(main, ["checkout", "--dry-run", "--force"], env=env)

    assert result.exit_code == 0, result.output
    assert "dry run: checkout" in result.stdout
    assert "calendar: not asked" in result.stdout
    assert requests_sent == []


# --- the language of what a person reads ------------------------------------------------


def russian(env: dict[str, str | None]) -> dict[str, str | None]:
    return {**env, "HT_LANGUAGE": "ru"}


def test_the_probe_names_the_language_among_the_settings(env: dict[str, str | None]) -> None:
    result = World(at(12, 0)).invoke(["probe"], env)

    assert result.stdout.splitlines()[0].endswith(", Europe/Moscow, language en")


def test_the_probe_reads_in_the_configured_language(env: dict[str, str | None]) -> None:
    result = World(at(12, 0)).invoke(["probe"], russian(env))

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0].startswith("настройки: в порядке - портал ")
    assert lines[0].endswith(", Europe/Moscow, язык ru")
    assert lines[1] == "портал: в порядке - бандлы клиента: app-htmlaccess.fake-2312.js"
    assert lines[2] == "календарь: в порядке - isdayoff.ru: 2026-10-21 - рабочий день"
    assert lines[3] == (
        f"браузер chrome: в порядке - Chrome 131.0.6778.85 запущен из {env['HT_CHROME_PATH']}"
    )
    assert lines[4] == f"отсутствия: в порядке - нет ({env['HT_STATE_DIR']}/absences.json)"
    assert lines[5] == "расписание: сегодня 07:41 / 16:43"


def test_a_failed_probe_check_reads_in_the_configured_language(
    env: dict[str, str | None],
) -> None:
    world = World(at(12, 0), calendar_answer=None)
    world.client.fail_on("client_bundles", HorizonClientError(Reason.PORTAL_UNREACHABLE))

    result = world.invoke(["probe"], russian(env))

    assert result.exit_code == 1
    assert "портал: сбой - нет ответа: portal_unreachable" in result.stdout
    assert "календарь: частично - isdayoff.ru не ответил за 2026-10-21" in result.stdout


def test_a_dry_run_reads_in_the_configured_language(env: dict[str, str | None]) -> None:
    result = World(at(7, 30)).invoke(["checkin", "--dry-run"], russian(env))

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        "пробный прогон: checkin в 2026-10-21 07:30:00 MSK",
        "запустился бы сейчас: да (run)",
        "ждал бы до: 07:41",
        "календарь: календарь isdayoff.ru",
        "расписание: сегодня 07:41 / 16:43",
        "шаги одной попытки:",
        "  1. войти на портал Horizon",
        "  2. открыть стол 'DEV desktop' и дождаться Blast-соединения и прорисованного стола",
        "  3. держать стол открытым 120 секунд, чтобы завершился вход в Windows",
        "  4. прочитать состояние сессии, затем отключиться (сессия Windows продолжает работать)",
        "  5. войти снова и убедиться, что сессия в состоянии DISCONNECTED",
        "  6. пропустить день, на который через бота внесено отсутствие, ещё до вопроса календарю",
        "  7. ждать разыгранного момента 07:41, если запуск начат от 07:30; "
        "более ранний запуск пропускается как слишком ранний",
        "  8. повторять неудачную попытку, до 3 попыток через 30 секунд, пока позволяет окно",
        "  9. отправить один отчёт в Telegram",
    ]


def test_a_forced_dry_run_names_the_force_in_the_configured_language(
    env: dict[str, str | None],
) -> None:
    result = World(at(12, 0)).invoke(["checkout", "--dry-run", "--force"], russian(env))

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert "запустился бы сейчас: да (run, принудительно: окно и календарь не учитываются)" in lines
    assert "календарь: не спрашивали (принудительно)" in lines


def test_a_dry_run_on_a_day_the_calendar_could_not_answer_names_the_fallback(
    env: dict[str, str | None],
) -> None:
    result = World(at(*CHECK_IN), calendar_answer=None).invoke(["checkin", "--dry-run"], env)

    assert "calendar: isdayoff.ru unreachable, Mon-Fri rule" in result.stdout.splitlines()


@pytest.mark.parametrize(
    "args", [["probe"], ["checkin", "--dry-run"], ["checkout", "--dry-run", "--force"]]
)
def test_no_line_of_the_output_falls_into_the_other_language(
    args: list[str], env: dict[str, str | None]
) -> None:
    english = World(at(7, 30)).invoke(args, env).stdout.splitlines()
    russian_lines = World(at(7, 30)).invoke(args, russian(env)).stdout.splitlines()

    assert english
    assert not [line for line in english if CYRILLIC.search(line)]
    assert len(russian_lines) == len(english)
    assert not [line for line in russian_lines if not CYRILLIC.search(line)]


def test_the_log_stays_english_whatever_the_language(env: dict[str, str | None]) -> None:
    result = World(at(*CHECK_IN)).invoke(["checkin"], russian(env))

    assert result.exit_code == 0, result.output
    assert "checkin run succeeded" in result.stderr
    assert not CYRILLIC.search(result.stderr)


def test_a_configuration_error_is_said_once_to_an_english_reader(
    env: dict[str, str | None],
) -> None:
    result = World(at(7, 55)).invoke(["checkin"], {**env, "HORIZON_URL": None})

    assert result.exit_code == 1
    assert result.stderr.count("HORIZON_URL") == 1
    assert not CYRILLIC.search(result.stderr)


def test_a_configuration_error_reaches_a_russian_reader_in_russian_beside_the_english_log(
    env: dict[str, str | None],
) -> None:
    result = World(at(7, 55)).invoke(["probe"], {**russian(env), "HORIZON_URL": None})

    assert result.exit_code == 1
    lines = result.stderr.splitlines()
    assert any(
        line.endswith("configuration error: HORIZON_URL: is required and not set") for line in lines
    )
    assert "ошибка настройки: HORIZON_URL: обязательна и не задана" in lines
    assert result.stdout == ""


@pytest.mark.parametrize("value", ["de", "RU"])
def test_an_unknown_language_is_refused_at_start_naming_the_accepted_codes(
    value: str, env: dict[str, str | None]
) -> None:
    world = World(at(7, 55))

    result = world.invoke(["checkin"], {**env, "HT_LANGUAGE": value})

    assert result.exit_code == 1
    assert f"configuration error: HT_LANGUAGE: expected one of en, ru, got {value!r}" in (
        result.stderr
    )
    assert not CYRILLIC.search(result.stderr)
    assert world.opened == []


def test_a_refused_token_reaches_a_russian_reader_in_russian(
    env: dict[str, str | None], requests_sent: list[httpx.Request]
) -> None:
    result = CliRunner().invoke(
        main, ["checkin"], env={**russian(env), "TELEGRAM_BOT_TOKEN": "nonsense"}
    )

    assert result.exit_code == 1
    assert "ошибка настройки: TELEGRAM_BOT_TOKEN: искажён" in result.stderr
    assert "nonsense" not in result.output


@pytest.mark.parametrize(
    ("language", "headline"), [(None, "Check-in succeeded"), ("ru", "Вход выполнен")]
)
def test_the_notification_is_built_in_the_configured_language(
    language: str | None, headline: str, env: dict[str, str | None]
) -> None:
    # The notifier is built the production way, from the settings the command loaded.
    bot = RecordingBotApi()

    def deliver(settings: Settings) -> Notifier:
        return build_notifier(settings, bot.client())

    world = World(at(*CHECK_IN), delivery=deliver)

    result = world.invoke(["checkin"], {**env, "HT_LANGUAGE": language})

    assert result.exit_code == 0, result.output
    [message] = bot.messages
    assert message.text.splitlines()[0] == headline
