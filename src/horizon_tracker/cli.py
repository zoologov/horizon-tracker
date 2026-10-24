"""Wires the adapters into the use cases behind the ``horizon`` commands: the composition root.

``horizon checkin`` and ``horizon checkout`` run one daily run each: every run draws
today's check-in and check-out moments from the settings, waits for its own moment if its
timer fired earlier in the range, and may run in the window that opens there. ``--force``
ignores the window, the wait and the calendar (a manual run from the VPS), ``--dry-run``
names the plan and the day's moments and never logs in. ``horizon probe`` asks every
dependency whether a run could go ahead and names the day's moments last.

Settings come from the environment; a missing or malformed variable is named on stderr
and the command exits 1 before anything is built. What a person reads -- the plan, the
probe, a configuration error -- is in the language ``HT_LANGUAGE`` names (English by
default); the log stays English, and a configuration error is said in the reader's
language beside its English log line when the two differ. A run exits 1 only when it failed: a
success and a deliberate skip both exit 0, so systemd marks a unit ``failed`` exactly when
the owner has something to look at. Diagnostics go to stderr through ``logging``; command
output (the plan, the probe) goes to stdout. No credential is ever logged or printed.

The adapters are built by a factory carried in click's ``obj``: production uses
``open_adapters``, the tests hand in one that yields fakes.
"""

# beadloom:service=cli

import logging
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Protocol, TextIO

import click
import httpx

from horizon_tracker import __version__
from horizon_tracker.application import EveningCheckout, MorningCheckin, WindowedRun
from horizon_tracker.application.probe import (
    Check,
    DryRun,
    Probe,
    ProbeReport,
    RunPlan,
    schedule_detail,
)
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.messages import DEFAULT_LANGUAGE, Language, Message, text
from horizon_tracker.domain.ports import (
    ArtifactStore,
    Clock,
    HorizonClient,
    Notifier,
    WorkingDayCalendar,
)
from horizon_tracker.domain.report import Outcome
from horizon_tracker.domain.schedule import (
    DailyMoments,
    RetryPolicy,
    RunKind,
    TimeRange,
    draw_moments,
    window_from,
)
from horizon_tracker.infrastructure.absence_store import JsonAbsenceStore
from horizon_tracker.infrastructure.artifacts import DirectoryArtifactStore
from horizon_tracker.infrastructure.clock import SystemClock
from horizon_tracker.infrastructure.config import ConfigError, Settings, language_from_env
from horizon_tracker.infrastructure.horizon_playwright import PlaywrightHorizonClient
from horizon_tracker.infrastructure.isdayoff import IsDayOffCalendar
from horizon_tracker.infrastructure.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILED = 1

# Not configurable: three attempts half a minute apart fit the default five-minute window,
# and the window, not the count, is what ends a scheduled run. A --force run has the whole
# day as its window, so there the count is the bound.
RETRY_POLICY = RetryPolicy(max_attempts=3, backoff=timedelta(seconds=30))

# The probe never screenshots, but the Horizon adapter is built for one kind of run.
_PROBE_RUN_KIND = RunKind.CHECKIN

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_PACKAGE_LOGGER = "horizon_tracker"

# The probe's check that names the day's drawn moments; the dry run prints the same line.
_SCHEDULE = "schedule"

# The log is read by the operator and stays in English whatever the owner reads.
_LOG_LANGUAGE = Language.EN

_SOURCE_KEY = {
    VerdictSource.CALENDAR: "plan.source.calendar",
    VerdictSource.WEEKDAY_FALLBACK: "plan.source.weekday_fallback",
    None: "plan.source.not_asked",
}


class PrunableArtifactStore(ArtifactStore, Protocol):
    """An artifact store the composition root can also clear of expired files."""

    def prune(self) -> list[Path]:
        """Remove expired artifacts; return the paths removed."""
        ...


@dataclass(frozen=True)
class Adapters:
    """The ports one command runs over, built for one run kind."""

    clock: Clock
    calendar: WorkingDayCalendar
    notifier: Notifier
    horizon: HorizonClient
    artifacts: PrunableArtifactStore


AdapterFactory = Callable[[Settings, RunKind], AbstractContextManager[Adapters]]


@contextmanager
def open_adapters(settings: Settings, kind: RunKind) -> Iterator[Adapters]:
    """Build the production adapters; close the HTTP client and the browser on exit.

    The calendar and the notifier share one HTTP client. Building opens no connection:
    the browser starts on the first Horizon call, the HTTP client on the first request.
    """
    clock = SystemClock(settings.timezone)
    artifacts = DirectoryArtifactStore(settings.artifacts_dir, clock)
    with httpx.Client() as http:
        notifier = build_notifier(settings, http)
        horizon = PlaywrightHorizonClient(
            horizon_url=settings.horizon_url,
            username=settings.username,
            password=settings.password,
            chrome_path=settings.chrome_path,
            artifacts=artifacts,
            run_kind=kind,
        )
        with horizon:
            yield Adapters(clock, IsDayOffCalendar(http), notifier, horizon, artifacts)


