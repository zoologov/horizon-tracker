# PRD: HT-009 — Check-in success screenshot after the hold

> **Status:** Approved
> **Created:** 2026-10-22

---

## Problem

A successful morning check-in sends a photo of `#/desktop` that is solid black.
Evidence (Telegram): check-in 2026-10-22 08:06 MSK (message 08:08), caption «Вход выполнен»,
calendar isdayoff.ru, sidebar toggler of HTML Access visible, Blast area black. The previous
evening's check-out (2026-10-21 17:08 MSK) photo of `#/launchitems` is fine. That day's
check-out had not run yet when the black check-in was reported.

Root cause: HT-004 takes the success screenshot inside `open_desktop`, after the canvas has
a non-zero size and a 2 s settle, **before** `MorningCheckin` holds the desktop for
`HT_HOLD_SECONDS` so Windows can finish logging on. The run still succeeds (CONNECTED →
DISCONNECTED after the hold); the photo is simply too early.

## Impact

The owner cannot trust the check-in preview by eye. The check-in itself still records a
Windows logon; only the proof in Telegram is wrong. Leaving it unfixed keeps a false
«opened desktop» image in every successful morning report.

## Goals

- [x] A successful check-in's success photo is taken **after** the hold, while Blast is still
      open, and before disconnect, and only from a non-blank frame of the remote surface.
- [x] `open_desktop` no longer returns a success screenshot; a separate capture on the open
      desktop supplies the path (or `None`).
- [x] Check-out success photos and failure screenshots behave as today.
- [x] A missing success photo still yields a text success report; the run does not fail for it.

## Non-goals

- Changing hold length, calendar, or notification wording.
- An agent inside the Windows session, or OCR, to tell the shell from the login screen.
- A photo when the remote surface stays blank: that capture returns `None` and the report is text.
- Video or a manual Telegram request for a screenshot.
- Splitting the fix and the `1.0.1` release into two pull requests (one PR ships both).

## User Stories

### US-1: Check-in preview after Windows is up
**As** the owner, **I want** the check-in photo to show the desktop after the hold,
**so that** I see a drawn Windows session, not a black Blast frame.

**Acceptance criteria** (each references a scenario in `tests/acceptance/features/`):
- [x] Scenario: `A successful check-in sends a screenshot of the opened desktop`
- [x] Scenario: `A successful check-in's screenshot is taken after the desktop was held`
- [x] Scenario: `A check-in whose screenshot failed still reports success as text`

### US-2: Check-out unchanged
**As** the owner, **I want** evening check-out photos to stay as they are,
**so that** this fix does not regress the launch-list preview.

**Acceptance criteria**:
- [x] Scenario: `A successful check-out sends a screenshot of the launch list without a session`

## Acceptance Criteria (overall)

Behaviour-bearing criteria are scenarios; the suite holds their text and this list references
them by name. `beadloom lint` reports a referenced scenario the suite does not contain.

- [x] Scenario: `A successful check-in sends a screenshot of the opened desktop`
- [x] Scenario: `A successful check-in's screenshot is taken after the desktop was held`
- [x] Scenario: `A check-in whose screenshot failed still reports success as text`
- [x] Scenario: `A successful check-out sends a screenshot of the launch list without a session`

**Non-behavioural criteria** stay checkboxes and are labelled, so the absence of a scenario is
a stated decision rather than a gap:

- [x] Released as `1.0.1` (PATCH: no public-surface change) with the fix in one PR — non-behavioural: version and change log are release process, not a Gherkin observer
  - Met on 2026-10-22: PR #3, merged as da3ac21 and tagged `v1.0.1`.
- [x] Live `ht checkin --force` after the `v1.0.1` deploy shows a non-black desktop photo in Telegram — non-behavioural: observer outside the suite (owner's chat on the VPS)
  - Met on 2026-10-24: the check-in photo of 07:36 MSK in the owner's chat, taken on the
    host after the `v1.0.1` deploy, shows the painted Windows desktop. The record names the
    photo, not whether that run was forced. The HTML Access Fullscreen dialog in the same
    photo is HT-010's.
