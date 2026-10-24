# ACTIVE: HT-010 — No client dialog in the check-in photo

> **Last updated:** 2026-10-24
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-01 (ht-3fs) — dev: dismiss the client dialog before the post-hold capture
**Goal:** the post-hold photo shows the desktop without the Fullscreen dialog; a dialog that will not close leaves a text success
**Done when:** the fixture test and the two scenarios are green and their sabotage goes red

## Progress

- [x] BRIEF approved by the owner (2026-10-24); the owner's standing decision covers the rest of the flow ("веди сам")
- [x] Beads created as one plan: parent ht-m13; ht-3fs (dev1) → ht-chm (dev2) → ht-igr (review) → ht-lh0 (docs); ht-c7x (chore, coordinator)
- [ ] Wave 1: BEAD-01 dev (ht-3fs) + BEAD-05 chore (ht-c7x, inline)
- [ ] Wave 2: BEAD-02 dev (ht-chm)
- [ ] Wave 3: BEAD-03 review (ht-igr)
- [ ] Wave 4: BEAD-04 tech-writer (ht-lh0)
- [ ] Gate green → PR features/HT-010 → main → merge (no release; v1.1.0 is cut after HT-012)

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Open | — |
| BEAD-02 | Open | — |
| BEAD-03 | Open | — |
| BEAD-04 | Open | — |
| BEAD-05 | Open | — |

## Notes

- Branch `features/HT-010`, one PR to `main`. HT-012's documents wait in the coordinator's scratchpad until HT-010 is merged: an untracked PRD naming unimplemented scenarios reddens `beadloom lint` on this tree.
- Review of v1.0.1 (2026-10-24, no bead): ISSUES 0/3/5; its text is summarised in the BRIEF's Problem section.
