# Absence store

The `AbsenceStore` port on one JSON file: the absences and the highest id issued, a
missing file empty, a malformed one refused, written atomically and readable by its owner
only.

## Source

`src/horizon_tracker/infrastructure/absence_store.py`

## Specification

### Purpose

The owner's absences must outlive a run, a restart, a deploy and a reboot, so they live in
a file outside the checkout: `HT_STATE_DIR/absences.json`, by default
`/opt/horizon-tracker/state/absences.json` (the `settings` SPEC). The bot writes the file
and the scheduled runs read it. A write that fails must not destroy the absences already
entered, and a file the store cannot make sense of must be refused, not half-read.

### How it works

The file holds one JSON object:

```json
{
  "last_issued": 6,
  "absences": [
    {"id": 1, "kind": "vacation", "first_day": "2026-11-03", "last_day": "2026-11-14"}
  ]
}
```

`kind` is an `AbsenceKind` value (`vacation`, `sick_leave`, `day_off`), and the days are
ISO dates written exactly as `YYYY-MM-DD`. `last_issued` is the highest id ever handed
out, so the id of a deleted absence is not reissued (the `absence` SPEC).

`load()` reads the file into an `AbsenceBook`:

- a missing file, or a missing state directory, is the empty book, and reading creates
  nothing;
- a file without `last_issued` reads as the highest id it holds (`AbsenceBook.of`);
- anything else that does not fit the layout raises `AbsenceStoreError` naming the file
  and what is wrong: not UTF-8 text, not valid JSON, not an object, `"absences"` not a
  list, an entry that is not an object, an id or `last_issued` that is not a whole number
  (a JSON `true` included), an unknown kind, a day not in the form `YYYY-MM-DD` (the
  basic form `20261103` included), a last day before the first, one id twice, or a
  `last_issued` below an id held. An entry's fault names its position:
  `absence 1: kind 'holiday' is not one of vacation, sick_leave, day_off`. Keys the
  layout does not name are ignored;
- a file that cannot be read (a directory in its place, a permission refused) raises
  `AbsenceStoreError` with `cannot be read: <ErrorType>`.

`save(book)` writes the whole book, indented, ending in a newline, the absences in the
book's order. The write is atomic: the text goes to a temporary file
`.absences.json.<random>` in the same directory, is flushed and `fsync`ed, and only then
replaces `absences.json` with `os.replace`. When any step fails the temporary file is
removed, the previous file is left byte for byte as it was, and `AbsenceStoreError` is
raised with `cannot be written: <ErrorType>`. The temporary file is created 0600 by
`mkstemp` whatever the umask allows, and the rename carries that mode over, so the file is
readable by its owner only even when an earlier file had a wider mode. A missing state
directory is created, with its missing parents, with mode 0700. An existing one keeps its
mode.

The store logs nothing: the callers decide what a refusal means (a run treats a broken
store as empty, `probe` reports it).

## Invariants

- A failed `save` leaves the previous file intact and no temporary file behind.
- The file is mode 0600, and a state directory the store created is mode 0700.
- `load` never returns a book the file does not describe exactly: a malformed file is
  refused as a whole.
- `load` on a missing file creates no directory and no file.

## API

Module `src/horizon_tracker/infrastructure/absence_store.py`:

- `JsonAbsenceStore(path: Path)` — implements `AbsenceStore`:
  - `load() -> AbsenceBook`;
  - `save(book: AbsenceBook) -> None`;
  - both raise `AbsenceStoreError(path, detail)` (declared in `domain/ports.py`).
- `PRIVATE_DIRECTORY` — `0o700`, the mode of a state directory the store creates.

The path is `Settings.absences_file`, `HT_STATE_DIR / "absences.json"`.

## Testing

Tests: `tests/unit/infrastructure/test_absence_store.py`, on `tmp_path`: the round trip
and the file's layout, a file without `last_issued`, twenty-one malformed files, a file
that is not UTF-8 and one that cannot be read, the modes under a permissive umask, a
directory the store creates and one it keeps, no temporary file after a write, and a
write failing at `fsync` and at `os.replace` that leaves the previous file intact.

## Dependencies

Derived from the imports on reindex.

- Depends on: `absence`, `ports`
- Used by: `cli` (built once in `open_adapters` for every command: the runs read it, the
  probe's `absences` check reads it, `horizon bot` reads and writes it)

## Parent

`infrastructure` — [infrastructure README](../../README.md)
