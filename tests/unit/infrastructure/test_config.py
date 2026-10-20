"""Tests for the settings read from the environment: required secrets, defaults, masking."""

from collections.abc import Callable
from datetime import time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.domain.schedule import TimeRange, Window
from horizon_tracker.infrastructure.config import ConfigError, Settings

PASSWORD = "S3cret-Pa55word!"
TOKEN = "123456:AAH-bot-token-value"
CHAT_ID = "987654321"
USERNAME = "corp\\ivanov"
SEED = "jitter-seed-value"
RETIRED = {"HT_CHECKIN_WINDOW": "HT_CHECKIN_RANGE", "HT_CHECKOUT_WINDOW": "HT_CHECKOUT_RANGE"}
RANGES = ("HT_CHECKIN_RANGE", "HT_CHECKOUT_RANGE")
MINUTES = ("HT_SESSION_LENGTH_MINUTES", "HT_SESSION_EXTRA_MAX_MINUTES", "HT_WINDOW_GRACE_MINUTES")

REQUIRED = {
    "HORIZON_URL": "https://horizon.example.invalid/portal/webclient/",
    "HORIZON_USERNAME": USERNAME,
    "HORIZON_PASSWORD": PASSWORD,
    "TELEGRAM_BOT_TOKEN": TOKEN,
    "TELEGRAM_CHAT_ID": CHAT_ID,
}

FULL = {
    **REQUIRED,
    "HORIZON_DESKTOP": "QA desktop",
    "HT_TIMEZONE": "Asia/Tokyo",
    "HT_CHECKIN_RANGE": "09:10-09:40",
    "HT_CHECKOUT_RANGE": "18:00-18:45",
    "HT_SESSION_LENGTH_MINUTES": "480",
    "HT_SESSION_EXTRA_MAX_MINUTES": "15",
    "HT_WINDOW_GRACE_MINUTES": "7",
    "HT_JITTER_SEED": SEED,
    "HT_HOLD_SECONDS": "300",
    "HT_CHROME_PATH": "/opt/chrome/chrome",
    "HT_ARTIFACTS_DIR": "/var/tmp/horizon-artifacts",
}


def _env(**overrides: str | None) -> dict[str, str]:
    """The required set with overrides; an override of ``None`` removes the variable."""
    environ = dict(REQUIRED)
    for name, value in overrides.items():
        if value is None:
            environ.pop(name, None)
        else:
            environ[name] = value
    return environ


# --- the full set ---------------------------------------------------------------


def test_every_variable_is_read_into_its_field() -> None:
    settings = Settings.from_env(FULL)

    assert settings.horizon_url == FULL["HORIZON_URL"]
    assert settings.username == USERNAME
    assert settings.password == PASSWORD
    assert settings.desktop == "QA desktop"
    assert settings.telegram_token == TOKEN
    assert settings.telegram_chat_id == CHAT_ID
    assert settings.timezone == ZoneInfo("Asia/Tokyo")
    assert settings.checkin_range == TimeRange(time(9, 10), time(9, 40))
    assert settings.checkout_range == TimeRange(time(18, 0), time(18, 45))
    assert settings.session_length == timedelta(minutes=480)
    assert settings.session_extra_max == timedelta(minutes=15)
    assert settings.window_grace == timedelta(minutes=7)
    assert settings.jitter_seed == SEED.encode()
    assert settings.hold_seconds == 300
    assert settings.chrome_path == Path("/opt/chrome/chrome")
    assert settings.artifacts_dir == Path("/var/tmp/horizon-artifacts")


def test_unset_optional_variables_take_the_documented_defaults() -> None:
    settings = Settings.from_env(REQUIRED)

    assert settings.desktop == "DEV desktop"
    assert settings.timezone == ZoneInfo("Europe/Moscow")
    assert settings.checkin_range == TimeRange(time(7, 30), time(8, 10))
    assert settings.checkout_range == TimeRange(time(16, 30), time(17, 10))
    assert settings.session_length == timedelta(minutes=540)
    assert settings.session_extra_max == timedelta(minutes=10)
    assert settings.window_grace == timedelta(minutes=5)
    assert settings.hold_seconds == 120
    assert settings.chrome_path == Path("/usr/bin/google-chrome")
    assert settings.artifacts_dir == Path("/opt/horizon-tracker/artifacts")


def test_unset_or_blank_optional_durations_and_ranges_take_their_defaults() -> None:
    blank = dict.fromkeys((*RANGES, *MINUTES), "  ")

    assert Settings.from_env(_env(**blank)) == Settings.from_env(REQUIRED)


# --- the seed of the draw -------------------------------------------------------


