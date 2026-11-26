# ACTIVE: HT-014 — Sign out of Windows during evening check-out

> **Last updated:** 2026-11-26
> **Phase:** Development complete; coordinated verification next

---

## Current Bead

**Bead:** ht-51k — Verify the corrected checkout candidate in production
**Goal:** Exercise the checkout-only Fullscreen grant on the VPS and check first-attempt confirmation and attendance.
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
- [x] Merged candidate cd694c65's delayed initial Fullscreen grant controls reproduced RED and passed locally
- [x] Repeated Fullscreen controls, full-tree and clean-room validation for the checkout-only grant
- [ ] Release v1.1.6 through the tag workflow
- [ ] Production check-in → check-out and attendance-record verification after deployment

## Results

| Bead | Status | Details |
|------|--------|---------|
| ht-oe6 | Done | cd694c65 showed Fullscreen after the final guards and a fresh-list confirmation timeout. Delayed initial-offer integration and acceptance controls were RED with Cancel and no grant before Windows input. Checkout now grants only normalized exact permission text once through one visible OK plus Cancel, waits for both buttons to hide and restores painted focus before Start/Run or keys; a painted desktop arriving first waits on visible OK within action_ms, not an added delay. Different and later dialogs, delayed morning capture, menu-click interception, one Enter, canLogoff and screenshots remain Cancel-only/unchanged. Four controls passed 20/20 tree and 10/10 clean room. Full tree and room each passed 2051 tests, 5 skipped, 3 macOS baselines deselected; Ruff, format, mypy 3.12/3.13 targets and Beadloom Gate green. No public API, live access, version, release, push or merge. |
| ht-0tu | Done | Independently restored the cd694c65 adapter in rebuilt room-ht-0tu: delayed integration and acceptance controls were RED (2 failed, 2 passed, 86 deselected), recording Cancel and zero OK before Windows input; wrong-text and delayed-morning controls stayed GREEN. Corrected four controls passed 20/20 tree and 10/10 room repetitions. Targeted: 87 passed, 3 macOS baselines deselected in 253.12 s; 92.60% adapter branch coverage. Full room: 2051 passed, 5 skipped, 3 deselected in 337.07 s; 98.22% total branch coverage. Source audit confirmed exact normalized text, one visible OK/Cancel, both-button hidden wait and focus before input, with later/mismatched/morning dialogs Cancel-only. Menu recovery, canLogoff, one Enter, safe screenshots and all 9 public signatures are unchanged. Tree/room Ruff, format and mypy plus tree Beadloom checks are green. No tests were added; no repository production/version edit, live access, push, merge or other bead closure. Darwin only; the room covers 11 named carries, not combined-tree interactions. |
| ht-pea | Done | Final independent re-review OK |
| ht-ga0 | Done | Adapter Testing now lists all seven fixture-backed acceptance scenarios: two check-in and five Windows sign-out, including `Checkout grants a delayed initial Fullscreen permission once before Windows input`. The adapter, infrastructure and portal prose already record the checkout-only exact initial Fullscreen OK grant once, while mismatched, later and morning dialogs remain Cancel-only; the related docs carry no stale scenario totals. Assigned pairs ok, stale 0; reindex/lint/doctor/Gate/diff checks passed |

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

Merged cd694c65 was confirmed as the live source on 2026-11-26. Attempt 1 showed Fullscreen over Run after the final
guards with `shutdown /l` selected, then failed as `logoff_not_confirmed`; attempt 2 ended Windows but fresh-list
confirmation timed out, and attempt 3 skipped. The production correction grants only the exact initial Fullscreen
permission once during checkout, using the existing visible OK/Cancel controls and the full-hide barrier proven by the
earlier staged diagnostic. It awaits a delayed offer by visibility and restores painted surface focus before any
Windows input. Morning, other dialog text, every later offer and the actual fresh-list menu-click recovery stay
Cancel-only. No live portal, version, release, push or merge action is part of this correction.

PR #24 CI run 45557757282 then failed on both Linux test legs because the fixture omitted the requested fresh-list
Fullscreen dialog. Its initial route rendered before the asynchronous behaviour response, so a fast launch-items
response won the race. Delaying only the behaviour response reproduced the CI event list and assertion exactly. The
fixture now loads configuration before its first render; the adapter and its Cancel-only guard are unchanged. The
regression passed 20/20 tree repetitions and 10/10 clean-room repetitions, and the clean-room suite passed 2044 tests
with 5 skips and the three recorded macOS cases deselected. No Linux leg was entered locally.
