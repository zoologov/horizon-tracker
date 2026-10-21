# ACTIVE: HT-007 — i18n

> **Last updated:** 2026-10-20
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-04 (ht-m1h) review
**Goal:** the verdict on BEAD-01..03 on the final tree
**Done when:** the verdict in the bead's comments; no major, or a fix bead is opened

## Progress

- [x] The documents are approved by the owner's standing decision (2026-10-20); the beads are created, parent ht-7a0
- [x] BEAD-01 … BEAD-03 (2026-10-21)
- [ ] BEAD-04 → BEAD-04 → BEAD-05 → BEAD-06

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-7kx, 9070895: `domain/messages.py` (`Language`, 75 keys en/ru, `text`, `missing_translations`), `render(report, language)`; 282 tests, 1058 passed / 4 skipped, coverage 99 %, mutations 301/303 (99.3 %; the survivors — `schedule._pick`), 13 sabotages bite; a temporary constant `_LANGUAGE = RU` in the notifier until BEAD-02 |
| BEAD-02 | Done | ht-1yu, 87b2809: `Settings.language` from `HT_LANGUAGE` (en by default, ru; anything else refused at start-up), `TelegramNotifier(..., language)`, `build_notifier`; probe/dry-run/configuration errors through `Message` and the catalogue (77 keys); a configuration error — the log in English + an echo in the reader's language to stderr; 57 tests, 1115 passed / 4 skipped, coverage 99 %, mutations 308/310, 20 sabotages bite; the deployment reads `vars.HT_LANGUAGE` |
| BEAD-03 | Done | ht-bsc, e7aff90: the 4 PRD scenarios + 7 edge cases = 17 tests through `HT_LANGUAGE` → Settings → `build_notifier`; no stubs left in the suite; 1132 passed / 0 skipped, coverage 99 %; 16 sabotages bite |
| BEAD-04 | Open | — |
| BEAD-05 | Open | — |
| BEAD-06 | Open | — |

## Notes

- The four PRD scenarios need to be put into the suite as SKIP stubs until BEAD-03 (as with HT-003/HT-004), otherwise `scenario-coverage` keeps the gate red.
- BEAD-02 changes the plan of the live check (BEAD-06): the deployment rewrites `/opt/horizon-tracker/.env` on every roll-out, so `HT_LANGUAGE=ru` is set not by hand in .env but as a variable of the `horizon-vps` environment: `gh variable set HT_LANGUAGE --env horizon-vps --body ru`; the workflow reads `vars.HT_LANGUAGE`.
