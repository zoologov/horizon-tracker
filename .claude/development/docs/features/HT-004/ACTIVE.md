# ACTIVE: HT-004 — Screenshot in the notification

> **Last updated:** 2026-10-20
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-02 (ht-owz) — the use cases carry the success screenshot into the RunReport
**Goal:** the path from `open_desktop`/`log_off` reaches the report and the notification
**Done when:** the use case unit tests are green and bite, mypy is clean

## Progress

- [x] The documents are approved by the owner's standing decision (2026-10-20); the beads are created, parent ht-2r9
- [x] BEAD-01 (2026-10-20)
- [ ] BEAD-02 → BEAD-03 → BEAD-04 → BEAD-05 → BEAD-06

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-ah3, b2b3c23: the port and the adapter return `Path | None`; 8 tests, 7 sabotages bite; `success_settle_ms` 2 s; a failure writing the screenshot → `HorizonClientError` without a screenshot; two lines in the layer READMEs; the «page already closed» line is not covered |
| BEAD-02 | Open | — |
| BEAD-03 | Open | — |
| BEAD-04 | Open | — |
| BEAD-05 | Open | — |
| BEAD-06 | Open | — |

## Notes

- BEAD-01 waited for ht-slm and ht-5ni so as not to share the adapter and test files with their waves.
- A gap in BEAD-01: no test that the log off photo is taken after the confirmation, not before — only the code holds the order; BEAD-03 (ht-bm9) must close it.
- BEAD-01 went into the PR together with HT-003/HT-005 (one branch): the adapter hands out the path, the use cases do not read it yet — the behaviour does not change.
- The three PRD scenarios lie in the suite as explicit SKIPs with a reason (`screenshot_preview.feature`); BEAD-03 (ht-bm9) replaces the stubs.
