# Contributing to horizon-tracker

horizon-tracker is maintained by its owner, [@zoologov](https://github.com/zoologov). Bug
reports and feature requests are welcome through the issue forms. A vulnerability is never
reported in a public issue: see [`SECURITY.md`](SECURITY.md). Everyone taking part follows the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Setting up a fresh clone

You need Python 3.12, [`uv`](https://docs.astral.sh/uv/), the Beadloom CLI
(`uv tool install beadloom==9.0.0`, the version CI installs) and `bd`, the
[beads](https://github.com/steveyegge/beads) CLI.

```bash
git clone https://github.com/zoologov/horizon-tracker.git
cd horizon-tracker
uv sync --all-extras                   # the package and the dev tools, from uv.lock
uv run playwright install chromium     # the browser the adapter tests drive
git config beads.role maintainer       # or "contributor"; bd asks for it
beadloom install-hooks                 # pre-commit checks and the pre-push Beadloom Gate
beadloom reindex                       # build the local architecture index
```

A fresh clone carries the work items only as the export `.beads/issues.jsonl`, not as a beads
database. `bd init --prefix ht` followed by `bd import` builds the database from that export
(the sequence that worked on the bd release [`.claude/CLAUDE.md`](.claude/CLAUDE.md) names),
and the same file describes everything `bd` and `beadloom` do after that.

## How work is done

The project is developed with the Beadloom agentic flow. A change starts as a work item with
a key (`HT-xxx`): `/task-init` writes its documents under
`.claude/development/docs/features/<KEY>/` and splits it into beads, the units of work `bd`
tracks. Each bead is claimed, implemented test-first (a failing test, then the code that makes
it pass, then the refactor), checked by the gates below and closed with a comment saying what
changed. `beadloom prime` and `beadloom ctx <ref>` give the architecture context; the layers
and their dependency direction are enforced by `beadloom lint --strict`. The full protocol,
including the roles and the multi-agent waves, is in [`.claude/CLAUDE.md`](.claude/CLAUDE.md).

## Trunk-based development

`main` is the trunk, and it is protected on GitHub: nobody pushes to it directly, the owner
included.

- **A branch per work item**, named `features/<KEY>` (for example `features/HT-008`), cut from
  `main`.
- **One pull request per work item** (or per shippable slice of one), not one per commit.
- **CI must pass.** The pull request runs the CI workflow, and its `ci-ok` check is required;
  the branch must be up to date with `main` before it merges.
- **The owner merges** once `ci-ok` is green. No review approval is required, and the review
  of a change is part of the Beadloom flow.
- **A release is a tag on `main`** (see "Releasing" below); release tags are created by the
  owner only and are never moved or deleted.

## Commit messages

```text
[HT-xxx] <type>: <description>
```

The type is one of `feat`, `fix`, `refactor`, `docs`, `test` or `chore`; the description says
what the commit does, in the imperative. For example: `[HT-007] feat: HT_LANGUAGE picks the
language of the notification and the CLI output`.

## The gates

Run these before you push; CI runs the same checks on the pull request.

```bash
uv run pytest                       # the suite; CI adds --cov and the 80 % floor
uv run ruff check                   # lint, the whole repository as CI runs it
uv run ruff format --check
uv run mypy                         # strict; the scope is [tool.mypy] files
beadloom ci                         # architecture and documentation gate (the pre-push Gate)
scripts/mutation.sh --changed-since main --out /tmp/mutation   # mutation gate, per change
```

The mutation gate covers the pure domain only (`[tool.mutmut]` in `pyproject.toml`). On a pull
request CI runs it over the changed domain functions with a minimum score of 85 %; its verdict
is reported beside `ci-ok` and is not part of it.

## Releasing

The owner cuts releases. The version follows [Semantic Versioning](https://semver.org/)
over the service's public surface, and [`docs/guides/releasing.md`](docs/guides/releasing.md)
states that surface and the full procedure. In brief:

1. classify the changes since the last release by the public surface: MAJOR, MINOR or PATCH;
2. bump `[project] version` in `pyproject.toml`, then run `uv lock` (the deploy's
   `uv sync --locked` refuses a stale lock) and `beadloom setup-agentic-flow` (the
   `Current version` line of `.claude/CLAUDE.md`);
3. move the `[Unreleased]` entries of [`CHANGELOG.md`](CHANGELOG.md) into a section
   `## [X.Y.Z] - YYYY-MM-DD`;
4. open one pull request, wait for `ci-ok` and merge it;
5. tag the merge commit with `git tag -a vX.Y.Z` and push the tag;
6. the Release workflow verifies the tag, runs CI, deploys to the host, publishes the GitHub
   Release and the architecture portal.

A pull request that changes the public surface adds its line under `[Unreleased]` in
`CHANGELOG.md` as part of the change.

## Language

Code, docstrings, documentation, the work-item documents and commit messages are written in
English. The language of the notifications and of the CLI output is a runtime setting
(`HT_LANGUAGE`): the message catalogue in `src/horizon_tracker/domain/messages.py` holds every
user-facing text in each supported language.
