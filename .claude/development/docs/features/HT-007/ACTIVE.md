# ACTIVE: HT-007 — i18n

> **Last updated:** 2026-10-21
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-05 (ht-zyh) tech-writer
**Goal:** the SPECs of messages / run-report / settings, cli.md and the graph node describe the catalogue and the language as they are
**Done when:** `sync-check` is clean, `docs audit` is clean

## Progress

- [x] The documents are approved by the owner's standing decision (2026-10-20); the beads are created, parent ht-7a0
- [x] BEAD-01 … BEAD-03 (2026-10-21)
- [x] BEAD-04 (2026-10-21)
- [x] fix ht-7a0.1 (2026-10-21)
- [ ] BEAD-05 → BEAD-06

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-7kx, 9070895: `domain/messages.py` (`Language`, 75 keys en/ru, `text`, `missing_translations`), `render(report, language)`; 282 tests, 1058 passed / 4 skipped, coverage 99 %, mutations 301/303 (99.3 %; the survivors — `schedule._pick`), 13 sabotages bite; a temporary constant `_LANGUAGE = RU` in the notifier until BEAD-02 |
| BEAD-02 | Done | ht-1yu, 87b2809: `Settings.language` from `HT_LANGUAGE` (en by default, ru; anything else refused at start-up), `TelegramNotifier(..., language)`, `build_notifier`; probe/dry-run/configuration errors through `Message` and the catalogue (77 keys); a configuration error — the log in English + an echo in the reader's language to stderr; 57 tests, 1115 passed / 4 skipped, coverage 99 %, mutations 308/310, 20 sabotages bite; the deployment reads `vars.HT_LANGUAGE` |
| BEAD-03 | Done | ht-bsc, e7aff90: the 4 PRD scenarios + 7 edge cases = 17 tests through `HT_LANGUAGE` → Settings → `build_notifier`; no stubs left in the suite; 1132 passed / 0 skipped, coverage 99 %; 16 sabotages bite |
| fix | Done | ht-7a0.1, be6754b: `ScheduleError(reason: Message)` for the five refusals reachable from the settings; `Message.in_language` renders nested messages; the catalogue at 83 keys; `Check.label`/`status_label` are built at creation; `Message.fields` read-only; 1214 passed, coverage 99 %, mutations 370/372, 14 sabotages bite |
| BEAD-04 | Done | ht-m1h: OK — 0 critical, 0 major, 2 minor, 4 nit; minor 1 (mixed languages in domain refusals) + nits 4, 5 → ht-7a0.1; minor 2 (the reason for excluding the catalogue from mutations) recorded in flow.yml; nit 3 — a documented decision; nit 6 closed |
| BEAD-05 | Open | — |
| BEAD-06 | Open | — |

## Notes

- The four PRD scenarios need to be put into the suite as SKIP stubs until BEAD-03 (as with HT-003/HT-004), otherwise `scenario-coverage` keeps the gate red.
- BEAD-02 changes the plan of the live check (BEAD-06): the deployment rewrites `/opt/horizon-tracker/.env` on every roll-out, so `HT_LANGUAGE=ru` is set not by hand in .env but as a variable of the `horizon-vps` environment: `gh variable set HT_LANGUAGE --env horizon-vps --body ru`; the workflow reads `vars.HT_LANGUAGE`.
