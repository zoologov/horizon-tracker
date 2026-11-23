# ACTIVE: HT-014 — Sign out of Windows during evening check-out

> **Last updated:** 2026-11-23
> **Phase:** Release

---

## Current Bead

**Bead:** ht-51k — Release v1.1.2 and repeat the owner's live verification
**Goal:** Deploy the WebMKS keyboard-focus correction, then run `checkout --force` on the VPS with an existing session.
**Done when:** The release is green, the host runs v1.1.2, and the live check-out confirms the Windows session ended.

## Progress

- [x] Explore derived the axes; scope was limited to `horizon-playwright-client`
- [x] BRIEF approved by the owner
- [x] Parent bug and dev → test → review → tech-writer DAG created
- [x] Development implementation and targeted tests
- [x] Test verification and full-suite comparison with the baseline
- [x] Read-only review
- [x] Documentation refresh and Beadloom validation
- [x] PR #16 merged; required CI and post-merge CI green
- [x] Release v1.1.1 deployed; live check-out exposed missing WebMKS keyboard focus
- [x] WebMKS focus correction tested, reviewed and documented
- [ ] Release v1.1.2 through the tag workflow
- [ ] Repeat live VPS `checkout --force` and attendance-record verification after deployment

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-oe6 | Done | WMKS surface focus before keyboard input; full room 2031 passed, 5 skipped, 3 baseline failures |
| ht-0tu | Done | Live-focus 09a9980: 24/24 ordering checks and 66 adapter tests passed; clean room 2031 passed, 5 skipped, 3 baseline failures |
| ht-pea | Done | Final independent re-review OK |
| ht-ga0 | Done | WebMKS focus and the locally verified v1.1.1 failure documented; stale pairs 0 |

## Notes

The baseline suite was run before any code change on 2026-11-22: 2024 passed, 4 failed, 5 skipped. Three failures are
macOS child-process assertions in `test_entering_the_client_starts_nothing_until_a_step_needs_the_browser`; the fourth
was ShellCheck SC2329 for `clean_bytecode` in `scripts/mutation.sh`, since fixed and covered by an execution test. Later
runs distinguish the three remaining platform-specific baseline failures from regressions.

Release v1.1.1 deployed successfully, and a live check-in succeeded. The following live check-out made three attempts,
each opening the desktop and ending `logoff_not_confirmed`: the launch button retained focus, so WebMKS did not receive
the Windows keys. The correction clicks the painted remote surface first and is locally verified only until v1.1.2 is
deployed and the live check-out is repeated. No live portal login was permitted from the development sandbox; the owner
explicitly authorised the VPS checks. The existing `.beads/issues.jsonl` modification and untracked `.DS_Store` /
metrics files predated HT-014 and are not part of its implementation.