def test_without_a_seed_the_draw_is_seeded_by_the_username_in_utf8() -> None:
    settings = Settings.from_env(_env(HORIZON_USERNAME="corp\\иванов"))

    assert settings.jitter_seed == "corp\\иванов".encode()


def test_a_blank_seed_counts_as_unset() -> None:
    settings = Settings.from_env(_env(HT_JITTER_SEED="   "))

    assert settings.jitter_seed == USERNAME.encode()


def test_an_explicit_seed_is_taken_verbatim_in_utf8() -> None:
    settings = Settings.from_env(_env(HT_JITTER_SEED=" зерно 7 "))

    assert settings.jitter_seed == " зерно 7 ".encode()


# --- the HT-001 windows ---------------------------------------------------------


def test_the_cli_keeps_the_fixed_ht001_windows_until_it_draws_its_moments() -> None:
    # Interim (HT-003 BEAD-03 -> BEAD-04): no variable sets these any more; the CLI
    # reads them until it builds each run's window from the drawn moment.
    settings = Settings.from_env(FULL)

    assert settings.checkin_window == Window(time(7, 55), time(8, 0))
    assert settings.checkout_window == Window(time(17, 0), time(17, 5))


@pytest.mark.parametrize("value", ["07:55-08:00", ""])
@pytest.mark.parametrize(("retired", "successor"), sorted(RETIRED.items()))
def test_a_retired_window_variable_is_refused_with_its_successors_named(
    retired: str, successor: str, value: str
) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env({**FULL, retired: value})

    assert caught.value.variable == retired
    message = str(caught.value)
    assert successor in message
    assert "HT_WINDOW_GRACE_MINUTES" in message


def test_a_retired_variable_is_named_before_any_other_problem() -> None:
    stale = {**_env(HORIZON_URL=None), "HT_CHECKIN_WINDOW": "07:55-08:00"}

    with pytest.raises(ConfigError) as caught:
        Settings.from_env(stale)

    assert caught.value.variable == "HT_CHECKIN_WINDOW"


def test_an_empty_optional_variable_falls_back_to_its_default() -> None:
    settings = Settings.from_env(_env(HT_HOLD_SECONDS="", HT_TIMEZONE="  "))

    assert settings.hold_seconds == 120
    assert settings.timezone == ZoneInfo("Europe/Moscow")


def test_settings_cannot_be_changed_after_reading() -> None:
    settings = Settings.from_env(REQUIRED)

    with pytest.raises(AttributeError):
        settings.password = "other"  # type: ignore[misc]  # proving the dataclass is frozen


# --- required variables ---------------------------------------------------------


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_a_missing_required_variable_is_refused_by_name(name: str) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(**{name: None}))

    assert caught.value.variable == name
    assert name in str(caught.value)


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_a_blank_required_variable_counts_as_missing(name: str) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(**{name: "   "}))

    assert caught.value.variable == name


def test_required_values_are_not_stripped_of_meaningful_whitespace() -> None:
    settings = Settings.from_env(_env(HORIZON_PASSWORD=" pass word "))

    assert settings.password == " pass word "


# --- malformed values -----------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "07:55",
        "7:55-8:00",
        "07:55-08:00-09:00",
        "07:55 - 08:00",
        "25:00-26:00",
        "07:60-08:00",
        "abc",
    ],
)
@pytest.mark.parametrize("name", RANGES)
def test_a_malformed_range_is_refused_by_name(name: str, value: str) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(**{name: value}))

    assert caught.value.variable == name
    assert value in str(caught.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("HT_CHECKIN_RANGE", "08:10-07:30"),
        ("HT_CHECKIN_RANGE", "07:30-07:30"),
        ("HT_CHECKOUT_RANGE", "17:10-16:30"),
        ("HT_CHECKOUT_RANGE", "16:30-16:30"),
    ],
)
def test_a_range_the_domain_refuses_is_refused_by_name(name: str, value: str) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(**{name: value}))

    assert caught.value.variable == name
    assert "before its end" in str(caught.value)


@pytest.mark.parametrize(
    "environ",
    [
        {"HT_CHECKOUT_RANGE": "08:10-17:10"},
        {"HT_CHECKOUT_RANGE": "08:00-17:10"},
        {"HT_CHECKIN_RANGE": "16:00-16:30"},
    ],
    ids=["touching", "overlapping", "check-in-moved-late"],
)
def test_a_check_out_range_not_after_the_check_in_range_is_refused_naming_both(
    environ: dict[str, str],
) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(**environ))

    assert caught.value.variable == "HT_CHECKOUT_RANGE"
    assert "HT_CHECKIN_RANGE" in str(caught.value)


