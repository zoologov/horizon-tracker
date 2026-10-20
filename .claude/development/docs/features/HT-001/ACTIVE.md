# ACTIVE: HT-001 — Automatic check-in and check-out of Horizon VDI

> **Last updated:** 2026-10-20 (wave 5 landed, the Gate is green)
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-13 (ht-bl6) — the live run on the VPS by the owner's hand; the PR to `main` is opened by the coordinator
**Goal:** the secrets in the environment `horizon-vps`, the PR merge, the deploy, `horizon probe`, `checkin --force` and `checkout --force`, a check against the Horizon journal, enabling the timers
**Done when:** the check-in and the check-out are confirmed outside our system, the timers are enabled, the first scheduled run reported to Telegram

## Progress

- [x] PRD, RFC, CONTEXT, PLAN approved by the owner (2026-10-20)
- [x] The beads created as one plan, parent ht-jz5, the DAG confirmed by `bd ready`: exactly BEAD-01 and BEAD-02 are ready
- [x] Wave 1: BEAD-01, BEAD-02 (landed 2026-10-20: 930a582, d21e406; 117 tests on the tree)
- [x] Wave 2: BEAD-03, BEAD-04, BEAD-05, BEAD-06 (landed 2026-10-20: a7695cd, 282811b, 88dce67, b7bbddc; 287 tests on the tree)
- [x] Wave 3: BEAD-07, BEAD-14 (landed 2026-10-20: f0f958c, aaac43d; 358 tests on the tree)
- [x] Wave 4: BEAD-08, BEAD-09 (landed 2026-10-20: a784433, 7d68763; 416 tests on the tree)
- [ ] Wave 5: BEAD-10 ✓ → BEAD-11 ✓ (ISSUES) → BEAD-15 ✓ → BEAD-16 ✓ OK → BEAD-12 ✓; BEAD-13 the owner (after the PR merge)

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-0x2, 930a582: schedule.py, calendar.py; 45 tests, green in a clean room over 6 files |
| BEAD-02 | Done | ht-6sc, d21e406: session.py, report.py, ports.py; 71 tests, 117/117 on the tree and in a clean room |
| BEAD-03 | Done | ht-0jm, 88dce67: checkin.py, checkout.py, windowed_run.py, fakes; 47 tests, 266/266 in a clean room over 9 files |
| BEAD-04 | Done | ht-c5q, 282811b: config.py, clock.py, artifacts.py; 57 tests, 219/219 in a clean room over 7 files |
| BEAD-05 | Done | ht-axc, a7695cd: isdayoff.py, telegram.py; 45 tests, 162/162 in a clean room over 4 files |
| BEAD-06 | Done | ht-xlh, b7bbddc: horizon_playwright.py, the htmlaccess fixture, pytest-bdd+mutmut in dev; 21 adapter tests, 287/287 in a clean room over 10 files |
| BEAD-07 | Done | ht-oqx, f0f958c: cli.py, application/probe.py; 65 tests, 359/359 in a clean room over 4 files |
| BEAD-08 | Done | ht-2h2, a784433: 4 systemd units, bootstrap.sh, RUNBOOK.md (ru); 31 tests, 389 on the tree; the bootstrap does not enable the timers — the owner enables them after BEAD-13 |
| BEAD-09 | Done | ht-spa, 7d68763: ci.yml, deploy.yml; actionlint rc 0; 27 tests, the .env assembly checked against the systemd parser; the real Actions run and the deploy wait for BEAD-13 |
| BEAD-10 | Done | ht-1ex, 5aff543: the 12 PRD scenarios in 6 feature files (20 cases), 442/442, coverage 96.38 %, domain mutants 111/111; the rule `scenario-coverage` in the graph; the Playwright test moved to `tests/integration/infrastructure/` |
| BEAD-11 | Done | ht-9uk: ISSUES — 0 critical, 1 major (the coverage threshold is not checked in CI), 6 minor; 11 sabotages, each went red by name; fix → ht-jz5.2, re-review → ht-jz5.3 |
| BEAD-12 | Done | ht-6rw, 3af981c: 15 feature nodes with SPEC.md, the layer READMEs, cli.md, architecture.md, the RUNBOOK; all 12 scenarios bound; gate rc 0 on a clean index |
| BEAD-13 | In Progress | the VPS prepared by the local agent (horizon, /opt/horizon-tracker at 8db4966, 4 units disabled, no .env); the environment `horizon-vps` with 8 secrets; a read-only deploy key for horizon, origin over SSH; waiting for: the PR merge → the deploy → probe/--force → the timers |
| BEAD-15 | Done | ht-jz5.2, 8fd731f: CI with `--cov`, concurrency greenlet, probe → `client_bundles()` + `browser_version()` (a real Chrome start), DryRun over WindowedRun, prune/close best-effort; 466 tests, coverage 98.47 %, mutants 111/111; 8 document pairs went stale → BEAD-12 |
| BEAD-16 | Done | ht-jz5.3: OK — six findings closed, no regressions; 2 minor + 2 nits for BEAD-12; withholding did not hold (UX #6), `--release` exit 1 (UX #7) |
| BEAD-14 | Done | ht-jz5.1, aaac43d: `Reason.TOO_EARLY`; 5 tests, 293/293 in a clean room over 4 files |

## Notes

- The session branch `claude/horizon-vdi-automation-id6b6m` plays the role of `features/HT-001`: pushing to another session branch is not allowed. Therefore `beadloom waves` does not compare the declared axes with the branch name (finding `declarations_not_compared`) and does not read the focus document (`focus-document: unmeasured`) — limitations of the tool, not of the plan.
- Wave 1: the owner's gate on the shared tree — the domain README extended with a module table, the surface rewritten, `beadloom ci` rc 0, ruff/mypy/pytest green.
- The API that differs from the PLAN (see the API CHANGE comments on ht-0x2 and ht-6sc): `Decision` also has `SKIP_EARLY` and `GIVE_UP`; `RunKind` lives in `domain.schedule`; `checkin_succeeded(while_open, after_disconnect)`; `Notifier.send(report)` without a separate screenshot argument — it is inside `RunReport`.

- The epic's axes declared by the owner (a derivation without a seed on the empty skeleton), see the RFC.
- The "desktop open" signal in the adapter is a hypothesis from the bundle until the first `probe` on the VPS (BEAD-13).
- bd 1.3.1: `bd create --graph` accepted the plan of 13 nodes and 15 edges; `bd ready --limit 0` confirmed the DAG.
- Wave 2: the owner's gate on the tree — the application and infrastructure READMEs extended with module tables, the surface rewritten, the inert wave-1 override removed from flow.yml.
- Deviations from the PLAN in wave 2 (API CHANGE on the beads): a third module `application/windowed_run.py`; the constructors `MorningCheckin(client, clock, runner, desktop, hold)` and `EveningCheckout(client, clock, runner, desktop)` without `ArtifactStore`; `PlaywrightHorizonClient` with keyword arguments and `run_kind`; `TelegramNotifier(token, chat_id, client)`; `Settings` requires `HORIZON_URL` and also masks the username and the chat id; `prune()` of the artifacts is called by the CLI.
- A defect found: a start before the window (`SKIP_EARLY`) is reported as "after the window", the domain has no reason for an early start → BEAD-14.
- The Playwright test lay in `tests/adapters/` and was "unplaced"; BEAD-10 moved it to `tests/integration/infrastructure/` (a real browser against a local server), beadloom bound it to `infrastructure`. A stale comment about `tests/adapters` remains in `ci.yml` — for BEAD-12.
- The scratchpad is shared between parallel agents: one agent overwrote another's file. Agents need per-bead subdirectories; recorded in UX-Issues.
- Wave 3: the owner's gate on the tree — the application README extended with `probe.py`, `docs/services/cli.md` rewritten by the API CHANGE of ht-oqx (commands, exit codes, output, variables), the surface rebased, the inert overrides removed.
- CLI: the retry policy is a CLI constant (3 attempts 30 s apart, within the window), not in Settings; the log only to stderr under journald, there is no log file (a deviation from the PLAN, the reason — journald holds the rotation).
- Wave 4: the deploy runs only for `main` (a guard in the job), the gate before the deploy is the full `ci.yml` (on a push to main CI runs twice, deliberately); the smoke test `horizon probe` through `systemd-run --uid=horizon -p EnvironmentFile=...`, because `sudo -u` does not provide the variables from `.env`; the timers `try-restart`, so as not to enable a disabled timer before the owner's first manual run.
- For BEAD-12: the RFC said `systemctl restart` (corrected in the RFC with a note), RUNBOOK §2.2 names five secret values instead of four. For BEAD-10: `pyyaml` is needed as a direct dev dependency (it currently arrives transitively through mutmut).
- BEAD-13 is unblocked for the owner: the secrets in the environment `horizon-vps` can be created right now; the deploy itself fires after the PR merge into `main`.
- Wave 5 landed; the Gate loop on the final tree: `beadloom ci` rc 0 on the first attempt, ruff/mypy clean, 466 tests, coverage 98 %, 32 pairs fresh, `docs spaces --strict` clean. The PR to `main` is open; next is the owner (BEAD-13).
- For the owner (from the adapter's SPEC and RUNBOOK §3): a scheduled run that could not start Chrome reports "the Horizon portal is unreachable", because the browser starts inside the login step; only `horizon probe` can tell the two apart. A separate reason would need a code change — a candidate for the next work item.
- BEAD-13, the local agent's report of 2026-10-20: the repository is private, so the clone on the VPS is over SSH with a read-only deploy key for `horizon` (RUNBOOK §1.1); `owner-setup.sh` is not applicable with password SSH disabled, the steps were done by hand. Before the merge the owner presses /start on the notification bot, otherwise the first notification will not arrive.
