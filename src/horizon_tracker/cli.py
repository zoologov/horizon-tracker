"""Wires the adapters into the use cases behind the ``horizon`` commands: the composition root.

``horizon checkin`` and ``horizon checkout`` run one daily run each; ``--force`` ignores
the window and the calendar (a manual run from the VPS), ``--dry-run`` names the plan and
never logs in. ``horizon probe`` asks every dependency whether a run could go ahead.

Settings come from the environment; a missing or malformed variable is named on stderr
and the command exits 1 before anything is built. A run exits 1 only when it failed: a
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
from horizon_tracker.application.probe import DryRun, Probe, ProbeReport, RunPlan
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.ports import (
    ArtifactStore,
    Clock,
    HorizonClient,
    Notifier,
    WorkingDayCalendar,
)
from horizon_tracker.domain.report import Outcome
from horizon_tracker.domain.schedule import RetryPolicy, RunKind, Window
from horizon_tracker.infrastructure.artifacts import DirectoryArtifactStore
from horizon_tracker.infrastructure.clock import SystemClock
from horizon_tracker.infrastructure.config import ConfigError, Settings
from horizon_tracker.infrastructure.horizon_playwright import PlaywrightHorizonClient
from horizon_tracker.infrastructure.isdayoff import IsDayOffCalendar
from horizon_tracker.infrastructure.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILED = 1

# Not configurable: three attempts half a minute apart fit a five-minute window, and the
# window, not the count, is what ends a scheduled run. A --force run has the whole day as
# its window, so there the count is the bound.
RETRY_POLICY = RetryPolicy(max_attempts=3, backoff=timedelta(seconds=30))

# The probe never screenshots, but the Horizon adapter is built for one kind of run.
_PROBE_RUN_KIND = RunKind.CHECKIN

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_PACKAGE_LOGGER = "horizon_tracker"

_SOURCE_TEXT = {
    VerdictSource.CALENDAR: "isdayoff.ru",
    VerdictSource.WEEKDAY_FALLBACK: "isdayoff.ru unreachable, Mon-Fri rule",
    None: "not asked (forced)",
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
        notifier = _notifier(settings, http)
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


def _notifier(settings: Settings, http: httpx.Client) -> TelegramNotifier:
    """The Telegram notifier; a token it refuses is a configuration error, not a crash."""
    try:
        return TelegramNotifier(settings.telegram_token, settings.telegram_chat_id, http)
    except ValueError as error:
        # The adapter's message never echoes the token; Settings has already refused a
        # blank chat id, so the token is the only value this constructor can refuse.
        raise ConfigError("TELEGRAM_BOT_TOKEN", str(error)) from error


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
    "--force", is_flag=True, help="Ignore the window and the calendar (a manual run)."
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
        return EXIT_FAILED


def _run(factory: AdapterFactory, kind: RunKind, *, dry_run: bool, force: bool) -> int:
    settings = Settings.from_env(os.environ)
    with factory(settings, kind) as adapters:
        use_case = _use_case(adapters, settings, kind)
        if dry_run:
            _echo_plan(DryRun(use_case).plan(force=force))
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


def _use_case(
    adapters: Adapters, settings: Settings, kind: RunKind
) -> MorningCheckin | EveningCheckout:
    runner = WindowedRun(
        calendar=adapters.calendar,
        clock=adapters.clock,
        notifier=adapters.notifier,
        window=_window(settings, kind),
        policy=RETRY_POLICY,
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
        ).run()
    _echo_probe(settings, report)
    return EXIT_OK if report.ok else EXIT_FAILED


def _window(settings: Settings, kind: RunKind) -> Window:
    return settings.checkin_window if kind is RunKind.CHECKIN else settings.checkout_window


def _hold(settings: Settings) -> timedelta:
    return timedelta(seconds=settings.hold_seconds)


def _span(window: Window) -> str:
    return f"{window.start:%H:%M}-{window.end:%H:%M}"


def _echo_plan(plan: RunPlan) -> None:
    verdict = "yes" if plan.would_run else "no"
    forced = ", forced: window and calendar ignored" if plan.forced else ""
    click.echo(f"dry run: {plan.kind} at {plan.at:%Y-%m-%d %H:%M:%S %Z}")
    click.echo(f"would run now: {verdict} ({plan.decision}{forced})")
    click.echo(f"calendar: {_SOURCE_TEXT[plan.verdict_source]}")
    click.echo("steps of one attempt:")
    for number, step in enumerate(plan.steps, start=1):
        click.echo(f"  {number}. {step}")


def _echo_probe(settings: Settings, report: ProbeReport) -> None:
    # Reaching this line means Settings.from_env accepted every variable. Only values
    # that are not credentials are named.
    click.echo(
        f"settings: ok - portal {settings.horizon_url}, desktop {settings.desktop!r}, "
        f"check-in {_span(settings.checkin_window)}, "
        f"check-out {_span(settings.checkout_window)}, {settings.timezone.key}"
    )
    for item in report.checks:
        click.echo(f"{item.name}: {item.status} - {item.detail}")


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
