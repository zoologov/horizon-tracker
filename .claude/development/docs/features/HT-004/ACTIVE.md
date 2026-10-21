# ACTIVE: HT-004 — Screenshot in the notification

> **Last updated:** 2026-10-21
> **Phase:** Completed

---

## Current Bead

**Bead:** none — the work item is closed (BEAD-06 live check passed 2026-10-21)
**Goal:** a successful check-in and check-out arrive at the notification bot as a photo with a caption
**Done when:** two notifications with photos received by the owner, no errors in the log

## Progress

- [x] The documents are approved by the owner's standing decision (2026-10-20); the beads are created, parent ht-2r9
- [x] BEAD-01 … BEAD-05 (2026-10-21)
- [x] BEAD-06: the live check after the merge → BEAD-03 → BEAD-04 → BEAD-05 → BEAD-06 — ht-2kp closed 2026-10-21: the check-out photo received (the desktop list, no session); the check-in photo is first observed on 2026-10-22, the morning run predated the deploy

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-ah3, b2b3c23: the port and the adapter return `Path | None`; 8 tests, 7 sabotages bite; `success_settle_ms` 2 s; a failure writing the screenshot → `HorizonClientError` without a screenshot; two lines in the layer READMEs; the «page already closed» line is not covered |
| BEAD-02 | Done | ht-owz, f9505e9: `checkin`/`checkout` put the path on `AttemptResult.screenshot` only on success; the chain beyond it was already there (WindowedRun → RunReport → a photo with a caption); 9 tests, 6 sabotages bite; 767 passed / 7 skipped, coverage 98.8 %; the SPEC of morning-checkin/evening-checkout/run-report and the application README updated |
| BEAD-03 | Done | ht-bm9, ef2c868: the 3 PRD scenarios with real steps + 2 edge cases (a check-in without confirmation — no photo; a check-out confirmed only by the retry — as text); both gaps of BEAD-01/02 pinned (the order of the log off photo through a spy on `Page.screenshot`, the retry without a photo); the fake got `lose_on`; 10 sabotages bite; 776 passed / 4 skipped, coverage 98.8 % |
| BEAD-04 | Done | ht-2l1: OK — 0 critical, 0 major, 3 minor, 2 nit; 9 sabotages in a copy of HEAD bite; minor 1 and 2 → BEAD-05, minor 3 deferred (CONTEXT); the nits (the fake's path in the RFC, the CONTEXT phase) and the stale graph summary closed by the coordinator |
| BEAD-05 | Done | ht-8i1: 5 SPECs (morning-checkin, evening-checkout, telegram-notifier, windowed-run, horizon-playwright-client); minor 1 and 2 of the review closed; sync-check 32/32 ok, docs audit clean |
| BEAD-06 | Done | ht-2kp: the check-out notification of 2026-10-21 17:08 arrived as a photo of the launch list with the caption; the check-in photo follows on the next working day (the owner's decision to close) |

## Notes

- BEAD-01 waited for ht-slm and ht-5ni so as not to share the adapter and test files with their waves.
- The BEAD-01 gap (the order of the log off photo) is closed in BEAD-03 by an integration test on the fixture; line 525 of the adapter («page already closed») stays uncovered — unreachable through the public API.
- BEAD-02 decision: if the log off worked but the confirmation was lost, the retry finds no session and ends in success without a photo — the photo of the first attempt is not carried over (so in the SPEC; not pinned by a test — BEAD-03 may pin it).
- For BEAD-05 (tech-writer): the evening-checkout SPEC may name both ways the confirmation can be lost (the log off worked and answered «not confirmed» / the read after the log off failed); the telegram-notifier SPEC line «A failure carries its screenshot» is incomplete — a success carries one too; check the windowed-run SPEC.
- BEAD-01 and BEAD-02 went into PR #3 together with HT-003/HT-005 (one branch): the adapter hands out the path, the use cases do not read it yet — the behaviour does not change.
- The three PRD scenarios lie in the suite as explicit SKIPs with a reason (`screenshot_preview.feature`); BEAD-03 (ht-bm9) replaces the stubs.
