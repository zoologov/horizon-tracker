# RFC: HT-004 — Screenshot in the notification of a successful check-in and check-out

> **Status:** Done
> **Created:** 2026-10-20

---

## Overview

The `HorizonClient` port returns the path to the success screenshot from `open_desktop` and `log_off`
(`Path | None`); the adapter takes it through `ArtifactStore` after the desktop is drawn and after the
desktop list is reloaded; the use cases put the path into `RunReport.screenshot`, which the
notifier already sends as a photo with a caption. The failure report carries its screenshot as before.

## Motivation

### Problem
Success is confirmed by text only.

### Solution
Three points: the port returns the path, the adapter takes the screenshot, the use case puts it into the report. The notifier and
the report do not change.

## Technical Context

### Constraints
- A success screenshot is never taken on `#/home`; the adapter already holds an allowlist of routes.
- A screenshot failure (a Playwright error, the disk) is logged by its type and yields `None`; the run does not fail.
- `RunReport.screenshot` is one field for success and failure: the notifier already handles photos.
- No new dependencies.

### Affected Areas
The port in `domain/ports.py`, the adapter, `checkin.py`, `checkout.py`; the port fakes in the tests.

## Axes

Derived, never authored. Run `beadloom impact <path|symbol>`, paste its answer into the table,
then take the scope decision in the last two columns — the derivation says what a change ranges
over, a person says how much of it this work item takes. The `refs:` of every bead below is
generated from the rows kept in scope, so a bead naming a node this table does not is a finding.

Rule each row by the node's role in the change: the axis a node surfaced under is not its role.
The axis is the node's relation to the seed, so a `callers` row can be a work site — a node that
calls into the change can also own what the change must edit. `Owns unread` names the files the
node owns that the derivation could not read; a count there is a question to answer before `no`.

> **Derived by:** `beadloom impact src/horizon_tracker/domain/ports.py --section` (and over `application/checkin.py`) over `src/horizon_tracker`, 2026-10-20, role explore
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 13 name-defined-more-than-once, 1 no-seed, 4 unresolved-terminator-name; the Telegram notifier, the consumer of `report.screenshot`, is in no row — it does not change

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — no declared effect rule found a sink this target reaches, so there is no commit point to ask who else writes through | — | no | no row |
| callers | artifact-store | 2 — `src/horizon_tracker/infrastructure/artifacts.py:34` | none | no | implements `screenshot_path`, the contract does not change |
| callers | cli | 1 — `src/horizon_tracker/cli.py:227` | none | no | the assembly does not change |
| callers | evening-checkout | 1 — `src/horizon_tracker/application/checkout.py:62` | none | yes | puts the path from `log_off` into the report |
| callers | horizon-playwright-client | 4 — `src/horizon_tracker/infrastructure/horizon_playwright.py:392` | none | yes | takes the success screenshot and returns the path |
| callers | morning-checkin | 1 — `src/horizon_tracker/application/checkin.py:51` | none | yes | puts the path from `open_desktop` into the report |
| callers | probe | 3 — `src/horizon_tracker/application/probe.py:95` | none | no | does not touch the desktop |
| callers | settings | 1 — `src/horizon_tracker/infrastructure/config.py:73` | none | no | no settings are added |
| callers | system-clock | 2 — `src/horizon_tracker/infrastructure/clock.py:16` | none | no | not involved |
| callers | windowed-run | 6 — `src/horizon_tracker/application/windowed_run.py:124` | none | no | the report already carries `screenshot`; the loop does not change |
| branches | ports | `open_desktop`: 0 branch(es), 0 exit form(s), over every call | none | yes | the signature returns `Path \| None` |
| branches | ports | `log_off`: 0 branch(es), 0 exit form(s), over every call | none | yes | the same |
| branches | ports | the other methods (`login`, `desktop_status`, `disconnect`, `client_bundles`, `browser_version`, `is_working_day`, `send`, `now`, `sleep`, `screenshot_path`, `__init__`) | none | no | do not change |
| branches | morning-checkin | `_attempt`: 2 branch(es), 2 exit form(s), over every call, from a caller's seat | none | yes | receives the path and hands it to the report |
| branches | evening-checkout | `__call__`: 4 branch(es), 3 exit form(s), over every call, from a caller's seat | none | yes | the same |
| branches | horizon-playwright-client | `_screenshot`: 1 branch(es), 2 exit form(s), over every call, from a caller's seat | none | yes | the shared screenshot for success and failure |
| branches | probe / windowed-run / cli / artifact-store / system-clock / settings | the other rows of the derivation | none | no | call sites, the contract does not change |

## Proposed Solution

### Changes

| File / Module | Change |
|---------------|--------|
| `src/horizon_tracker/domain/ports.py` | `open_desktop(name) -> Path \| None`, `log_off(name) -> Path \| None`: the path to the success screenshot or `None` |
| `src/horizon_tracker/infrastructure/horizon_playwright.py` | after the desktop is drawn and after the list is reloaded — `_screenshot(kind)` through `ArtifactStore`; a failure → `None` and a log line by type |
| `src/horizon_tracker/application/checkin.py`, `checkout.py` | the path → `RunReport.screenshot` on `SUCCEEDED` |
| `tests/support/fakes.py`, the use case and adapter tests, BDD | the three PRD scenarios |
| `docs/domains/**/SPEC.md` of the ports, the adapter, the use cases | API |

### API Changes
Only the port signatures above. No environment variables.

## Alternatives Considered

### Option A: the adapter sends the photo to Telegram itself
Breaks the boundary: the desktop adapter does not know the notifier. Rejected.

### Option B: a separate `success_screenshot` field in the report
A second field for one meaning. Rejected.

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| The desktop screenshot is heavy for Telegram (`sendPhoto` up to 10 MB) | Low | Low | a 1280×720 PNG of the screen is hundreds of KB; when the API refuses, the notifier already falls back to text |
| A screenshot before the desktop is drawn — an empty frame | Low | Low | taken after the «desktop opened» signal and a 2 s hold |

## Open Questions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Approval of the documents | Decided: by the owner's standing decision of 2026-10-20 («carry the tasks on yourself») |
