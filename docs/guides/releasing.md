# Releasing horizon-tracker

horizon-tracker's version number follows [Semantic Versioning](https://semver.org/). A version
number is a promise about a declared public surface and about nothing else, so this guide
declares that surface, states which change raises which part of the version, and gives the
release steps as `.github/workflows/release.yml` enforces them. Each release's section of
[`CHANGELOG.md`](../../CHANGELOG.md) classifies its changes against this guide.

A release is a tag `vX.Y.Z` on a commit of `main`. Nothing reaches the host except a release:
a merge to `main` runs CI and deploys nothing.

---

## What the version number promises

horizon-tracker is a service, not a library. Its public surface is what an operator and a host
depend on: the command the timers run, the configuration it reads and the contract the deploy
keeps with the host.

### The public surface

1. **The `horizon` command: its subcommands, options and exit codes.** The subcommands are
   `checkin`, `checkout` and `probe`. `checkin` and `checkout` take `--dry-run` and `--force`,
   and the group takes `--version` and `--help`. The exit codes:

   | Exit code | When |
   |-----------|------|
   | 0 | a run that succeeded or skipped on purpose (a day off, too early, too late), every `--dry-run`, a `probe` whose checks are `ok` or only `degraded`, `--version`, `--help` |
   | 1 | a run whose report is FAILED, a `probe` with a FAILED `portal` or `chrome` check, and a configuration error in any command |
   | 2 | an unknown subcommand or option (click's usage error) |

   The reference is [`docs/services/cli.md`](../services/cli.md) and `horizon --help`.
2. **The environment variables: their names, defaults and accepted values.** Every variable
   the command reads, the default it takes when the variable is unset or blank, and the
   values it accepts and refuses. That includes the two retired names, `HT_CHECKIN_WINDOW` and
   `HT_CHECKOUT_WINDOW`, whose presence makes every command exit 1. The reference is the
   settings table in
   [`docs/domains/infrastructure/features/settings/SPEC.md`](../domains/infrastructure/features/settings/SPEC.md),
   and the `.env` the deploy writes is section 3.3 of the
   [deployment guide](deployment.md#33-what-the-deploy-writes-the-env-contract).
3. **The deploy contract.** The names of the secrets and variables of the GitHub Environment
   `horizon-vps` (sections 3.1 and 3.2 of the [deployment guide](deployment.md)); the four unit
   names `horizon-checkin.service`, `horizon-checkin.timer`, `horizon-checkout.service` and
   `horizon-checkout.timer`; the layout of `/opt/horizon-tracker` (the clone,
   `.venv/bin/horizon`, `.env` owned by `horizon:horizon` with mode `0600`, `artifacts/`); and
   the system user `horizon` the units run as.

**The promise.** Within one major version nothing on this list is removed, renamed or changed
in a way that breaks a host configured as documented. A release that does any of those is a
new major version, and its change log names the change under *Breaking* before anything else.

### What is not promised

- **The shape of the Telegram report.** The report is prose for a person: its wording, its
  order and its layout can change in any release, and the version number does not say when.
- **Python import paths.** The modules, classes and functions under `horizon_tracker.*` can
  move, be renamed or be removed in any release. The wheel and the sdist a release carries
  are the service's distribution, not a library. The *API* sections of the node documents
  under `docs/domains/` describe a module's interface to the rest of this codebase and are not
  part of this promise.

<!-- TODO: verify with the owner whether the lines `horizon probe` and `--dry-run` print are
part of the surface or, like the Telegram report, prose for a person. -->

## How a change sets the version

| Change to a public surface | Version part |
|----------------------------|--------------|
| A subcommand or option is removed or renamed | MAJOR |
| The same input gets a different exit code | MAJOR |
| An environment variable is removed or renamed, its default changes, or it gets a different meaning | MAJOR |
| A value a variable accepted is now refused | MAJOR |
| A new variable is required, or an optional one becomes required | MAJOR |
| A `horizon-vps` secret or variable is removed or renamed, or a new one is required | MAJOR |
| A unit is renamed, the `/opt/horizon-tracker` layout changes, or the units run as another user | MAJOR |
| A subcommand or option is added | MINOR |
| An optional variable is added whose default keeps today's behaviour | MINOR |
| A variable accepts a value it refused before | MINOR |
| An optional `horizon-vps` secret or variable is added | MINOR |
| A fix that changes no public surface | PATCH |

A new required variable or secret is MAJOR although it is an addition: a host configured as
the previous release documented has no value for it, so the command refuses to start or the
deploy's `Build .env` step stops on the empty value. A change is classified by the highest row
it reaches, and the change log states, in one sentence at the top of the release's section,
which line made the version what it is.

## Where the version is stated

`pyproject.toml` `[project] version` is the one source. Every other place derives from it or
is checked against it:

- `horizon --version` prints the version of the installed distribution
  (`importlib.metadata`), whose metadata is built from `pyproject.toml`; the package carries no
  copy. `tests/unit/test_cli.py` holds the two equal.
- `uv.lock` records the project's own version. `uv lock` rewrites it after a bump, and the
  deploy's `uv sync --locked` refuses a lock that disagrees with `pyproject.toml`.
- The `Current version` line of `.claude/CLAUDE.md` is regenerated by
  `beadloom setup-agentic-flow` and checked by `beadloom doctor`, which `beadloom ci` runs.
- The release tag is checked by the Release workflow's `verify` job (below).

`beadloom version-surface` lists every place the project states a version and the instrument
that checks each one. It reports four files as checked by nothing: `CHANGELOG.md`, the
work-item documents under `.claude/development/docs/features/`, and the version placeholder of
`.github/ISSUE_TEMPLATE/bug_report.yml`. A version the change log or a work-item document
states is a record of history, true of the release or the plan it describes, and is not a
claim about the current version. The bug form's placeholder is an example of the format
`horizon --version` prints. None of them needs a checker.

## Which workflow an event starts

One workflow per event, so the name of a run says what started it:

| Event | Workflow | What runs |
|-------|----------|-----------|
| a pull request to `main` | `ci.yml` (CI) | lint, types and workflow lint; then the tests on Python 3.12 and 3.13, the Beadloom gate and `mutation-per-change`; then `ci-ok` |
| a push to `main` (a merge) | `ci.yml` (CI) | the same without `mutation-per-change`; nothing reaches the host |
| a tag `vX.Y.Z` pushed | `release.yml` (Release) | `verify` -> `gate` (CI on the tag's commit) -> `deploy` -> `publish` -> `portal-build` -> `portal-deploy` |
| Actions -> Release -> Run workflow, naming a tag | `release.yml` (Release) | the same jobs for an existing release tag: the redeploy |
| Monday 04:23 UTC, or by hand | `mutation.yml` (Mutation sample) | the weekly mutation sample of the domain |
| a Dependabot pull request | `ci.yml` (CI) | as any pull request |

CI also runs by hand (Actions -> CI -> Run workflow). `ci-ok` is the check a pull request must
pass. `mutation-per-change` is not among its needs: its verdict is informative.

## Cutting a release

The owner cuts releases.

1. **Classify.** Read the `[Unreleased]` section of `CHANGELOG.md` and the changes merged
   since the last tag (`git log --oneline vA.B.C..origin/main`) against the table above. The
   highest row any change reaches decides MAJOR, MINOR or PATCH.
2. **Bump the version** on a branch for the release:

   ```bash
   # set [project] version = "X.Y.Z" in pyproject.toml, then
   uv lock                       # uv.lock records the project's new version
   beadloom setup-agentic-flow   # regenerates the Current version line of .claude/CLAUDE.md
   ```

   `verify` refuses a tag whose version `pyproject.toml` does not declare at the tagged
   commit. CI installs with `uv sync --extra dev`, which does not check the lock, so a stale
   `uv.lock` passes CI and stops the deploy at its `Update the code` step.
3. **Write the change log.** Move the `[Unreleased]` entries into a section
   `## [X.Y.Z] - YYYY-MM-DD` with *Breaking* first, then *Added*, *Changed* and *Fixed*, and
   one sentence at the top naming the line that set the version. Leave `## [Unreleased]`
   empty above it, and add the link references at the end of the file:

   ```markdown
   [Unreleased]: https://github.com/zoologov/horizon-tracker/compare/vX.Y.Z...HEAD
   [X.Y.Z]: https://github.com/zoologov/horizon-tracker/releases/tag/vX.Y.Z
   ```

   `verify` extracts the section, without the link references, as the release notes.
4. **One pull request**, `ci-ok` green, merge.
5. **Tag the merge commit** and push the tag:

   ```bash
   git switch main && git pull --ff-only
   git tag -a vX.Y.Z -m "vX.Y.Z"      # on the merge commit, now main's head
   git push origin vX.Y.Z
   ```

   A tag cut through the GitHub Releases page starts the same workflow, and `publish` then
   edits the release that page created instead of creating a second one. That release is
   visible before the deploy has run, so the tag pushed from a clone is the route this guide
   follows.
6. **The Release workflow runs** its jobs in order, each only when the one before it passed:
   `verify`, `gate` (the full CI through `workflow_call` on the tag's commit), `deploy` (the
   host, in the Environment `horizon-vps`; section 6.3 of the
   [deployment guide](deployment.md#63-updating-a-release)), `publish` (the GitHub Release),
   `portal-build` and `portal-deploy` (the portal). `publish` runs after a green deploy, so no
   GitHub Release names a version the host does not run.
7. **Check the result:**
   - the GitHub Release `vX.Y.Z` exists, its notes are the change log section, and its assets
     are one wheel and one sdist;
   - the `deploy` job's summary names the tag, the version and the commit, and shows the
     answer of `horizon probe` and the timers;
   - on the host, `ht --version` prints `horizon, version X.Y.Z` and `ht probe` answers
     `settings: ok`, `portal: ok` and `chrome: ok` (the `ht` wrapper is section 4.2 of the
     [deployment guide](deployment.md#42-running-horizon-by-hand));
   - the portal at <https://zoologov.github.io/horizon-tracker/> shows the released tree with
     its assets loading.

Two releases never run at once: the workflow's concurrency group holds the next one until the
running one ends, and of several waiting runs GitHub keeps the newest.

## What `verify` refuses

`verify` reads every file from the tag's commit through git, never from the working tree,
because on a run by hand the working tree is `main`'s head. A refused tag deploys nothing and
publishes nothing. The failing step names the check in its `::error` annotation, titled
`verify: <check>`.

| Check | Refused when | Why |
|-------|--------------|-----|
| `tag` | the name is not `vMAJOR.MINOR.PATCH` with numbers without leading zeros (a number with a leading zero, a tag of two parts, any name given by hand) | the trigger's filter admits a leading zero and a run by hand admits any name; a release tag is strict SemVer without a pre-release or build part |
| `tag` | a run by hand names a tag the repository does not hold | a redeploy deploys an existing release, nothing else |
| `main` | the tag's commit is not an ancestor of `origin/main` | only a commit of `main` is released: a tag on a branch, or on a commit `main` never merged, stops |
| `version` | `pyproject.toml` at the tag's commit declares another version | the version has one source, and the tag names it |
| `changelog` | `CHANGELOG.md` is absent at the tag, has no section `## [X.Y.Z] - `, the section carries no date `YYYY-MM-DD`, or the section is empty | the section is the release's notes; a release without them names nothing it changed |

A tag with a pre-release part, such as `vX.Y.Z-rc.1`, starts no workflow at all: the trigger's
pattern does not match it.

**After a refusal.** The tag ruleset (below) forbids moving or deleting a pushed release tag,
so a refused tag stays where it is and no GitHub Release names it. The correction lands through
a pull request like any change, and the release takes the next version number.

**After a red `gate` or `deploy`.** `gate` red means the tagged commit does not pass CI;
nothing reached the host. A red `deploy` before `Update the code` (a missing variable, an
unreachable host) changed nothing on the host; a red step after it can leave the host on the
new code. Fix the cause (section 7 of the [deployment guide](deployment.md#7-troubleshooting))
and re-run the failed jobs, or redeploy the tag by hand.

## Redeploying a release

A rotated secret, a changed variable or a rebuilt host needs a deploy without a new version:
Actions -> Release -> Run workflow, *Use workflow from* `main`, and in `tag` the current
release tag. From a clone:

```bash
gh release view --json tagName --jq .tagName    # the latest release tag
gh workflow run release.yml -f tag=vX.Y.Z
```

The run takes the same jobs as a pushed tag. `verify` applies the same checks to the named tag;
`gate` checks the tag's commit (through the `ref` input of `ci.yml`), not the head of `main`
the run itself starts from; `deploy` checks out the tag's commit on the host and rewrites
`.env` from the Environment; `publish` edits the existing GitHub Release and replaces its
assets; and the portal is rebuilt from the tag's tree. Naming an older release tag deploys that
release: the host, the GitHub Release and the portal then show it.

## Protecting the trunk and the tags

The trunk and the release tags are held by GitHub once the repository is public. The owner sets
both, and reads them back:

```bash
beadloom setup-branch-protection --repo zoologov/horizon-tracker --check ci-ok --dry-run
beadloom setup-branch-protection --repo zoologov/horizon-tracker --check ci-ok
gh api repos/zoologov/horizon-tracker/branches/main/protection
gh api repos/zoologov/horizon-tracker/rulesets
```

- **`main`.** The protection call requires a pull request and makes `ci-ok` the one required
  status check, strict, so a branch must be up to date with `main` before it merges. It sets
  `enforce_admins: true`, so nobody pushes to `main` directly, the owner included, and 0
  required reviews, so the owner merges their own pull request. It leaves force-push and
  deletion at GitHub's default, forbidden. `--check ci-ok` is mandatory: without it the command
  requires Beadloom's own job names (`gate`, `tests (3.10)`, `site-build` and others), which
  this repository never produces, and a required check that never reports makes `main`
  unmergeable. `--dry-run` prints the call and its payload without making it.
- **The release tags.** A tag ruleset on `v*` (Settings -> Rules -> Rulesets) lets only the
  repository owner create a release tag and nobody update or delete one, so a release tag is
  cut by one person and never moved. A ruleset's bypass list applies to every rule in it, so
  the owner-only creation and the update and deletion that nobody may perform take two
  rulesets.

## The portal

`portal-build` and `portal-deploy` publish the Beadloom portal of the released tree (the
architecture overview, a page per graph node and the dashboard) to GitHub Pages at
<https://zoologov.github.io/horizon-tracker/>. The portal follows releases, not pushes to
`main`.

- **The repository settings it needs**, which the owner sets once: Settings -> Pages -> Build
  and deployment -> Source = GitHub Actions; and the `github-pages` environment allowing
  deployments from the tags `v*`, because GitHub creates that environment allowing the default
  branch only. `horizon-vps` needs the same tag rule if it restricts deployments to branches.
- **Its base.** GitHub Pages serves a project repository under `/horizon-tracker/`. That base
  is `site.base` in `.beadloom/config.yml` and `PORTAL_BASE` in `release.yml`, which carry the
  same value. `portal-build` refuses a run when `PORTAL_BASE` differs from the base Pages
  reports, because a portal built for one base and served under another loads none of its
  assets.
- **Its steps** are those `beadloom docs site --pages-workflow` writes for the beadloom version
  the workflow installs. That command is never run in this repository: the file it writes
  deploys on every push to `main`, so it would be a second deploy path. When beadloom is
  upgraded, the portal jobs are compared with what the new version writes.
- **Its permissions.** `portal-deploy` is the only job that writes to Pages
  (`pages: write`, `id-token: write`). It runs in the `github-pages` environment and the
  concurrency group `pages`.
