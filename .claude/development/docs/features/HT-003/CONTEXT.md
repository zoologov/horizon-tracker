# CONTEXT: HT-003 — Random check-in and check-out moments inside ranges

> **Status:** Approved
> **Created:** 2026-10-20
> **Last updated:** 2026-10-20

---

## Goal

Every working day the check-in happens at a random minute from 07:30–08:10 (configured time zone), the check-out —
9 hours plus 0–10 minutes later, no later than 17:10; both moments are computed from the date deterministically,
the timers fire at the start of the ranges, the service waits for its moment inside the process.

## Key Constraints

- The draw is a pure domain function of `(date, seed, parameters)` on `hmac-sha256`; no
  system `random`; minute precision.
- Waiting only through the `Clock.sleep` port; the browser is not started before the moment (the lazy
  `_launch` in the adapter is pinned by a test).
- The behaviour after the moment (check-in, holding, disconnect, log off, retries in the 5-minute window,
  one notification) does not change: HT-001 and HT-002 remain in force.
- `--force` starts immediately, without the wait and the ranges.
- The `.env` contract changes in one work item as a whole: `Settings`, `deploy.yml`, RUNBOOK,
  cli.md and the workflow test; `Settings` rejects the old `HT_*_WINDOW` with a hint.
- Layer direction and cohesion-driven — as in the project layer of CLAUDE.md; TDD, BDD for the seven
  PRD scenarios, the mutation gate of the core on `domain/` (score ≥ 85 %).
- The live portal only from the VPS; the owner watches the first run of the new timers in Telegram.

## Code Standards

### Language and Environment
- Python 3.12, `uv`, the same dependencies as in HT-001; no new packages required (`hmac`,
  `hashlib`, `datetime` from the standard library).

### Methodologies

| Methodology | Application |
|-------------|-------------|
| TDD | tests of the draw's bounds (07:30, 08:10, clipping to 17:10, determinism, different days) before the code |
| Clean Code | `draw_moments` — one function with named parameters, no global time constants |
| Architecture | the draw in `domain/schedule.py`, the wait in `application/windowed_run.py`, the variables in `infrastructure/config.py`, the wiring in `cli.py` |
| Cohesion-driven | `schedule` remains the "window and decision" node; the draw is a part of it, not a new module, while there is one function |
| BDD acceptance | the 7 scenarios of PRD HT-003 in `tests/acceptance/features/`, on fake clock and calendar |
| Mutation | `mutmut` on `domain/`, the number of mutants named, the equivalent ones listed |

### Testing
- **Framework:** pytest, pytest-bdd; a fake `Clock` with virtual time, `sleep` advances it.
- **Coverage:** ≥ 80 % over `src/`, not below the current 98 %.
- **Whether the tests bite:** every new test goes red under sabotage; the number collected and passed
  is named in the bead comment.

### Code Quality
- `uv run ruff check src/ tests/`, `uv run mypy src/`; the Gate on a clean index
  `rm -f .beadloom/beadloom.db && beadloom reindex && beadloom ci`.

### Restrictions
- No unjustified escape hatch from the type system
- No stray debug output — use the language's logging facility
- No catch-all exception handler — name the exception
- The password, the token, the seed (`HT_JITTER_SEED`) do not reach the log or `repr`.
- No `time.sleep` outside the clock adapter.

## Architectural Decisions

| Date | Decision | Reason |
|------|----------|--------|
| 2026-10-20 | The draw is deterministic from the date and the seed (`hmac-sha256`), no state between runs | morning and evening agree after a reboot and a loss of files |
| 2026-10-20 | Check-out = check-in + 9 h + 0–10 min clipped to 17:10 | the owner's examples; the day is never shorter |
| 2026-10-20 | The wait inside the process, the timers at the start of the ranges | `RandomizedDelaySec` would not tie the morning to the evening; one process per day is fragile |
| 2026-10-20 | The default seed is `HORIZON_USERNAME`, an explicit `HT_JITTER_SEED` is optional | stable between deploys; no more secret than the account itself |
| 2026-10-20 | The old `HT_*_WINDOW` are rejected by `Settings` with a hint | an outdated `.env` after the rollout must not silently work "as before" |
| 2026-10-20 | `probe` prints `schedule: today HH:MM / HH:MM` | a cheap verification of the draw on the VPS without a check-in |
| 2026-10-20 | `--force` is a run flag `run(force=True)`, the moment of the day is kept, there is no wait (BEAD-04) | "moment = now" would fail before midnight: `window_from` rejects a window that crosses midnight |

## Related Files

(discover via `beadloom ctx <ref-id>` — never hardcode)

- `beadloom ctx schedule` / `windowed-run` / `probe` / `settings` / `cli` / `horizon-tracker`
- PRD, RFC, PLAN, ACTIVE in `.claude/development/docs/features/HT-003/`

## Current Phase

- **Phase:** Development (wave 5: documentation)
- **Current bead:** BEAD-08 (ht-6l0)
- **Blockers:** —
- **Deferred from review (minor):** the pair of optional `moment`/`range_start` in `WindowedRun` (fold into one value object) and the `schedule` special case in `_probe_line` (carry the moments on `ProbeReport`) — they do not change behaviour, to be filed as a separate work item at the next touch of these modules
