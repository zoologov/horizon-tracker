"""Reads the service's settings from environment variables and refuses an incomplete set.

Credentials have no defaults: a missing or blank one raises ``ConfigError`` naming the
variable, never its value. Everything else falls back to the documented default. A
``Settings`` never renders a credential: ``repr``/``str`` show ``'***'`` in its place.
"""

# beadloom:domain=infrastructure

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from horizon_tracker.domain.schedule import Window

MASK = "***"

DEFAULT_DESKTOP = "DEV desktop"
DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_CHECKIN_WINDOW = "07:55-08:00"
DEFAULT_CHECKOUT_WINDOW = "17:00-17:05"
DEFAULT_HOLD_SECONDS = "120"
DEFAULT_CHROME_PATH = "/usr/bin/google-chrome"
DEFAULT_ARTIFACTS_DIR = "/opt/horizon-tracker/artifacts"

_WINDOW_FORMAT = re.compile(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})")
_HOLD_FORMAT = re.compile(r"\d+")
# Fields read from secret variables (the AD account and the bot's address): never rendered.
_CREDENTIALS = frozenset({"username", "password", "telegram_token", "telegram_chat_id"})


class ConfigError(Exception):
    """A configuration variable is missing or malformed; names the variable, not a secret."""

    def __init__(self, variable: str, problem: str) -> None:
        super().__init__(f"{variable}: {problem}")
        self.variable = variable


@dataclass(frozen=True, repr=False)
class Settings:
    """Everything the composition root needs to build the adapters, read once at start."""

    horizon_url: str
    username: str
    password: str
    desktop: str
    telegram_token: str
    telegram_chat_id: str
    timezone: ZoneInfo
    checkin_window: Window
    checkout_window: Window
    hold_seconds: int
    chrome_path: Path
    artifacts_dir: Path

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        """Read the settings from ``environ``; raise ``ConfigError`` on the first bad variable."""
        return cls(
            horizon_url=_required(environ, "HORIZON_URL"),
            username=_required(environ, "HORIZON_USERNAME"),
            password=_required(environ, "HORIZON_PASSWORD"),
            desktop=_optional(environ, "HORIZON_DESKTOP", DEFAULT_DESKTOP),
            telegram_token=_required(environ, "TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_required(environ, "TELEGRAM_CHAT_ID"),
            timezone=_timezone(environ, "HT_TIMEZONE"),
            checkin_window=_window(environ, "HT_CHECKIN_WINDOW", DEFAULT_CHECKIN_WINDOW),
            checkout_window=_window(environ, "HT_CHECKOUT_WINDOW", DEFAULT_CHECKOUT_WINDOW),
            hold_seconds=_hold_seconds(environ, "HT_HOLD_SECONDS"),
            chrome_path=Path(_optional(environ, "HT_CHROME_PATH", DEFAULT_CHROME_PATH)),
            artifacts_dir=Path(_optional(environ, "HT_ARTIFACTS_DIR", DEFAULT_ARTIFACTS_DIR)),
        )

    def __repr__(self) -> str:
        shown = (
            f"{field.name}={MASK if field.name in _CREDENTIALS else getattr(self, field.name)!r}"
            for field in fields(self)
        )
        return f"{type(self).__name__}({', '.join(shown)})"


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "")
    if not value.strip():
        raise ConfigError(name, "is required and not set")
    return value


def _optional(environ: Mapping[str, str], name: str, default: str) -> str:
    value = environ.get(name, "").strip()
    return value or default


def _timezone(environ: Mapping[str, str], name: str) -> ZoneInfo:
    key = _optional(environ, name, DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ConfigError(name, f"unknown time zone {key!r}") from error


def _window(environ: Mapping[str, str], name: str, default: str) -> Window:
    text = _optional(environ, name, default)
    match = _WINDOW_FORMAT.fullmatch(text)
    if match is None:
        raise ConfigError(name, f"expected HH:MM-HH:MM, got {text!r}")
    start_hour, start_minute, end_hour, end_minute = (int(part) for part in match.groups())
    try:
        return Window(time(start_hour, start_minute), time(end_hour, end_minute))
    except ValueError as error:
        raise ConfigError(name, f"not a valid window {text!r}: {error}") from error


def _hold_seconds(environ: Mapping[str, str], name: str) -> int:
    text = _optional(environ, name, DEFAULT_HOLD_SECONDS)
    if _HOLD_FORMAT.fullmatch(text) is None:
        raise ConfigError(name, f"expected a whole number of seconds, got {text!r}")
    return int(text)
