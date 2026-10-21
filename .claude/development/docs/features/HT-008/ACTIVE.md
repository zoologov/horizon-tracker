# ACTIVE: HT-008 — Release flow on tags, one workflow per event, a protected trunk, the portal on Pages, and the repository's public face

> **Last updated:** 2026-10-21
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-01 (ht-qdg) and BEAD-02 (ht-cix) — wave 1, in parallel
**Goal:** the three workflows (CI / Release with the portal / Mutation sample), the version from `pyproject.toml` alone at `1.0.0`, and the repository's public face
**Done when:** the contract tests in `tests/unit/deploy/` hold the new layout and pass; the community files, README badges and `[1.0.0]` changelog exist; the gates are green

## Progress

- [x] BRIEF approved by the owner (2026-10-21)
- [x] Beads created: parent ht-6hx; ht-qdg, ht-cix, ht-w52, ht-2gj, ht-30c
- [ ] Wave 1: BEAD-01 + BEAD-02
- [ ] Wave 2: BEAD-03 (docs, project layer)
- [ ] Wave 3: BEAD-04 (review)
- [ ] Owner: BEAD-05 (public, Pages, protection, merge, v1.0.0)

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Open | - |
| BEAD-02 | Open | - |
| BEAD-03 | Open | - |
| BEAD-04 | Open | - |
| BEAD-05 | Open | - |

## Notes

- Branch `features/HT-008`, one PR to `main`.
- Owner's rulings of 2026-10-21: the repository becomes public; the portal follows releases, not pushes to `main`; branch protection with `--check ci-ok` and a `v*` tag ruleset; the first release is `1.0.0` (the service is in production).
- `beadloom setup-branch-protection` must be run with `--check ci-ok` (its defaults are Beadloom's own job names — UX-Issues #14).
- The HT-005 bead `ht-hdv` is closed by BEAD-05.
