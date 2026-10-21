# RFC: HT-003 — Random check-in and check-out moments inside ranges

> **Status:** Approved
> **Created:** 2026-10-20

---

## Overview

The check-in moment and the check-out moment stop being constants. The pure core gets a function
that deterministically "draws" a pair of moments from the date and a secret seed: the check-in from
07:30–08:10, the check-out = check-in + 9 h + 0–10 min, clipped to 16:30–17:10. The systemd timers
move to the start of the ranges (07:30, 16:30); after starting, the service waits for its moment
inside the process (through the `Clock.sleep` port, the browser is not started before that), then acts
in the window `[moment, moment + 5 min]` exactly as today. Morning and evening agree without shared
state, because both compute the same pair from the same date.

## Motivation

### Problem
The fixed 07:55 and 17:00 read in the log as machine-made. The owner wants a human-like
spread with a full working day (PRD HT-003).

### Solution
A deterministic draw in the domain, the wait in the use case, two new ranges and a seed in
the config, the timers at the start of the ranges. The behaviour after the moment (check-in, holding,
disconnect, log off, retries, notifications) does not change.

## Technical Context

### Constraints
- The domain has no I/O: the draw is a pure function of `(date, seed, parameters)`; the randomness is
  `hmac.sha256(seed, date.isoformat())`, two integers out of the digest; no `random`
  with a system seed.
- Time reaches the domain as an argument; waiting happens only through the `Clock.sleep` port, in tests
  a fake with virtual time.
- A wait of up to 40 minutes must not keep an open browser: the Playwright adapter starts
  Chrome lazily, on `login()`, not on construction (to be checked in BEAD-03 and, if it is not so,
  fixed in the adapter, that is its node).
- The unit's `TimeoutStartSec` must cover the range (40 min) + the window (5 min) + the run itself
  (up to 15 min, as now) = 60 min.
- The `.env` contract changes: `HT_CHECKIN_WINDOW`/`HT_CHECKOUT_WINDOW` go away, the ranges and
  the seed arrive; deploy.yml, RUNBOOK, cli.md and the workflow test are updated in the same
  work item, otherwise the deploy would write an outdated `.env`.
- `--force` starts immediately, without the wait and the ranges.

### Affected Areas
The `schedule` domain, the `windowed-run` use case, `probe`/`DryRun` (names the moment of the day),
`settings`, `cli` (wiring), the units and `deploy.yml` (the root service), the AS-IS documents.

## Axes

Derived, never authored. Run `beadloom impact <path|symbol>`, paste its answer into the table,
then take the scope decision in the last two columns — the derivation says what a change ranges
over, a person says how much of it this work item takes. The `refs:` of every bead below is
generated from the rows kept in scope, so a bead naming a node this table does not is a finding.

Rule each row by the node's role in the change: the axis a node surfaced under is not its role.
The axis is the node's relation to the seed, so a `callers` row can be a work site — a node that
calls into the change can also own what the change must edit. `Owns unread` names the files the
node owns that the derivation could not read; a count there is a question to answer before `no`.

