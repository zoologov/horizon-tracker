# ACTIVE: HT-014 — Sign out of Windows during evening check-out

> **Last updated:** 2026-11-23
> **Phase:** Release

---

## Current Bead

**Bead:** ht-51k — Release v1.1.1 and perform the owner's live verification
**Goal:** Deploy the merged Windows sign-out fix through the release workflow, then run `checkout --force` on the VPS.
**Done when:** The release is green, the host runs v1.1.1, and the live check-out confirms the Windows session ended.

## Progress

- [x] Explore derived the axes; scope was limited to `horizon-playwright-client`
- [x] BRIEF approved by the owner
- [x] Parent bug and dev → test → review → tech-writer DAG created
- [x] Development implementation and targeted tests
- [x] Test verification and full-suite comparison with the baseline
- [x] Read-only review
- [x] Documentation refresh and Beadloom validation
- [x] PR #16 merged; required CI and post-merge CI green
- [ ] Release v1.1.1 through the tag workflow
- [ ] Live VPS `checkout --force` and attendance-record verification after deployment

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-oe6 | Done | Atomic fixture input/sign-out recording; 24/24 order checks, full room 2031 passed, 5 skipped, 3 baseline failures |
| ht-0tu | Done | Final 1cda2e3: 84 targeted tests passed; clean room 2030 passed, 5 skipped, 3 macOS baseline failures |
| ht-pea | Done | Final independent re-review OK |
| ht-ga0 | Done | Current Windows sign-out and portal documentation refreshed; stale pairs 0 |

## Notes

The baseline suite was run before any code change on 2026-11-22: 2024 passed, 4 failed, 5 skipped. Three failures are
macOS child-process assertions in `test_entering_the_client_starts_nothing_until_a_step_needs_the_browser`; the fourth
was ShellCheck SC2329 for `clean_bytecode` in `scripts/mutation.sh`, since fixed and covered by an execution test. Later
runs distinguish the three remaining platform-specific baseline failures from regressions.

No live portal login was permitted from the development sandbox. The owner has now explicitly authorised the post-release
VPS `checkout --force`. The existing `.beads/issues.jsonl` modification and untracked `.DS_Store` / metrics files
predated HT-014 and are not part of its implementation.
