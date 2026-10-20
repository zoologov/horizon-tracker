"""Implements the ``ArtifactStore`` port on a directory: names screenshots and rotates them.

A screenshot is named ``YYYYMMDD-HHMMSS-<kind>.png`` by the clock's wall time, so the
directory sorts by time. Rotation removes only files of that shape whose name is older
than the retention; anything else in the directory is left alone.
"""

# beadloom:domain=infrastructure

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from horizon_tracker.domain.ports import Clock
from horizon_tracker.domain.schedule import RunKind

RETENTION = timedelta(days=14)

_STAMP_FORMAT = "%Y%m%d-%H%M%S"
_SCREENSHOT_NAME = re.compile(r"(\d{8}-\d{6})-[a-z][a-z_]*\.png")

logger = logging.getLogger(__name__)


class DirectoryArtifactStore:
    """Screenshots of runs in one directory, with a time-stamped name and a retention."""

    def __init__(self, directory: Path, clock: Clock, retention: timedelta = RETENTION) -> None:
        self._directory = directory
        self._clock = clock
        self._retention = retention

    def screenshot_path(self, kind: RunKind) -> Path:
        """A path named by the current wall time and ``kind``; creates the directory."""
        self._directory.mkdir(parents=True, exist_ok=True)
        stamp = self._clock.now().strftime(_STAMP_FORMAT)
        return self._directory / f"{stamp}-{kind.value}.png"

    def prune(self) -> list[Path]:
        """Remove screenshots older than the retention; return the paths removed."""
        if not self._directory.is_dir():
            return []
        cutoff = self._clock.now().replace(tzinfo=None) - self._retention
        removed = [path for path, taken_at in self._screenshots() if taken_at < cutoff]
        for path in removed:
            path.unlink()
            logger.info("removed expired artifact %s", path.name)
        return removed

    def _screenshots(self) -> list[tuple[Path, datetime]]:
        """The files named as screenshots, each with the wall time in its name."""
        found = []
        for path in self._directory.iterdir():
            taken_at = _taken_at(path)
            if taken_at is not None and path.is_file():
                found.append((path, taken_at))
        return found


def _taken_at(path: Path) -> datetime | None:
    """The wall time in a screenshot's name, or ``None`` when the name is not ours."""
    match = _SCREENSHOT_NAME.fullmatch(path.name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), _STAMP_FORMAT)
    except ValueError:
        return None
