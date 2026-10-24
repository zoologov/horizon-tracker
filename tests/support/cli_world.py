"""The fakes behind one ``horizon`` invocation, and the adapter factory that hands them out.

The CLI takes its adapter factory through click's context object, so a test passes
``World.factory`` as ``obj`` and every port the command touches is a fake it can read
back: the Horizon calls, the calendar questions, the reports sent, the prunes.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from click.testing import CliRunner, Result

from horizon_tracker.cli import Adapters, main
from horizon_tracker.domain.ports import HorizonClient, Notifier
from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.domain.session import SessionState
from horizon_tracker.infrastructure.config import Settings
from tests.support.fakes import FakeCalendar, FakeClock, FakeHorizonClient, FakeNotifier

DESKTOP = "DEV desktop"
PACKAGE_LOGGER = "horizon_tracker"


@dataclass
class FakeArtifacts:
    """An artifact store that counts its prunes and writes nothing.

    ``prune_error`` scripts a store whose directory cannot be cleared: every prune
    raises it after being counted.
    """

    prunes: int = 0
    prune_error: OSError | None = None

    def screenshot_path(self, kind: RunKind) -> Path:
        return Path("/nonexistent") / f"{kind.value}.png"

    def prune(self) -> list[Path]:
        self.prunes += 1
        if self.prune_error is not None:
            raise self.prune_error
        return []


# Builds the notifier a command delivers through from the settings that command loaded,
# as the composition root does: the language of the notification is the configured one.
Delivery = Callable[[Settings], Notifier]


class World:
    """The fakes behind one CLI invocation, and the factory that hands them out.

    ``delivery`` replaces the recording notifier with a real one, built from the settings
    the command loaded; ``notifier`` then stays empty and the test reads what the real
    notifier delivered instead.
    """

    def __init__(
        self,
        now: datetime,
        calendar_answer: bool | None = True,
        state: SessionState = SessionState.NO_SESSION,
        desktop: str = DESKTOP,
        delivery: Delivery | None = None,
    ) -> None:
        self.clock = FakeClock(now)
        self.calendar = FakeCalendar(calendar_answer)
        self.notifier = FakeNotifier()
        # What the command delivers through; the recording fake unless a test hands in
        # a way to build a real notifier (the acceptance suite drives the Telegram adapter).
        self.delivery = delivery
        self.client = FakeHorizonClient(desktop=desktop, state=state, clock=self.clock)
        # The Horizon client the command runs over instead of the fake, when a scenario
        # drives the real adapter on the HTML Access fixture; ``client`` then stays unused.
        self.horizon: HorizonClient | None = None
        self.artifacts = FakeArtifacts()
        self.opened: list[tuple[Settings, RunKind]] = []
        self.closed = 0

    @contextmanager
    def factory(self, settings: Settings, kind: RunKind) -> Iterator[Adapters]:
        self.opened.append((settings, kind))
        notifier = self.notifier if self.delivery is None else self.delivery(settings)
        try:
            yield Adapters(
                clock=self.clock,
                calendar=self.calendar,
                notifier=notifier,
                horizon=self.client if self.horizon is None else self.horizon,
                artifacts=self.artifacts,
            )
        finally:
            self.closed += 1

    def invoke(self, args: list[str], env: dict[str, str | None]) -> Result:
        return CliRunner().invoke(main, args, obj=self.factory, env=env)


@contextmanager
def cli_log_handlers_restored() -> Iterator[None]:
    """Take off any handler an invocation left on the package logger once the test ends.

    The CLI attaches a stderr handler on each run; under ``CliRunner`` that stream is
    closed after the invocation, so the handler must not outlive the test.
    """
    package = logging.getLogger(PACKAGE_LOGGER)
    before = list(package.handlers)
    try:
        yield
    finally:
        for handler in package.handlers:
            if handler not in before:
                package.removeHandler(handler)
