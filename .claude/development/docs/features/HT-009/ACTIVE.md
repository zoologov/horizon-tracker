# ACTIVE: HT-009 — Check-in success screenshot after the hold

> **Last updated:** 2026-10-24
> **Phase:** Completed

---

## Current Bead

**Bead:** none — every bead of HT-009 is closed, and the epic `ht-qq2` is closed in the tracker
**Goal:** met: a successful check-in's photo is taken after the hold, from a painted frame
**Done when:** done — released as `v1.0.1` (2026-10-22); the live check-in photo of 2026-10-24 is painted

## Progress

- [x] PRD, RFC, CONTEXT, PLAN approved (paint poll, 2026-10-22)
- [x] Beads created under ht-qq2
- [x] BEAD-01 dev
- [x] BEAD-02 dev
- [x] BEAD-03 test
- [x] BEAD-04 review
- [x] BEAD-05 tech-writer
- [x] Landing: version `1.0.1` and one PR (#3, merged as da3ac21, tagged `v1.0.1`)
- [x] Live: the check-in photo of 2026-10-24 07:36 MSK on the host shows the painted Windows desktop

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-22u | Done | open_desktop returns None; capture_open_desktop saves the first non-blank element frame |
| ht-rqz | Done | Capture runs after the hold; the report time stays at open_desktop's return; an unconfirmed check-in sends no photo |
| ht-bic | Done | The check-in photograph is taken after the hold and before disconnect; the caption time stays the open moment. All four PRD scenario names pass. Coverage 97.57% on Python 3.12.12, floor 80%. |
| ht-7qx | Done | Review passed (2026-10-22): the port, the capture order, opened_at, blank frames, check-out and the allowlist match the RFC; closed by commit 1ea117b |
| ht-o5u | Done | SPECs match the code: open_desktop returns None, capture_open_desktop saves the first non-blank frame after the hold, and success_settle_ms is gone |

## Notes

As released in `1.0.1`: capture polls the largest canvas or video in `#canvas-container`. A
32×32 element screenshot is non-blank when at least 8 pixels have `max(R,G,B) ≥ 24`. Bound
`desktop_paint_ms` is 60 s. A blank timeout returns `None`. `opened_at` stays at
`open_desktop`'s return. `success_settle_ms` is removed.

The live photo of 2026-10-24 07:36 MSK proved the paint poll: the Windows desktop is painted.
It also carried the HTML Access dialog "Fullscreen — Click OK to grant permission for full
screen" over the desktop. That dialog, and the findings of the independent review of
`v1.0.1` (2026-10-24), are HT-010's (`ht-m13`). HT-010 changed the capture: it cancels a
client dialog before the frame and has the page decode the element screenshot, and the
horizon-playwright-client SPEC describes the current rule. Review Minor-6 stays a known
trade-off of this item (see CONTEXT.md).
