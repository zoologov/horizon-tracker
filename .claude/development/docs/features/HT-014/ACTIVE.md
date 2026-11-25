# ACTIVE: HT-014 — Sign out of Windows during evening check-out

> **Last updated:** 2026-11-25
> **Phase:** Release

---

## Current Bead

**Bead:** ht-51k — Release v1.1.6 and verify production check-in → check-out
**Goal:** Deploy existing-Run reuse and the Win+X fallback, then create a session and close it with the production command.
**Done when:** The host runs v1.1.6 and production `checkout --force` confirms `NO_SESSION` after opening and signing out of Windows.

## Progress

- [x] Explore derived the axes; scope was limited to `horizon-playwright-client`
- [x] BRIEF approved by the owner
- [x] Parent bug and dev → test → review → tech-writer DAG created
- [x] Development implementation and targeted tests
- [x] Test verification and full-suite comparison with the baseline
- [x] Read-only review
- [x] Documentation refresh and Beadloom validation
- [x] PR #16 merged; required CI and post-merge CI green
- [x] Releases v1.1.1–v1.1.4 deployed; staged diagnostics isolated keyboard-focus and readiness failures
- [x] Live diagnostic proved Start right-click → Run → `shutdown /l` → Enter ends Windows
- [x] Production Win+X path, fixture/acceptance coverage, independent review and docs complete
- [x] v1.1.5 production check-in succeeded; checkout exposed an already-open Run state with no typing
- [x] Guarded existing-Run detection and no-reopen fixture/acceptance coverage implemented
- [x] Full validation, documentation refresh and landing without a version bump or live access
- [ ] Release v1.1.6 through the tag workflow
- [ ] Production check-in → check-out and attendance-record verification after deployment

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-oe6 | Done | Guarded existing-Run reuse and Win+X fallback; tree and clean room 2039 passed, 5 skipped, 3 baseline failures |
| ht-0tu | Done | Existing Run e52fefb: 8/8 state checks and 73 adapter tests passed; clean room 2039 passed, 5 skipped, 3 baseline failures |
| ht-pea | Done | Final independent re-review OK |
| ht-ga0 | Done | Existing-Run geometry, direct typing, Win+X fallback and v1.1.5 readiness evidence documented; stale pairs 0 |

## Notes

The baseline suite was run before any code change on 2026-11-22: 2024 passed, 4 failed, 5 skipped. Three failures are
macOS child-process assertions in `test_entering_the_client_starts_nothing_until_a_step_needs_the_browser`; the fourth
was ShellCheck SC2329 for `clean_bytecode` in `scripts/mutation.sh`, since fixed and covered by an execution test. Later
runs distinguish the three remaining platform-specific baseline failures from regressions.

The staged live path right-clicked Start at remote `(20,700)`, left-clicked Run at `(85,600)`, replaced the field with
`shutdown /l`, and pressed Enter once. A following production check-out reported `already_logged_off`. The production
port reuses the dialog/paint readiness and focus guards at every action boundary and captures checkout evidence before
Enter. The diagnostic remains untracked. No live portal login was made from the development sandbox; the owner explicitly
authorised the VPS checks. The existing `.beads/issues.jsonl` modification and untracked `.DS_Store` / metrics files
predated HT-014 and are not part of its implementation.

The v1.1.5 production check-in succeeded, but all three checkout attempts stopped at `Horizon desktop not ready for
Windows input`. Their screenshots showed an empty Windows Run dialog left open by the staged diagnostics. The v1.1.6
follow-up recognises that window's language-independent frame and input geometry only between HTML Access dialog guards,
refocuses it and skips Win+X. A plain desktop or uncertain reading still uses the proven scaled Start/Run path.
