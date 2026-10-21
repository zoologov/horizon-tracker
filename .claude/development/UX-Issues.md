# UX Issues — Beadloom and bd (dogfooding)

Entry template: `## #N — short name` · **Tool** · **What happened** · **What was expected** · **Where** (command, bead, date) · **Class** (friction / false signal / missing / external).

## #1 — the flow core is written for bd 1.0.4, the installer installs 1.3.1
- **Tool:** beadloom 9.0.0 (the CLAUDE.md core) · bd (External)
- **What happened:** `scripts/install.sh` in `steveyegge/beads` redirects to `gastownhall/beads` and installs 1.3.1; the old `install.sh` path returns 404. The core states facts about 1.0.4 (`--limit`, `--suggest-next`) that were not re-verified on 1.3.1.
- **What was expected:** the core names a version range or checks `bd version`.
- **Where:** installation, 2026-10-20. **Class:** friction.

## #2 — `beadloom waves` does not compare the axes when the branch name is set from outside
- **Tool:** beadloom `waves`, `ci` (scope-check)
- **What happened:** the session branch `claude/horizon-vdi-automation-id6b6m` is set by the harness and carries no epic key; `waves` gives `declarations_not_compared`, `ci` — `scope-check SKIP`. The branch cannot be renamed.
- **What was expected:** a way to name the work item explicitly (`--work-item HT-001`) or through `flow.yml`.
- **Where:** waves 1–2 of HT-001, 2026-10-20. **Class:** missing.

## #3 — one node per layer serialises beads with non-overlapping modules
- **Tool:** beadloom `waves`
- **What happened:** two domain and three infrastructure beads declared one node and were serialised although the files did not overlap; an override had to be declared on every wave.
- **What was expected:** a comparison by the files the bead declared when the node is shared.
- **Where:** HT-001 waves 1–2. **Class:** friction.

## #4 — tests in `tests/adapters/` are not bound to a node
- **Tool:** beadloom reindex (test binding)
- **What happened:** `tests/adapters/test_horizon_playwright.py` is the only "unplaced" file; the tests in `tests/unit/infrastructure/` were bound.
- **What was expected:** binding by the imported module regardless of the directory, or a documented list of directories.
- **Where:** BEAD-06, 2026-10-20. **Class:** friction.

## #5 — a shared scratchpad between parallel subagents
- **Tool:** harness (not beadloom)
- **What happened:** the BEAD-04 agent found its `sabotage.py` overwritten by a neighbour.
- **What was expected:** a subdirectory per bead by default; for now — an explicit instruction in the launch prompt.
- **Where:** wave 2, 2026-10-20. **Class:** external.

## #6 — the review launch prompt retold the author's deviations, and withholding did not hold
- **Tool:** process (`/coordinator`, review-brief)
- **What happened:** in a re-review (ht-jz5.3) the coordinator listed in the launch prompt two of the author's deviations and the list of fixes "so that the reviewer checks exactly those". The reviewer wrote into the verdict that withholding did not hold. By the coordinator's rule the review prompt must hold only the bead id.
- **What was expected:** for a re-review the rule is the same: only the id and `--release`; the reviewer reads the list of findings from the `bd comments` of the first review on its own.
- **Where:** BEAD-16, 2026-10-20. **Class:** process (a lesson for the coordinator).

