"""Tests for the absences file: its layout, its refusals and the atomic private write."""

import json
import os
import stat
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from horizon_tracker.domain.absence import Absence, AbsenceBook, AbsenceKind
from horizon_tracker.domain.ports import AbsenceStore, AbsenceStoreError
from horizon_tracker.infrastructure.absence_store import JsonAbsenceStore

VACATION = Absence(1, AbsenceKind.VACATION, date(2026, 11, 3), date(2026, 11, 14))
DAY_OFF = Absence(4, AbsenceKind.DAY_OFF, date(2026, 12, 31), date(2026, 12, 31))
BOOK = AbsenceBook(absences=(VACATION, DAY_OFF), last_issued=6)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def permissive_umask() -> Iterator[None]:
    """A umask that takes nothing away, so only the store can make a file private."""
    previous = os.umask(0)
    yield
    os.umask(previous)


# --- reading ----------------------------------------------------------------------


def test_the_store_implements_the_port(tmp_path: Path) -> None:
    store: AbsenceStore = JsonAbsenceStore(tmp_path / "absences.json")

    assert store.load() == AbsenceBook()


def test_a_missing_file_is_an_empty_book_and_reading_creates_nothing(tmp_path: Path) -> None:
    state = tmp_path / "state"

    assert JsonAbsenceStore(state / "absences.json").load() == AbsenceBook()
    assert not state.exists()


def test_a_saved_book_is_loaded_back_as_it_was(tmp_path: Path) -> None:
    store = JsonAbsenceStore(tmp_path / "absences.json")

    store.save(BOOK)

    assert store.load() == BOOK
    assert JsonAbsenceStore(tmp_path / "absences.json").load() == BOOK


def test_the_file_holds_the_last_issued_id_and_the_absences_with_iso_dates(
    tmp_path: Path,
) -> None:
    path = tmp_path / "absences.json"

    JsonAbsenceStore(path).save(BOOK)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "last_issued": 6,
        "absences": [
            {"id": 1, "kind": "vacation", "first_day": "2026-11-03", "last_day": "2026-11-14"},
            {"id": 4, "kind": "day_off", "first_day": "2026-12-31", "last_day": "2026-12-31"},
        ],
    }
    assert path.read_text(encoding="utf-8").endswith("}\n")


def test_a_file_without_a_last_issued_id_reads_as_the_highest_id_held(tmp_path: Path) -> None:
    path = tmp_path / "absences.json"
    entry = {"id": 3, "kind": "sick_leave", "first_day": "2026-11-03", "last_day": "2026-11-05"}
    path.write_text(json.dumps({"absences": [entry]}), encoding="utf-8")

    book = JsonAbsenceStore(path).load()

    assert book.last_issued == 3
    assert book.absences == (
        Absence(3, AbsenceKind.SICK_LEAVE, date(2026, 11, 3), date(2026, 11, 5)),
    )


def test_a_saved_book_replaces_the_previous_one_as_a_whole(tmp_path: Path) -> None:
    store = JsonAbsenceStore(tmp_path / "absences.json")
    store.save(BOOK)

    store.save(AbsenceBook(last_issued=6))

    assert store.load() == AbsenceBook(last_issued=6)


_ENTRY = {"id": 1, "kind": "vacation", "first_day": "2026-11-03", "last_day": "2026-11-14"}


def _with(**changes: object) -> dict[str, object]:
    entry: dict[str, object] = dict(_ENTRY)
    for key, value in changes.items():
        if value is None:
            entry.pop(key)
        else:
            entry[key] = value
    return entry


MALFORMED = {
    "not JSON": "{absences: []",
    "a list at the top": "[]",
    "no absences": '{"last_issued": 0}',
    "absences not a list": '{"absences": {}}',
    "an entry not an object": '{"absences": [1]}',
    "no id": json.dumps({"absences": [_with(id=None)]}),
    "an id not a number": json.dumps({"absences": [_with(id="1")]}),
    "an id that is a boolean": json.dumps({"absences": [_with(id=True)]}),
    "an id of zero": json.dumps({"absences": [_with(id=0)]}),
    "an unknown kind": json.dumps({"absences": [_with(kind="holiday")]}),
    "no kind": json.dumps({"absences": [_with(kind=None)]}),
    "no first day": json.dumps({"absences": [_with(first_day=None)]}),
    "a date not in ISO form": json.dumps({"absences": [_with(last_day="14.11.2026")]}),
    "a date in the basic ISO form": json.dumps({"absences": [_with(first_day="20261103")]}),
    "a date that is a number": json.dumps({"absences": [_with(last_day=20261114)]}),
    "a last day before the first": json.dumps({"absences": [_with(last_day="2026-11-02")]}),
    "one id twice": json.dumps({"absences": [_ENTRY, _ENTRY]}),
    "a last issued id below an id held": json.dumps({"last_issued": 0, "absences": [_ENTRY]}),
    "a negative last issued id": json.dumps({"last_issued": -1, "absences": []}),
    "a last issued id not a number": json.dumps({"last_issued": "2", "absences": []}),
    "a last issued id that is a boolean": json.dumps({"last_issued": True, "absences": []}),
}


