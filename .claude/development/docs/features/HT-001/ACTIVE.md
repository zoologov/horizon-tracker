# ACTIVE: HT-001 — Automatic check-in and check-out of Horizon VDI

> **Last updated:** 2026-10-20 (wave 2 landed)
> **Phase:** Development

---

## Current Bead

**Bead:** wave 3 — BEAD-07 (ht-oqx) CLI and the fix bead BEAD-14 (the reason for an early start)
**Goal:** composition root, probe, dry-run; the domain gets a `Reason` for a start before the window
**Done when:** every command is covered through CliRunner, dry-run does not call login, SKIP_EARLY is reported correctly

## Progress

- [x] PRD, RFC, CONTEXT, PLAN approved by the owner (2026-10-20)
- [x] The beads created as one plan, parent ht-jz5, the DAG confirmed by `bd ready`: exactly BEAD-01 and BEAD-02 are ready
- [x] Wave 1: BEAD-01, BEAD-02 (landed 2026-10-20: 930a582, d21e406; 117 tests on the tree)
- [x] Wave 2: BEAD-03, BEAD-04, BEAD-05, BEAD-06 (landed 2026-10-20: a7695cd, 282811b, 88dce67, b7bbddc; 287 tests on the tree)
- [ ] Wave 3: BEAD-07, BEAD-14 (fix: a Reason for an early start)
- [ ] Wave 4: BEAD-08, BEAD-09
- [ ] Wave 5: BEAD-10 → BEAD-11 → BEAD-12; BEAD-13 the owner

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-0x2, 930a582: schedule.py, calendar.py; 45 tests, green in a clean room over 6 files |
| BEAD-02 | Done | ht-6sc, d21e406: session.py, report.py, ports.py; 71 tests, 117/117 on the tree and in a clean room |
| BEAD-03 | Done | ht-0jm, 88dce67: checkin.py, checkout.py, windowed_run.py, fakes; 47 tests, 266/266 in a clean room over 9 files |
| BEAD-04 | Done | ht-c5q, 282811b: config.py, clock.py, artifacts.py; 57 tests, 219/219 in a clean room over 7 files |
| BEAD-05 | Done | ht-axc, a7695cd: isdayoff.py, telegram.py; 45 tests, 162/162 in a clean room over 4 files |
| BEAD-06 | Done | ht-xlh, b7bbddc: horizon_playwright.py, the htmlaccess fixture, pytest-bdd+mutmut in dev; 21 adapter tests, 287/287 in a clean room over 10 files |
| BEAD-07 | Open | — |
| BEAD-08 | Open | — |
| BEAD-09 | Open | — |
| BEAD-10 | Open | — |
| BEAD-11 | Open | — |
| BEAD-12 | Open | — |
| BEAD-13 | Open | — |
| BEAD-14 | Open | fix: a `Reason` for a start before the window; found by BEAD-03 |

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
- `tests/adapters/test_horizon_playwright.py` is "unplaced" for beadloom (not bound to a node); the other adapter tests lie in `tests/unit/infrastructure/`. The decision on a single place is BEAD-10's.
- The scratchpad is shared between parallel agents: one agent overwrote another's file. Agents need per-bead subdirectories; recorded in UX-Issues.
