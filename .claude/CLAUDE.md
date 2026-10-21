<!-- beadloom:composed — this file is CORE + the architecture/stack overlays your
`.beadloom/flow.yml` selects. Put YOUR project's rules in `.beadloom/flow/claude/CLAUDE.md`:
the project layer composes AFTER the core, survives every upgrade, and does not trip
`beadloom config-check`. Editing this body directly is reported and never rewritten. -->

# CLAUDE.md — Multi-Agent Development Core

> **Version:** 3.1 (agents/ + commands/ split)
> **Integration:** steveyegge/beads CLI (1.0.4, embedded Dolt)
> **Process skills (`.claude/commands/`, slash, run in main loop):** `/task-init`, `/coordinator`, `/checkpoint`, `/templates`
> **Role subagents (`.claude/agents/`, launched via the `Agent` tool):** `explore`, `dev`, `test`, `review`, `tech-writer`
> **See §0.0 Process Architecture for how these fit together.**

---

## 0.0 Process Architecture (entry point → roles)

One entry point, two kinds of unit. This is the whole map:

```
CLAUDE.md  ← entry point: critical rules, setup, bd/beadloom essentials, this map
│
├─ .claude/commands/  — SLASH SKILLS, injected into the MAIN-LOOP session (you, now)
│    /task-init    scaffold any work item (PRD/RFC/CONTEXT/PLAN/ACTIVE or BRIEF) + create beads
│    /coordinator  orchestrate multi-agent work (waves, gates, landing lock) — MAIN-LOOP only
│    /checkpoint   bd-comment + ACTIVE.md progress saves
│    /templates    document templates used by /task-init
│
└─ .claude/agents/    — ROLE SUBAGENTS, launched via the `Agent` tool (isolated context)
     explore · dev · test · review · tech-writer   (canonical role definitions; scoped tools; model: opus)
```

**Why coordinator is a command, not an agent:** the coordinator IS the main-loop process that *spawns* subagents via the `Agent` tool. A subagent cannot spawn subagents, so orchestration must live in the main loop. `/coordinator` is a skill injected into that loop.

**Two ways a role runs:**
- **Multi-agent (default for epics/features):** `/coordinator` launches roles as subagents — `Agent(subagent_type="explore"|"dev"|"test"|"review"|"tech-writer", run_in_background=True)`. The role's full protocol lives in `.claude/agents/<role>.md` (single source of truth) and is NOT re-injected by the coordinator.
- **Single-agent (one small bead, no orchestration):** the main loop adopts the role inline by reading and following `.claude/agents/<role>.md` directly. (There are no `/explore` `/dev` `/test` `/review` `/tech-writer` slash commands — roles are subagents, not skills.)

**Flow:** `/task-init` (Explore derives the axes at step 0.5, then docs + beads) → `/coordinator` (waves: dev → test → review → tech-writer, gated by bead dependencies) → commit per wave. Durable state lives in files (`CONTEXT.md`/`ACTIVE.md`) + bead comments, never chat.

---

## 0. CRITICAL RULES

> **READ FIRST. ALWAYS FOLLOW.**

### Setup (one-time, per clone)

```bash
git config beads.role maintainer   # or "contributor" — required by bd 1.0.4 (silences GH#2950 warning)
beadloom install-hooks             # pre-commit (lint + sync-check + ACTIVE/tracker coherence) +
                                   # pre-push Beadloom Gate (`beadloom ci`; blocks on red, --no-verify to skip).
                                   # It does not run the test suite, and names that under its verdict.
```

### BEFORE any work

```bash
# 1. Get project context
beadloom prime                    # compact architecture + health overview

# 2. Check available tasks
bd ready

# 3. Claim task
bd update <bead-id> --status in_progress --claim

# 4. Read context via Beadloom (never hardcode paths)
beadloom ctx <ref-id>             # architecture context for the area you'll touch
beadloom why <ref-id>             # impact: what depends on this?

# 5. Read epic context (if applicable)
# .claude/development/docs/features/{ISSUE-KEY}/CONTEXT.md
# .claude/development/docs/features/{ISSUE-KEY}/ACTIVE.md

# 6. Confirm understanding to user
```

### DURING work

```bash
# Checkpoint every 30 min or 5 steps
bd comments add <bead-id> "CHECKPOINT: [what was done]"

# Update ACTIVE.md after each significant action
```

### WHEN COMPLETING bead

