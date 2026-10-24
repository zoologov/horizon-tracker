# BRIEF: HT-013 — The landscape: every external contract declared in the graph

> **Type:** chore
> **Status:** Approved
> **Created:** 2026-10-24

---

## Problem

The portal's "Landscape map" is empty: `landscape.data.json` carries no node, no edge and
no contract. `beadloom docs site` builds that map from the repository's own
`produces` / `consumes` edges and their `contract` payloads (reconciled by the same code
as the federation gate), and this graph declares none: every edge is `depends_on`
between the package's own nodes. So the portal shows the inside of the service and
nothing of what it is bound to outside: the Horizon portal and its broker, the
production calendar, the Telegram Bot API, the host's `.env` and units, the GitHub
Environment the deploy reads. Those bindings are where a change hurts and where
development needs the check.

## Solution

Declare the external systems as nodes and the bindings as contracts, in a new graph
file `.beadloom/_graph/landscape.yml`, with one SPEC per external node under
`docs/domains/external/` that states the surface in words (fields, status codes,
selectors) since Beadloom compares a surface only for `amqp` and `graphql` and shows the
rest as a plain dependency with a presence verdict (honest: the map says "undeclared"
where no surface is read, never a fabricated one).

Nodes (kind `service`, lifecycle `external` — the loader accepts `external`; the contract
EDGES stay `active`, because the Mermaid fallback paints an `external` edge grey while the JSON
says `confirmed`): `horizon-portal` (HTML Access web client + the broker),
`isdayoff` (the production calendar), `telegram-bot-api`, `owner-chat` (the owner's
Telegram chat, the reader of every notice and, after HT-012, the writer of commands),
`vps-host` (systemd, `.env`, the state and artifact directories), `github-environment`
(`horizon-vps`: the secrets and variables the deploy turns into `.env`).

Contracts, each a `produces` edge on the one side and a `consumes` edge on the other, so
the reconciler reads both ends and the verdict is `confirmed`:

