# ACTIVE: HT-014 — Sign out of Windows during evening check-out

> **Last updated:** 2026-11-22
> **Phase:** Development

---

## Current Bead

**Bead:** ht-oe6 — Implement Windows keyboard sign-out in the Playwright adapter
**Goal:** Replace the tile-menu broker logout with a real Windows sign-out through the open desktop.
**Done when:** The adapter opens the desktop, waits for safe input, sends Win+R → `shutdown /l` → Enter, and confirms `NO_SESSION` through freshly fetched launch items without changing the public port or evening use case.

## Progress

- [x] Explore derived the axes; scope was limited to `horizon-playwright-client`
- [x] BRIEF approved by the owner
- [x] Parent bug and dev → test → review → tech-writer DAG created
- [ ] Development implementation and targeted tests
- [ ] Test verification and full-suite comparison with the baseline
- [ ] Read-only review
- [ ] Documentation refresh and Beadloom validation
- [ ] Live VPS `checkout --force` and attendance-record verification after deployment

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-oe6 | Ready | Windows keyboard sign-out in the Playwright adapter |
| ht-0tu | Blocked | Depends on ht-oe6 |
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