def build_notifier(settings: Settings, http: httpx.Client) -> TelegramNotifier:
    """The Telegram notifier, in the configured language; a refused token is a config error."""
    try:
        return TelegramNotifier(
            settings.telegram_token, settings.telegram_chat_id, http, settings.language
        )
    except ValueError as error:
        # The adapter's message never echoes the token; Settings has already refused a
        # blank chat id, so the token is the only value this constructor can refuse.
        raise ConfigError("TELEGRAM_BOT_TOKEN", Message("config.malformed_token")) from error


@click.group()
@click.version_option(__version__, prog_name="horizon")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Scheduled check-in and check-out of a VMware Horizon VDI session."""
    _configure_logging()
    if ctx.obj is None:
        ctx.obj = open_adapters


_DRY_RUN = click.option("--dry-run", is_flag=True, help="Name the plan's steps; never log in.")
_FORCE = click.option(
    "--force",
    is_flag=True,
    help="Run now: no wait for the drawn moment, no window, no calendar (a manual run).",
)


@main.command()
@_DRY_RUN
@_FORCE
@click.pass_context
def checkin(ctx: click.Context, dry_run: bool, force: bool) -> None:
    """Open the desktop, hold it until Windows logs on, then disconnect."""
    ctx.exit(_guarded(lambda: _run(ctx.obj, RunKind.CHECKIN, dry_run=dry_run, force=force)))


@main.command()
@_DRY_RUN
@_FORCE
@click.pass_context
def checkout(ctx: click.Context, dry_run: bool, force: bool) -> None:
    """Log the desktop's Windows session off and confirm it ended."""
    ctx.exit(_guarded(lambda: _run(ctx.obj, RunKind.CHECKOUT, dry_run=dry_run, force=force)))


@main.command()
@click.pass_context
def probe(ctx: click.Context) -> None:
    """Check the settings, the portal, the calendar and Chrome without logging in."""
    ctx.exit(_guarded(lambda: _probe(ctx.obj)))


def _guarded(command: Callable[[], int]) -> int:
    """Run ``command``; a configuration error is named on stderr and exits 1."""
    try:
        return command()
    except ConfigError as error:
        logger.error("configuration error: %s", error)
        _say_in_the_readers_language(error)
        return EXIT_FAILED


def _say_in_the_readers_language(error: ConfigError) -> None:
    """Echo ``error`` to stderr in the reader's language, unless the log line already is.

    The settings did not load, so the language is read on its own; an ``HT_LANGUAGE``
    that cannot be read leaves the default, and that refusal is the error being named.
    """
    try:
        language = language_from_env(os.environ)
    except ConfigError:
        language = DEFAULT_LANGUAGE
    if language is _LOG_LANGUAGE:
        return
    click.echo(text("config.error", language, error=error.in_language(language)), err=True)


def _run(factory: AdapterFactory, kind: RunKind, *, dry_run: bool, force: bool) -> int:
    settings = Settings.from_env(os.environ)
    with factory(settings, kind) as adapters:
        moments = _todays_moments(settings, adapters.clock)
        use_case = _use_case(adapters, settings, kind, moments)
        if dry_run:
            _echo_plan(DryRun(use_case, moments).plan(force=force), settings.language)
            return EXIT_OK
        _prune(adapters.artifacts)
        report = use_case.run(force=force)
    return EXIT_FAILED if report.outcome is Outcome.FAILED else EXIT_OK


def _prune(artifacts: PrunableArtifactStore) -> None:
    """Clear expired artifacts, best-effort: a run that cannot prune still runs and reports.

    Only the error's type is logged; its message names a path on the VPS and adds nothing
    the type does not say about what to fix.
    """
    try:
        artifacts.prune()
    except OSError as error:
        logger.warning("artifact prune failed, the run goes on: %s", type(error).__name__)


def _todays_moments(settings: Settings, clock: Clock) -> DailyMoments:
    """Draw today's check-in and check-out moments; ``Settings`` validated these arguments."""
    return draw_moments(
        clock.now().date(),
        settings.jitter_seed,
        settings.checkin_range,
        settings.session_length,
        settings.session_extra_max,
        settings.checkout_range,
    )


