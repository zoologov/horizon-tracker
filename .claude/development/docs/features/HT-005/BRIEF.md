# BRIEF: HT-005 — GitHub Actions by best practice: stages, pins, Dependabot, nightly mutations

> **Type:** chore
> **Status:** Approved
> **Created:** 2026-10-20

---

## Problem

The HT-001 workflows work (two green deploys), but are assembled as one job and lack some of the
practices a repository with auto-deploy to a server is expected to keep:

- `ci.yml` — a single job `ci` for everything: ruff, mypy, Playwright, pytest, beadloom. No
  stages and no early failure: 2 extra minutes of Chromium and tests on a linter error; no
  single aggregating status that branch protection could require.
- Actions are referenced by tag (`actions/checkout@v4`, `astral-sh/setup-uv@v6`), not by
  SHA: a tag can be rewritten, the supply chain is not pinned. Dependabot is configured neither
  for actions nor for `uv.lock`.
- `actionlint`, `shellcheck` for `deploy/*.sh` and `systemd-analyze verify` for the units
  run only by the agents' hands; CI has none of them.
- `ruff format --check` and `mypy tests/` do not run in CI (clean locally, but there is no gate).
- The mutation gate of the core (`scripts/mutation.sh`, 243 mutants) runs only manually.
- No job summary: coverage and the timers' state after the deploy are visible only in the log.
- `main` is not protected: a direct push goes through, no required check is set. For a neighbouring service on the same host the same
  GitHub plan answered 403 to branch protection; not measured here.

## Solution

**`ci.yml`, three stages with early failure, one aggregating status:**

| Stage | Jobs (parallel within the stage) | What it does |
|--------|----------------------------------|------------|
| 1 | `lint`, `types`, `workflow-lint` | `ruff check` + `ruff format --check`; `mypy src/ tests/`; `actionlint`, `shellcheck deploy/*.sh`, `systemd-analyze verify deploy/*.service deploy/*.timer` (in a sandbox root, as the unit test does) |
| 2 | `tests` (needs: stage 1), `beadloom-gate` (needs: stage 1) | pytest with coverage (the 80 % threshold is already in pyproject), `coverage.xml` as an artifact and a line in `$GITHUB_STEP_SUMMARY`; beadloom on a clean index + `docs spaces --strict` |
| 3 | `ci-ok` (needs: all) | the single status for branch protection; red if any job is red or skipped |

Python matrix: `3.12` (the VPS, mandatory) and `3.13` (the development environment). Every job:
`timeout-minutes`, `permissions: contents: read`, a uv cache and a Playwright browser cache keyed by
the version from `uv.lock`.

**Pins and updates:** every `uses:` by full SHA with a version comment;
`.github/dependabot.yml` — `github-actions` and `uv` weekly, grouping minor/patch.

