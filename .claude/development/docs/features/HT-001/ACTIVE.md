# ACTIVE: HT-001 — Automatic check-in and check-out of Horizon VDI

> **Last updated:** 2026-10-20 (wave 1 landed)
> **Phase:** Development

---

## Current Bead

**Bead:** wave 2 — BEAD-03 (ht-0jm), BEAD-04 (ht-c5q), BEAD-05 (ht-axc), BEAD-06 (ht-xlh), in parallel
**Goal:** the use cases over the ports; the config/clock/artifacts adapters, isdayoff/Telegram, the Playwright client with a fixture
**Done when:** every bead's tests are green and bite, not one call to the live portal

## Progress

- [x] PRD, RFC, CONTEXT, PLAN approved by the owner (2026-10-20)
- [x] The beads created as one plan, parent ht-jz5, the DAG confirmed by `bd ready`: exactly BEAD-01 and BEAD-02 are ready
- [x] Wave 1: BEAD-01, BEAD-02 (landed 2026-10-20: 930a582, d21e406; 117 tests on the tree)
- [ ] Wave 2: BEAD-03, BEAD-04, BEAD-05, BEAD-06
- [ ] Wave 3: BEAD-07
- [ ] Wave 4: BEAD-08, BEAD-09
- [ ] Wave 5: BEAD-10 → BEAD-11 → BEAD-12; BEAD-13 the owner

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-0x2, 930a582: schedule.py, calendar.py; 45 tests, green in a clean room over 6 files |
| BEAD-02 | Done | ht-6sc, d21e406: session.py, report.py, ports.py; 71 tests, 117/117 on the tree and in a clean room |
| BEAD-03 | Open | — |
| BEAD-04 | Open | — |
| BEAD-05 | Open | — |
| BEAD-06 | Open | — |
| BEAD-07 | Open | — |
| BEAD-08 | Open | — |
| BEAD-09 | Open | — |
| BEAD-10 | Open | — |
| BEAD-11 | Open | — |
| BEAD-12 | Open | — |
| BEAD-13 | Open | — |

## Notes

- The session branch `claude/horizon-vdi-automation-id6b6m` plays the role of `features/HT-001`: pushing to another session branch is not allowed. Therefore `beadloom waves` does not compare the declared axes with the branch name (finding `declarations_not_compared`) and does not read the focus document (`focus-document: unmeasured`) — limitations of the tool, not of the plan.
- Wave 1: the owner's gate on the shared tree — the domain README extended with a module table, the surface rewritten, `beadloom ci` rc 0, ruff/mypy/pytest green.
- The API that differs from the PLAN (see the API CHANGE comments on ht-0x2 and ht-6sc): `Decision` also has `SKIP_EARLY` and `GIVE_UP`; `RunKind` lives in `domain.schedule`; `checkin_succeeded(while_open, after_disconnect)`; `Notifier.send(report)` without a separate screenshot argument — it is inside `RunReport`.

- The epic's axes declared by the owner (a derivation without a seed on the empty skeleton), see the RFC.
- The "desktop open" signal in the adapter is a hypothesis from the bundle until the first `probe` on the VPS (BEAD-13).
- bd 1.3.1: `bd create --graph` accepted the plan of 13 nodes and 15 edges; `bd ready --limit 0` confirmed the DAG.
