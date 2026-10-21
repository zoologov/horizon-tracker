"""Reads the service's settings from environment variables and refuses an incomplete set.

Credentials have no defaults: a missing or blank one raises ``ConfigError`` naming the
variable, never its value. Everything else falls back to the documented default. The
ranges and durations of the daily draw are checked at load by the domain's own rules,
so a bad ``.env`` fails at start rather than at 07:30. A variable this service no longer
reads (``HT_CHECKIN_WINDOW``, ``HT_CHECKOUT_WINDOW``) is refused by name, so a stale
``.env`` cannot keep running as before unnoticed. A ``Settings`` never renders a
credential or the seed of the draw: ``repr``/``str`` show ``'***'`` in their place.

``HT_LANGUAGE`` picks the language of what a person reads (``en`` by default, ``ru``).
A refusal carries its problem as a message key, so the CLI can show it in that language;
its ``str`` is the English text the log carries. A refusal by the domain's rules carries
the domain's reason as a message too, so no line mixes two languages.
"""

# beadloom:domain=infrastructure

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from datetime import date, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from horizon_tracker.domain.messages import DEFAULT_LANGUAGE, Language, Message
from horizon_tracker.domain.schedule import (
    ScheduleError,
    TimeRange,
    draw_moments,
    window_from,
)

MASK = "***"

CHECKIN_RANGE = "HT_CHECKIN_RANGE"
CHECKOUT_RANGE = "HT_CHECKOUT_RANGE"
SESSION_LENGTH = "HT_SESSION_LENGTH_MINUTES"
SESSION_EXTRA_MAX = "HT_SESSION_EXTRA_MAX_MINUTES"
WINDOW_GRACE = "HT_WINDOW_GRACE_MINUTES"
JITTER_SEED = "HT_JITTER_SEED"
LANGUAGE = "HT_LANGUAGE"

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

# Variables an older release read, and the hint that replaces each.
_RETIRED = {
    "HT_CHECKIN_WINDOW": Message(
        "config.retired.checkin_window",
        {"checkin_range": CHECKIN_RANGE, "grace": WINDOW_GRACE},
    ),
    "HT_CHECKOUT_WINDOW": Message(
        "config.retired.checkout_window",
        {
            "checkout_range": CHECKOUT_RANGE,
            "session_length": SESSION_LENGTH,
            "extra_max": SESSION_EXTRA_MAX,
            "grace": WINDOW_GRACE,
        },
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
    """A configuration variable is missing or malformed; names the variable, not a secret.

    ``problem`` is a message, so the refusal reads in any language; ``str`` is English.
    """

    def __init__(self, variable: str, problem: Message) -> None:
        self.variable = variable
        self.problem = problem
        super().__init__(self.in_language(Language.EN))

    def in_language(self, language: Language) -> str:
        """``<VARIABLE>: <problem>`` with the problem in ``language``."""
        return f"{self.variable}: {self.problem.in_language(language)}"


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
    language: Language

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
            language=language_from_env(environ),
        )

    def __repr__(self) -> str:
        shown = (
            f"{field.name}={MASK if field.name in _MASKED else getattr(self, field.name)!r}"
            for field in fields(self)
        )
        return f"{type(self).__name__}({', '.join(shown)})"


def language_from_env(environ: Mapping[str, str]) -> Language:
    """The language ``HT_LANGUAGE`` names, ``en`` when unset or blank; read on its own.

    ``Settings.from_env`` reads it like any other variable; the CLI also reads it alone,
    to name a configuration error in the configured language when the settings fail.
    """
    code = _optional(environ, LANGUAGE, DEFAULT_LANGUAGE.value)
    try:
        return Language(code)
    except ValueError as error:
        choices = ", ".join(language.value for language in Language)
        problem = Message("config.unknown_language", {"choices": choices, "text": code})
        raise ConfigError(LANGUAGE, problem) from error


def _refuse_retired(environ: Mapping[str, str]) -> None:
    for name, hint in _RETIRED.items():
        if name in environ:
            raise ConfigError(name, hint)


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "")
    if not value.strip():
        raise ConfigError(name, Message("config.required"))
    return value


def _optional(environ: Mapping[str, str], name: str, default: str) -> str:
    value = environ.get(name, "").strip()
    return value or default


def _timezone(environ: Mapping[str, str], name: str) -> ZoneInfo:
    key = _optional(environ, name, DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ConfigError(name, Message("config.unknown_time_zone", {"key": key})) from error


def _time_range(environ: Mapping[str, str], name: str, default: str) -> TimeRange:
    text = _optional(environ, name, default)
    match = _RANGE_FORMAT.fullmatch(text)
    if match is None:
        raise ConfigError(name, Message("config.expected_range", {"text": text}))
    start_hour, start_minute, end_hour, end_minute = (int(part) for part in match.groups())
    try:
        start, end = time(start_hour, start_minute), time(end_hour, end_minute)
    except ValueError as error:
        reason = Message("config.no_such_time")
        raise ConfigError(name, _invalid_range(text, reason)) from error
    try:
        return TimeRange(start, end)
    except ScheduleError as refusal:
        raise ConfigError(name, _invalid_range(text, refusal.reason)) from refusal


def _invalid_range(text: str, reason: Message) -> Message:
    return Message("config.invalid_range", {"text": text, "error": reason})


def _minutes(environ: Mapping[str, str], name: str, default: str) -> timedelta:
    text = _optional(environ, name, default)
    if _WHOLE_NUMBER.fullmatch(text) is None or int(text) > _MINUTES_PER_DAY:
        problem = Message("config.expected_minutes", {"limit": _MINUTES_PER_DAY, "text": text})
        raise ConfigError(name, problem)
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

    Each try adds one value to those already accepted, so the domain's refusal can only
    be about the variable named. The extra minutes need no try of their own: a whole
    number from 0 to a day is everything the draw asks of them.
    """
    _domain_check(
        CHECKOUT_RANGE,
        Message("config.checkout_after_checkin", {"checkin_range": CHECKIN_RANGE}),
        lambda: draw_moments(
            _PROBE_DAY, seed, checkin_range, _SHORTEST_SESSION, extra_max, checkout_range
        ),
    )
    _domain_check(
        SESSION_LENGTH,
        Message("config.unusable_session_length"),
        lambda: draw_moments(
            _PROBE_DAY, seed, checkin_range, session_length, extra_max, checkout_range
        ),
    )
    # The latest moment the draw can name is the end of the check-out range.
    _domain_check(
        WINDOW_GRACE,
        Message("config.unusable_grace"),
        lambda: window_from(checkout_range.end, grace),
    )


def _domain_check(name: str, problem: Message, check: Callable[[], object]) -> None:
    """Run ``check``; the domain's reason, a message, becomes ``problem``'s ``error`` field."""
    try:
        check()
    except ScheduleError as refusal:
        reason = Message(problem.key, {**problem.fields, "error": refusal.reason})
        raise ConfigError(name, reason) from refusal


def _hold_seconds(environ: Mapping[str, str], name: str) -> int:
    text = _optional(environ, name, DEFAULT_HOLD_SECONDS)
    if _WHOLE_NUMBER.fullmatch(text) is None:
        raise ConfigError(name, Message("config.expected_seconds", {"text": text}))
    return int(text)
