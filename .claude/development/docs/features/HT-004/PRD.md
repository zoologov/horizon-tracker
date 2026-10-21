# PRD: HT-004 — Screenshot in the notification of a successful check-in and check-out

> **Status:** Done
> **Created:** 2026-10-20

---

## Problem

The success notification is text only: «Check-in succeeded, time…». The owner sees that the service
reported, but not what exactly it opened. A screenshot exists only on failure.

## Impact

The owner receives in their private chat proof of the check-in (the drawn desktop) and of the check-out
(the desktop list without a session) and can verify them by eye without opening the Horizon client.
The desktop screenshot shows its icons and windows and goes only to the owner's private chat; the password
is not on it by construction (it is taken away from the login page).

## Goals

- [ ] The notification of a successful check-in arrives as a photo of the opened desktop with a caption
      (the previous text), taken after the desktop is drawn, before the disconnect.
- [ ] The notification of a successful check-out arrives as a photo of the desktop list after Log Off, where
      the desktop has no session, with a caption.
- [ ] If the screenshot could not be taken, the notification goes out as text, as now; the run does not
      fail because of the screenshot.
- [ ] Success screenshots live in the same artifact directory and are rotated by the same policy.

## Non-goals

- Video or a series of frames; requesting a screenshot manually through Telegram.
- Changing the notification text (that is HT-007, i18n).

## User Stories

### US-1: Check-in preview
**As** the owner, **I want** to see a screenshot of the opened desktop in the check-in notification,
**so that** I can be sure the check-in was real.

**Acceptance criteria** (each references a scenario in `tests/acceptance/features/`):
- [ ] Scenario: `A successful check-in sends a screenshot of the opened desktop`
- [ ] Scenario: `A check-in whose screenshot failed still reports success as text`

### US-2: Check-out preview
**As** the owner, **I want** to see the desktop list without a session in the check-out notification,
**so that** I can be sure the session has ended.

**Acceptance criteria**:
- [ ] Scenario: `A successful check-out sends a screenshot of the launch list without a session`

## Acceptance Criteria (overall)

Behaviour-bearing criteria are scenarios; the suite holds their text and this list references
them by name. `beadloom lint` reports a referenced scenario the suite does not contain.

- [ ] Scenario: `A successful check-in sends a screenshot of the opened desktop`
- [ ] Scenario: `A check-in whose screenshot failed still reports success as text`
- [ ] Scenario: `A successful check-out sends a screenshot of the launch list without a session`

**Non-behavioural criteria** stay checkboxes and are labelled, so the absence of a scenario is
a stated decision rather than a gap:

- [x] The first live notification with a photo received by the owner — non-behavioural: an observer outside the system. (the check-out photo, 2026-10-21 17:08 MSK)
