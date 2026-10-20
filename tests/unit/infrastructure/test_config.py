"""Tests for the settings read from the environment: required secrets, defaults, masking."""

from collections.abc import Callable
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.domain.schedule import Window
from horizon_tracker.infrastructure.config import ConfigError, Settings

PASSWORD = "S3cret-Pa55word!"
TOKEN = "123456:AAH-bot-token-value"
CHAT_ID = "987654321"
USERNAME = "corp\\ivanov"

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
    "HT_CHECKIN_WINDOW": "09:10-09:20",
    "HT_CHECKOUT_WINDOW": "18:30-18:45",
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
    assert settings.checkin_window == Window(time(9, 10), time(9, 20))
    assert settings.checkout_window == Window(time(18, 30), time(18, 45))
    assert settings.hold_seconds == 300
    assert settings.chrome_path == Path("/opt/chrome/chrome")
    assert settings.artifacts_dir == Path("/var/tmp/horizon-artifacts")


def test_unset_optional_variables_take_the_documented_defaults() -> None:
    settings = Settings.from_env(REQUIRED)

    assert settings.desktop == "DEV desktop"
    assert settings.timezone == ZoneInfo("Europe/Moscow")
    assert settings.checkin_window == Window(time(7, 55), time(8, 0))
    assert settings.checkout_window == Window(time(17, 0), time(17, 5))
    assert settings.hold_seconds == 120
    assert settings.chrome_path == Path("/usr/bin/google-chrome")
    assert settings.artifacts_dir == Path("/opt/horizon-tracker/artifacts")


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
def test_a_malformed_window_is_refused_by_name(value: str) -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(HT_CHECKIN_WINDOW=value))

    assert caught.value.variable == "HT_CHECKIN_WINDOW"
    assert value in str(caught.value)


def test_a_window_that_ends_before_it_starts_is_refused_by_name() -> None:
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(_env(HT_CHECKOUT_WINDOW="17:05-17:00"))

    assert caught.value.variable == "HT_CHECKOUT_WINDOW"


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

    for secret in (PASSWORD, TOKEN, CHAT_ID, USERNAME):
        assert secret not in text


def test_the_rendering_still_names_the_masked_fields_and_shows_the_rest() -> None:
    text = repr(Settings.from_env(FULL))

    assert "password='***'" in text
    assert "telegram_token='***'" in text
    assert "QA desktop" in text
    assert "Asia/Tokyo" in text


def test_a_config_error_never_echoes_a_secret_value() -> None:
    environ = _env(HORIZON_PASSWORD=PASSWORD, HT_CHECKIN_WINDOW="nonsense")

    with pytest.raises(ConfigError) as caught:
        Settings.from_env(environ)

    assert PASSWORD not in str(caught.value)