def test_a_check_out_range_starting_a_minute_after_the_check_in_range_is_accepted() -> None:
    settings = Settings.from_env(_env(HT_CHECKOUT_RANGE="08:11-17:10"))

    assert settings.checkout_range == TimeRange(time(8, 11), time(17, 10))


@pytest.mark.parametrize("value", ["nine hours", "1.5", "-1", "1441", "99999999999999999999"])
@pytest.mark.parametrize("name", MINUTES)
def test_minutes_that_are_not_a_whole_number_within_a_day_are_refused_by_name(
    name: str, value: str
) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(**{name: value}))

    assert caught.value.variable == name
    assert value in str(caught.value)


@pytest.mark.parametrize("name", ["HT_SESSION_LENGTH_MINUTES", "HT_SESSION_EXTRA_MAX_MINUTES"])
def test_a_full_day_is_the_longest_session_duration_accepted(name: str) -> None:
    Settings.from_env(_env(**{name: "1440"}))


def test_a_session_of_zero_minutes_is_refused_by_name() -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(HT_SESSION_LENGTH_MINUTES="0"))

    assert caught.value.variable == "HT_SESSION_LENGTH_MINUTES"


def test_no_extra_minutes_are_accepted() -> None:
    settings = Settings.from_env(_env(HT_SESSION_EXTRA_MAX_MINUTES="0"))

    assert settings.session_extra_max == timedelta(0)


def test_a_grace_of_zero_minutes_is_refused_by_name() -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(HT_WINDOW_GRACE_MINUTES="0"))

    assert caught.value.variable == "HT_WINDOW_GRACE_MINUTES"


def test_a_grace_that_carries_the_last_window_past_midnight_is_refused_by_name() -> None:
    environ = _env(HT_CHECKOUT_RANGE="23:00-23:58", HT_WINDOW_GRACE_MINUTES="2")

    with pytest.raises(ConfigError) as caught:
        Settings.from_env(environ)

    assert caught.value.variable == "HT_WINDOW_GRACE_MINUTES"
    assert "midnight" in str(caught.value)


def test_a_grace_that_closes_the_last_window_at_the_last_minute_is_accepted() -> None:
    environ = _env(HT_CHECKOUT_RANGE="23:00-23:58", HT_WINDOW_GRACE_MINUTES="1")

    assert Settings.from_env(environ).window_grace == timedelta(minutes=1)


def test_an_unknown_time_zone_is_refused_by_name() -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(HT_TIMEZONE="Mars/Olympus_Mons"))

    assert caught.value.variable == "HT_TIMEZONE"


def test_a_time_zone_that_is_not_a_key_is_refused_by_name() -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(HT_TIMEZONE="../../etc/passwd"))

    assert caught.value.variable == "HT_TIMEZONE"


@pytest.mark.parametrize("value", ["two minutes", "1.5", "-1"])
def test_a_hold_that_is_not_a_non_negative_whole_number_is_refused_by_name(value: str) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(HT_HOLD_SECONDS=value))

    assert caught.value.variable == "HT_HOLD_SECONDS"


def test_a_zero_hold_is_accepted() -> None:
    assert Settings.from_env(_env(HT_HOLD_SECONDS="0")).hold_seconds == 0


# --- masking --------------------------------------------------------------------


@pytest.mark.parametrize("render", [repr, str, lambda s: f"{s}", lambda s: f"{s!r}"])
def test_no_rendering_of_the_settings_shows_a_credential(
    render: Callable[[Settings], str],
) -> None:
    text = render(Settings.from_env(FULL))

    for secret in (PASSWORD, TOKEN, CHAT_ID, USERNAME, SEED):
        assert secret not in text


@pytest.mark.parametrize("environ", [_env(HORIZON_USERNAME="ivanov"), _env(HT_JITTER_SEED=SEED)])
def test_the_seed_is_masked_whether_set_or_taken_from_the_username(
    environ: dict[str, str],
) -> None:
    text = repr(Settings.from_env(environ))

    assert "jitter_seed='***'" in text
    assert "ivanov" not in text
    assert SEED not in text


def test_the_rendering_still_names_the_masked_fields_and_shows_the_rest() -> None:
    text = repr(Settings.from_env(FULL))

    assert "password='***'" in text
    assert "telegram_token='***'" in text
    assert "QA desktop" in text
    assert "Asia/Tokyo" in text


def test_a_config_error_never_echoes_a_secret_value() -> None:
    environ = _env(HORIZON_PASSWORD=PASSWORD, HT_CHECKIN_RANGE="nonsense")

    with pytest.raises(ConfigError) as caught:
        Settings.from_env(environ)

    assert PASSWORD not in str(caught.value)
