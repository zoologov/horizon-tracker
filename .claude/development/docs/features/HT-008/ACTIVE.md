# ACTIVE: HT-008 — Release flow on tags, one workflow per event, a protected trunk, the portal on Pages, and the repository's public face

> **Last updated:** 2026-10-21 (re-review: ISSUES on docs; docs fix running)
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-08 (ht-6hx.1) — docs after the fix, tech-writer
**Goal:** deployment guide 6.3 and 7, README Releases and the releasing guide describe `verify`'s lock check and the main-only manual run; the dispatch "Why" names what `verify` does not stop
**Done when:** `beadloom ci` green; then BEAD-07 re-review runs again

## Progress

- [x] BRIEF approved by the owner (2026-10-21)
- [x] Beads created: parent ht-6hx; ht-qdg, ht-cix, ht-w52, ht-2gj, ht-30c
- [x] Wave 1: BEAD-01 + BEAD-02 landed (3fabae9, f786296 — ids after the authorship rewrite of 2026-10-21; before it: d68369d, aeb415f); gate green on the tree (gate owner ht-qdg)
- [x] Wave 2: BEAD-03 landed (c68f839)
- [x] Wave 3: BEAD-04 review → ISSUES (0 critical, 1 major, 6 minor) — verdict in `bd comments ht-2gj`
- [x] Fix wave: BEAD-06 landed (4413a32)
- [x] BEAD-07 re-review, first pass → ISSUES (1 major: stale docs; 2 minor) — verdict in `bd comments ht-1dd`
- [ ] BEAD-08 docs fix (ht-6hx.1) → BEAD-07 re-review, second pass
- [ ] Owner: BEAD-05 (public, Pages, protection, merge, v1.0.0)

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | 3fabae9: release.yml (verify, gate, deploy, publish, portal), ci.yml + mutation-per-change + dispatch, mutation.yml sample only, deploy.yml removed, version 1.0.0 from pyproject only, site: block; 17 files; tests 1290 passed (4 known macOS failures) |
| BEAD-02 | Done | f786296: LICENSE, CHANGELOG [1.0.0], CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, PR template, issue forms, README (badges, Requirements, Getting started, Releases, License); links to docs/guides/releasing.md dangle until BEAD-03 |
| BEAD-03 | Done | c68f839 |
| BEAD-04 | Done | ISSUES: Major-1 uv.lock unchecked before the host's `--locked` sync; Minor-1 PR template gates narrower than CI; Minor-2 environment tag rules not named for the owner; Minor-3 dispatch from another branch; Minor-4 TODO in the releasing guide; Minor-5 acceptance criterion 4 not met as written; Minor-6 ACTIVE named pre-rewrite commit ids. Coordinator took Minor-2, -5, -6 (this file, BRIEF, ht-30c); the rest is BEAD-06 |
| BEAD-05 | Open | - |
| BEAD-06 | Done | 4413a32: CI `--locked`, verify checks uv.lock and refuses a manual run off main, PR template gates = CI, the TODO resolved; 10 contract tests |
| BEAD-07 | In Progress | first pass ISSUES: deployment.md 6.3/7 and README Releases stale on verify's new checks; releasing.md one-source bullet and dispatch Why; the Minor-4 wording reconciled by the coordinator (confirmed) |
| BEAD-08 | Open | docs after the fix (ht-6hx.1) |

## Notes

- Branch `features/HT-008`, one PR to `main`.
- Owner's rulings of 2026-10-21: the repository becomes public; the portal follows releases, not pushes to `main`; branch protection with `--check ci-ok` and a `v*` tag ruleset; the first release is `1.0.0` (the service is in production).
- `beadloom setup-branch-protection` must be run with `--check ci-ok` (its defaults are Beadloom's own job names — UX-Issues #14).
- The HT-005 bead `ht-hdv` is closed by BEAD-05.
- History: all commits were rewritten to the author `v.zoologov <zoologov@gmail.com>` on 2026-10-21 (owner's request); `main` was force-pushed with a lease. Commit ids older than 9186a33 changed; this file names the new ones.
- Owner's decision of 2026-10-21 (Minor-4, confirmed in chat): the text `horizon probe` / `--dry-run` print is not promised surface; their exit codes are. The releasing guide states it as the decision.
