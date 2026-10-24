# ACTIVE: HT-013 — The landscape: every external contract declared in the graph

> **Last updated:** 2026-10-24
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
- [x] Wave 1: BEAD-01 dev — `landscape.yml` (6 external nodes, 22 contract edges), the `service-needs-parent` exclude, 6 SPECs under `docs/domains/external/`; the portal built to a scratch directory lists 10 contracts, all `confirmed`
- [ ] Wave 2: BEAD-02 review
- [ ] Wave 3: BEAD-03 tech-writer
- [ ] Gate → PR features/HT-013 → main → merge (the coordinator merges; the map is published by the v1.1.0 release)

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | 27 nodes (+6), 105 edges (+22); lint --strict, doctor, sync-check and `beadloom ci` rc 0; `landscape.data.json`: 10 contracts confirmed, 12 participants; detail in the bead's comments |
| BEAD-02 | Open | — |
| BEAD-03 | Open | — |

## Notes

- Branch `features/HT-013`, one PR to `main`. HT-012 follows on `main` after this merge.
- Beadloom compares a contract surface only for `amqp` and `graphql`; every other protocol is a plain dependency with a presence verdict. The surfaces are therefore written in the external nodes' SPECs, in words.
