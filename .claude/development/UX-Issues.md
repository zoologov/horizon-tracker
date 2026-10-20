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
