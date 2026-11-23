# ACTIVE: HT-014 — Sign out of Windows during evening check-out

> **Last updated:** 2026-11-22
> **Phase:** CI verification

---

## Current Bead

No bead is active. The development and test waves are closed; CI verification is pending on the shared diagnostic-filter follow-up.

## Progress

- [x] Explore derived the axes; scope was limited to `horizon-playwright-client`
- [x] BRIEF approved by the owner
- [x] Parent bug and dev → test → review → tech-writer DAG created
- [x] Development implementation and targeted tests
- [ ] Test verification and full-suite comparison with the baseline
- [ ] Read-only review
- [ ] Documentation refresh and Beadloom validation
- [ ] Live VPS `checkout --force` and attendance-record verification after deployment

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-oe6 | Done | Windows sign-out and CI fixes; shared systemd filter, full room 2030 passed, 5 skipped, 3 baseline failures |
| ht-0tu | Done | Final 1cda2e3: 84 targeted tests passed; clean room 2030 passed, 5 skipped, 3 macOS baseline failures |
| ht-pea | Blocked | Depends on ht-0tu |
| ht-ga0 | Blocked | Depends on ht-pea |

## Notes

The baseline suite was run before any code change on 2026-11-22: 2024 passed, 4 failed, 5 skipped. Three failures are
macOS child-process assertions in `test_entering_the_client_starts_nothing_until_a_step_needs_the_browser`; the fourth
is ShellCheck SC2329 for `clean_bytecode` in `scripts/mutation.sh`. Later runs must distinguish these baseline failures
from regressions.

No live portal login is permitted from the development sandbox. Only the VPS may perform the real `checkout --force`.
The existing `.beads/issues.jsonl` modification and untracked `.DS_Store` / metrics files predated HT-014 and are not
part of its implementation.
