# ACTIVE: HT-009 — Check-in success screenshot after the hold

> **Last updated:** 2026-10-22
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-01 — Port and adapter capture a non-blank desktop frame (ht-22u)
**Goal:** `open_desktop` returns nothing; `capture_open_desktop` saves the first non-blank remote-surface frame
**Done when:** a black surface is not saved, a painted one is, and a screenshot error returns `None`

## Progress

- [x] PRD, RFC, CONTEXT, PLAN approved (paint poll, 2026-10-22)
- [x] Beads created under ht-qq2
- [ ] BEAD-01 dev
- [ ] BEAD-02 dev
- [ ] BEAD-03 test
- [ ] BEAD-04 review
- [ ] BEAD-05 tech-writer
- [ ] Landing: version `1.0.1` and one PR

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-22u | In Progress | Port and adapter: non-blank capture |
| ht-rqz | Open | Morning check-in after the hold; blocked by ht-22u |
| ht-bic | Open | Acceptance scenarios; blocked by ht-rqz |
| ht-7qx | Open | Review; blocked by ht-bic |
| ht-o5u | Open | SPECs; blocked by ht-7qx |

## Notes

Capture polls the largest canvas or video in `#canvas-container`. A 32×32 element screenshot is non-blank when at least 8 pixels have `max(R,G,B) ≥ 24`. Bound `desktop_paint_ms` is 60 s. A blank timeout returns `None`. `opened_at` stays at `open_desktop`'s return. `success_settle_ms` is removed.