**`mutation.yml`, as in beadloom (the owner's correction of 2026-10-20):** `.beadloom/flow.yml`
declares `mutation.targets: [src/horizon_tracker/domain/]`; the job `mutation-per-change` on
`pull_request` mutates only the functions the PR touched within the declared area —
`beadloom mutation --changed-since <merge-base>` gives the population and the plan, `mutmut` runs
over it, `beadloom mutation --stats … --min-score 0.85` judges; an empty population is an explicit
"nothing to mutate", not a green. The job `mutation-sample` on a weekly schedule and by
button: a random sample of the whole area with a stride (`--sample-of`). A full run of all
mutants on every PR is not done — that is exactly the beadloom scheme.

**`deploy.yml`:** without changing the contract (`workflow_call` → `ci.yml`, environment
`horizon-vps`, the same SHA, `try-restart`, smoke `probe`); a preflight SSH step is added
(`ssh … true` before any change) and a summary after the deploy: the commit, the `probe` output,
`systemctl list-timers 'horizon-*'`. Pins by SHA as in CI.

**The workflow contract tests** (`tests/unit/deploy/test_ci_workflow.py`,
`test_deploy_workflow.py`) are updated to the stages: the order of `needs`, `ci-ok` depends on
all, every `uses:` is pinned to a SHA, no step is under `continue-on-error`.

**Branch protection (the owner or the local agent with `gh`):** required check `ci-ok`,
force-push and deletion forbidden, 0 required reviews (the owner merges alone). If the plan
answers 403 — record it in the project layer of CLAUDE.md, as the neighbouring service did, instead of claiming
"main is protected".

## Axes

Derived, never authored. Run `beadloom impact <path|symbol>`, paste its answer into the table,
then take the scope decision in the last two columns — the derivation says what a change ranges
over, a person says how much of it this work item takes. The `refs:` of every bead below is
generated from the rows kept in scope, so a bead naming a node this table does not is a finding.

Rule each row by the node's role in the change: the axis a node surfaced under is not its role.
The axis is the node's relation to the seed, so a `callers` row can be a work site — a node that
calls into the change can also own what the change must edit. `Owns unread` names the files the
node owns that the derivation could not read; a count there is a question to answer before `no`.

> **Derived by:** `beadloom impact .github/workflows/ci.yml --section` over `.github` (and over `deploy.yml`, `tests/unit/deploy/`, `deploy/` — the same result), 2026-10-20, role explore
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 1 no-seed, 1 sweep-narrower-than-the-project, 1 unreadable-target (the derivation reads Python; YAML workflows, shell and systemd units it does not read, and `tests/unit/deploy/` belongs to no node — `no-node-for-path`)

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — this derivation reads Python source and could not read .github/workflows/ci.yml, so nothing that file defines was read and no caller or writer of it was found | — | no | no row: no node named |
| callers | — | unresolved — this derivation reads Python source and could not read .github/workflows/ci.yml, so nothing that file defines was read and no caller or writer of it was found | — | no | no row: no node named |
| declared (outside the derivation) | horizon-tracker | `.github/workflows/ci.yml`, `deploy.yml`, the new `mutation.yml`, `dependabot.yml`; `tests/unit/deploy/test_ci_workflow.py`, `test_deploy_workflow.py` | `.github/**`, `deploy/**` — not Python | yes | the root service owns the workflows and the deploy; the layers' code does not change |

## Beads

**Parent bead:** ht-s7q

Status lives in ACTIVE.md, reconciled from the tracker by the pre-commit active-sync, so this
table names the beads and carries no status. The Tracker cell holds `-` until the beads are
created, and then the id the tracker answered.

| ID | Tracker | Name | Priority |
|----|---------|------|----------|
| BEAD-01 | ht-5ni | Workflows: CI stages, `ci-ok`, pins by SHA, Dependabot, `mutation.yml` per change + a weekly sample, preflight and summary in deploy; contract tests | P1 |
| BEAD-02 | ht-kc1 | Review: stage order, pins, absence of `continue-on-error`, secrets | P1 |
| BEAD-03 | ht-hdv | Owner/local agent: branch protection of `main` with required `ci-ok` (or a 403 record in the project layer) | P1 |

Order: BEAD-01 starts after BEAD-05 of HT-003 (`ht-978`), which changes the `.env` contract in
`deploy.yml`, so that two work items do not edit one file in parallel.

## Acceptance Criteria

- [ ] CI on a PR shows three stages and the `ci-ok` status; a `ruff` error stops the run before Chromium and the tests — non-behavioural: a property of the workflow, checked by the contract test and by a live run on a PR
- [ ] Every `uses:` is pinned to a SHA; Dependabot opens PRs for updates — non-behavioural: a property of the repository
- [ ] `mutation-per-change` on a PR mutates only the touched functions and names their count; `mutation-sample` ran by button with a sample stride — non-behavioural: observation in Actions
- [ ] The deploy on merge is green with preflight and summary — non-behavioural: a Deploy run
- [ ] Branch protection is set or its unavailability is recorded — non-behavioural: a GitHub setting

## Non-behavioural declaration

| Node | Reason it carries no behaviour |
|------|-------------------------------|
| horizon-tracker | workflows and GitHub settings change how the code is checked and rolled out, not what the service does; the observer is Actions and branch protection, not a user of the service |
