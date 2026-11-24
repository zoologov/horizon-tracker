# ACTIVE: HT-014 — Sign out of Windows during evening check-out

> **Last updated:** 2026-11-24
> **Phase:** Handoff

---

## Current Bead

**Bead:** None — the ht-oe6 production follow-up is complete and closed.
**Next:** The coordinator chooses from `bd ready --limit 0`; this follow-up starts no release work.

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
- [x] Release v1.1.2 deployed with surface focus; live check-out exposed Run-dialog timing loss
- [x] Release v1.1.3 deployed with pacing; staged screenshots exposed false painted readiness on gray frames
- [x] Variation-aware painted predicate tested, reviewed and documented
- [x] Uncommitted live diagnostic proved Start right-click → Run → `shutdown /l` → Enter ends Windows
- [x] Production Win+X path and fixture/acceptance coverage implemented
- [x] Full validation, documentation refresh and landing without a version bump or deployment
- [ ] Release v1.1.4 through the tag workflow
- [ ] Repeat live VPS `checkout --force` and attendance-record verification after deployment

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-oe6 | Done | Live-proven scaled Win+X path; tree and clean room 2037 passed, 5 skipped, 3 baseline failures |
| ht-0tu | Done | Paint predicate 5c90833: 12/12 gray/desktop checks and 36/36 regressions passed; clean room 2035 passed, 5 skipped, 3 baseline failures |
| ht-pea | Done | Final independent re-review OK |
| ht-ga0 | Done | Luminance/chroma readiness and staged gray-frame evidence documented; stale pairs 0 |

## Notes

The baseline suite was run before any code change on 2026-11-22: 2024 passed, 4 failed, 5 skipped. Three failures are
macOS child-process assertions in `test_entering_the_client_starts_nothing_until_a_step_needs_the_browser`; the fourth
was ShellCheck SC2329 for `clean_bytecode` in `scripts/mutation.sh`, since fixed and covered by an execution test. Later
runs distinguish the three remaining platform-specific baseline failures from regressions.

Live v1.1.1 exposed missing keyboard focus; v1.1.2 added it but exposed input timing; v1.1.3 added pacing and still
failed. Staged screenshots then showed a uniform gray repaint passing the brightness-only readiness check before
`Meta+R`. The v1.1.4 predicate requires luminance variation or chroma, so it waits for actual desktop content. This is
locally verified only until the live check-out is repeated. No live portal login was permitted from the development
sandbox; the owner explicitly authorised the VPS checks. The existing `.beads/issues.jsonl` modification and untracked
`.DS_Store` / metrics files predated HT-014 and are not part of its implementation.

The live diagnostic subsequently proved the scaled Windows path: right-click Start at remote `(20,700)`, left-click Run
at `(85,600)`, replace the field with `shutdown /l`, and press Enter once. A following production check-out reported
`already_logged_off`. The production follow-up reuses the dialog/paint readiness and focus guards at every action
boundary and captures checkout evidence before Enter. The diagnostic remains untracked; no live portal login was made
from the development sandbox.
