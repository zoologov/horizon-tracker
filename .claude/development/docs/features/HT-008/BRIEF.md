# BRIEF: HT-008 — Release flow on tags, one workflow per event, a protected trunk, the portal on Pages, and the repository's public face

> **Type:** chore
> **Status:** Done
> **Created:** 2026-10-21

---

## Problem

The repository deploys on every push to `main`, has never been released, and carries no public
face:

- **Every event starts several workflows, and one of them runs twice.** A push to `main` runs
  `ci.yml` (its `push` trigger) and `deploy.yml`, whose `gate` job calls `ci.yml` again through
  `workflow_call`: the same commit is checked twice, in two runs, before anything reaches the
  VPS. A pull request starts `ci.yml` and `mutation.yml`: two workflows, two check lists, for one
  change. Nothing says which event starts what.
- **Deploy is not a release.** Whatever lands on `main` is on the VPS minutes later, whether it
  was meant to run on the host or not. There is no tag, no version anyone can name on the
  host, and `pyproject.toml` has said `0.1.0` since the first commit; `__version__` in
  `src/horizon_tracker/__init__.py` is a second copy that nothing checks
  (`beadloom version-surface`: "checked by nothing").
- **No release policy.** No CHANGELOG, no statement of what the version number promises, no
  rule that turns a change into MAJOR, MINOR or PATCH. Beadloom holds all three (its
  `CONTRIBUTING.md` "Release Process" and `docs/guides/public-api.md`); this repository holds
  none.
- **No community files.** No `LICENSE` although `pyproject.toml` declares MIT, no
  `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, no pull-request or issue templates.
  The README has no badges; the neighbouring Bob repository has the set the owner wants here.
- **`main` is held by discipline, not by GitHub.** The core of CLAUDE.md states trunk-based
  development with a protected `main`; the project layer says "not measured, 403" because
  branch protection is a paid feature on a private repository (`gh api
  .../branches/main/protection` answered `403 Upgrade to GitHub Pro` on 2026-10-21). The owner
  makes the repository **public** in this work item, which lifts the limit: protection can be set,
  measured and written down, and the project layer stops describing a gap.
- **No portal.** Beadloom builds a portal of the architecture graph (`beadloom docs site`:
  overview, a page per node, the dashboard) and nothing publishes it; the repository has no
  GitHub Pages.
- **The version lies.** `0.1.0` reads as a prototype, and the service has been in production on
  the VPS since the HT-001 deploys: the timers fire, the owner is checked in and out every
  working day. The first release has to say so.

## Solution

**One workflow per event.** Three files, each with one trigger family; a reader can tell from
the file name what started a run:

| Event | Workflow | Runs today | Runs after |
|-------|----------|------------|------------|
| pull request to `main` | `ci.yml` (CI) | `ci.yml` + `mutation.yml` | `ci.yml` |
| push to `main` (a merge) | `ci.yml` (CI) | `ci.yml` + `deploy.yml` → `ci.yml` again, then the VPS | `ci.yml`; nothing reaches the VPS |
| tag `vX.Y.Z` pushed | `release.yml` (Release) | — | `release.yml`: verify → CI (`workflow_call`) → deploy → GitHub Release → the portal on Pages |
| Monday 04:23 UTC / by hand | `mutation.yml` (Mutation sample) | the weekly sample | the weekly sample, unchanged |
| Dependabot's weekly PRs | `ci.yml` | `ci.yml` + `mutation.yml` | `ci.yml` |

- **`ci.yml`** keeps its three stages and `ci-ok`. `mutation-per-change` moves in from
  `mutation.yml` as a stage-2 job with `if: github.event_name == 'pull_request'`; it stays out of
  `ci-ok`'s `needs` (the owner's HT-005 decision: the mutation verdict is informative). The
  `push: main` trigger stays: a merge is re-checked once on `main` (the post-merge safety net a
  plan without branch protection needs), and the README badge reads it.
- **`release.yml`** is new; `deploy.yml` is removed and its `deploy` job moves here with the
  same contract: Environment `horizon-vps`, the same secrets and variables, the same steps in the
  same order, `try-restart`, the `horizon probe` smoke, the summary. Triggers: `push` of a tag
  matching `v[0-9]+.[0-9]+.[0-9]+` (strict `MAJOR.MINOR.PATCH`, so a pre-release tag starts
  nothing), and `workflow_dispatch` with one input `tag` naming an existing release tag (the
  redeploy a secret rotation needs; nothing else reaches the host). Jobs, each starting only when
  the one before it passed:
  1. `verify` — the tag is strict semver; its commit is an ancestor of `origin/main` (only
     `main` is released); `pyproject.toml` `[project] version` equals the tag without `v`;
     `CHANGELOG.md` holds `## [X.Y.Z] - YYYY-MM-DD` for it, and that section is extracted as the
     release notes (an artifact). A tag that fails any check deploys nothing and the step names
     the check.
  2. `gate` — `ci.yml` through `workflow_call`, on the tagged commit: what reaches the host
     passed what a pull request passes.
  3. `deploy` — today's deploy job; the summary names the tag and the version beside the commit.
  4. `publish` — `uv build` and a GitHub Release `vX.Y.Z` with the extracted notes and the wheel
     and sdist as assets; `permissions: contents: write` in this job only; idempotent (a release
     that exists is edited, not duplicated, so a tag created through the GitHub Releases UI and a
     redeploy by dispatch both work). Published after a green deploy, so no release names a
     version the host does not run.
  5. `portal` — the Beadloom portal to GitHub Pages, after `publish`: the steps of the workflow
     `beadloom docs site --pages-workflow` generates (Configure Pages and the base check,
     `pip install "beadloom[languages]==9.0.0"`, `beadloom reindex`, `beadloom docs site --out
     site`, Node 22, `npm ci`, `npm run docs:build`, `upload-pages-artifact`), then
     `deploy-pages` in a job of its own with `pages: write` + `id-token: write` and the
     `github-pages` environment, concurrency group `pages`. The generated file itself is not
     used: it deploys on every push to `main`, and the owner wants the portal to follow releases
     — so `beadloom docs site --pages-workflow` is never run here (its file would be a second
     deploy path) and the release's job carries a comment saying which generator version its
     steps come from. `.beadloom/config.yml` gets the `site:` block: `title`, `description`,
     `base: /horizon-tracker/` (the base GitHub Pages serves a project repository under; `docs
     site` warns without it), `repo_url: https://github.com/zoologov/horizon-tracker`. The
     dispatch redeploy runs the portal too: the portal shows the released tree.
