# Artifact store

The `ArtifactStore` port on a directory: names screenshots by wall time and run kind,
and removes its own files older than 14 days.

## Source

`src/horizon_tracker/infrastructure/artifacts.py`

## Specification

### Purpose

A failed run attaches a screenshot to its report, and the file stays on the VPS for
later inspection. The directory must not grow without bound, and rotation must never
remove a file the service did not write.

### How it works

`screenshot_path(kind)` creates the directory if needed and returns
`<directory>/YYYYMMDD-HHMMSS-<kind>.png`, stamped with the clock's wall time, so the
directory sorts by time. The Horizon adapter writes the screenshot to that path.

`prune()` removes the files whose name has that shape and whose stamp is older than
the retention (14 days by default), logs each removed name, and returns the removed
paths. Any other file in the directory is left alone, and a missing directory prunes
nothing.

The CLI calls `prune()` once before every run that is not a dry run. The call is
best-effort: an `OSError` is logged by its type
(`artifact prune failed, the run goes on: <Type>`) and the run goes on.

## Invariants

- Only files named like `YYYYMMDD-HHMMSS-<kind>.png` are ever removed.
- The age of a file is read from its name, not from the file system.
- `prune()` on a missing directory returns an empty list.

## API

Module `src/horizon_tracker/infrastructure/artifacts.py`:

- `DirectoryArtifactStore(directory: Path, clock: Clock, retention: timedelta =
  RETENTION)` — implements `ArtifactStore`:
  - `screenshot_path(kind: RunKind) -> Path`;
  - `prune() -> list[Path]`.
- `RETENTION` — `timedelta(days=14)`.

The directory is `HT_ARTIFACTS_DIR` (`/opt/horizon-tracker/artifacts` by default).

## Testing

Tests: `tests/unit/infrastructure/test_artifacts.py`; the best-effort prune is
`test_an_artifact_directory_that_cannot_be_pruned_does_not_stop_the_run` in
`tests/unit/test_cli.py`.

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `schedule`
- Used by: `cli`

## Parent

`infrastructure` — [infrastructure README](../../README.md)