```bash
# 1. Tests pass, 2. lint + type-check clean
#    -> the concrete commands come from the STACK section below, not from here:
#       the core is stack-neutral and `uv run pytest` is not every project's suite.

# 3. Beadloom validation
beadloom reindex
beadloom sync-check
beadloom lint --strict

# 4. Final checkpoint
bd comments add <bead-id> "COMPLETED: [results]"

# 5. Close bead (shows newly unblocked work)
bd close <bead-id> --suggest-next
# (append --session "$CLAUDE_SESSION_ID" only if that env var is set)
```

---

## 0.1 Project: horizon-tracker

<!-- beadloom:auto-start project-info -->
- **Stack:** Python (>=3.12) — click, httpx, playwright
- **Tests:** pytest + pytest-cov
- **Linter/formatter:** ruff (lint + format)
- **Type checking:** mypy --strict
- **Architecture:** DDD packages -- `application/`, `domain/`, `infrastructure/`
- **Current version:** 1.0.0
<!-- beadloom:auto-end -->

---

## 1. Skills — Dynamic Loading

**Slash skills (main loop):**

| Situation | Command | Description |
|-----------|---------|-------------|
| New work item | `/task-init` | Setup any type: epic, feature, bug, task, chore |
| Parallel work | `/coordinator` | Orchestrate multi-agent waves (spawns role subagents) |
| Need templates | `/templates` | PRD, RFC, CONTEXT, PLAN, ACTIVE, BRIEF |
| Create checkpoint | `/checkpoint` | Format, rules |

**Role subagents (via the `Agent` tool — see §0.0):** `explore` (the axes, before a work item has a type), `dev` (TDD implementation), `test` (tests, coverage), `review` (quality, read-only), `tech-writer` (doc refresh). Defined in `.claude/agents/<role>.md`. For a single small bead without orchestration, the main loop adopts a role inline by following its `.claude/agents/<role>.md`.

**Rule:** Invoke a slash skill when you need detailed instructions; launch a role subagent (or follow its agent file inline) to do role work.

---

## 2. Beads CLI — Essentials

```bash
# Available tasks (no blockers)
bd ready
bd ready --claim                  # atomically claim the next ready bead (1.0.4)

# All tasks — `--all` because bd otherwise omits every closed bead, silently,
# and caps the rest at 50 with a notice only on stderr (bd 1.0.4)
bd list --all

# Details + history
bd show <id>
bd comments <id>

# Claim task
bd update <id> --status in_progress --claim

# Add checkpoint (does NOT overwrite description)
bd comments add <id> "checkpoint text"

# Close task (--suggest-next shows newly unblocked beads; 1.0.4)
bd close <id> --suggest-next

# Dependency graph
bd graph --all

# Add dependency, then READ THE ECHO — bd names both beads' full titles, and that
# echo is the only check on an edge built from an id you wrote down yourself
bd dep add <id> <depends-on-id>
bd dep tree <id>                  # confirm the edge against the titles, not the ids
```

**Multi-agent coordination (new in 1.0.4) — used by `/coordinator`:**
- `bd swarm` — epic → DAG → waves (`create` / `validate` / `status`)
- `bd gate` — async wait conditions (review→tech-writer; CI via `gh:run` / `gh:pr`)
- the merge slot — serialize parallel LANDINGS: `bd merge-slot acquire --holder <bead-id>`,
  where exit 0 means you hold it, and `release --holder <bead-id>`, the only release form bd
  verifies. It orders the commits and nothing else; keeping two agents out of one FILE is what
  `beadloom waves` derives

**IMPORTANT:**
- `bd comments add` — for checkpoints (preserves history)
- `bd update --append-notes` — for notes
- NEVER work on a task without `--claim`
- ALWAYS close via `bd close`; `--suggest-next` lists *candidate* unblocked beads — **confirm with `bd ready --limit 0`** (it named a still-blocked bead in sixteen of twenty-three dependency shapes measured on bd 1.0.4; `--limit 0` because the default caps at 100)
- `--session "$CLAUDE_SESSION_ID"` on close is optional (audit trail; only if the env var is set)

---

## 2.1 Beadloom CLI — Essentials

