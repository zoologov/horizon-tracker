"""Keeps the owner's absences in one JSON file: the ``AbsenceStore`` port on the disk.

The file holds ``{"last_issued": N, "absences": [...]}``, each absence an object with its
id, its kind and its first and last day as ISO dates. A missing file is an empty book; a
file written before ``last_issued`` existed reads as the highest id it holds. Anything
else that is not that shape is refused with ``AbsenceStoreError``, never guessed at.

A save is atomic: the book goes to a temporary file in the same directory, is flushed to
the disk, and only then replaces the old file, so a failed write leaves the previous book
intact. The file is readable by its owner only (0600), and a state directory the store
has to create is private to its owner (0700).
"""

# beadloom:domain=infrastructure
# beadloom:feature=absence-store

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from horizon_tracker.domain.absence import Absence, AbsenceBook, AbsenceKind
from horizon_tracker.domain.ports import AbsenceStoreError

PRIVATE_DIRECTORY = 0o700  # the mode of a state directory the store creates

_KINDS = ", ".join(kind.value for kind in AbsenceKind)


class JsonAbsenceStore:
    """The absences file at ``path``: loads and saves the whole book, atomically."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> AbsenceBook:
        """The book in the file; an empty book when there is no file yet."""
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return AbsenceBook()
        except UnicodeDecodeError as error:
            raise AbsenceStoreError(self._path, "not UTF-8 text") from error
        except OSError as error:
            detail = f"cannot be read: {type(error).__name__}"
            raise AbsenceStoreError(self._path, detail) from error
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise AbsenceStoreError(self._path, f"not valid JSON: {error}") from error
        try:
            return _book_from(document)
        except ValueError as error:
            raise AbsenceStoreError(self._path, str(error)) from error

    def save(self, book: AbsenceBook) -> None:
        """Replace the file with ``book``; on failure the previous file is left as it was."""
        text = json.dumps(_document_of(book), indent=2) + "\n"
        try:
            _ensure_private_directory(self._path.parent)
            _write_atomically(self._path, text)
        except OSError as error:
            detail = f"cannot be written: {type(error).__name__}"
            raise AbsenceStoreError(self._path, detail) from error


def _ensure_private_directory(directory: Path) -> None:
    """Create ``directory`` for its owner only when it is missing; an existing one is kept."""
    if not directory.is_dir():
        directory.mkdir(mode=PRIVATE_DIRECTORY, parents=True)


def _write_atomically(path: Path, text: str) -> None:
    """Write ``text`` to a temporary file beside ``path``, sync it, then rename it over ``path``.

    ``mkstemp`` creates the file readable and writable by its owner only (0600), whatever
    the umask allows, and the rename carries that mode over to ``path``.
    """
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _document_of(book: AbsenceBook) -> dict[str, object]:
    return {
        "last_issued": book.last_issued,
        "absences": [
            {
                "id": absence.id,
                "kind": absence.kind.value,
                "first_day": absence.first_day.isoformat(),
                "last_day": absence.last_day.isoformat(),
            }
            for absence in book.absences
        ],
    }


def _book_from(document: object) -> AbsenceBook:
    """The book a parsed file describes; ``ValueError`` names what does not fit the layout."""
    if not isinstance(document, dict):
        raise ValueError("the file is not a JSON object")
    entries = document.get("absences")
    if not isinstance(entries, list):
        raise ValueError('"absences" is not a list')
    absences = tuple(_absence_from(index, entry) for index, entry in enumerate(entries))
    if "last_issued" not in document:
        return AbsenceBook.of(absences)
    last_issued = _whole_number(document["last_issued"], '"last_issued"')
    return AbsenceBook(absences=absences, last_issued=last_issued)


def _absence_from(index: int, entry: object) -> Absence:
    if not isinstance(entry, dict):
        raise ValueError(f"absence {index}: not a JSON object")
    try:
        return Absence(
            id=_whole_number(entry.get("id"), "id"),
            kind=_kind(entry.get("kind")),
            first_day=_day(entry.get("first_day"), "first_day"),
            last_day=_day(entry.get("last_day"), "last_day"),
        )
    except ValueError as error:
        raise ValueError(f"absence {index}: {error}") from error


def _whole_number(value: object, name: str) -> int:
    # A JSON true is a Python int as well; it is not an id.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} {value!r} is not a whole number")
    return value


def _kind(value: object) -> AbsenceKind:
    if not isinstance(value, str) or value not in AbsenceKind:
        raise ValueError(f"kind {value!r} is not one of {_KINDS}")
    return AbsenceKind(value)


def _day(value: object, name: str) -> date:
    """An ISO ``YYYY-MM-DD`` date, written exactly so; the basic form ``YYYYMMDD`` is refused."""
    if isinstance(value, str):
        try:
            day = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            if day.isoformat() == value:
                return day
    raise ValueError(f"{name} {value!r} is not a date in the form YYYY-MM-DD")
