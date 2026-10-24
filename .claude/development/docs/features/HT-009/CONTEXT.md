# CONTEXT: HT-009 — Check-in success screenshot after the hold

> **Status:** Approved
> **Created:** 2026-10-22
> **Last updated:** 2026-10-24

---

## Goal

A successful check-in's Telegram photo is taken after the hold, while Blast is still open,
so the owner sees a drawn desktop rather than a black early frame; ship as PATCH `1.0.1`.

## Key Constraints

- Design A: `open_desktop -> None`; `capture_open_desktop() -> Path | None` after hold.
- Screenshot allowlist and soft-fail (`None` + log) unchanged; check-out / notifier / env unchanged.
- One PR: fix + `1.0.1` surface; live VPS check only after the release deploy.
- Layer boundaries and standards — project layer of CLAUDE.md; TDD; BDD for PRD scenarios.

## Code Standards

### Language and Environment
- Python 3.12, uv, Playwright over system Chrome

### Methodologies

| Methodology | Application |
|-------------|-------------|
| TDD | Red -> Green -> Refactor |
| Clean Code | SRP, DRY, KISS |
| Architecture | DDD packages: cli → infrastructure → application → domain |

### Testing
- **Framework:** pytest + pytest-cov + pytest-bdd
- **Coverage:** minimum 80% (project holds higher; do not regress)

### Code Quality
- **Linter/type-checker:** ruff (lint + format), mypy --strict

### Restrictions
- No unjustified `# type: ignore` / `Any`
- No `print` / `breakpoint` — use logging
- No bare `except:`
- Password never in logs or screenshots (allowlist already enforces)

## Architectural Decisions

| Date | Decision | Reason |
|------|----------|--------|
| 2026-10-22 | Split open and capture on the port; checkin orders hold then capture | early photo was the live black-screen cause; Design A owner-approved |
| 2026-10-22 | Method name `capture_open_desktop` | RFC Q1 |
| 2026-10-22 | After the hold, save the first non-blank element screenshot of the remote surface, bound 60 s; a blank timeout returns `None` | a fixed settle cannot tell a black frame from a painted desktop; the whole page is the wrong sample |
| 2026-10-22 | Full feature flow (three kept axes) | bug/BRIEF cannot hold >1 node |
| 2026-10-22 | Capture after hold, before disconnect; attach the path only on SUCCEEDED | success is known only after disconnect, so the photo cannot wait for it |
| 2026-10-22 | `opened_at` is when `open_desktop` returns, not when the photo is taken | otherwise «Время» shifts by `HT_HOLD_SECONDS` (default 120); only the old 2 s settle leaves that instant |
| 2026-10-22 | One PR for fix + `1.0.1`; live after deploy | owner; PATCH, no public-surface change |
| 2026-10-22 | Tech-writer edits `docs/` only; the version bump is the landing of the same PR | the role does not own `pyproject.toml`, the lock, or `CHANGELOG.md` |
| 2026-10-24 | Known trade-off, left to the owner (independent review of `v1.0.1`, Minor-6): the capture runs in every attempt that reaches the hold, including one the broker will not confirm, and spends up to `desktop_paint_ms` (60 s) of the window before the retry | the confirmation needs the disconnect, which ends the Blast connection the photo is taken over, so the capture cannot wait for it. Skipping the capture on an attempt already unconfirmed would mean reading the session state before the capture, an application-layer change; HT-010 kept `application/` untouched. Taking it costs at most 60 s of the window per unconfirmed attempt, and changing it is the owner's call |
| 2026-10-24 | HT-010 restored the RFC's "the same composited pixels Telegram would get, not a WebGL readback" (Approach, step 2) after briefly reversing it: the verdict judges the element screenshot, decoded in the page, and the frame judged is the frame saved | HT-010 BEAD-02 read the live surface with `drawImage`; its review (`ht-igr`, Major-1) measured a 1920×1080 WebGL canvas without `preserveDrawingBuffer` reading 0 of 1024 lit cells that way and 1024 through its element screenshot (Chrome 155 and Chromium 156, headless). The owner receives the composited screenshot, and nothing records how the 2312.1 client draws, so only that screenshot can decide whether the photo is blank. Decoding it in the page keeps the PNG codec out of the adapter |

## Related Files

(discover via `beadloom ctx <ref-id>` — never hardcode): `ports`, `morning-checkin`,
`horizon-playwright-client`.

## Current Phase

- **Phase:** Completed (released as `v1.0.1` on 2026-10-22; the live check-in photo of
  2026-10-24 is painted)
- **Current bead:** none — every bead and the epic `ht-qq2` are closed
- **Blockers:** none. The capture's follow-ups are HT-010 (`ht-m13`)
