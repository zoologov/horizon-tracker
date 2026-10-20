"""Tests for the ``horizon`` commands: wiring, flags, exit codes, and what never leaves the run.

Every command runs through ``CliRunner`` with the adapter factory replaced by fakes, so
nothing here reaches the portal, the calendar or Telegram. The few tests that use the
real factory exercise only the paths that open no connection.
"""

import logging
from collections.abc import Iterator
from datetime import datetime
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from click.testing import CliRunner

from horizon_tracker import __version__
from horizon_tracker.cli import main, open_adapters
from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Outcome, Reason
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import SessionState
from horizon_tracker.infrastructure.artifacts import DirectoryArtifactStore
from horizon_tracker.infrastructure.clock import SystemClock
from horizon_tracker.infrastructure.config import ConfigError, Settings
from horizon_tracker.infrastructure.horizon_playwright import PlaywrightHorizonClient
from horizon_tracker.infrastructure.isdayoff import IsDayOffCalendar
from horizon_tracker.infrastructure.telegram import TelegramNotifier
from tests.support.cli_world import DESKTOP, World, cli_log_handlers_restored

MSK = ZoneInfo("Europe/Moscow")
USERNAME = "svc.horizon.user"
PASSWORD = "Pa$$w0rd-never-shown"
TOKEN = "123456:SECRET-token_never-shown"
CHAT_ID = "987654321"

ONE_CHECKIN = ["login", "open_desktop", "desktop_status", "disconnect", "login", "desktop_status"]
ONE_CHECKOUT = ["login", "desktop_status", "log_off", "desktop_status"]


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
        "HT_CHECKIN_WINDOW": "07:55-08:00",
        "HT_CHECKOUT_WINDOW": "17:00-17:05",
        "HT_HOLD_SECONDS": "120",
        "HT_CHROME_PATH": str(chrome),
        "HT_ARTIFACTS_DIR": str(tmp_path / "artifacts"),
    }


# --- the group ------------------------------------------------------------------------


def test_version_is_reported() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_the_three_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    commands = result.output.split("Commands:")[1]
    assert {line.split()[0] for line in commands.strip().splitlines()} == {
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


def test_checkin_in_its_window_checks_in_and_exits_zero(env: dict[str, str | None]) -> None:
    world = World(at(7, 55))

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
    world = World(at(7, 55))

    world.invoke(["checkin"], {**env, "HT_HOLD_SECONDS": "7"})

    assert world.clock.sleeps[0] == 7


def test_a_failed_checkin_exits_one(env: dict[str, str | None]) -> None:
    world = World(at(7, 55))
    world.client.fail_on("open_desktop", HorizonClientError(Reason.DESKTOP_DID_NOT_OPEN), times=9)

    result = world.invoke(["checkin"], env)

    assert result.exit_code == 1
    (report,) = world.notifier.sent
    assert report.outcome is Outcome.FAILED
    assert report.reason is Reason.DESKTOP_DID_NOT_OPEN


def test_checkin_retries_inside_its_window(env: dict[str, str | None]) -> None:
    world = World(at(7, 55))
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
    world = World(at(7, 55))

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


def test_checkout_in_its_window_logs_off_and_exits_zero(env: dict[str, str | None]) -> None:
    world = World(at(17, 0), state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == ONE_CHECKOUT
    (report,) = world.notifier.sent
    assert report.kind is RunKind.CHECKOUT
    assert report.outcome is Outcome.SUCCEEDED
    assert [kind for _, kind in world.opened] == [RunKind.CHECKOUT]


def test_an_unconfirmed_checkout_exits_one(env: dict[str, str | None]) -> None:
    world = World(at(17, 0), state=SessionState.DISCONNECTED)
    world.client.log_off_takes_effect = False

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 1
    assert world.notifier.sent[-1].reason is Reason.LOGOFF_NOT_CONFIRMED


def test_checkout_with_no_session_reports_the_skip_and_exits_zero(
    env: dict[str, str | None],
) -> None:
    world = World(at(17, 0), state=SessionState.NO_SESSION)

    result = world.invoke(["checkout"], env)

    assert result.exit_code == 0, result.output
    assert world.notifier.sent[0].reason is Reason.ALREADY_LOGGED_OFF


def test_checkout_uses_the_checkout_window_not_the_checkin_one(
    env: dict[str, str | None],
) -> None:
    world = World(at(7, 55), state=SessionState.DISCONNECTED)

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
    world = World(at(17, 0), state=SessionState.DISCONNECTED)

    result = world.invoke(["checkout", "--dry-run"], env)

    assert result.exit_code == 0, result.output
    assert world.client.calls == []
    assert world.notifier.sent == []
    assert "dry run: checkout" in result.stdout
    assert "log off from the tile menu" in result.stdout
    assert "hold" not in result.stdout


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
    hour, minute = (7, 55) if command == "checkin" else (17, 0)
    world = World(at(hour, minute), state=state)
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
    assert [line.split(":")[0] for line in lines] == ["settings", "portal", "calendar", "chrome"]
    assert lines[0].startswith("settings: ok")
    assert lines[1] == "portal: ok - client bundles: app-htmlaccess.fake-2312.js"
    assert lines[3] == f"chrome: ok - Chrome 131.0.6778.85 started from {env['HT_CHROME_PATH']}"
    assert world.notifier.sent == []


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


# --- configuration ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "args", [["checkin"], ["checkin", "--dry-run"], ["checkout", "--force"], ["probe"]]
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

    result = world.invoke(["checkin"], {**env, "HT_CHECKIN_WINDOW": "8am"})

    assert result.exit_code == 1
    assert "configuration error: HT_CHECKIN_WINDOW" in result.stderr


def test_a_configuration_error_names_the_variable_but_not_its_value(
    env: dict[str, str | None],
) -> None:
    world = World(at(7, 55))

    result = world.invoke(["checkin"], {**env, "HORIZON_PASSWORD": " "})

    assert result.exit_code == 1
    assert "HORIZON_PASSWORD" in result.stderr


# --- logging and secrets ----------------------------------------------------------------


def test_a_run_logs_to_stderr_and_prints_nothing(env: dict[str, str | None]) -> None:
    world = World(at(7, 55))

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
    World(at(7, 55)).invoke(["checkin"], env)
    result = World(at(7, 55)).invoke(["checkin"], env)

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
        assert "run_kind=checkout" in repr(adapters.horizon)
    assert requests_sent == []


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
