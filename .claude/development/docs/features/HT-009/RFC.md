# RFC: HT-009 — Check-in success screenshot after the hold

> **Status:** Approved
> **Created:** 2026-10-22

---

## Overview

Move the check-in's success screenshot out of `open_desktop` and onto a new
`HorizonClient` method called **after** `MorningCheckin` holds the desktop for
`HT_HOLD_SECONDS`. `open_desktop` only opens Blast; `capture_open_desktop()` photographs
`#/desktop` (or returns `None`). Check-out's `log_off` → path behaviour is unchanged.
Ship as PATCH `1.0.1` in the same pull request as the fix.

## Motivation

### Problem
HT-004 photographs inside `open_desktop` after canvas size + `success_settle_ms` (2 s),
before the hold that exists so Windows can log on. Live check-in photos are often black
while check-out launch-list photos are fine.

### Solution
Design A (owner-approved): split «open» and «photograph». The use case owns the order:
open → `opened_at` → hold → capture → status → disconnect. The adapter's route allowlist
and soft-fail screenshot policy stay.

## Technical Context

### Constraints
- Python 3.12, Playwright headless Chrome, no new dependencies.
- Success screenshots never on `#/home`; shared `_screenshot` allowlist unchanged.
- A capture failure → `None` + log by type; the run verdict does not change.
- `RunReport.screenshot` stays one field; the notifier is untouched.
- No new or renamed environment variables (PATCH public surface).

### Affected Areas
`domain/ports.py`, `application/checkin.py`, `infrastructure/horizon_playwright.py`,
test fakes and suites that assume `open_desktop` returns a photo; SPEC docs for those
nodes. Not: checkout, notifier, windowed-run loop, settings.

## Axes

Derived, never authored. Run `beadloom impact <path|symbol>`, paste its answer into the table,
then take the scope decision in the last two columns — the derivation says what a change ranges
over, a person says how much of it this work item takes. The `refs:` of every bead below is
generated from the rows kept in scope, so a bead naming a node this table does not is a finding.

Rule each row by the node's role in the change: the axis a node surfaced under is not its role.
The axis is the node's relation to the seed, so a `callers` row can be a work site — a node that
calls into the change can also own what the change must edit. `Owns unread` names the files the
node owns that the derivation could not read; a count there is a question to answer before `no`.

> **Derived by:** `beadloom impact src/horizon_tracker/domain/ports.py --section` over `src/horizon_tracker`, 2026-10-22, role explore (Design A; checkin-only impact omitted ports/adapter and was discarded as the seed)
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 13 name-defined-more-than-once, 1 no-seed, 4 unresolved-terminator-name (run of 2026-10-22)

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — no declared effect rule found a sink this target reaches, so there is no commit point to ask who else writes through | — | no | no row |
| callers | artifact-store | 2 — `src/horizon_tracker/infrastructure/artifacts.py:34` | none | no | `screenshot_path` unchanged |
| callers | cli | 1 — `src/horizon_tracker/cli.py:252` | none | no | assembly unchanged; release bump is the same PR, not this node's behaviour |
| callers | evening-checkout | 1 — `src/horizon_tracker/application/checkout.py:65` | none | no | still uses `log_off` → path; no capture call |
| callers | horizon-playwright-client | 4 — `src/horizon_tracker/infrastructure/horizon_playwright.py:402` | none | yes | stops success photo in `open_desktop`; implements `capture_open_desktop` |
| callers | morning-checkin | 1 — `src/horizon_tracker/application/checkin.py:53` | none | yes | calls capture after hold; puts path on the report |
| callers | probe | 3 — `src/horizon_tracker/application/probe.py:107` | none | no | no desktop open/capture |
| callers | schedule | 1 — `src/horizon_tracker/domain/schedule.py:48` | none | no | unrelated |
| callers | settings | 1 — `src/horizon_tracker/infrastructure/config.py:92` | none | no | no new settings |
| callers | system-clock | 2 — `src/horizon_tracker/infrastructure/clock.py:16` | none | no | hold already uses `sleep` |
| callers | windowed-run | 6 — `src/horizon_tracker/application/windowed_run.py:125` | none | no | still copies `AttemptResult.screenshot` |
| branches | ports | `open_desktop` | none | yes | return becomes `None` (void open); docstring |
| branches | ports | `capture_open_desktop` (new) | none | yes | `() -> Path \| None` |
| branches | ports | `log_off` and other methods | none | no | unchanged |
| branches | morning-checkin | `_attempt` | none | yes | order: open → hold → capture |
| branches | morning-checkin | `kind` / `run` / `steps` | none | no | steps text unchanged |
| branches | horizon-playwright-client | `open_desktop`, `capture_open_desktop`, `_screenshot` | none | yes | move the success photo onto capture; wait until the remote surface is non-blank |
| branches | evening-checkout / probe / windowed-run / cli / artifact-store / system-clock / settings / schedule | other derivation rows | none | no | not work sites for this change |

Kept nodes: **ports**, **morning-checkin**, **horizon-playwright-client** (full feature flow).

## Proposed Solution

### Approach

1. **Port.** `open_desktop(name) -> None` (raises on failure as today). New
   `capture_open_desktop() -> Path | None`: the first non-blank frame of the open remote
   surface, or `None` if none appears in time, the page left the allowlist, or the shot
   failed. A missing photo never fails the step.
