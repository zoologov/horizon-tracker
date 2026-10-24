# BRIEF: HT-010 — No client dialog in the check-in photo

> **Type:** bug
> **Status:** Approved
> **Created:** 2026-10-24

---

## Problem

Since v1.0.1 (HT-009) the success photo of the morning check-in is taken after the hold,
from a painted frame of the remote desktop. The photo of 2026-10-24 07:36 MSK shows the
painted Windows desktop with the HTML Access dialog **"Fullscreen — Click OK to grant
permission for full screen"** (OK / Cancel) on top of it. `open_desktop` cancels that offer
once (`#cancelDialogBtn`, see the horizon-playwright-client SPEC), but the client shows it
again, or first shows it, after that point, so it is in the frame when the capture runs.

The independent review of v1.0.1 (2026-10-24, no review bead; the verdict is recorded in
this work item) found the fix correct against its PRD and RFC and left 3 major and 5 minor
findings, all but one inside the same capture:

- **Major-1.** Nothing pins the poll loop: a sabotage that keeps the first sample and drops
  the loop leaves all tests green.
- **Major-2.** The adapter (572 → 762 lines) now carries a hand-written PNG codec and the
  paint rule, a second responsibility, tested only through a private name.
- **Major-3.** `.claude/hooks/beadloom-guard.sh`, a generated file, was hand-edited to run
  the Cursor translator; under Claude Code a WARN now exits 0 with JSON on stdout and a
  blocking guard would (inferred, not measured) no longer block.
- **Minor-4.** A page closed between samples raises `HorizonClientError` out of the capture,
  so the attempt fails as UNEXPECTED instead of a text success.
- **Minor-5.** Each sample decodes the whole frame in Python (0.77 s at 1280×720, 1.69 s at
  1920×1080 on this Mac) and the deadline is read only between samples: a capture can overrun
  its bound by a sample plus the 15 s action timeout. systemd is not reached.
- **Minor-6.** The capture runs on every attempt, including one the broker will not confirm,
  spending up to 60 s of the window before the retry. Application layer; **out of this item**
  (recorded in HT-009's CONTEXT as a known trade-off, for the owner's call).
- **Minor-7.** The "largest surface" rule is not pinned: the test appends the small canvas
  after the Blast one.
- **Minor-8.** HT-009's ACTIVE and PRD are stale: phase Development, unticked boxes, a review
  bead shown open that commit 1ea117b closed; the epic `ht-qq2` is still open in the tracker.

## Solution

Right before the post-hold capture, dismiss any open client dialog (the Cancel button of the
dialog the client renders) and capture only once no dialog is visible, inside the capture's
existing time bound. If the dialog cannot be dismissed, the capture returns `None` and the
report goes out as text, as HT-009 already prescribes for a frame that never paints. The
check-in's outcome, the hold and the quiet disconnect do not change. The fix is pinned on the
HTML Access fixture: a dialog opened after the desktop is painted, and the capture that
dismisses it; the sabotage "do not dismiss" must go red.

The review's findings inside the capture are closed in the same item, so that one agent
edits the function once:

- the paint rule leaves Python: the browser downsamples the largest surface to the 32×32
  grid (a 2D canvas `drawImage` + `getImageData`) and returns the lit count, the hand-written
  PNG codec is deleted, and the deadline holds across a sample (Major-2, Minor-5); if a
  separate module is still needed, it gets its own graph node and the BRIEF is amended;
- the poll loop, the largest-surface rule and "a page closed mid-capture returns `None`" are
  pinned by tests whose sabotages go red (Major-1, Minor-4, Minor-7);
- the guard hook is restored to the generated form and the Cursor translator stays under
  `.cursor/` (Major-3); HT-009 is closed in its documents and the tracker (Minor-8).

## Axes

Derived, never authored. The derivation found no effect sink under `capture_open_desktop`, so
its seed is `none` and every axis is unresolved rather than empty; the rows below are the
callers and the nodes whose branches it listed (the branches rows, 90 functions over 11 nodes,
are collapsed to one row per node here; the full answer is reproduced by the command).

