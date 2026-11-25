# ACTIVE: HT-014 — Sign out of Windows during evening check-out

> **Last updated:** 2026-11-25
> **Phase:** Live verification

---

## Current Bead

**Bead:** ht-51k — Verify the click-interception recovery in production
**Goal:** Exercise the corrected fresh-list confirmation path on the VPS and check the attendance record.
**Done when:** A first check-out attempt with an existing session confirms `NO_SESSION` and the attendance record observes Windows sign-out.

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
- [x] v1.1.6 Run geometry and fresh-list Fullscreen failures reproduced and corrected locally
- [x] Post-Run wait, pre-Enter screenshot and final-focus Fullscreen gaps reproduced RED and guarded GREEN locally
- [x] PR #24 Linux fresh-list fixture race reproduced deterministically and corrected without a production guard change
- [x] Merged candidate 5a81342's delayed fresh-list Fullscreen race reproduced RED and corrected GREEN locally
- [x] Merged candidate 6b041fd's beyond-100 ms actual-click interception reproduced RED and recovered GREEN locally
- [ ] Release v1.1.6 through the tag workflow
- [ ] Production check-in → check-out and attendance-record verification after deployment

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-oe6 | Done | Merged 6b041fd still failed live because Fullscreen arrived beyond 100 ms and intercepted the real fresh-list overflow click. New acceptance and integration controls were RED with logoff_not_confirmed/TimeoutError. The 100 ms wait is removed: a 1000 ms actionability-bounded click catches only PlaywrightTimeoutError, requires the existing morning Cancel-only helper and both existing buttons hidden, then retries only the same read-only menu opening within action_ms. Controls passed 20/20 tree and 10/10 clean room; full tree and room each passed 2046 tests, 5 skipped, 3 macOS baselines deselected; static checks and Gate green. No OK, No Running items inference, repeated Enter/Log Off, public API or live access. |
| ht-0tu | Done | Independently restored HEAD 6b041fd in a disposable room: beyond-100 ms integration and acceptance controls were RED with logoff_not_confirmed/TimeoutError from real overflow clicks. Corrected controls passed 20/20 each on the tree and 20/20 each in room-ht-0tu. Added one no-dialog actionability-timeout regression proving re-raise, one attempt, no Cancel/OK and no repeated Windows sign-out. Targeted: 83 passed, 3 macOS baselines deselected; 92.18% coverage (484 statements, 130 branches). Full room: 2047 passed, 5 skipped, 3 deselected in 272.54 s. Static and Beadloom checks green. Source audit confirmed only the morning Cancel-only helper, both buttons hidden before retry, the read-only canLogoff-backed menu read, and no No Running items inference or repeated Enter/Log Off. |
| ht-pea | Done | Final independent re-review OK |
| ht-ga0 | Done | Actual fresh-list overflow-click timeout recovery documented: the Cancel-only helper, both-button hidden barrier and same read-only menu retry precede the unchanged canLogoff-backed NO_SESSION read. Adapter Testing now lists all six fixture-backed acceptance scenarios, including four Windows sign-out scenarios and the omitted menu-interception case. Related infrastructure and portal prose already matched; assigned pairs ok, stale 0; reindex/lint/doctor/Gate/diff checks passed |

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

The v1.1.6 evidence exposed two narrower defects. The Run detector used the old fixture geometry and sampled every
second row, missing the live one-pixel focused blue input borders. It now uses the measured geometry, accepts a
contrasting border and samples every row in both border bands. After Enter, the fresh launch-items list can carry
Fullscreen even when it already says `No Running items`; confirmation now cancels that dialog through the morning
Cancel-only helper before opening the tile menu. Offline checks recognise all three desktop evidence frames and reject
the launch-list frame. The production-shaped acceptance and integration regressions pass; a corrected candidate still
requires the VPS production check-out and attendance verification.

The subsequent review found that Fullscreen could arise during the post-Run wait or the pre-Enter page screenshot,
after the previous readiness guard. New local regressions inject both states and prove that Cancel, painted readiness
and restored surface focus now precede Ctrl+A, typing and exactly one Enter. The final focus also has a Cancel-only
clean-dialog check that fails closed before another key. Existing-Run geometry, fresh-list confirmation, safe
screenshots and the public contracts are unchanged. The full clean-room suite passed 2044 tests with 5 skips and only
the three recorded macOS child-process cases deselected; no live portal or release action was taken.

PR #24 CI run 45557757282 then failed on both Linux test legs because the fixture omitted the requested fresh-list
Fullscreen dialog. Its initial route rendered before the asynchronous behaviour response, so a fast launch-items
response won the race. Delaying only the behaviour response reproduced the CI event list and assertion exactly. The
fixture now loads configuration before its first render; the adapter and its Cancel-only guard are unchanged. The
regression passed 20/20 tree repetitions and 10/10 clean-room repetitions, and the clean-room suite passed 2044 tests
with 5 skips and the three recorded macOS cases deselected. No Linux leg was entered locally.
