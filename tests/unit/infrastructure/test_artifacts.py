"""Tests for the artifact directory: screenshot naming and the 14-day rotation."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.domain.schedule import RunKind
from horizon_tracker.infrastructure.artifacts import RETENTION, DirectoryArtifactStore

MOSCOW = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 20, 7, 55, 3, tzinfo=MOSCOW)


class FixedClock:
    """A clock that always answers the same instant."""

    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def now(self) -> datetime:
        return self.moment

    def sleep(self, seconds: float) -> None:
        raise AssertionError("the artifact store must not wait")


def _store(directory: Path, moment: datetime = NOW) -> DirectoryArtifactStore:
    return DirectoryArtifactStore(directory, FixedClock(moment))


def _touch(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(b"png")
    return path


# --- naming ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        (RunKind.CHECKIN, "20261020-075503-checkin.png"),
        (RunKind.CHECKOUT, "20261020-075503-checkout.png"),
    ],
)
def test_a_screenshot_is_named_by_its_local_time_and_kind(
    tmp_path: Path, kind: RunKind, name: str
) -> None:
    assert _store(tmp_path).screenshot_path(kind) == tmp_path / name


def test_the_name_carries_the_clock_wall_time_not_utc(tmp_path: Path) -> None:
    evening = datetime(2026, 10, 20, 17, 0, 0, tzinfo=MOSCOW)

    path = _store(tmp_path, evening).screenshot_path(RunKind.CHECKOUT)

    assert path.name == "20261020-170000-checkout.png"


def test_the_directory_is_created_on_first_use(tmp_path: Path) -> None:
    directory = tmp_path / "nested" / "artifacts"

    path = _store(directory).screenshot_path(RunKind.CHECKIN)

    assert directory.is_dir()
    assert path.parent == directory


def test_asking_for_a_path_writes_no_file(tmp_path: Path) -> None:
    path = _store(tmp_path).screenshot_path(RunKind.CHECKIN)

    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


# --- rotation -------------------------------------------------------------------


def test_the_retention_is_fourteen_days() -> None:
    assert timedelta(days=14) == RETENTION


def test_rotation_removes_screenshots_older_than_fourteen_days(tmp_path: Path) -> None:
    stale = _touch(tmp_path, "20261006-075502-checkin.png")  # 14 days and 1 second old
    old = _touch(tmp_path, "20260901-170000-checkout.png")

    removed = _store(tmp_path).prune()

    assert sorted(removed) == sorted([stale, old])
    assert not stale.exists()
    assert not old.exists()


def test_rotation_keeps_a_screenshot_exactly_fourteen_days_old(tmp_path: Path) -> None:
    boundary = _touch(tmp_path, "20261006-075503-checkin.png")

    assert _store(tmp_path).prune() == []
    assert boundary.exists()


def test_rotation_keeps_recent_screenshots(tmp_path: Path) -> None:
    recent = _touch(tmp_path, "20261019-170000-checkout.png")
    today = _touch(tmp_path, "20261020-075500-checkin.png")

    assert _store(tmp_path).prune() == []
    assert recent.exists()
    assert today.exists()


@pytest.mark.parametrize(
    "name",
    [
        "service.log",
        "20200101-000000-checkin.txt",
        "notes-20200101-000000-checkin.png",
        "20201399-000000-checkin.png",
        "2020-01-01-checkin.png",
    ],
)
def test_rotation_leaves_files_it_did_not_name_alone(tmp_path: Path, name: str) -> None:
    foreign = _touch(tmp_path, name)

    assert _store(tmp_path).prune() == []
    assert foreign.exists()


def test_rotation_leaves_directories_alone(tmp_path: Path) -> None:
    folder = tmp_path / "20200101-000000-checkin.png"
    folder.mkdir()

    assert _store(tmp_path).prune() == []
    assert folder.is_dir()


def test_rotation_of_a_directory_that_does_not_exist_yet_removes_nothing(tmp_path: Path) -> None:
    assert _store(tmp_path / "absent").prune() == []