| Contract (`protocol:name`) | Producer → consumer | What it binds |
|---|---|---|
| `http:horizon-client-bundle` | horizon-portal → probe, horizon-playwright-client | the unauthenticated bundle names the probe reads and the selectors the adapter takes from the 2312.1 markup |
| `http:horizon-broker-session` | horizon-portal → horizon-playwright-client | login, launch items, `kill-session` (status + the broker's confirmation the check-out waits for) |
| `blast:desktop-session` | horizon-portal → horizon-playwright-client | the websocket the check-in holds; its open/close is the disconnect |
| `http:isdayoff-day` | isdayoff → isdayoff-calendar | `GET /{YYYYMMDD}` → `0`/`1`, timeout, the `None` fallback |
| `http:telegram-sendMessage`, `http:telegram-sendPhoto` | telegram-bot-api → telegram-notifier | the two methods, the caption limit, the token in the URL |
| `notification:run-report` | telegram-notifier → owner-chat | the four-line text in `HT_LANGUAGE` (the surface the owner reads; HT-012 changes it) |
| `env:dot-env` | vps-host → settings | every variable of `.env` with its default and secrecy |
| `env:github-environment` | github-environment → vps-host | the secrets and variables the Release's deploy writes into `.env` |
| `systemd:units` | vps-host → cli | the timers and services, `TimeoutStartSec`, the user and the home |

After HT-012: `http:telegram-getUpdates` (telegram-bot-api → telegram-bot),
`command:bot-text` (owner-chat → bot-commands), `file:absences` (vps-host →
absence-store). HT-012's beads declare those; this item declares the ones that exist
today and the convention.

What Explore established about the loader and the generator (2026-10-24), binding for BEAD-01:

- An edge is `{src, dst, kind, lifecycle?, contract: {protocol, name}}`; the endpoint the
  reconciler reads is the edge's **`src`**: the producer side is `src: <producer>, kind:
  produces, dst: <consumer>`, the consumer side `src: <consumer>, kind: consumes, dst:
  <producer>`. Both must exist for `verdict: confirmed` (`verdict_basis: presence`).
- Only `amqp` and `graphql` go through the surface reconciler; the protocols here reach the
  file through the legacy path with `protocol: ""` and the key `<protocol>:<name>` kept.
  That is the honest rendering: a plain dependency with a presence verdict.
- `rules.yml`'s `service-needs-parent` requires a `part_of` edge to `horizon-tracker` from
  every `service` node and ignores lifecycle: the six external nodes go into that rule's
  `exclude` list with a reason (they are not part of the service), not under a fake
  `part_of`. `produces` / `consumes` are not valid `edge_kind` values for a rule matcher,
  so no rule is written over them.
- `reindex` picks the first node without a `source` as the root for the deep config. Every
  external node therefore declares `source:` pointing at its own SPEC file (an existing
  path, no warning), so no node is sourceless and the root stays `horizon-tracker`; BEAD-01
  checks `beadloom prime` / `status` before and after.
- `doctor` wants every node documented and none isolated: the SPEC and the contract edges
  cover both; BEAD-01 reads `doctor`'s answer rather than assuming.

Verification: `beadloom reindex`, `lint --strict`, `doctor`, `sync-check` clean;
`beadloom docs site --out <scratch>` writes a `landscape.data.json` whose contracts list is
the ten keys of the table above (the Telegram row holds two) with every verdict
`confirmed` and the six external nodes plus the six consuming nodes as participants.

## Axes

Derived, never authored. Four runs of `beadloom impact` (Explore, 2026-10-24), each with seed
`none` under rule `reaches-an-effect-sink`, so every axis is unresolved rather than empty; the
branches rows are collapsed to one per node. The external systems are not in the swept tree,
so no run names the nodes the contract edges point at: they are created here and listed
after the table.

> **Derived by:** `beadloom impact` over `src/horizon_tracker/infrastructure/isdayoff.py` (run 1), `.../telegram.py` (run 2), `.../config.py` (run 3), `.beadloom/_graph` (run 4)
> **Seed:** none in all four runs
> **Unresolved:** run 1: 2 name-defined-more-than-once, 1 no-seed, 1 unresolved-terminator-name; run 2: 2, 1, 4; run 3: 1 dynamic-dispatch, 3, 1, 7; run 4: 1 no-seed, 1 sweep-narrower-than-the-project (YAML only)

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved in all four runs | — | no | no code is written; the graph gains edges |
| branches | isdayoff-calendar | `is_working_day`, `__init__` (run 1) | none | yes | the consumer end of `http:isdayoff-day` |
| branches | telegram-notifier | `send`, `_call`, `_redact`, `filter`, … (run 2) | none | yes | the consumer end of `http:telegram-sendMessage` / `sendPhoto`; the producer end of `notification:run-report` |
| branches | settings | `from_env`, `_required`, `_optional`, … (run 3) | none | yes | the consumer end of `env:dot-env` |
| callers | probe | `src/horizon_tracker/application/probe.py:116` (run 1) | none | yes | the consumer end of `http:horizon-client-bundle` (and of `http:isdayoff-day` through the calendar port — declared on the adapter, not twice) |
| callers | cli | `src/horizon_tracker/cli.py:212` (run 3) | none | yes | the consumer end of `systemd:units` (the entry point the units start) |
| — (authored) | horizon-playwright-client | the adapter (not a seed of these runs; HT-010's derivation covers it) | none | yes | the consumer end of the three Horizon contracts |
| callers | ports, schedule, windowed-run, messages | constructor arguments and the port protocols | none | no | the contracts bind adapters, not the ports or the use cases |
| callers | horizon-tracker | run 4: no site found, the graph directory holds YAML only; the root node is the one the graph describes | the whole directory | yes | the work site: `.beadloom/_graph/landscape.yml` and `rules.yml`'s exclude list |
| — (authored) | horizon-portal | created by this item: `docs/domains/external/horizon-portal/SPEC.md` and its edges in `landscape.yml` | the SPEC (no code) | yes | the producer end of the three Horizon contracts |
| — (authored) | isdayoff | created by this item: `docs/domains/external/isdayoff/SPEC.md` and its edges in `landscape.yml` | the SPEC (no code) | yes | the producer end of `http:isdayoff-day` |
| — (authored) | telegram-bot-api | created by this item: `docs/domains/external/telegram-bot-api/SPEC.md` and its edges in `landscape.yml` | the SPEC (no code) | yes | the producer end of `http:telegram-sendMessage` / `sendPhoto` |
| — (authored) | owner-chat | created by this item: `docs/domains/external/owner-chat/SPEC.md` and its edges in `landscape.yml` | the SPEC (no code) | yes | the consumer end of `notification:run-report` |
| — (authored) | vps-host | created by this item: `docs/domains/external/vps-host/SPEC.md` and its edges in `landscape.yml` | the SPEC (no code) | yes | the producer end of `env:dot-env` and `systemd:units`, the consumer end of `env:github-environment` |
| — (authored) | github-environment | created by this item: `docs/domains/external/github-environment/SPEC.md` and its edges in `landscape.yml` | the SPEC (no code) | yes | the producer end of `env:github-environment` |

The six external nodes above exist only once this item lands, so no derivation could list
them: their rows are authored and marked so. The route check reports that the simplified
route holds one node while the kept axes name more. That is recorded here as the crossing it
is: the item writes one graph file and its documents and changes no code node, so one BRIEF
carries it, as HT-008 carried its repository-wide chore; the nodes kept are the endpoints the
new edges name, not nodes whose code changes.

## Beads

Status lives in ACTIVE.md, reconciled from the tracker by the pre-commit active-sync, so this
table names the beads and carries no status. The Tracker cell holds `-` until the beads are
created, and then the id the tracker answered.

| ID | Tracker | Name | Priority |
|----|---------|------|----------|
| BEAD-01 | ht-azz | dev: `landscape.yml` (nodes + contract edges), the external SPECs, the portal built once to a scratch directory and its `landscape.data.json` checked | P2 |
| BEAD-02 | ht-y3f | review: every contract has both ends and a `confirmed` verdict; the surfaces in the SPECs match the code's actual calls (status codes, methods, variables); no secret value in any SPEC | P2 |
| BEAD-03 | ht-2q0 | tech-writer: `docs/architecture.md` and the README's "What it is made of" name the landscape and the external systems; the portal section of `releasing.md` names the map | P3 |
| BEAD-04 | ht-lsb.1 | fix after review ht-y3f: the probe's client-bundle edges dropped (the contract sits on the adapter, as the calendar's), the telegram and isdayoff SPEC wordings, the semicolons split | P2 |

## Acceptance Criteria

- [ ] `landscape.data.json` of a local `beadloom docs site` build lists the ten contracts with producers and consumers and `verdict: confirmed` — non-behavioural: a property of the generated portal
- [ ] `beadloom ci` rc 0 on the tree — non-behavioural: graph and documents only
- [ ] The portal at https://zoologov.github.io/horizon-tracker/landscape.html shows the map after the next release — non-behavioural: the observer is the portal

## Non-behavioural declaration

| Node | Reason it carries no behaviour |
|------|-------------------------------|
| horizon-tracker | the graph and the documents describe the service's bindings; no line of the service's code changes and no run on the host behaves differently |