> **Derived by:** `beadloom impact src/horizon_tracker/domain/schedule.py --section` over `src/horizon_tracker`, 2026-10-20, explore role
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 1 name-defined-more-than-once, 1 no-seed, 1 unresolved-terminator-name (run of 2026-10-20); `config.py`, `cli.py` and the units did not pass the derivation — they are declared below

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — no declared effect rule found a sink this target reaches, so there is no commit point to ask who else writes through | — | no | no row: no seed was found, no node was named |
| callers | windowed-run | 1 — `src/horizon_tracker/application/windowed_run.py:130` | none | yes | this is where the wait for the moment before the first attempt and the window from the moment appear |
| branches | schedule | `decide`: 2 branch(es), 7 exit form(s), over every call | none | yes | `decide` does not change, but the node gets the draw of the moments and builds a `Window` from the moment |
| branches | schedule | `__post_init__`: 1 branch(es), 1 exit form(s), over every call | none | yes | validation of the new values (range, day length) |
| branches | schedule | `contains`: 0 branch(es), 1 exit form(s), over every call | none | yes | the same node |
| branches | schedule | `__post_init__`: 1 branch(es), 1 exit form(s), over every call | none | yes | the same node |
| branches | windowed-run | `_decide`: 2 branch(es), 2 exit form(s), over every call, from a caller's seat | none | yes | the first attempt waits for the moment; `DryRun` calls the same point |
| declared (outside the derivation) | probe | `DryRun.plan` in `src/horizon_tracker/application/probe.py` | none | yes | the dry run names the moment drawn for the day |
| declared (outside the derivation) | settings | `Settings.from_env` in `src/horizon_tracker/infrastructure/config.py` | none | yes | new variables `HT_CHECKIN_RANGE`, `HT_CHECKOUT_RANGE`, `HT_SESSION_LENGTH_MINUTES`, `HT_SESSION_EXTRA_MAX_MINUTES`, `HT_WINDOW_GRACE_MINUTES`, `HT_JITTER_SEED`; the old windows go away |
| declared (outside the derivation) | cli | `src/horizon_tracker/cli.py` | none | yes | wiring: draw → window → `WindowedRun`; `--force` without the wait |
| declared (outside the derivation) | horizon-tracker | `deploy/*.timer`, `deploy/*.service`, `.github/workflows/deploy.yml`, `deploy/RUNBOOK.md` — outside `src/` | none | yes | the timers 07:30/16:30, `TimeoutStartSec=60min`, the `.env` contract |

## Proposed Solution

### Approach

**Domain (`domain/schedule.py`, the same `schedule` node):**

- `TimeRange(start: time, end: time)` — the range of the draw (validates `start < end`).
- `DailyMoments(check_in: time, check_out: time)` — the pair for a day.
- `draw_moments(day: date, seed: bytes, checkin_range: TimeRange, session_length: timedelta,
  extra_max: timedelta, checkout_range: TimeRange) -> DailyMoments`:
  `digest = hmac.new(seed, day.isoformat().encode(), "sha256").digest()`;
  `check_in = start + minutes(int.from_bytes(digest[:4]) % (span_minutes + 1))`;
  `check_out = clip(check_in + session_length + minutes(int.from_bytes(digest[4:8]) % (extra_max_minutes + 1)), checkout_range)`.
  Minute precision. Invariants: `check_in ∈ checkin_range`; `check_out ∈ checkout_range`;
  `check_out − check_in ≥ session_length` if that fits in the range, otherwise `check_out = end`.
- `window_from(moment: time, grace: timedelta) -> Window` — the attempt window from the moment.
- `decide`, `Decision`, `RetryPolicy`, `FIRST_ATTEMPT` do not change.

**Application (`windowed_run.py`):** `WindowedRun` receives `moment: time` and `grace`
(or a ready `Window` plus `moment`): before the first attempt, if `now < moment`, it calls
`clock.sleep((moment − now).total_seconds())` once (the fake clock in tests
advances the time), then `decide` as now. A start before the range start is `SKIP_EARLY`,
as now. `DryRun.plan` prints the line «drawn moment today: HH:MM (check-in), HH:MM
(check-out)». The report of a successful run carries the planned moment and the actual time (the
`planned_at` field in `RunReport`, the `report` domain, the text rendering).

**Infrastructure (`config.py`):** the variables below; `HT_JITTER_SEED` is optional, by
default the seed is `HORIZON_USERNAME` in UTF-8 (stable between deploys, no more secret than
the account itself; masked in `repr`, like the username).

**CLI:** `draw_moments(today)` → `window_from(moment)` → `WindowedRun(moment, window, …)`;
`--force` passes `moment = now` and `grace`, that is, no wait. `horizon probe` prints
a fifth line `schedule: today HH:MM / HH:MM`.

