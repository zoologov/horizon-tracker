# ACTIVE: HT-012 — Absences through the bot, and one notice for a skipped day

> **Last updated:** 2026-10-24
> **Phase:** Development

---

## Current Bead

**Bead:** — (BEAD-01 ht-162 closed; wave 2 is BEAD-02 ht-koc, BEAD-03 ht-4um, BEAD-04 ht-egg)
**Goal:** —
**Done when:** —

## Progress

- [x] PRD approved by the owner (2026-10-24, "Утверждаю, всё"); RFC, CONTEXT, PLAN approved by the owner's standing decision ("Дальше веди сам") and reported at the control point
- [x] Beads created as one plan: epic ht-t28; 01 ht-162 → {02 ht-koc, 03 ht-4um, 04 ht-egg} → 05 ht-fzd, 06 ht-jc9, 08 ht-ekd → 07 ht-xad → 09 ht-3lc → 10 ht-h0l → 11 ht-3fz → 12 ht-mr9 → 13 ht-1t7 → 14 ht-pwp (owner)
- [x] Wave 1: BEAD-01 (ht-162): `absence.py`, 38 unit tests, 41 of 41 mutants killed; the ten PRD scenarios in the suite as SKIP stubs; node `absence` with its SPEC
- [ ] Wave 2: BEAD-02, BEAD-03, BEAD-04 (shape by `beadloom waves`; 02 and 03 share `messages`)
- [ ] Wave 3: BEAD-05, BEAD-06, BEAD-08
- [ ] Wave 4: BEAD-07
- [ ] Wave 5: BEAD-09
- [ ] Test wave: BEAD-10 · Review: BEAD-11 · Docs: BEAD-12
- [ ] Release 1.1.0: BEAD-13 (PR, merge, tag, the Release run) · Owner live check: BEAD-14

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Closed | `domain/absence.py`; `allocate_id` takes `last_issued` (CONTEXT decision); stubs in `absences.feature` (9) and `production_calendar.feature` (1) |
| BEAD-02 | Open | — |
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
| BEAD-14 | Open | — |

## Notes

- Branch `features/HT-012`, one PR to `main`; the tag `v1.1.0` on its merge commit releases HT-010, HT-013 and this item together.
- The PRD's ten scenarios enter the suite as SKIP stubs in BEAD-01 (as HT-004/HT-007 did), otherwise `scenario-coverage` keeps the gate red before the first commit.
- Owner's rulings: one notice in the morning on any day-level skip, the evening silent; text commands only.