## #7 — `review-brief --release` exit 1: the author and the reviewer share one tracker identity
- **Tool:** beadloom `review-brief --release`
- **What happened:** all beads are created and commented by the actor "Claude", so the tracker cannot show that the verdict was independent, and `--release` refused.
- **What was expected:** an actor per role (`BEADS_ACTOR=review` in the role's launch prompt) or a documented path for single-agent teams.
- **Where:** BEAD-16, 2026-10-20. **Class:** friction.

## #8 — `sync-check` reads as fresh on a stale document after the database is rewritten
- **Tool:** beadloom `sync-check`
- **What happened:** after the ht-jz5.2 fix (the port API changed) the agent's `beadloom ci` showed 8 stale pairs; a few minutes later on the same tree `sync-check` returns 17/17 ok, although the application README still describes `client.probe()`. The freshness database in the gitignored index was rewritten (reindex/record-surface in a clean room or on the tree) after the last commit.
- **What was expected:** the freshness database is bound to the commit (document hash + code hash in git), not to the state of the local index; `--record-surface` is unavailable from a clean room or requires explicit confirmation.
- **Where:** between BEAD-15 and BEAD-12, 2026-10-20; the tech-writer checks by content, not by `sync-check`. **Class:** false signal.

## #9 — ACTIVE.md carries the author's narrative and defeats the review's withholding
- **Tool:** process (`review-brief`, ACTIVE.md)
- **What happened:** the HT-002 reviewer read the work item's ACTIVE.md before the bundle; the Results row carried the author's report, including the risk the reviewer then found alone. The withholding of `review-brief` is partly defeated by a document the reviewer is supposed to read.
- **What was expected:** either `review-brief` warns that ACTIVE holds the author's words, or the coordinator does not put the author's narrative into ACTIVE before the review verdict (only the id, the commit, the numbers).
- **Where:** BEAD-02 of HT-002, 2026-10-20. **Class:** process.

## #10 — the one-time setup of a fresh clone is incomplete, and `prime` degrades instead of building the index
- **Tool:** beadloom 9.0.0 (the CLAUDE.md core §0 "Setup", `prime`, `install-hooks`)
- **What happened:** the core's one-time setup names two commands (`git config beads.role`, `beadloom install-hooks`). A fresh clone has no `.beadloom/beadloom.db`, so `beadloom prime` — the first command the core tells every session to run — printed `Warning: Database not found. Run beadloom reindex` and returned a context without nodes; `sync-check`/`lint` would have exited 2 the same way. The setup also says nothing about the bd database (see #13) nor about `uv sync` / `playwright install chromium`, which the project's own tests need. `install-hooks` installs the pre-commit hook in `warn` mode by default while the core describes it as a check; the verdict is one line (`mode: warn`) that is easy to miss.
- **What was expected:** `prime` reindexes when the index is absent (or has `--reindex`), and the core's Setup section lists `beadloom reindex` plus the stack's dependency step composed from `flow.yml`, so that a clone is ready after the section is followed top to bottom.
- **Where:** fresh clone on the Mac, 2026-10-21. **Class:** missing.

## #11 — `beadloom ci` warns about the project layer on every run and says in the same line that no action is needed
- **Tool:** beadloom `ci` (config-drift, section-not-in-use)
- **What happened:** on a clean tree, rc 0, `ci` printed five `::warning::` lines: `config-drift: project layer in effect (...) this is the supported place for a standing practice and needs no action`, two `section-not-in-use` lines that say "no document is reported for it", and two `scenario-coverage` population statements. A reader who scans the Gate for warnings sees five and has to read each to learn that none asks anything of them.
- **What was expected:** a statement that needs no action is printed as `::notice::` (or once, on first detection), and `::warning::` is reserved for a finding that names a file or a document to change.
- **Where:** `beadloom ci` after setup, 2026-10-21. **Class:** false signal.

## #12 — the porcelain row of a `scenario-coverage` warning carries no node and no message
- **Tool:** beadloom `lint` (`--format porcelain`, the default when piped)
- **What happened:** piped `beadloom lint --strict` printed `scenario-coverage:scenario_coverage:warn::::` twice — rule, kind, severity and four empty fields. The agent runs every command piped, so this is the form it always sees; which two nodes the rule warns about is only visible under `ci` or in the rich format.
- **What was expected:** the porcelain row fills the node and message fields for every finding, as the rich and github formats do.
- **Where:** post-setup gates, 2026-10-21. **Class:** friction.

## #13 — a fresh clone with bd 1.0.4 embedded Dolt: `bd prime` creates an empty database, the export deletes `issues.jsonl`, and `bd init` commits to main
- **Tool:** bd 1.0.4 (External; the SessionStart hook `bd prime` is installed by `bd init`, not by beadloom)
- **What happened:** the SessionStart hook ran `bd prime` before anything was bootstrapped and created `.beads/embeddeddolt/ht` with no `issue_prefix`; `export.auto: true` then deleted the git-tracked `.beads/issues.jsonl` (58 issues) on every bd command. `bd import` refused ("issue_prefix config is missing"), `bd config set issue_prefix` refused, `bd bootstrap` failed on the existing directory and then on "remote contains no Dolt data", `bd init --reinit-local` refused claiming origin has `refs/dolt/data` although `git ls-remote` shows none. What worked: remove the empty directory, `BD_NON_INTERACTIVE=1 bd init --prefix ht`, `bd import` from a copy of the jsonl. `bd init` then committed on `main` ("bd init: initialize beads issue tracking") with a generic root `CLAUDE.md` and `AGENTS.md`, `.beads/hooks/`, and a reordered `.claude/settings.json`; the commit was reset and the files restored.
- **What was expected:** `bd prime` does not create a database; a fresh clone with a tracked `issues.jsonl` and no Dolt remote is bootstrapped by `bd bootstrap` from the jsonl without a manual recipe; `bd init` never commits or writes agent instruction files unasked. For the beadloom core: the Setup section names the bootstrap step for the clone's tracker (#10).
- **Where:** fresh clone on the Mac, 2026-10-21; the recipe is also in the agent's project memory. **Class:** external.

## #14 — `setup-branch-protection` requires Beadloom's own job names by default
- **Tool:** beadloom `setup-branch-protection` (BDL-049)
- **What happened:** the default `DEFAULT_STATUS_CHECK_CONTEXTS` is `gate`, `tests (3.10)` … `tests (3.13)`, `tests-locale (C)`, `tests-locale (en_US.ISO-8859-1)`, `site-build`, `ai-techwriter` — the job names of Beadloom's own `ci.yml`. An adopter whose CI has other job names (here: `ci-ok`) and runs the command as the core's §6 suggests requires nine checks that never report, and `main` becomes unmergeable; the core's §6 note describes exactly this failure and still names the command without `--check`.
- **What was expected:** no default contexts for an adopter — either `--check` required, or the contexts read from the adopter's `ci.yml` (the job that `needs:` every other, as `ci-ok` does), or the default taken from `flow.yml`.
- **Where:** planning HT-008 (branch protection after the repository goes public), 2026-10-21. **Class:** friction (a trap).

## #15 — the generated Pages workflow deploys on every push to `main` and cannot follow a release
- **Tool:** beadloom `docs site --pages-workflow`
- **What happened:** the generated `beadloom-portal.yml` triggers on `push: main` (+ dispatch) and refuses any ref that is not the default branch. A project that deploys on tags wants the portal to show the released tree, so the generated file cannot be used; its steps have to be copied into the release workflow by hand, and the generator's "an edited copy is never written over" protection is then lost (no file to protect). `--pages-workflow` also refuses `--out` outside the project, so reading the template means writing into the repository and cleaning up (`site/`, the workflow, and an untracked `.beadloom/metrics_history.json` that `docs site` leaves behind).
- **What was expected:** a `--on tag|main` (or `site.deploy_on`) choice for the trigger, a dry-run or `--stdout` for the template, and `metrics_history.json` either gitignored by `beadloom init` or not written by a read-only generation.
- **Where:** planning HT-008, 2026-10-21. **Class:** missing.
