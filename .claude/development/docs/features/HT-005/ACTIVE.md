# ACTIVE: HT-005 — GitHub Actions by best practice

> **Last updated:** 2026-10-20
> **Phase:** Development

---

## Current Bead

**Bead:** PR #3 → main (the owner merges); then BEAD-03 (ht-hdv) branch protection
**Goal:** CI green on the PR, `ci-ok` as the required check
**Done when:** the PR is merged, the protection of main is measured (or the 403 recorded)

## Progress

- [x] BEAD-01 (ht-5ni, 7992e96): stages, ci-ok, pins, Dependabot, mutation.yml, preflight/summary; 150 contract tests
- [x] BEAD-02 (ht-kc1): OK, 4 minor, 3 nit
- [x] BEAD-04 (ht-s7q.1, 88c9d3d) fix
- [ ] PR → main
- [ ] BEAD-03 (ht-hdv) branch protection — the owner/the local agent

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-5ni, 7992e96; pins checkout v7.0.1, setup-uv v10.3.0, cache v6.1.0, upload-artifact v7.0.2; mutation per change 198/243 → 99.0 %, sample 60 → 98.3 % |
| BEAD-02 | Done | ht-kc1: OK (0 major, 4 minor, 3 nit) |
| BEAD-03 | Open | ht-hdv: after the merge |
| BEAD-04 | Done | ht-s7q.1, 88c9d3d: both review sabotages are now caught (3 and 5 tests go red); `coverage report --fail-under=0` for the summary line; mypy on `tests` and `.github/scripts`; `persist-credentials: false`; +17 deploy tests |

## Notes

- Gates on HEAD b2b3c23 in a clean room: ruff/format/mypy clean, 758 passed, 7 skipped, coverage 99 %, `beadloom ci` rc 0.
- The coordinator closed one mypy error in the adapter tests that the new job `types` found (c418c42).