2. **Adapter.** `open_desktop` cancels Fullscreen, waits for the canvas, logs Blast, returns
   without `_screenshot`. `capture_open_desktop` polls the remote surface until a frame is
   non-blank, then saves that frame. The surface is the largest `canvas` or `video` inside
   `#canvas-container`. Each sample is an element screenshot — the same composited pixels
   Telegram would get, not a WebGL readback and not the whole page (the Horizon chrome
   would look "ready" while the desktop is black). A 32×32 sample is non-blank when at
   least 8 pixels have `max(R, G, B) ≥ 24`. Poll every `poll_ms`, bound
   `HorizonTimeouts.desktop_paint_ms` (60 s). The passing PNG is the artifact. On timeout
   or a screenshot error, log `Horizon desktop still blank` or the existing failure line
   and return `None`. No new dependency. `success_settle_ms` is removed: a fixed 2 s pause
   is not a paint signal.
3. **Use case.** In `_attempt`:
   ```text
   login → open_desktop → opened_at = now
        → sleep(hold) → shot = capture_open_desktop()
        → while_open = desktop_status → disconnect → login → after
        → SUCCEEDED with screenshot=shot | FAILED without that photo
   ```
   Capture always runs after the hold and before `disconnect`, while Blast is still open.
   Success is known only after disconnect, so the photo cannot wait for the verdict.
   A failed confirmation does not put `shot` on the report (existing scenario: no photo
   of the opened desktop). `opened_at` stays the instant `open_desktop` returns — before
   the hold and before the paint poll. Moving it to the photo would shift the
   reported «Время» by `HT_HOLD_SECONDS` (default 120) plus up to `desktop_paint_ms`.
   Dropping the old settle from `open_desktop` moves that instant earlier by about 2 s.
4. **Fakes / tests.** Fake records call order so the new scenario can assert
   `open_desktop` → (clock advanced / hold) → `capture_open_desktop` → `disconnect`.
   The existing check-in time line stays the open moment, which fails if `opened_at`
   moves past the hold. Adapter integration tests: open returns no path; a black surface
   is not saved; a painted surface is saved.
5. **Docs / release.** Tech-writer updates SPECs under `docs/` for the three nodes.
   The version bump (`pyproject.toml`, `uv.lock`, `CHANGELOG.md`, the regenerated
   version line) is the same PR but not a tech-writer edit. Tag after merge; live
   check after deploy.

### Changes

| File / Module | Change |
|---------------|--------|
| `src/horizon_tracker/domain/ports.py` | `open_desktop -> None`; add `capture_open_desktop() -> Path \| None` |
| `src/horizon_tracker/infrastructure/horizon_playwright.py` | implement the split; drop success photo from `open_desktop` |
| `src/horizon_tracker/application/checkin.py` | capture after hold; report path from capture |
| `tests/support/fakes.py` and unit/acceptance/integration | signatures, order scenario, adapter cases |
| `tests/acceptance/features/screenshot_preview.feature` | new scenario for after-hold capture |
| `docs/domains/**` SPEC for ports, morning-checkin, horizon-playwright-client | API and order |
| `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `.claude/CLAUDE.md` via setup-agentic-flow | `1.0.1` release surface |

### API Changes

| Symbol | Before | After |
|--------|--------|-------|
| `HorizonClient.open_desktop` | `-> Path \| None` | `-> None` |
| `HorizonClient.capture_open_desktop` | — | `-> Path \| None` |
| `HorizonClient.log_off` | `-> Path \| None` | unchanged |

Internal Python ports only — not part of the SemVer public surface
(`docs/guides/releasing.md`). No CLI/env/deploy contract change → **PATCH**.

## Alternatives Considered

### Option B: `open_desktop(..., photograph_after=hold)` and drop the use-case sleep
Puts hold timing into the adapter; double-sleep risk if checkin still sleeps. Rejected
(owner chose Design A).

### Option C: Only lengthen `success_settle_ms` to match hold inside `open_desktop`
Couples a UI settle to Windows logon; checkin would still sleep again or lose a clear
`opened_at`. Rejected.

### Option D: Two PRs (fix then release)
Owner chose one PR for the PATCH.

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| The remote surface stays black for the whole paint bound (decoder never presents a frame) | Med | Med | Return `None` and send text; do not attach the black frame. Live check after `v1.0.1` shows whether 60 s is enough |
| A dark wallpaper has fewer than 8 lit samples | Low | Med | The bar is 8 of 1024; tune only if a live painted desktop fails it |
| Capture after disconnect by mistake | Low | High | Capture after hold and before `disconnect`; tests pin that order |
| `opened_at` taken at the photo, so «Время» jumps by the hold | Low | Med | Read `opened_at` when `open_desktop` returns; the existing time line pins it |
| Callers still expect `open_desktop` → path | Low | Med | Grep/fakes/suite update in the same wave; mypy --strict |

## Open Questions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Method name `capture_open_desktop` vs shorter `capture_desktop` | Decided: `capture_open_desktop` (pairs with open, not launch list) |
| Q2 | Keep `success_settle_ms` on capture after hold? | Superseded: the paint poll replaces it; the timeout is removed |