```bash
# Agent context (start of session)
beadloom prime                   # compact context for AI agent injection (<2K tokens)

# Project structure (use instead of hardcoded paths)
beadloom status                  # overview: nodes, edges, docs, coverage, trends
beadloom graph                   # Mermaid architecture diagram
beadloom ctx <ref-id>            # full context: code, docs, constraints
beadloom ctx <ref-id> --json     # structured JSON for parsing
beadloom search "<query>"        # FTS5 search across nodes and docs
beadloom why <ref-id>            # impact analysis: upstream deps + downstream dependents

# Validation (run before committing)
beadloom reindex                 # rebuild index after code/graph changes
beadloom sync-check              # check doc-code freshness (exit 2 = stale)
beadloom lint --strict           # architecture boundary check (exit 1 = violation)
beadloom doctor                  # graph integrity validation

# Change tracking & visualization
beadloom diff --since <git-ref>  # graph changes vs a git ref (exit 1 = changes) — use in the review role
beadloom snapshot save           # snapshot architecture state; `snapshot compare <a> <b>` to diff
beadloom link <ref-id> <url>     # link a graph node to an external tracker issue (GitHub/Jira)

# Cross-repo federation (hub + satellites)
beadloom export [--out FILE]     # deterministic federation artifact (schema v1: graph + lifecycle + AMQP contract meta)
beadloom federate <exports...>   # hub: aggregate >=2 satellite exports -> federated graph (drift verdicts + staleness)

# Documentation
beadloom docs generate           # generate doc skeletons from graph
beadloom docs polish             # structured data for AI doc enrichment

# Setup (one-time)
beadloom init                    # initialize beadloom in a project
beadloom setup-rules             # create IDE rules files referencing AGENTS.md
beadloom setup-mcp               # configure MCP server for IDE
beadloom setup-agentic-flow      # compose+write role adapters from .beadloom/flow.yml (ddd|fsd × stack, claude/cursor)
beadloom install-hooks           # pre-commit (lint + sync-check + coherence) + pre-push Beadloom Gate (`beadloom ci`;
                                 # graph and documents, not the suite — the verdict names what it did not run)

# After changing code
# 1. beadloom reindex            — re-index changed files
# 2. beadloom sync-check         — check if docs went stale
# 3. If stale: update the doc, then beadloom reindex again
# 4. beadloom lint --strict      — verify architecture boundaries
```

**IMPORTANT:**
- NEVER hardcode file paths — use `beadloom ctx`/`graph`/`search` to discover structure
- ALWAYS start sessions with `beadloom prime` for project context
- ALWAYS run `beadloom sync-check` before committing
- If sync-check reports stale docs, update them before proceeding

---

## 3. File Memory (protection against auto-compaction)

<!-- beadloom:auto-start doc-language -->
**Document language:** ALL documents (PRD, RFC, CONTEXT, PLAN, ACTIVE, BRIEF) MUST be written in English — set by `language: en` in `.beadloom/flow.yml`.
<!-- beadloom:auto-end -->

```
.claude/development/docs/features/{ISSUE-KEY}/
├── PRD.md       <- REQUIREMENTS: business goals (epic/feature only)
├── RFC.md       <- ARCHITECTURE: technical solution (epic/feature only)
├── CONTEXT.md   <- CORE: state, decisions, standards (epic/feature only)
├── PLAN.md      <- DAG: beads and dependencies (epic/feature only)
├── BRIEF.md     <- COMBINED: problem + solution + plan (bug/task/chore only)
└── ACTIVE.md    <- FOCUS: current work, progress (ALL types)
```

| Priority | File | When to read |
|----------|------|--------------|
| **P0** | CONTEXT.md | Always at the start |
| **P0** | ACTIVE.md | Always at the start |
| **P1** | beads comments | When resuming work |

**Rule:** NEVER rely on "memory" from chat. Read the files!

---

## 4. Agent Roles

| Role | How it runs | When to use |
|------|-------------|-------------|
| **Explorer** | `agents/explore.md` (`subagent_type: explore`) | Deriving how far a change ranges, before its type is chosen (`/task-init` step 0.5) |
| **Developer** | `agents/dev.md` (`subagent_type: dev`) | Implementing beads (TDD) |
| **Reviewer** | `agents/review.md` (`subagent_type: review`) | Quality verification (read-only) |
| **Tester** | `agents/test.md` (`subagent_type: test`) | Writing tests |
| **Tech Writer** | `agents/tech-writer.md` (`subagent_type: tech-writer`) | Documentation updates |
| **Coordinator** | `/coordinator` skill (main loop) | Multi-agent orchestration |

### Single agent (one small bead, no orchestration)
The main loop adopts the role inline by following `.claude/agents/<role>.md` directly; use `/checkpoint` for saving progress.