**Deploy:** `OnCalendar=*-*-* 07:30:00 Europe/Moscow` and `16:30:00`, `TimeoutStartSec=60min`,
`AccuracySec=1s`; `deploy.yml` writes the new variables into `.env`; RUNBOOK §2.2, §5 and cli.md.

### Changes

| File / Module | Change |
|---------------|--------|
| `src/horizon_tracker/domain/schedule.py` | `TimeRange`, `DailyMoments`, `draw_moments`, `window_from` |
| `src/horizon_tracker/domain/report.py` | `planned_at` in `RunReport`, the notification text with the planned and the actual time |
| `src/horizon_tracker/application/windowed_run.py` | the wait for the moment before the first attempt |
| `src/horizon_tracker/application/probe.py` | the dry run and the probe name the moments of the day |
| `src/horizon_tracker/infrastructure/config.py` | new variables, the old windows removed |
| `src/horizon_tracker/cli.py` | wiring, `--force` without the wait |
| `deploy/horizon-*.timer`, `deploy/horizon-*.service`, `.github/workflows/deploy.yml`, `deploy/RUNBOOK.md` | timers, timeout, the `.env` contract |
| `tests/**` | unit tests of the draw (bounds, determinism, clipping), BDD for the 7 PRD scenarios, the unit-file and workflow tests |
| `docs/**` | SPEC `schedule`, `windowed-run`, `probe`, `settings`, `cli.md`, `architecture.md` |

### API Changes

| Variable | Default value in the deploy |
|------------|-------------------------------|
| `HT_CHECKIN_RANGE` | `07:30-08:10` |
| `HT_CHECKOUT_RANGE` | `16:30-17:10` |
| `HT_SESSION_LENGTH_MINUTES` | `540` (9 h) |
| `HT_SESSION_EXTRA_MAX_MINUTES` | `10` |
| `HT_WINDOW_GRACE_MINUTES` | `5` |
| `HT_JITTER_SEED` | not set → the seed comes from `HORIZON_USERNAME` |

Removed: `HT_CHECKIN_WINDOW`, `HT_CHECKOUT_WINDOW`. `Settings.from_env` rejects their
presence with a hint at the new names, so that an outdated `.env` does not pass silently.

## Alternatives Considered

### Option A: `RandomizedDelaySec` in the systemd timers
The randomness is independent in the two timers, the evening does not know the morning, the day length floats ±50 min.
Rejected.

### Option B: the morning run writes a "check-out moment" file, the evening run reads it
Shared state on disk: a lost file or a reboot breaks the pair. Rejected in favour of
a deterministic function of the date.

### Option C: one timer per day, the process lives all day
One process for 10 hours for the sake of two actions; a process crash during the day loses the evening. Rejected.

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Chrome starts on adapter construction and hangs for 40 minutes | Med | Low | check that `_launch` is lazy; a test "the browser is not started before `login()`" |
| A reboot of the VPS during the wait | Low | Med | `Persistent=no` as now: the run is skipped with a notification; a restart the same day by hand with `--force` |
| A change of `HORIZON_USERNAME` changes the draw | Low | Low | `HT_JITTER_SEED` sets the seed explicitly |
| An outdated `.env` after the rollout | Low | High | `Settings` rejects the old names; deploy.yml and the workflow test are updated in one work item |
| A `TimeoutStartSec` of 60 min hides a hung Chrome longer than before | Low | Low | the wait happens before the browser starts; the timeout of the adapter's own steps does not change |

## Open Questions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Day length 9 h + 0–10 min | Decided (the owner, 2026-10-20): per the PRD examples |
| Q2 | Should `probe` print the moments of the day | Decided: yes, a fifth line `schedule:`; cheap and helps verification |
| Q3 | Seconds in the moments | Decided: minute precision, seconds 00; a spread in minutes is enough |
