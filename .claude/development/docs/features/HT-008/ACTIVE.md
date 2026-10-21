# ACTIVE: HT-008 — Release flow on tags, one workflow per event, a protected trunk, the portal on Pages, and the repository's public face

> **Last updated:** 2026-10-21 (wave 1 landed)
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-03 (ht-w52) — wave 2, tech-writer
**Goal:** `docs/guides/releasing.md`, deployment guide 6.3/6.4 and cross-references (4.1 still says a merge deploys), README Development/Deployment consistency, the project layer's "Git" section (trunk-based development as GitHub holds it; the measurement date left for BEAD-05), `.claude/CLAUDE.md` regenerated, the `flow.yml` comment about `mutation.yml` corrected
**Done when:** no dangling link to the guide; `beadloom ci` green on the tree

## Progress

- [x] BRIEF approved by the owner (2026-10-21)
- [x] Beads created: parent ht-6hx; ht-qdg, ht-cix, ht-w52, ht-2gj, ht-30c
- [x] Wave 1: BEAD-01 + BEAD-02 landed (d68369d, aeb415f); gate green on the tree (gate owner ht-qdg)
- [ ] Wave 2: BEAD-03 (docs, project layer)
- [ ] Wave 3: BEAD-04 (review)
- [ ] Owner: BEAD-05 (public, Pages, protection, merge, v1.0.0)

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | d68369d: release.yml (verify, gate, deploy, publish, portal), ci.yml + mutation-per-change + dispatch, mutation.yml sample only, deploy.yml removed, version 1.0.0 from pyproject only, site: block; 17 files; tests 1290 passed (4 known macOS failures) |
| BEAD-02 | Done | aeb415f: LICENSE, CHANGELOG [1.0.0], CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, PR template, issue forms, README (badges, Requirements, Getting started, Releases, License); links to docs/guides/releasing.md dangle until BEAD-03 |
| BEAD-03 | Open | - |
| BEAD-04 | Open | - |
| BEAD-05 | Open | - |

## Notes

- Branch `features/HT-008`, one PR to `main`.
- Owner's rulings of 2026-10-21: the repository becomes public; the portal follows releases, not pushes to `main`; branch protection with `--check ci-ok` and a `v*` tag ruleset; the first release is `1.0.0` (the service is in production).
- `beadloom setup-branch-protection` must be run with `--check ci-ok` (its defaults are Beadloom's own job names — UX-Issues #14).
- The HT-005 bead `ht-hdv` is closed by BEAD-05.