### Multi-agent mode (default for epics/features)
Coordinator MUST be activated before multi-bead work:
1. Invoke `/coordinator` skill (main-loop only — see §0.0).
2. Complete `/task-init` flow BEFORE creating any beads or writing code.
3. Coordinator gets technical context through filtered sources (strategy specs, sub-agent summaries), NEVER reads raw source code directly.
4. Coordinator launches roles as first-class subagents via the `Agent` tool (`subagent_type: explore|dev|test|review|tech-writer`), tracked through `bd swarm` / `gate` / the landing lock.

Roles are defined canonically in `.claude/agents/{explore,dev,test,review,tech-writer}.md` (single source of truth; no slash-command wrappers).

---

## 5. DAG and Priorities

| Priority | Description | Rule |
|----------|-------------|------|
| **P0** | Critical, blocks others | Execute first |
| **P1** | High, important | After P0 |
| **P2** | Medium, improvements | When there is time |
| **P3** | Low, nice-to-have | Last priority |

**Rules:**
- Only take from `bd ready`
- Do NOT take a bead with unresolved dependencies
- Do NOT take P2/P3 while P0/P1 exist

---

## 6. Git — Trunk-based development

`main` is **branch-protected** (no direct push). All work integrates via a PR.

```
Trunk-based flow:
1. Branch off main:   git switch -c features/{ISSUE-KEY}
2. Commit per wave    onto features/{ISSUE-KEY} (dev → test → review → tech-writer)
3. ONE PR to main     per epic/feature (or shippable slice) — not one PR per commit
4. The PR triggers     the AI tech-writer (commits its doc refresh INTO the PR branch)
                       + CI (`beadloom ci` is a REQUIRED status check)
5. Merge when green    human merges once CI is green + the doc refresh has landed
                       (no auto-merge; no direct push to main → main stays always-green)
```

```
Commit format:
[{ISSUE-KEY}] <type>: <description>

Types: feat, fix, refactor, docs, test, chore

Example:
[MCP-001] feat: add health endpoint
```

One-time per repo: `beadloom setup-branch-protection` configures `main` protection
(PR required, `beadloom ci` a required check, `enforce_admins: true` — strict
trunk-based, even the owner integrates via a PR — and 0 required reviews → the
owner still self-merges).

> **Idempotent is not harmless.** The command applies whatever
> `DEFAULT_STATUS_CHECK_CONTEXTS` currently says, not whatever is already live, so
> re-running it after an upgrade can require checks your workflow does not yet
> produce — and a required check that never reports makes `main` unmergeable.
> Before re-running, confirm every context it will require exists as a job and is
> green. `gh api repos/:owner/:repo/branches/main/protection` shows what is live now.

---

## 7. Anti-patterns (NEVER)

### Planning
- Starting without an agreed plan
- Taking a bead with unresolved dependencies
- Changing DAG without notifying the user
- Creating beads before PLAN is approved (beads are created in Step 3 of /task-init)
- Coordinator reading raw source code (use strategy specs + sub-agent summaries instead)

### Work
- Starting without reading CONTEXT.md
- Relying on chat memory
- Working on multiple beads simultaneously
- Ignoring checkpoints

### Completion
- Completing a bead without `bd comments add`
- Completing without `bd close`
- Committing with failing tests

### Beadloom
- Committing without `beadloom sync-check`
- Hardcoding file paths instead of using `beadloom ctx`/`graph`
- Skipping `beadloom reindex` after graph YAML changes
- Ignoring `beadloom lint` violations

> Language- and shell-specific anti-patterns live in the STACK section, composed
> from `.beadloom/flow.yml` — they are not universal and the core does not claim
> they are.

---

> **Need detailed instructions?** Slash skills: `/task-init` | `/coordinator` | `/templates` | `/checkpoint`.
> Role subagents (`Agent` tool / follow the agent file inline): `explore` | `dev` | `test` | `review` | `tech-writer` — see §0.0.

---

## STACK (Python) — composed from `.beadloom/flow.yml`

The core above is stack-neutral. These are this project's concrete commands and
the anti-patterns that only mean something in Python.

### Commands the completion checklist refers to

```bash
uv run pytest                      # 1. tests pass
uv run ruff check src/ tests/      # 2. lint (same check as CI)
uv run mypy src/                   # 2. types (strict)
beadloom ci                        # the full pre-push Gate (rc 0 required)
```

### Anti-patterns (Python)

- Using `Any` / `# type: ignore` without a stated reason
- Leaving `print()` / `breakpoint()` — use logging
- Bare `except:` without naming the exception type
- `import *`
- Mutable default arguments (`def f(x=[]):`)
- `os.path` instead of `pathlib`; f-strings in SQL instead of `?` parameters;
  `yaml.load` instead of `yaml.safe_load`

