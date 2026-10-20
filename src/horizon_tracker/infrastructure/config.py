"""Reads the service's settings from environment variables and refuses an incomplete set.

Credentials have no defaults: a missing or blank one raises ``ConfigError`` naming the
variable, never its value. Everything else falls back to the documented default. The
ranges and durations of the daily draw are checked at load by the domain's own rules,
so a bad ``.env`` fails at start rather than at 07:30. A variable this service no longer
reads (``HT_CHECKIN_WINDOW``, ``HT_CHECKOUT_WINDOW``) is refused by name, so a stale
``.env`` cannot keep running as before unnoticed. A ``Settings`` never renders a
credential or the seed of the draw: ``repr``/``str`` show ``'***'`` in their place.
"""

# beadloom:domain=infrastructure

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from datetime import date, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from horizon_tracker.domain.schedule import TimeRange, Window, draw_moments, window_from

MASK = "***"

CHECKIN_RANGE = "HT_CHECKIN_RANGE"
CHECKOUT_RANGE = "HT_CHECKOUT_RANGE"
SESSION_LENGTH = "HT_SESSION_LENGTH_MINUTES"
SESSION_EXTRA_MAX = "HT_SESSION_EXTRA_MAX_MINUTES"
WINDOW_GRACE = "HT_WINDOW_GRACE_MINUTES"
JITTER_SEED = "HT_JITTER_SEED"

DEFAULT_DESKTOP = "DEV desktop"
DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_CHECKIN_RANGE = "07:30-08:10"
DEFAULT_CHECKOUT_RANGE = "16:30-17:10"
DEFAULT_SESSION_LENGTH_MINUTES = "540"
DEFAULT_SESSION_EXTRA_MAX_MINUTES = "10"
DEFAULT_WINDOW_GRACE_MINUTES = "5"
DEFAULT_HOLD_SECONDS = "120"
DEFAULT_CHROME_PATH = "/usr/bin/google-chrome"
DEFAULT_ARTIFACTS_DIR = "/opt/horizon-tracker/artifacts"

# Interim (HT-003 BEAD-03 -> BEAD-04): the HT-001 windows the CLI still reads until it
# builds each run's window from the day's drawn moment. No variable sets them any more.
HT001_CHECKIN_WINDOW = Window(time(7, 55), time(8, 0))
HT001_CHECKOUT_WINDOW = Window(time(17, 0), time(17, 5))

# Variables an older release read, and the hint that replaces each.
_RETIRED = {
    "HT_CHECKIN_WINDOW": (
        f"is no longer read: the check-in moment is drawn daily from {CHECKIN_RANGE} and "
        f"its window lasts {WINDOW_GRACE}; remove HT_CHECKIN_WINDOW from the environment"
    ),
    "HT_CHECKOUT_WINDOW": (
        f"is no longer read: the check-out moment is drawn daily from {CHECKOUT_RANGE} "
        f"({SESSION_LENGTH} plus up to {SESSION_EXTRA_MAX} after the check-in) and its "
        f"window lasts {WINDOW_GRACE}; remove HT_CHECKOUT_WINDOW from the environment"
    ),
}