def _use_case(
    adapters: Adapters, settings: Settings, kind: RunKind, moments: DailyMoments
) -> MorningCheckin | EveningCheckout:
    # A --force run is told so by run(force=True): it then waits for nothing, ignores the
    # window and names no planned moment, so the drawn moment can stay. Passing the moment
    # "now" instead would gain nothing and break a manual run in the last minutes before
    # midnight, where a window from "now" cannot be built.
    moment = moments.check_in if kind is RunKind.CHECKIN else moments.check_out
    runner = WindowedRun(
        calendar=adapters.calendar,
        clock=adapters.clock,
        notifier=adapters.notifier,
        window=window_from(moment, settings.window_grace),
        policy=RETRY_POLICY,
        moment=moment,
        range_start=_draw_range(settings, kind).start,
    )
    if kind is RunKind.CHECKIN:
        return MorningCheckin(
            adapters.horizon, adapters.clock, runner, settings.desktop, _hold(settings)
        )
    return EveningCheckout(adapters.horizon, adapters.clock, runner, settings.desktop)


def _probe(factory: AdapterFactory) -> int:
    settings = Settings.from_env(os.environ)
    with factory(settings, _PROBE_RUN_KIND) as adapters:
        report = Probe(
            client=adapters.horizon,
            calendar=adapters.calendar,
            clock=adapters.clock,
            chrome_path=settings.chrome_path,
            file_exists=Path.is_file,
            absences=JsonAbsenceStore(settings.absences_file),
            absences_file=settings.absences_file,
            moments=_todays_moments(settings, adapters.clock),
        ).run()
    _echo_probe(settings, report)
    return EXIT_OK if report.ok else EXIT_FAILED


def _draw_range(settings: Settings, kind: RunKind) -> TimeRange:
    """The range ``kind``'s moment is drawn from; its timer fires at the range's start."""
    return settings.checkin_range if kind is RunKind.CHECKIN else settings.checkout_range


def _hold(settings: Settings) -> timedelta:
    return timedelta(seconds=settings.hold_seconds)


def _span(span: TimeRange) -> str:
    return f"{span.start:%H:%M}-{span.end:%H:%M}"


def _echo_plan(plan: RunPlan, language: Language) -> None:
    verdict = text("plan.verdict.yes" if plan.would_run else "plan.verdict.no", language)
    forced = text("plan.forced", language) if plan.forced else ""
    at = f"{plan.at:%Y-%m-%d %H:%M:%S %Z}"
    click.echo(text("plan.header", language, kind=plan.kind, at=at))
    click.echo(
        text("plan.would_run", language, verdict=verdict, decision=plan.decision, forced=forced)
    )
    if plan.waits_until is not None:
        click.echo(text("plan.waits_until", language, moment=f"{plan.waits_until:%H:%M}"))
    source = text(_SOURCE_KEY[plan.verdict_source], language)
    click.echo(text("plan.calendar", language, source=source))
    if plan.moments is not None:
        detail = schedule_detail(plan.moments).in_language(language)
        click.echo(text("plan.schedule", language, detail=detail))
    click.echo(text("plan.steps", language))
    for number, step in enumerate(plan.steps, start=1):
        click.echo(f"  {number}. {step.in_language(language)}")


def _echo_probe(settings: Settings, report: ProbeReport) -> None:
    # Reaching this line means Settings.from_env accepted every variable. Only values
    # that are not credentials are named.
    language = settings.language
    click.echo(
        text(
            "probe.settings.ok",
            language,
            url=settings.horizon_url,
            desktop=settings.desktop,
            checkin=_span(settings.checkin_range),
            checkout=_span(settings.checkout_range),
            timezone=settings.timezone.key,
            language=language,
        )
    )
    for item in report.checks:
        click.echo(_probe_line(item, language))


def _probe_line(item: Check, language: Language) -> str:
    name = item.label.in_language(language)
    detail = item.detail.in_language(language)
    # The day's moments are a fact to read, not a dependency's health: no status.
    if item.name == _SCHEDULE:
        return f"{name}: {detail}"
    return f"{name}: {item.status_label.in_language(language)} - {detail}"


def _configure_logging() -> None:
    """Send the package's log records to the current stderr, replacing an earlier handler.

    The handler sits on the package logger rather than the root, so a host that already
    configured logging (pytest, for one) keeps its own handlers. It is replaced on each
    invocation so a repeated in-process call neither duplicates lines nor writes to a
    stream that has since been closed.
    """
    package = logging.getLogger(_PACKAGE_LOGGER)
    for handler in [h for h in package.handlers if isinstance(h, _StderrHandler)]:
        package.removeHandler(handler)
    handler = _StderrHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    package.addHandler(handler)
    package.setLevel(logging.INFO)


class _StderrHandler(logging.StreamHandler[TextIO]):
    """The CLI's own stderr handler, told apart from any handler a host installed."""
