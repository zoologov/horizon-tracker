# CONTEXT: HT-004 — Screenshot in the notification of a successful check-in and check-out

> **Status:** Approved
> **Created:** 2026-10-20
> **Last updated:** 2026-10-20

---

## Goal

A successful check-in and check-out report with a photo and a caption: the opened desktop in the morning, the desktop list
without a session in the evening; a screenshot failure does not break the run.

## Key Constraints

- A screenshot only outside `#/home`; one `RunReport.screenshot` field for success and failure.
- A screenshot failure → `None` + a log line by error type; the outcome of the run does not change.
- Layer boundaries and standards — as in the project layer of CLAUDE.md; TDD, BDD over the three scenarios.
- Starts after HT-003 and HT-005 have landed, so as not to share the adapter and test files.

## Code Standards

See CONTEXT HT-001/HT-003: Python 3.12, uv, ruff, mypy strict, pytest + pytest-bdd, coverage
≥ 80 %, domain mutations (ports are out of the mutmut scope by convention).

## Architectural Decisions

| Date | Decision | Reason |
|------|----------|--------|
| 2026-10-20 | The port returns the screenshot path, the adapter takes it, the use case puts it into the report | the adapter does not know the notifier; the report already carries `screenshot` |
| 2026-10-20 | A screenshot failure does not affect the outcome | the photo is proof, not a condition of success |
| 2026-10-20 | The documents are approved by the owner's standing decision («carry the tasks on yourself», 2026-10-20) | so as not to wait for gates on every small piece of work |

## Related Files

(discover via `beadloom ctx <ref-id>` — never hardcode): `ports`, `horizon-playwright-client`,
`morning-checkin`, `evening-checkout`.

## Current Phase

- **Phase:** Planning
- **Current bead:** —
- **Blockers:** the landing of HT-003 (ht-slm) and HT-005 (ht-5ni)