- **`mutation.yml`** keeps `mutation-sample` and its `schedule` + `workflow_dispatch`; the
  `pull_request` trigger and `mutation-per-change` leave it.
- **`dependabot.yml`** is unchanged.
- Every `uses:` stays pinned to a SHA with its version comment; no `continue-on-error`, no
  `|| true`; no `${{ }}` inside a `run:` script; secrets enter through `env:` only — the HT-005
  rules, now also the contract of `release.yml`.

**The first release is `1.0.0`.** The service is in production, so SemVer §5 applies: the
public surface is in use and the version says so. BEAD-01 bumps `pyproject.toml` to `1.0.0` and
regenerates the `Current version` line of `.claude/CLAUDE.md` (`beadloom setup-agentic-flow`
writes it; `beadloom doctor` checks it); the first tag is `v1.0.0` on the merge commit of this
work item.

**The version has one source.** `pyproject.toml` `[project] version` is the source of truth
(`beadloom version-surface` already names it so). `src/horizon_tracker/__init__.py` reads
`__version__` from `importlib.metadata.version("horizon-tracker")` instead of carrying a copy;
`horizon --version` keeps printing it; a unit test holds `horizon --version` equal to the
`pyproject.toml` value, which closes the "checked by nothing" row. `beadloom doctor` keeps
checking the `Current version` line of `.claude/CLAUDE.md`.

