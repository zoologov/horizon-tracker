# ACTIVE: HT-010 — No client dialog in the check-in photo

> **Last updated:** 2026-10-24 (merged; live observation pending)
> **Phase:** Development

---

## Current Bead

**Bead:** none open — PR to `main`, the owner merges
**Goal:** HT-010 on `main`; the next morning's photo without a dialog
**Done when:** merged; the live criterion observed on the next working day

## Progress

- [x] BRIEF approved by the owner (2026-10-24); the owner's standing decision covers the rest of the flow ("веди сам")
- [x] Beads created as one plan: parent ht-m13; ht-3fs (dev1) → ht-chm (dev2) → ht-igr (review) → ht-lh0 (docs); ht-c7x (chore, coordinator)
- [x] Wave 1: BEAD-01 dev (ht-3fs, b98c5f4) + BEAD-05 chore (ht-c7x, inline) — landed 2026-10-24; green in the dev's clean room over 11 files (1329 tests minus the 4 environment failures); the combined tree is measured by the coordinator after wave 2 (same module)
- [x] Wave 2: BEAD-02 dev (ht-chm, a950d9d) — landed 2026-10-24; green in the dev's clean room over 1328 tests; the combined tree measured by the coordinator (suite, ruff, mypy, `beadloom ci`) — result below
- [x] Wave 3: BEAD-03 review (ht-igr) → ISSUES 0 critical, 1 major, 3 minor (2026-10-24); combined tree before it: 1324 passed + 4 known, ruff/format/mypy clean, `beadloom ci` red on sync-check only (the adapter's two pairs)
- [x] Fix wave: BEAD-06 (ht-m13.1, d9c88e4) landed 2026-10-24; green in the dev's clean room (1325 passed + 4 known)
- [x] BEAD-07 re-review (ht-m13.2) → ISSUES 0 critical, 1 major (test-only), 1 minor; the four first-pass findings closed; the WebGL measurement re-done
- [x] BEAD-08 test fix (ht-m13.3, eeaa64c) landed 2026-10-24
- [x] BEAD-09 re-review pass 3 (ht-m13.4) → OK (0 critical, 0 major): the STOP sabotage red, the src diff docstrings only; combined tree at eeaa64c: 1325 passed + 4 known, ruff/format/mypy clean, gate red on sync-check only
- [x] Wave 4: BEAD-04 tech-writer (ht-lh0, 0df8326) — sync-check 2 → 0 stale pairs; `beadloom ci` rc 0 on the tree; suite on the final tree: the 4 known failures only
- [x] Gate green on 0df8326 (2026-10-24)
- [x] PR #4 features/HT-010 → main: CI green (8 checks), merged by the coordinator under the owner's delegation of 2026-10-24 (b999ba0); no release — v1.1.0 is cut after HT-013 and HT-012
- [ ] Live: the next working day's check-in photo shows no dialog

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-3fs, b98c5f4: Cancel clicked (never OK) before the sample, bounded by the capture's remaining time; a dialog that stays or has only OK → None (text success); 3 fixture tests + the 2 scenarios in `client_dialog_in_the_photo.feature`; 4 sabotages red; the fixture portal moved to `tests/support/htmlaccess_portal.py`; sync-check: 2 stale pairs for the adapter left to BEAD-04 |
| BEAD-02 | Done | ht-chm, a950d9d: the paint rule runs in the page (largest canvas/video → 32×32 grid, cells with max(R,G,B) ≥ 24, threshold 8 of 1024 in Python); the PNG codec and `test_desktop_paint.py` removed (adapter 800 → 733 lines, no new module); `desktop_paint_ms` holds across a sample; a closed page → None; 9 integration tests, 8 sabotages red. Unverified risk the dev named: a WebGL/tainted Blast canvas could read blank or throw — handed to the review as a directed check |
| BEAD-03 | Done | ht-igr: ISSUES — Major-1: the live-surface `drawImage` read gives 0/1024 on a WebGL canvas without `preserveDrawingBuffer` (measured, Chrome 155) while the element screenshot gives 1024/1024, and nothing in the repository says how the 2312.1 client draws; Minor-1: no test pins the paint read's throw path; Minor-2: the infrastructure README named for ht-lh0, the HT-009 RFC decision reversal to be recorded; Minor-3: the pixels judged were not the pixels saved, and a dialog after the dismissal check is photographed. 12 of 12 sabotages red. Fix → ht-m13.1, re-review → ht-m13.2 |
| BEAD-06 | Done | ht-m13.1, d9c88e4: the verdict judges the element screenshot decoded in the page (createImageBitmap → 32×32 → lit count); a 1920×1080 WebGL canvas without preserveDrawingBuffer reads 0/1024 through the old surface read and 1024/1024 through the new one (Chrome 155 and Playwright Chromium 156, headless); worst-case 5.9 MiB frame: screenshot 287–409 ms, decode 474–541 ms; a dialog after the frame discards it; the decode's throw → None, pinned; a budget under 250 ms gives up quietly; the judged PNG is the saved one; 6 tests added; 14 of 14 sabotages red |
| BEAD-07 | Done | ht-m13.2: ISSUES — Major-1: the closed-page test, after the frame moved before the paint read, no longer pins the quiet STOP (the sabotage 'raise instead of STOP' went green; behaviour intact); Minor-1: the 250 ms floor is below one worst-case sample and the in-page decode is unbounded (≈0.56 s overrun at most, against 60 s) → stated in the SPEC by ht-lh0; nitpick: docstrings repeat the constants. Confirmed closed: Major-1 (0/1024 old read vs 1024/1024 new, Chrome 155 + Chromium 156, also under a 'none' CSP), Minor-1, Minor-3, the nitpick of pass 1 |
| BEAD-08 | Done | ht-m13.3, eeaa64c: the closed-page test rewritten as `test_a_page_closed_after_a_blank_sample_stops_the_capture_without_a_failure` (quiet STOP asserted: None, no artifact, no failure log); the STOP sabotage red again, 4 of 4 on the new test while the old test stayed green under all four; docstrings name the constants; adapter coverage 95 % |
| BEAD-09 | Done | ht-m13.4: OK — the quiet STOP pinned again, nothing else moved |
| BEAD-04 | Done | ht-lh0, 0df8326: the adapter SPEC gains "The check-in capture" (the bound holds to within one in-page decode); the infrastructure README row revised and attested; the morning-checkin SPEC; HT-009 ACTIVE Completed, PRD live criterion ticked on the 2026-10-24 photo, CONTEXT records Minor-6 and the restored RFC decision |
| BEAD-05 | Done | ht-c7x (coordinator, inline): `beadloom-guard.sh` regenerated to `exec beadloom guard "$1" --hook claude-code`; `.cursor/` kept; `ht-qq2` closed |

## Notes

- Branch `features/HT-010`, one PR to `main`. HT-012's documents wait in the coordinator's scratchpad until HT-010 is merged: an untracked PRD naming unimplemented scenarios reddens `beadloom lint` on this tree.
- Review of v1.0.1 (2026-10-24, no bead): ISSUES 0/3/5; its text is summarised in the BRIEF's Problem section.
