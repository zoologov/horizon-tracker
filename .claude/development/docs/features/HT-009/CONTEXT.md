# CONTEXT: HT-009 — Check-in success screenshot after the hold

> **Status:** Approved
> **Created:** 2026-10-22
> **Last updated:** 2026-10-22

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

## Related Files

(discover via `beadloom ctx <ref-id>` — never hardcode): `ports`, `morning-checkin`,
`horizon-playwright-client`.

## Current Phase

- **Phase:** Development
- **Current bead:** BEAD-01 (ht-22u)
- **Blockers:** none
