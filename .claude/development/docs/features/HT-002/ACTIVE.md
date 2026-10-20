# ACTIVE: HT-002 — HTML Access 2312.1 selectors

> **Last updated:** 2026-10-20
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-02 (ht-75w) review; then the PR
**Was:** BEAD-01 (ht-m7u) — adapter: tile, canvas and menu selectors from the 2312.1 bundle; fixture and tests
**Goal:** `checkin --force` reaches the click on the tile and sees the open desktop; `checkout` tells "no session" apart
**Done when:** the adapter tests on the fixture with the real markup are green and bite, `beadloom ci` rc 0

## Progress

- [x] BRIEF approved by the owner (2026-10-20), beads created: ht-m7u, ht-75w, ht-28a
- [x] BEAD-01 dev (2026-10-20)
- [x] BEAD-02 review (ISSUES)
- [x] BEAD-04 fix (ht-tvn.1)
- [x] BEAD-05 re-review (ht-tvn.2) OK
- [x] BEAD-06 fix (ht-tvn.3)
- [ ] BEAD-07 re-review (ht-tvn.4)
- [ ] PR → main → deploy
- [ ] BEAD-03 live check from the VPS (the local agent), then the timers

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-m7u, 39b1149 + d69cf64: tile/canvas/menu from the bundle, fixture rewritten (the old adapter on it: 13 red of 25), 470 tests, coverage 98 %; found beyond the BRIEF: the menu closes by a click, not by Escape; `canvas#mainCanvas`; risk: the client marks the desktop "logged off" before the broker answers |
| BEAD-02 | Done | ht-75w: ISSUES — 1 major (the Log Off confirmation reads the client's optimistic flag, not the broker), 2 minor, 2 nit; 8 sabotages; fix → ht-tvn.1, re-review → ht-tvn.2 |
| BEAD-03 | Open | — |
| BEAD-04 | Done | ht-tvn.1, f706192: 473 tests, coverage 98 %, ci rc 0 |
| BEAD-05 | Done | ht-tvn.2: OK (0 major, 2 minor, 2 nit); minor 1 → ht-tvn.3, minor 2 → measurements in ht-28a |
| BEAD-06 | Done | ht-tvn.3, 9f243d8: 476 tests, coverage 99 %, ci rc 0 |
| BEAD-07 | Open | ht-tvn.4: narrow re-review |

## Notes

- Parent ht-tvn. The session branch `claude/horizon-vdi-automation-id6b6m` was restarted from `main` after the HT-001 merge.
- The real client bundle `app-htmlaccess.4eb7424a56fc03317f06.js` lies in the cloud session's scratchpad; the fixture is checked against it, not against memory.
