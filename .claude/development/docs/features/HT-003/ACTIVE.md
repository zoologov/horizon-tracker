# ACTIVE: HT-003 — Random check-in and check-out moments

> **Last updated:** 2026-10-20
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-09 (ht-02r) live check — after the owner merges PR #3
**Goal:** deploy to the VPS, `horizon probe` prints `schedule: today HH:MM / HH:MM`, the timers 07:30/16:30
**Done when:** the first scheduled runs (check-in and check-out) happened at random moments and the notifications arrived

## Progress

- [x] PRD, RFC, CONTEXT, PLAN approved by the owner (2026-10-20); the beads created, parent ht-1vd
- [x] Wave 1: BEAD-01 (2026-10-20)
- [x] Wave 2: BEAD-02, BEAD-03 (2026-10-20)
- [x] Wave 3: BEAD-04 (2026-10-20)
- [x] Wave 4: BEAD-05 (2026-10-20)
- [x] Wave 5: BEAD-06 → BEAD-07 → BEAD-08 (2026-10-20)
- [ ] BEAD-09: live check after the merge

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-ust, 852e697: 41 tests, 525 on the tree, mutations 241/243 (2 equivalent) |
| BEAD-02 | Done | ht-su5, 2a8b179: 38 tests, 615 on the tree |
| BEAD-03 | Done | ht-4vm, 5634cb1: 51 tests; the adapter was already lazy, pinned by a test; the CLI/BDD fixtures on the new variables |
| BEAD-04 | Done | ht-rat, a059be6: 635 tests, coverage 99 %; `--force` through `run(force=True)` keeping the moment (a window across midnight) |
| BEAD-05 | Done | ht-978, 6ca59d1: the timers 07:30/16:30, 60 min, .env without the old windows; 644 tests; README and SPEC morning-checkin still name 07:55/17:00 → BEAD-08 |
| BEAD-06 | Done | ht-slm, cfaaca3: the 7 scenarios are real (9 cases), 733/733, coverage 98.7 %, mutations 241/243 (2 equivalent) |
| BEAD-07 | Done | ht-evj: OK — 0 critical, 0 major, 4 minor, 1 nit; 11 sabotages of the core and 4 of the deploy bite; minor 1 and 3 → BEAD-08, minor 2 and 4 — deferred (see CONTEXT) |
| BEAD-08 | Done | ht-6l0, 7fc6e94: 12 documentation files; the stale list from the review closed; sync-check clean on a clean index |
| BEAD-09 | Open | — |

## Notes

- BEAD-01 waited for the live check of HT-002 (ht-28a, passed 2026-10-20): the schedule changes only after a confirmed check-in and check-out.
- The seven PRD scenarios lie in the suite as explicit SKIPs with a reason (`randomised_moments.feature`), otherwise `scenario-coverage` would have held the gate red until BEAD-06; BEAD-06 replaces the stubs with real steps.