### Anti-patterns (shell)

- Using `cp`, `mv`, `rm` without `-f` (may hang on an interactive prompt)
---

## Project layer — horizon-tracker's own rules (`.beadloom/flow/claude/CLAUDE.md`)

Everything above is the composition of the beadloom core and the overlays `.beadloom/flow.yml` selects.
Everything below is true of this repository only, survives a beadloom upgrade and
is never distributed.

### Project facts (authoritative; the auto-region §0.1 is coarser)

- **What it is.** A service on a VPS (Ubuntu, systemd timers, the configured time zone, e.g. `Europe/Moscow`) which in the morning
  opens a desktop (e.g. "DEV desktop") in VMware Horizon through HTML Access and quietly
  disconnects, and in the evening reconnects and performs a full Log Off. Working days come
  from a production calendar (isdayoff.ru) with a fallback to "Mon–Fri".
- **Stack.** Python 3.12 (`python3.12` is on the VPS), `uv`, Playwright over the system
  Chrome `/usr/bin/google-chrome` (already present on the VPS), `click`, `httpx`. Tests pytest,
  ruff, mypy --strict.
- **Neighbourhood.** A neighbouring service lives on the same host (in the neighbour's directory, under its own user). This service is
  a separate system user `horizon` with the home `/opt/horizon-tracker`; nothing of the
  neighbour is touched. Notifications go to the owner's private chat from the notification bot
  (its token), not in the neighbour's voice; the neighbour takes no part in the code.
- **bd.** The core above is written for bd 1.0.4. This environment has bd 1.3.1
  (`gastownhall/beads`, formerly `steveyegge/beads`). The core's flags and caveats about 1.0.4
  — verify against `bd <cmd> --help`, do not take them on trust.

### Horizon semantics — do not confuse

- **Disconnect** — close the client; the session on the VM lives on, the Windows user is not
  logged off. This is the morning's "quiet disconnect".
- **Log off** — end the Windows session. This is the evening's "check-out".
- A "check-in" is not authentication on the portal but an open Blast connection and a
  rendered desktop: the attendance record hangs on the Windows logon, not on the web client.

### Clean Architecture and cohesion-driven — standing rules

- **Direction of dependencies:** `cli` (composition root) → `infrastructure` (adapters)
  → `application` (use cases) → `domain`. Never the other way round. Ports (Protocol) are
  declared by `domain`, adapters implement them. The rule `architecture-layers` in
  `.beadloom/_graph/rules.yml` holds this, `beadloom lint --strict` reports a
  crossing.
- **Cohesion-driven:** every module and class has ONE nameable responsibility, and it is
  named in the first line of the docstring. `dev` names it before the code; `review` checks it both
  ways: no second responsibility in a module, and no single one smeared over several.
- **A pure core without I/O:** `domain` knows neither the browser, nor the network, nor the wall clock —
  time arrives as an argument. Everything that takes a decision (windows, attempts, the calendar
  verdict, the session state) lives there and is tested first (TDD).
- **A test on a fake proves the fake's contract.** The Playwright adapter is checked against a
  local copy of the HTML Access markup (a fixture from the real client bundle), and
  the only runs against the live portal happen on the VPS (`horizon probe`, the timers).

### Secrets and the live portal

- The AD account, the bot token and the chat id — only in the GitHub Environment `horizon-vps` and in
  `/opt/horizon-tracker/.env` (0600, written by the deploy). They are never in the repository.
- The password never reaches a log, a bead comment or an error screenshot (the screenshot is taken
  after leaving the login page or with the field masked).
- From CI and from the agent's sandbox, do NOT log in to the portal. Only
  unauthenticated access to the client bundle is allowed, to take the selectors.

### Git — what actually holds `main` here

The core above claims that `main` is branch-protected. For this repository that is not
measured: for a neighbouring service on the same host the same GitHub plan answered `403 Upgrade to Pro`. Until measured,
treat CI on a PR as **informative** and `main` as held by discipline: a branch per
work item, one PR, re-verification of the gates on the final tree. The measurement:
`gh api repos/:owner/:repo/branches/main/protection`.

### Language

The flow documents (PRD, RFC, CONTEXT, PLAN, ACTIVE, BRIEF) are written in English (`language: en`).
Code, docstrings, AS-IS documentation in `docs/` and commit messages are in English too; the language of notifications and the CLI is the runtime setting `HT_LANGUAGE` (default `en`).