**Release policy (`docs/guides/releasing.md`, after Beadloom's).** Semantic Versioning 2.0.0.
The guide names what the version number promises for a *service* — the public surface:

1. the `horizon` command: its subcommands, options and exit codes;
2. the environment variables: their names, defaults and accepted values (the `.env` contract
   of `docs/guides/deployment.md`);
3. the deploy contract: the names of the `horizon-vps` secrets and variables, the unit names,
   the `/opt/horizon-tracker` layout and the `horizon` user;
4. the shape of the Telegram report is **not** promised (prose for a person), and Python import
   paths are not public.

A table turns a change into a version part: a surface removed, renamed, or given a different
default or meaning → MAJOR; a surface added → MINOR; a fix that changes no surface → PATCH.
The release steps are the owner's: classify → bump `pyproject.toml` → move `[Unreleased]` into
`[X.Y.Z] - date` with *Breaking*, *Added*, *Changed*, *Fixed* and one sentence naming the line
that set the version → one PR, `ci-ok` green, merge → `git tag -a vX.Y.Z` on the merge commit,
`git push origin vX.Y.Z` → the Release workflow → verify the GitHub Release, the deploy summary
and `horizon probe` on the host. A redeploy without a version (a rotated secret): Actions →
Release → Run workflow → the current tag.

**`CHANGELOG.md`** (Keep a Changelog 1.1.0): `[Unreleased]`, then `[1.0.0] - 2026-10-21` — the
first release, describing the service as HT-001 … HT-007 and this chore leave it, with the one
sentence at the top saying why it is `1.0.0` (in production). BEAD-05 corrects the date if the
tag is cut on another day.

**Trunk-based development, held by GitHub (after the repository is public).** Protection of
`main` through `beadloom setup-branch-protection --repo zoologov/horizon-tracker --check ci-ok`
— the `--check` is mandatory: the command's default contexts are Beadloom's own job names
(`gate`, `tests (3.10)`, `site-build`, …), which this repository never produces, and a required
check that never reports makes `main` unmergeable (CLAUDE.md §6). The call sets: a pull request
required, `ci-ok` a required and strict status check, `enforce_admins: true` (the owner
integrates through a PR too), 0 required reviews (the owner self-merges), force-push and
deletion forbidden. Beside it a **tag ruleset** for `v*`: creation by the repository owner only,
update and deletion forbidden, so a release tag is cut by one person and never moved. Measured
with `gh api repos/zoologov/horizon-tracker/branches/main/protection` and `.../rulesets`; the
project layer of CLAUDE.md (`.beadloom/flow/claude/CLAUDE.md`, section "Git") is rewritten from
"not measured, 403" to the method and the measurement: a branch per work item, one PR, `ci-ok`
required, no direct push for anyone, a release is a tag on `main`, with the date the protection
was read. `beadloom setup-agentic-flow` then regenerates `.claude/CLAUDE.md`. `CONTRIBUTING.md`
states the same method. The HT-005 bead `ht-hdv` ("branch protection on main with required
ci-ok") is this work: it is closed when BEAD-05 has measured the protection, with the reason
naming HT-008.

**Community files**, each as the ecosystem expects them and each English:

| File | Content |
|------|---------|
| `LICENSE` | MIT, `Copyright (c) 2026 Vladimir Zoologov (GitHub: @zoologov)` — the holder named in Bob's licence; `pyproject.toml` already declares `license = "MIT"`, and a public repository needs the file for GitHub to show the licence |
| `CHANGELOG.md` | as above |
| `CONTRIBUTING.md` | setup (the `uv`, `bd`, `beadloom` steps of a fresh clone, including the ones CLAUDE.md §0 omits), the flow in one paragraph with a pointer to `.claude/CLAUDE.md`, the commit format, one PR per work item, the gates, the release process in brief with a pointer to the guide |
| `SECURITY.md` | reporting: GitHub private vulnerability reporting (Security → Report a vulnerability; the owner enables it in BEAD-05), never a public issue; supported: the latest release; what the project does with credentials: Environment + `.env` 0600 only, never in a log, a screenshot, a bead comment or a commit; CI never logs in to the portal |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1, contact the owner |
| `.github/PULL_REQUEST_TEMPLATE.md` | work-item key, what changed, the gates run, the CHANGELOG line, the public-surface classification (MAJOR / MINOR / PATCH / none) |
| `.github/ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml`, `config.yml` | forms; `blank_issues_enabled: false`; a contact link to `SECURITY.md` for vulnerabilities |

No `CODEOWNERS`: one owner, and the review of a pull request is the Beadloom flow's, not
GitHub's.

**README.** Badges in Bob's style, for a public repository — the ones GitHub can answer are
live, the rest static:

```markdown
![Status: production](https://img.shields.io/badge/status-production-brightgreen)
[![Release](https://img.shields.io/github/v/release/zoologov/horizon-tracker?sort=semver)](https://github.com/zoologov/horizon-tracker/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/zoologov/horizon-tracker/ci.yml?branch=main&label=CI)](https://github.com/zoologov/horizon-tracker/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
[![License: MIT](https://img.shields.io/github/license/zoologov/horizon-tracker)](LICENSE)
![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64?logo=ruff&logoColor=D7FF64)
![Type check: mypy strict](https://img.shields.io/badge/type%20check-mypy%20strict-blue)
![Versioning: SemVer](https://img.shields.io/badge/versioning-SemVer-informational)
[![Portal](https://img.shields.io/badge/portal-GitHub%20Pages-informational)](https://zoologov.github.io/horizon-tracker/)
![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-blueviolet?logo=anthropic&logoColor=white)
```

A new "Releases" section names the tag rule, the two workflows a change passes (CI, then
Release), the portal's address and points to the guide; "Development" and "Deployment" are
updated to the new layout and to trunk-based development as GitHub now holds it.

**Docs.** `docs/guides/releasing.md` is new. `docs/guides/deployment.md` section 6.3 becomes
"Updating: a release" (the tag starts it; the step table moves with the job and names the
tag), 6.4 "Rotating secrets" points at the dispatch redeploy, and section 1 and 4.1 name the
tag where they say "the deploy". The workflow contract tests in `tests/unit/deploy/` follow
the files: `test_deploy_workflow.py` becomes `test_release_workflow.py` (the deploy assertions
on the `deploy` job of `release.yml`, plus `verify` and `publish`), `test_ci_workflow.py` gains
the mutation job and the dispatch trigger, `test_mutation_workflow.py` loses the per-change job,
`test_workflow_hygiene.py` reads three files, and the shell of `verify` is held by shellcheck
through `actionlint` as today.

## Axes

Derived, never authored. Run `beadloom impact <path|symbol>`, paste its answer into the table,
then take the scope decision in the last two columns — the derivation says what a change ranges
over, a person says how much of it this work item takes. The `refs:` of every bead below is
generated from the rows kept in scope, so a bead naming a node this table does not is a finding.

Rule each row by the node's role in the change: the axis a node surfaced under is not its role.
The axis is the node's relation to the seed, so a `callers` row can be a work site — a node that
calls into the change can also own what the change must edit. `Owns unread` names the files the
node owns that the derivation could not read; a count there is a question to answer before `no`.

Five runs on 2026-10-21, role explore: `.github/workflows/deploy.yml`, `src/horizon_tracker/__init__.py`,
`src/horizon_tracker/cli.py` (and the bare symbol `main`, whose table matched the module's row for
row, so it is not repeated), `README.md`. `horizon_tracker.cli.main` as a dotted symbol was refused
(`no file and no symbol named ...`). `beadloom lint` reports no size-signal finding on any node named.

> **Derived by:** `beadloom impact .github/workflows/deploy.yml` over `.github`
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 1 no-seed, 1 sweep-narrower-than-the-project, 1 unreadable-target

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — this derivation reads Python source and could not read .github/workflows/deploy.yml, so nothing that file defines was read and no caller or writer of it was found | — | no | no node named; the file's owner is the root service, declared below |
| callers | — | unresolved — this derivation reads Python source and could not read .github/workflows/deploy.yml, so nothing that file defines was read and no caller or writer of it was found | — | no | no node named |

> **Derived by:** `beadloom impact src/horizon_tracker/__init__.py` over `src/horizon_tracker`
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 1 no-seed

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — no declared effect rule found a sink this target reaches, so there is no commit point to ask who else writes through | — | no | no node named |
| callers | — | no site found | — | no | the import of `__version__` in `cli.py` is read as a name, not a call; the printed value does not change |

> **Derived by:** `beadloom impact src/horizon_tracker/cli.py` over `src/horizon_tracker`
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 2 name-defined-more-than-once, 1 no-seed, 37 unresolved-terminator-name

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — no declared effect rule found a sink this target reaches, so there is no commit point to ask who else writes through | — | no | no node named |
| callers | schedule | 1 — `src/horizon_tracker/domain/schedule.py:157` | none | no | the domain is not touched: no workflow, document or version line reaches it |
| branches | cli | `open_adapters`: 1 branch(es), 0 exit form(s), over every call | none | no | `cli.py` is not edited: `click.version_option(__version__)` keeps its import and prints the same string |
| branches | cli | `build_notifier`: 1 branch(es), 2 exit form(s), over every call | none | no | as above |
| branches | cli | `main`: 1 branch(es), 0 exit form(s), over every call | none | no | as above — the `--version` option is declared here and is left as it is |
| branches | cli | `checkin`: 1 branch(es), 0 exit form(s), over every call | none | no | as above |
| branches | cli | `checkout`: 1 branch(es), 0 exit form(s), over every call | none | no | as above |
| branches | cli | `probe`: 1 branch(es), 0 exit form(s), over every call | none | no | as above |
| branches | cli | `_guarded`: 1 branch(es), 2 exit form(s), over every call | none | no | as above |
| branches | cli | `_say_in_the_readers_language`: 1 branch(es), 1 exit form(s), over every call | none | no | as above |
| branches | cli | `_run`: 2 branch(es), 2 exit form(s), over every call | none | no | as above |
| branches | cli | `_prune`: 1 branch(es), 0 exit form(s), over every call | none | no | as above |
| branches | cli | `_todays_moments`: 1 branch(es), 1 exit form(s), over every call | none | no | as above |
| branches | cli | `_use_case`: 2 branch(es), 2 exit form(s), over every call | none | no | as above |
| branches | cli | `_probe`: 1 branch(es), 1 exit form(s), over every call | none | no | as above |
| branches | cli | `_draw_range`: 0 branch(es), 1 exit form(s), over every call | none | no | as above |
| branches | cli | `_hold`: 1 branch(es), 1 exit form(s), over every call | none | no | as above |
| branches | cli | `_span`: 0 branch(es), 1 exit form(s), over every call | none | no | as above |
| branches | cli | `_echo_plan`: 3 branch(es), 0 exit form(s), over every call | none | no | as above |
| branches | cli | `_echo_probe`: 1 branch(es), 0 exit form(s), over every call | none | no | as above |
| branches | cli | `_probe_line`: 1 branch(es), 2 exit form(s), over every call | none | no | as above |
| branches | cli | `_configure_logging`: 1 branch(es), 0 exit form(s), over every call | none | no | as above |
| branches | cli | `prune`: 0 branch(es), 0 exit form(s), over every call | none | no | as above |
| branches | schedule | `draw_moments`: 1 branch(es), 1 exit form(s), over every call, from a caller's seat | none | no | the domain is not touched |

> **Derived by:** `beadloom impact README.md` over `.`
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 1 no-seed, 1 sweep-narrower-than-the-project, 1 unreadable-target

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — this derivation reads Python source and could not read README.md, so nothing that file defines was read and no caller or writer of it was found | — | no | no node named |
| callers | — | unresolved — this derivation reads Python source and could not read README.md, so nothing that file defines was read and no caller or writer of it was found | — | no | no node named |

The derivation reads Python, so it reached neither the workflows, nor the Markdown files, nor
`pyproject.toml`, nor the YAML-reading contract tests in `tests/unit/deploy/` (which belong to no
node, `no-node-for-path`, as in HT-005). The one row that names where the work lands is declared:

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| declared (outside the derivation) | horizon-tracker | `.github/workflows/ci.yml`, `release.yml` (new), `mutation.yml`, `deploy.yml` (removed), `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/*`; `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `README.md`; `pyproject.toml`, `src/horizon_tracker/__init__.py`; `docs/guides/releasing.md` (new), `docs/guides/deployment.md`; `tests/unit/deploy/*` | `.github/**`, `deploy/**`, the Markdown and TOML files — not Python | yes | the root service (`source: src/horizon_tracker/`) owns the package `__init__`, the workflows, the deploy and the repository's files; the layers' code does not change. One node kept: the simplified flow carries the change |

## Beads

**Parent bead:** ht-6hx

Status lives in ACTIVE.md, reconciled from the tracker by the pre-commit active-sync, so this
table names the beads and carries no status. The Tracker cell holds `-` until the beads are
created, and then the id the tracker answered.

| ID | Tracker | Name | Priority |
|----|---------|------|----------|
| BEAD-01 | ht-qdg | Workflows: `release.yml` (verify → CI gate → deploy → publish → portal on Pages), `ci.yml` with `mutation-per-change` and `workflow_dispatch`, `mutation.yml` as the weekly sample only, `deploy.yml` removed; `site:` in `.beadloom/config.yml`; version `1.0.0` from `pyproject.toml` alone, `.claude/CLAUDE.md` regenerated; the contract tests follow the files | P1 |
| BEAD-02 | ht-cix | The repository's public face: `LICENSE` (MIT), `CHANGELOG.md` with `[1.0.0]`, `CONTRIBUTING.md` (trunk-based development, the gates, the release in brief), `SECURITY.md` (private vulnerability reporting), `CODE_OF_CONDUCT.md`, PR and issue templates, README badges (live where GitHub answers) and "Releases" section | P1 |
| BEAD-03 | ht-w52 | Docs: `docs/guides/releasing.md` (public surface, the version table, the release steps, the redeploy, the portal), `docs/guides/deployment.md` 6.3 / 6.4 / cross-references, README "Development" and "Deployment"; the project layer's "Git" section rewritten to trunk-based development as GitHub holds it (the measurement date left for BEAD-05) and `.claude/CLAUDE.md` regenerated; `beadloom ci` green | P1 |
| BEAD-04 | ht-2gj | Review: trigger matrix (one workflow per event), `verify` refuses what it must, secrets in `release.yml` as in HT-005, the Pages permissions in one job only, pins, no excused step, the version single source, the guide and the project layer against the workflow | P1 |
| BEAD-05 | ht-30c | Owner: make the repository public; Pages source = GitHub Actions; the `github-pages` environment's deployment rule allows `v*` tags (review Minor-2); private vulnerability reporting on; `beadloom setup-branch-protection --check ci-ok` and the `v*` tag ruleset, measured with `gh api` and the date written into the project layer's "Measured" line, then `beadloom setup-agentic-flow` to regenerate CLAUDE.md; restrict the `horizon-vps` environment's deployments to `main` and `v*` tags (a manual run from another branch executes that branch's `release.yml`, which `verify` cannot stop); merge the PR; cut `v1.0.0` on the merge commit; watch the Release run (verify, gate, deploy, publish, portal); confirm the GitHub Release, `horizon probe` on the host and the portal address; correct the `[1.0.0]` date if cut on another day; close `ht-hdv` with the reason | P1 |
| BEAD-06 | ht-a3l | Fix after review ht-2gj: CI syncs `--locked` and `verify` refuses a tag whose `uv.lock` version differs (Major-1); the PR template's gates equal CI's (Minor-1); a dispatch runs only from `main` (Minor-3); the probe/dry-run TODO resolved with the owner's default (Minor-4) | P1 |
| BEAD-07 | ht-1dd | Re-review after the fix: the four findings closed, nothing else moved (`--release` allowed) | P1 |
| BEAD-08 | ht-6hx.1 | Docs after the fix (re-review Major-1, Minor-2): deployment guide 6.3 and 7, README Releases and the releasing guide describe `verify`'s lock check and the main-only manual run; the dispatch "Why" names what `verify` does not stop | P1 |

Order: BEAD-01 and BEAD-02 run in parallel (BEAD-01 owns `.github/workflows/`,
`tests/unit/deploy/`, `src/horizon_tracker/__init__.py`, `pyproject.toml`, `.beadloom/config.yml`
and the regenerated `.claude/CLAUDE.md`; BEAD-02 owns the root community files,
`.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/` and `README.md`). BEAD-03 after
both (it describes what they built; it is the second writer of `.claude/CLAUDE.md`, after
BEAD-01 is closed). BEAD-04 after BEAD-03. BEAD-05 after the review, partly before the merge
(public, Pages, protection — the PR then merges under the protection it set) and partly after it
(the tag); a fix bead is created from the review's findings if there are any. Review ht-2gj returned ISSUES (1 major, 6 minor): BEAD-06 and BEAD-07 were added on 2026-10-21 and block BEAD-05; the coordinator took Minor-2 (this table), Minor-5 (acceptance criterion 4 below) and Minor-6 (ACTIVE's commit ids after the authorship rewrite). The re-review's first pass returned ISSUES on the documents (stale on `verify`'s new checks): BEAD-08 was added and blocks BEAD-07's second pass. The Minor-4 ruling is the owner's decision of 2026-10-21, confirmed in chat: the text `horizon probe` / `--dry-run` print is not promised surface, their exit codes are.

## Acceptance Criteria

- [ ] A pull request starts exactly one workflow (CI) whose check list holds the three stages, `ci-ok` and `mutation-per-change`; a push to `main` starts CI once and nothing reaches the VPS — non-behavioural: a property of the workflow files, held by the contract tests and seen in Actions
- [ ] Pushing `v1.0.0` starts Release alone; `verify` passes, `gate` is `ci-ok` green, `deploy` ends with `horizon probe` ok on the host, `publish` leaves a GitHub Release `v1.0.0` whose notes are the CHANGELOG section and whose assets are the wheel and the sdist, and `portal` leaves the Beadloom portal at `https://zoologov.github.io/horizon-tracker/` with its assets loading — non-behavioural: a Release run and a page
- [ ] A tag whose version is not `pyproject.toml`'s, or has no CHANGELOG section, or is not on `main`, is refused by `verify` with the check named, and no later job runs — non-behavioural: a property of `release.yml`, held by the contract test on the job's conditions and by shellcheck on its script
- [ ] `horizon --version` prints the `pyproject.toml` version (`1.0.0`) and `beadloom version-surface` no longer lists `src/horizon_tracker/__init__.py` as "checked by nothing" — non-behavioural: the string is the release's version; its source moves to one place. Amended after review Minor-5: the criterion first said "no place checked by nothing", and `version-surface` still lists version strings in documents that state a version as history (`CHANGELOG.md` `[1.0.0]`, this BRIEF, ACTIVE.md, the issue form's placeholder); those are records, not claims about the current version, and the releasing guide says so instead of a checker being invented for them
- [ ] `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, the PR template and the issue forms exist and GitHub shows them in the repository's community profile — non-behavioural: repository files
- [ ] The README carries the badges and the "Releases" section; `docs/guides/releasing.md` exists and `beadloom ci` is green — non-behavioural: documentation
- [ ] `gh api repos/zoologov/horizon-tracker/branches/main/protection` shows a pull request required, `ci-ok` the one required strict check, `enforce_admins: true`, 0 reviews, no force-push and no deletion; a `v*` tag ruleset exists; the project layer's "Git" section states the method and the date it was measured; a direct push to `main` is refused — non-behavioural: a GitHub setting and a measurement

## Non-behavioural declaration

| Node | Reason it carries no behaviour |
|------|-------------------------------|
| horizon-tracker | workflows, repository files and guides change how the code is checked, released and rolled out and how the repository presents itself, not what the service does on the host; the observer is Actions, the GitHub Release page and a reader of the repository, not a user of the service. The one Python change moves the source of `__version__` to `pyproject.toml`, where the release sets it |
