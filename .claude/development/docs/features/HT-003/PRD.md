# PRD: HT-003 — Random check-in and check-out moments inside ranges

> **Status:** Draft
> **Created:** 2026-10-20

---

## Problem

Today the check-in and the check-out are set to fixed minutes: 07:55 and 17:00 (configured time zone) every working
day. Two identical times day after day, to the minute, read in the log as
machine-made. The owner wants the check-in and check-out moments to look human: different every day,
within reasonable ranges, while a full working day is still kept.

## Impact

The account owner and the look of their presence log are affected. Without the change the service
works, but its schedule is monotonous. The change concerns only the moment of the launch: the
check-in itself, disconnect and log off stay as in HT-001.

## Goals

- [ ] The check-in moment of every working day is drawn from the range **07:30–08:10** (configured time zone) to
      the minute, and it differs from day to day.
- [ ] The check-out moment equals the check-in moment **plus 9 hours plus 0 to 10 minutes** (8 working
      hours and a lunch hour, never shorter), and lies in the range **16:30–17:10**; if
      the sum goes past 17:10, the check-out is set to 17:10. The owner's examples: 07:30→16:32,
      07:58→16:58, 08:03→17:10.
- [ ] Both moments are computed from the date **deterministically** (the same day gives the same
      pair), so the morning and the evening runs agree without shared state and
      without a file recording "what was decided in the morning".
- [ ] Retries after a failure stay inside the window **[moment, moment + 5 minutes]**, as in HT-001;
      a run that has not started by the end of the window is skipped with a notification.
- [ ] `horizon checkin --dry-run` and `horizon checkout --dry-run` name the moment drawn for
      today; the success notification names the planned and the actual moments.
- [ ] The systemd timers fire at the start of the range (07:30 and 16:30), the service waits for its
      moment inside the process; `TimeoutStartSec` covers the wait until the end of the range plus
      the attempt window.

## Non-goals

- Different ranges per weekday or "special" days; the ranges are the same for every working day.
- Memory between days (for example "do not repeat yesterday's minute"): the deterministic draw
  from the date already gives different minutes on different days.
- Changing what happens after the moment: check-in, holding, disconnect, log off do not
  change.
- Manual `--force` ignores the ranges: it starts immediately, as before.

## User Stories

### US-1: Random check-in moment
**As** the owner, **I want** the check-in to happen at a random minute between 07:30 and 08:10,
**so that** the presence log does not look machine-made.

**Acceptance criteria** (each references a scenario in `tests/acceptance/features/`):
- [ ] Scenario: `The check-in moment of a working day lies inside the check-in range`
- [ ] Scenario: `Two different days draw different check-in moments`

### US-2: Check-out after a full day
**As** the owner, **I want** the check-out to happen 9 hours and a further 0–10 minutes after the
check-in, but no later than 17:10, **so that** the day is full and the check-out time varies too.

**Acceptance criteria**:
- [ ] Scenario: `The check-out moment is nine hours plus up to ten minutes after the check-in`
- [ ] Scenario: `A check-out past the end of its range is clipped to the end`

### US-3. Morning and evening agree
**As** the owner, **I want** the evening run to use the same check-in moment as the
morning one, without a shared file, **so that** a reboot of the VPS or a loss of state does not break the pair.

**Acceptance criteria**:
- [ ] Scenario: `The same date gives the same drawn moments in two separate runs`

### US-4. Waiting inside the process
**As** the owner, **I want** the timer to fire at the start of the range while the service waits for its
moment and then acts in its window, **so that** systemd does not need to know about the
randomness.

**Acceptance criteria**:
- [ ] Scenario: `A run started at the range start waits until its drawn moment before the first attempt`
- [ ] Scenario: `A dry run names the drawn moment of the day`

## Acceptance Criteria (overall)

Behaviour-bearing criteria are scenarios; the suite holds their text and this list references
them by name. `beadloom lint` reports a referenced scenario the suite does not contain.

- [ ] Scenario: `The check-in moment of a working day lies inside the check-in range`
- [ ] Scenario: `Two different days draw different check-in moments`
- [ ] Scenario: `The check-out moment is nine hours plus up to ten minutes after the check-in`
- [ ] Scenario: `A check-out past the end of its range is clipped to the end`
- [ ] Scenario: `The same date gives the same drawn moments in two separate runs`
- [ ] Scenario: `A run started at the range start waits until its drawn moment before the first attempt`
- [ ] Scenario: `A dry run names the drawn moment of the day`

**Non-behavioural criteria** stay checkboxes and are labelled, so the absence of a scenario is
a stated decision rather than a gap:

- [ ] The timers are moved to 07:30 and 16:30, `TimeoutStartSec` covers the range plus the window —
      non-behavioural: a property of the units, checked by the unit-parsing test and a live run.
- [ ] The first week of scheduled runs shows different check-in and check-out minutes in Telegram —
      non-behavioural: the owner's observation.
