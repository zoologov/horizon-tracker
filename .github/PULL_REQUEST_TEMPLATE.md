## Work item

<!-- The key of the work item, e.g. HT-008, and its documents under
     .claude/development/docs/features/<KEY>/. -->

Key:

## What changed and why

<!-- What the change does, in a few sentences, and the reason for it. -->

## Gates run

- [ ] `uv run pytest`
- [ ] `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`
- [ ] `uv run mypy src/`
- [ ] `beadloom ci`

## Changelog

<!-- The line this change adds under [Unreleased] in CHANGELOG.md, or "none" for a change
     a user of the service cannot see. -->

## Public surface

<!-- Which part of the version this change raises; docs/guides/releasing.md states the
     public surface and the rule. -->

- [ ] MAJOR: a surface removed, renamed, or given a different default or meaning
- [ ] MINOR: a surface added
- [ ] PATCH: a fix that changes no surface
- [ ] none: no release is needed for this change

## Secrets

- [ ] No secret is in the diff, in a test fixture, in a screenshot or in the logs of this
      change.
