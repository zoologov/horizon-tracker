# ACTIVE: HT-005 — GitHub Actions by best practice

> **Last updated:** 2026-10-20
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-04 (ht-s7q.1) — fix after the review; then the PR
**Goal:** the four minors of the ht-kc1 review are closed
**Done when:** the mutation.sh verdict test bites, the adapter passes lint, the coverage line is present even when the threshold fails

## Progress

- [x] BEAD-01 (ht-5ni, 7992e96): stages, ci-ok, pins, Dependabot, mutation.yml, preflight/summary; 150 contract tests
- [x] BEAD-02 (ht-kc1): OK, 4 minor, 3 nit
- [ ] BEAD-04 (ht-s7q.1) fix
- [ ] PR → main
- [ ] BEAD-03 (ht-hdv) branch protection — the owner/the local agent

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-5ni, 7992e96; pins checkout v7.0.1, setup-uv v10.3.0, cache v6.1.0, upload-artifact v7.0.2; mutation per change 198/243 → 99.0 %, sample 60 → 98.3 % |
| BEAD-02 | Done | ht-kc1: OK (0 major, 4 minor, 3 nit) |
| BEAD-03 | Open | ht-hdv: after the merge |
| BEAD-04 | Open | ht-s7q.1: fix after the review |

## Notes

- The coordinator closed one mypy error in the adapter tests that the new job `types` found (c418c42).
