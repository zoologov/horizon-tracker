# ACTIVE: HT-002 — HTML Access 2312.1 selectors

> **Last updated:** 2026-10-20
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-01 (ht-m7u) — the adapter: the tile, canvas and menu selectors from bundle 2312.1; the fixture and tests
**Goal:** `checkin --force` reaches the click on the tile and sees the open desktop; `checkout` tells "no session" apart
**Done when:** the adapter tests on the fixture with the real markup are green and bite, `beadloom ci` rc 0

## Progress

- [x] BRIEF approved by the owner (2026-10-20), beads created: ht-m7u, ht-75w, ht-28a
- [ ] BEAD-01 dev
- [ ] BEAD-02 review
- [ ] PR → main → deploy
- [ ] BEAD-03 live check from the VPS (the local agent), then the timers

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Open | — |
| BEAD-02 | Open | — |
| BEAD-03 | Open | — |

## Notes

- Parent ht-tvn. The session branch `claude/horizon-vdi-automation-id6b6m` was restarted from `main` after the HT-001 merge.
- The real client bundle `app-htmlaccess.4eb7424a56fc03317f06.js` lies in the cloud session's scratchpad; the fixture is checked against it, not against memory.
