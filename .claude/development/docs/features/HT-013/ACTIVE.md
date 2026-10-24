# ACTIVE: HT-013 — The landscape: every external contract declared in the graph

> **Last updated:** 2026-10-24 (all waves landed; PR pending)
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-01 (ht-azz) — dev: `landscape.yml`, the external SPECs, the portal built once to a scratch directory
**Goal:** the portal's Landscape map shows the service's external bindings as contracts with both ends
**Done when:** a local `beadloom docs site` build writes a `landscape.data.json` listing the ten contracts with `verdict: confirmed`; `beadloom ci` rc 0

## Progress

- [x] BRIEF written from the Beadloom docs and source (landscape = local `produces`/`consumes` edges with `contract` payloads, reconciled like the federation gate); the owner approved the item on 2026-10-24 ("Отлично, работаем!")
- [x] Explore (2026-10-24): four runs, all seed none; the loader and generator facts recorded in the BRIEF (src is the endpoint, both ends per contract, edge lifecycle active, source: on every node, the service-needs-parent exclude, ten keys not nine)
- [x] Beads created as one plan: parent ht-lsb; ht-azz (dev) → ht-y3f (review) → ht-2q0 (tech-writer)
- [x] Wave 1: BEAD-01 dev — `landscape.yml` (6 external nodes, 20 contract edges), the `service-needs-parent` exclude, 6 SPECs under `docs/domains/external/`; the portal built to a scratch directory lists 10 contracts, all `confirmed`
- [x] Wave 2: BEAD-02 review (ht-y3f) → OK
- [x] Wave 3: BEAD-03 tech-writer (ht-2q0, be91843) — architecture.md "Landscape", README, releasing.md, one "External contract" bullet per consumer doc; ci rc 0
- [x] Wave 4: BEAD-04 fix (ht-lsb.1, e8c8d0c) — the probe's edges dropped (participants 12 → 11, 20 contract edges), the SPEC wordings, the semicolons; ci rc 0
- [x] Gate green on e8c8d0c
- [ ] PR features/HT-013 → main; CI; the coordinator merges (the map is published by the v1.1.0 release)

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | 27 nodes (+6), 105 edges (+22); lint --strict, doctor, sync-check and `beadloom ci` rc 0; `landscape.data.json`: 10 contracts confirmed, 12 participants; detail in the bead's comments |
| BEAD-02 | Done | ht-y3f: OK — 0 critical, 0 major, 4 minor, 3 nitpick. Minor-3 (the six external nodes absent from the Axes rows → `outside-the-declared-axes` ×6, `route-not-supported` ×1) taken by the coordinator in the BRIEF; Minor-1 (telegram SPEC: a network error has no `description`), Minor-2 (the probe's two edges on `http:horizon-client-bundle` while the calendar contract sits on the adapter only), Minor-4 (semicolons joining clauses in the six SPECs), nitpick-5 (the dry run also asks the calendar) → fix bead BEAD-04; nitpick-6 (HT-010 ACTIVE housekeeping inside the HT-013 commit) and nitpick-7 (no `external/README.md`, left to the layout) recorded |
| BEAD-03 | Done | ht-2q0, be91843 |
| BEAD-04 | Done | ht-lsb.1, e8c8d0c |

## Notes

- Branch `features/HT-013`, one PR to `main`. HT-012 follows on `main` after this merge.
- Beadloom compares a contract surface only for `amqp` and `graphql`; every other protocol is a plain dependency with a presence verdict. The surfaces are therefore written in the external nodes' SPECs, in words.