@pytest.mark.parametrize("content", MALFORMED.values(), ids=MALFORMED.keys())
def test_a_malformed_file_is_refused_naming_the_file(tmp_path: Path, content: str) -> None:
    path = tmp_path / "absences.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(AbsenceStoreError) as refusal:
        JsonAbsenceStore(path).load()

    assert refusal.value.path == path
    assert refusal.value.detail
    assert str(refusal.value).startswith(f"{path}: ")


def test_a_file_that_is_not_utf8_text_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "absences.json"
    path.write_bytes(b'{"absences": ["\xff"]}')

    with pytest.raises(AbsenceStoreError, match="not UTF-8 text"):
        JsonAbsenceStore(path).load()


def test_a_file_that_cannot_be_read_is_refused_by_the_type_of_the_error(tmp_path: Path) -> None:
    path = tmp_path / "absences.json"
    path.mkdir()

    with pytest.raises(AbsenceStoreError, match="cannot be read: IsADirectoryError"):
        JsonAbsenceStore(path).load()


def test_the_refusal_names_the_entry_and_the_field_at_fault(tmp_path: Path) -> None:
    path = tmp_path / "absences.json"
    path.write_text(json.dumps({"absences": [_ENTRY, _with(id=2, kind="holiday")]}), "utf-8")

    with pytest.raises(AbsenceStoreError, match="absence 1: kind 'holiday' is not one of"):
        JsonAbsenceStore(path).load()


# --- writing ----------------------------------------------------------------------


@pytest.mark.usefixtures("permissive_umask")
def test_the_file_is_written_readable_by_its_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "absences.json"

    JsonAbsenceStore(path).save(BOOK)

    assert _mode(path) == 0o600


@pytest.mark.usefixtures("permissive_umask")
def test_a_previous_file_with_a_wider_mode_is_replaced_by_a_private_one(tmp_path: Path) -> None:
    path = tmp_path / "absences.json"
    path.write_text('{"absences": []}', encoding="utf-8")
    path.chmod(0o644)

    JsonAbsenceStore(path).save(BOOK)

    assert _mode(path) == 0o600


@pytest.mark.usefixtures("permissive_umask")
def test_a_missing_state_directory_is_created_private(tmp_path: Path) -> None:
    state = tmp_path / "opt" / "state"

    JsonAbsenceStore(state / "absences.json").save(BOOK)

    assert _mode(state) == 0o700
    assert JsonAbsenceStore(state / "absences.json").load() == BOOK


def test_an_existing_state_directory_keeps_its_mode(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    state.chmod(0o750)

    JsonAbsenceStore(state / "absences.json").save(BOOK)

    assert _mode(state) == 0o750


def test_a_successful_write_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    JsonAbsenceStore(tmp_path / "absences.json").save(BOOK)
    JsonAbsenceStore(tmp_path / "absences.json").save(AbsenceBook(last_issued=6))

    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["absences.json"]


def _fail(*_args: object) -> None:
    raise OSError(28, "No space left on device")


@pytest.mark.parametrize("step", ["fsync", "replace"])
def test_a_write_that_fails_leaves_the_previous_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    path = tmp_path / "absences.json"
    store = JsonAbsenceStore(path)
    store.save(BOOK)
    before = path.read_bytes()
    monkeypatch.setattr(os, step, _fail)  # the store calls os.fsync and os.replace

    with pytest.raises(AbsenceStoreError, match="cannot be written: OSError") as refusal:
        store.save(AbsenceBook(last_issued=6))

    monkeypatch.undo()
    assert refusal.value.path == path
    assert path.read_bytes() == before
    assert store.load() == BOOK
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["absences.json"]


def test_a_state_directory_that_cannot_be_created_is_refused(tmp_path: Path) -> None:
    blocker = tmp_path / "state"
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(AbsenceStoreError, match="cannot be written: FileExistsError"):
        JsonAbsenceStore(blocker / "absences.json").save(BOOK)
