# ACTIVE: HT-001 — Automatic check-in and check-out of Horizon VDI

> **Last updated:** 2026-10-20
> **Phase:** Development

---

## Current Bead

**Bead:** wave 1 — BEAD-01 (ht-0x2) and BEAD-02 (ht-6sc), in parallel
**Goal:** the pure core: the run window and the calendar verdict; session state, report, ports
**Done when:** the core's unit tests are green and bite, not one import from other layers

## Progress

- [x] PRD, RFC, CONTEXT, PLAN approved by the owner (2026-10-20)
- [x] The beads created as one plan, parent ht-jz5, the DAG confirmed by `bd ready`: exactly BEAD-01 and BEAD-02 are ready
- [ ] Wave 1: BEAD-01, BEAD-02
- [ ] Wave 2: BEAD-03, BEAD-04, BEAD-05, BEAD-06
- [ ] Wave 3: BEAD-07
- [ ] Wave 4: BEAD-08, BEAD-09
- [ ] Wave 5: BEAD-10 → BEAD-11 → BEAD-12; BEAD-13 the owner

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Open | — |
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

## Notes

- The epic's axes declared by the owner (a derivation without a seed on the empty skeleton), see the RFC.
- The "desktop open" signal in the adapter is a hypothesis from the bundle until the first `probe` on the VPS (BEAD-13).
- bd 1.3.1: `bd create --graph` accepted the plan of 13 nodes and 15 edges; `bd ready --limit 0` confirmed the DAG.