> **Derived by:** `beadloom impact capture_open_desktop` over `src/horizon_tracker` (Explore, 2026-10-24)
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`
> **Unresolved:** 15 name-defined-more-than-once, 1 no-seed, 20 unresolved-terminator-name (that run)

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — no commit point to ask who else writes through | — | no | nothing is written; the capture reads a frame and saves a file the artifact store already names |
| branches | horizon-playwright-client | `capture_open_desktop`, `_nonblank_frame`, `_settle_desktop`, `_confirm_logoff_dialog` and 64 more functions | none | yes | the work site: the dialog is dismissed inside the adapter, right before the capture |
| branches | ports | `capture_open_desktop` and 13 more protocol methods, 0 branches each | none | no | the port's signature and meaning (`Path \| None`) do not change |
| callers | morning-checkin | 1 — `src/horizon_tracker/application/checkin.py:57` | none | no | calls the port after the hold as today; a `None` already yields a text success |
| callers | windowed-run | 6 — `src/horizon_tracker/application/windowed_run.py:125` | none | no | the run loop is untouched |
| callers | evening-checkout | 1 — `src/horizon_tracker/application/checkout.py:65` | none | no | check-out photographs the launch list, not the desktop |
| callers | probe | 3 — `src/horizon_tracker/application/probe.py:107` | none | no | probe never opens a desktop |
| callers | cli | 1 — `src/horizon_tracker/cli.py:252` | none | no | composition root; no new wiring |
| callers | artifact-store | 2 — `src/horizon_tracker/infrastructure/artifacts.py:34` | none | no | the screenshot path is named as today |
| callers | schedule, settings, system-clock | 1, 1, 2 sites | none | no | surfaced through the client's constructor arguments; no change reaches them |

Kept axes name ONE node (`horizon-playwright-client`): the simplified flow carries the change.

## Beads

Status lives in ACTIVE.md, reconciled from the tracker by the pre-commit active-sync, so this
table names the beads and carries no status. The Tracker cell holds `-` until the beads are
created, and then the id the tracker answered.

| ID | Tracker | Name | Priority |
|----|---------|------|----------|
| BEAD-01 | ht-3fs | dev: dismiss the client dialog before the post-hold capture; fixture test; the two scenarios in the suite | P1 |
| BEAD-02 | ht-chm | dev: the paint rule in the browser, the PNG codec removed, the deadline across a sample; tests pin the poll loop, the largest surface and the closed page (review Major-1/2, Minor-4/5/7) | P1 |
| BEAD-03 | ht-igr | review: dialog gone from the frame, the capture bound, the disconnect untouched, no screenshot on the login page, the sabotages of BEAD-01/02 bite | P1 |
| BEAD-04 | ht-lh0 | tech-writer: horizon-playwright-client and morning-checkin SPECs; HT-009 documents closed (Minor-8); HT-009 CONTEXT records Minor-6 | P2 |
| BEAD-05 | ht-c7x | chore (coordinator): `beadloom-guard.sh` restored by `beadloom setup-agentic-flow`, `.cursor/` kept (Major-3); `ht-qq2` closed | P2 |

## Acceptance Criteria

- [ ] Scenario: `A successful check-in's photo shows the desktop without a client dialog`
- [ ] Scenario: `A client dialog that cannot be dismissed leaves the check-in a text success`
- [ ] The next scheduled check-in on the host sends a photo without the Fullscreen dialog — non-behavioural: the observer is the owner's chat
- [ ] The sabotages "one sample only", "first surface instead of largest" and "do not dismiss the dialog" each go red — non-behavioural: a property of the suite, measured by the review bead
- [ ] `horizon_playwright.py` holds no PNG decoding; its module docstring names one responsibility — non-behavioural: a property of the tree

## Non-behavioural declaration

Deleted: the change is behaviour-bearing and its criteria are the scenarios above.