_RANGE_FORMAT = re.compile(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})")
_WHOLE_NUMBER = re.compile(r"\d+")
# Nothing in a daily schedule lasts longer than a day; the bound also keeps the draw's
# arithmetic far from datetime's limits.
_MINUTES_PER_DAY = 1440
# Any day serves to try the draw at load: its parameters are refused or not whatever the day.
_PROBE_DAY = date(2000, 1, 1)
# The shortest session the draw accepts: lets the range order be tried on its own.
_SHORTEST_SESSION = timedelta(minutes=1)
# Fields read from secret variables (the AD account, the bot's address) and the seed of
# the draw, which is the username unless set: never rendered.
_MASKED = frozenset({"username", "password", "telegram_token", "telegram_chat_id", "jitter_seed"})


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
    checkin_range: TimeRange
    checkout_range: TimeRange
    session_length: timedelta
    session_extra_max: timedelta
    window_grace: timedelta
    jitter_seed: bytes
    hold_seconds: int
    chrome_path: Path
    artifacts_dir: Path
    checkin_window: Window = HT001_CHECKIN_WINDOW
    checkout_window: Window = HT001_CHECKOUT_WINDOW

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        """Read the settings from ``environ``; raise ``ConfigError`` on the first bad variable."""
        _refuse_retired(environ)
        horizon_url = _required(environ, "HORIZON_URL")
        username = _required(environ, "HORIZON_USERNAME")
        password = _required(environ, "HORIZON_PASSWORD")
        checkin_range = _time_range(environ, CHECKIN_RANGE, DEFAULT_CHECKIN_RANGE)
        checkout_range = _time_range(environ, CHECKOUT_RANGE, DEFAULT_CHECKOUT_RANGE)
        session_length = _minutes(environ, SESSION_LENGTH, DEFAULT_SESSION_LENGTH_MINUTES)
        extra_max = _minutes(environ, SESSION_EXTRA_MAX, DEFAULT_SESSION_EXTRA_MAX_MINUTES)
        grace = _minutes(environ, WINDOW_GRACE, DEFAULT_WINDOW_GRACE_MINUTES)
        seed = _seed(environ, username)
        _check_the_draw(seed, checkin_range, session_length, extra_max, checkout_range, grace)
        return cls(
            horizon_url=horizon_url,
            username=username,
            password=password,
            desktop=_optional(environ, "HORIZON_DESKTOP", DEFAULT_DESKTOP),
            telegram_token=_required(environ, "TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_required(environ, "TELEGRAM_CHAT_ID"),
            timezone=_timezone(environ, "HT_TIMEZONE"),
            checkin_range=checkin_range,
            checkout_range=checkout_range,
            session_length=session_length,
            session_extra_max=extra_max,
            window_grace=grace,
            jitter_seed=seed,
            hold_seconds=_hold_seconds(environ, "HT_HOLD_SECONDS"),
            chrome_path=Path(_optional(environ, "HT_CHROME_PATH", DEFAULT_CHROME_PATH)),
            artifacts_dir=Path(_optional(environ, "HT_ARTIFACTS_DIR", DEFAULT_ARTIFACTS_DIR)),
        )

    def __repr__(self) -> str:
        shown = (
            f"{field.name}={MASK if field.name in _MASKED else getattr(self, field.name)!r}"
            for field in fields(self)
        )
        return f"{type(self).__name__}({', '.join(shown)})"


def _refuse_retired(environ: Mapping[str, str]) -> None:
    for name, hint in _RETIRED.items():
        if name in environ:
            raise ConfigError(name, hint)


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


def _time_range(environ: Mapping[str, str], name: str, default: str) -> TimeRange:
    text = _optional(environ, name, default)
    match = _RANGE_FORMAT.fullmatch(text)
    if match is None:
        raise ConfigError(name, f"expected HH:MM-HH:MM, got {text!r}")
    start_hour, start_minute, end_hour, end_minute = (int(part) for part in match.groups())
    try:
        return TimeRange(time(start_hour, start_minute), time(end_hour, end_minute))
    except ValueError as error:
        raise ConfigError(name, f"not a valid range {text!r}: {error}") from error


def _minutes(environ: Mapping[str, str], name: str, default: str) -> timedelta:
    text = _optional(environ, name, default)
    if _WHOLE_NUMBER.fullmatch(text) is None or int(text) > _MINUTES_PER_DAY:
        raise ConfigError(
            name, f"expected a whole number of minutes from 0 to {_MINUTES_PER_DAY}, got {text!r}"
        )
    return timedelta(minutes=int(text))


def _seed(environ: Mapping[str, str], username: str) -> bytes:
    """The explicit seed taken verbatim, or the username when it is unset or blank."""
    value = environ.get(JITTER_SEED, "")
    return (value if value.strip() else username).encode("utf-8")


def _check_the_draw(
    seed: bytes,
    checkin_range: TimeRange,
    session_length: timedelta,
    extra_max: timedelta,
    checkout_range: TimeRange,
    grace: timedelta,
) -> None:
    """Try the draw and the last window with the domain; its refusal names the variable.

    Each try adds one value to those already accepted, so the domain's ``ValueError`` can
    only be about the variable named. The extra minutes need no try of their own: a whole
    number from 0 to a day is everything the draw asks of them.
    """
    _domain_check(
        CHECKOUT_RANGE,
        f"must start after {CHECKIN_RANGE} ends",
        lambda: draw_moments(
            _PROBE_DAY, seed, checkin_range, _SHORTEST_SESSION, extra_max, checkout_range
        ),
    )
    _domain_check(
        SESSION_LENGTH,
        "not a usable session length",
        lambda: draw_moments(
            _PROBE_DAY, seed, checkin_range, session_length, extra_max, checkout_range
        ),
    )
    # The latest moment the draw can name is the end of the check-out range.
    _domain_check(
        WINDOW_GRACE,
        "not a usable grace",
        lambda: window_from(checkout_range.end, grace),
    )


def _domain_check(name: str, problem: str, check: Callable[[], object]) -> None:
    try:
        check()
    except ValueError as error:
        raise ConfigError(name, f"{problem}: {error}") from error


def _hold_seconds(environ: Mapping[str, str], name: str) -> int:
    text = _optional(environ, name, DEFAULT_HOLD_SECONDS)
    if _WHOLE_NUMBER.fullmatch(text) is None:
        raise ConfigError(name, f"expected a whole number of seconds, got {text!r}")
    return int(text)
