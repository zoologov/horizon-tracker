# ACTIVE: HT-012 — Absences through the bot, and one notice for a skipped day

> **Last updated:** 2026-10-24
> **Phase:** Completed (released as v1.1.0; the owner's live check BEAD-14 is open)

---

## Current Bead

**Bead:** BEAD-14 (ht-pwp) — owner: the first absence entered through the bot on the host; the next skipped-day morning notice
**Goal:** the owner's live observation, recorded here from their report
**Done when:** `/add` is answered in the chat, `/list` shows it, and a skipped day produces one morning notice and a silent evening

## Progress

- [x] PRD approved by the owner (2026-10-24, "Утверждаю, всё"); RFC, CONTEXT, PLAN approved by the owner's standing decision ("Дальше веди сам") and reported at the control point
- [x] Beads created as one plan: epic ht-t28; 01 ht-162 → {02 ht-koc, 03 ht-4um, 04 ht-egg} → 05 ht-fzd, 06 ht-jc9, 08 ht-ekd → 07 ht-xad → 09 ht-3lc → 10 ht-h0l → 11 ht-3fz → 12 ht-mr9 → 13 ht-1t7 → 14 ht-pwp (owner)
- [x] Wave 1: BEAD-01 (ht-162): `absence.py`, 38 unit tests, 41 of 41 mutants killed; the ten PRD scenarios in the suite as SKIP stubs; node `absence` with its SPEC
- [x] Wave 2: BEAD-03 (ht-4um, 7c8303e) ∥ BEAD-04 (ht-egg, 0ade310, gate owner) — the serialisation on the edge ports → run-report overridden in flow.yml (disjoint files, until 2026-11-24); combined tree: 1476 passed + 4 known, ruff/format/mypy clean, `beadloom ci` rc 0
- [ ] Wave 3a: BEAD-06 (ht-jc9, gate owner) ∥ BEAD-08 (ht-ekd) — the shape `beadloom waves` gave; BEAD-02 (ht-koc) and BEAD-05 (ht-fzd) serialised after them on `messages` / `cli` edges that may be real (catalogue keys), not overridden
- [x] Wave 3a: BEAD-06 (ht-jc9, 932f53e) ∥ BEAD-08 (ht-ekd, 0a55b20) — combined tree by ht-jc9: 1563 passed + 4 known, ruff/format/mypy clean, `beadloom ci` rc 0; the gate's `outside-the-declared-axes` on the external SPECs closed by three authored rows in the RFC's Axes
- [x] Wave 3b: BEAD-02 (ht-koc, 01ac151) — 174 tests, 313/313 + 28/28 mutants; the year rule refined (the end is the next occurrence, the start the latest on or before it); a surviving `schedule._pick` mutant (`/` for `//`) handed to BEAD-10
- [x] Wave 4: BEAD-07 (ht-xad, ebcdc31) — 64 tests, six scenarios real; `Reply` lines, `AbsenceService(store, clock, checkin_range)`, `Adapters.absences/bot`, Ctrl-C a clean stop; ruling recorded: an absence entered after the check-in range start and covering today starts tomorrow (CONTEXT)
- [x] Wave 5: BEAD-05 (ht-fzd, a7ae643) ∥ BEAD-09 (ht-3lc, 0362801, gate owner) — `shared_node: cli` overridden in flow.yml; combined tree: 1964 passed + 4 known, ruff/format/mypy clean, `beadloom ci` rc 0, actionlint rc 0; the gate's `outside-the-declared-axes` on schedule.py closed by ruling the row in
- [x] Test wave: BEAD-10 (ht-h0l, ae322d8) — 18 tests, coverage 99.02 %, 807/809 mutants (the two `schedule._pick` survivors recorded equivalent with an exhaustive check), 18 sabotages red
- [x] Review: BEAD-11 (ht-3fz) — PASSED: 0 critical, 0 major, 6 minor (one withdrawn), 4 nitpick; 28 sabotages red; the directed checks hold. Minors 1–2 closed by the coordinator (CONTEXT rows: token discipline in telegram.py, KillSignal, `--lines=0`; the clip and edit rows committed with this wave); minor 6 ACCEPTED (CONTEXT row); minors 4, 5, 7 → fix bead ht-t28.1 + re-review ht-t28.2 (both under ht-t28, ht-mr9 now depends on ht-t28.2)
- [x] Fix: ht-t28.1 (a8e906e) — `not_over` in absence-service (the probe imports it; probe now depends_on absence-service), `/list` names current and upcoming absences and counts the finished ones, the reply rendered inside the loop's one try, annotations uniform + `tests/unit/test_graph_annotations.py`; on the tree: 2024 passed + 4 known, coverage 99.03 %, ci rc 0
- [x] Re-review: ht-t28.2 — PASSED over a8e906e: 0 critical, 0 major, 2 minor (recorded, not blocking: `not_over` lives in application rather than domain, deferred so the mutation gate stayed untouched; one scenario title and one test name still say "every absence"); the old bot_loop fails the new render test, the new one passes
- [x] Docs: BEAD-12 (ht-mr9, 1adeb93) — 13 files: 8 SPECs, cli.md (`horizon bot`, the `absences:` line, `HT_STATE_DIR`), deployment.md, architecture.md Landscape, README, CHANGELOG Unreleased (HT-010 Fixed, HT-012 + HT-013 Added, the notices Changed); sync-check 46/46, ci rc 0
- [x] Landscape gaps (under ht-1t7, 7bf4877): vps-host names five units, `file:absences` contract vps-host → absence-store; the portal build lists 13 contracts, all `confirmed`
- [x] Final tree before the release commit: `beadloom ci` rc 0, ruff + format + mypy clean, pytest 2024 passed, 5 skipped (systemd), 4 failed (the known Mac-only 3× /proc/self/task + shellcheck)
- [ ] Wave 5: BEAD-09
- [ ] Test wave: BEAD-10 · Review: BEAD-11 · Docs: BEAD-12
- [x] Release 1.1.0: BEAD-13 (ht-1t7) — c262902 bump; PR #6 ci-ok green (the informative mutation-per-change reached no verdict: mutmut's stats run fails the HT-010 photo scenario under its tracer → bug ht-7f0); merged ba1e032; tag v1.1.0; Release run 40128148896 all green (verify, gate, deploy, publish, portal); GitHub Release with wheel + sdist; the host's probe answers five checks ok incl. `absences: ok - none`; `horizon-bot.service` enabled by the deploy (its running state was shown in the step summary, not read from here); portal landscape 13 contracts, all confirmed
- [ ] Owner live check: BEAD-14 (ht-pwp)

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Closed | `domain/absence.py`; `allocate_id` takes `last_issued` (CONTEXT decision); stubs in `absences.feature` (9) and `production_calendar.feature` (1) |
| BEAD-02 | Done | ht-koc, 01ac151: `bot_commands.parse(text, today)` with Add/List/Delete/Edit/Help, ten parser error keys and the reply keys in both languages; node `bot-commands` + SPEC; `command:bot-text` on the landscape |
| BEAD-03 | Done | ht-4um, 7c8303e: absence reasons, `RunReport.absence` + `is_day_level_skip`, no time line for a day-level skip, calendar line keys `report.calendar.<source>` (one full line per source, both languages), absence reason with its span; 44 report cases; 213/213 mutants; four feature files' texts; ruff `allowed-confusables` for the en dash |
| BEAD-04 | Done | ht-egg, 0ade310: `AbsenceBook(absences, last_issued)` in absence.py; ports `AbsenceStore`, `BotTransport`, `IncomingMessage`; `JsonAbsenceStore` (atomic, 0600, parent 0700, `AbsenceStoreError`); `Settings.state_dir`; 55 tests; the fake store; node `absence-store` + SPEC |
| BEAD-05 | Done | ht-fzd, a7ae643: the absence verdict before the calendar (no calendar call), `notify_day_skips` by `is_day_level_skip`, evening silent, forced runs ignore absences, a raising store read as empty; `Decision.SKIP_ABSENT` for the dry run; three plan keys; the clip-to-tomorrow rule and note in `AbsenceService.add` (edit of an absence already covering today keeps today); 44 tests; the three US-3 scenarios real |
| BEAD-06 | Done | ht-jc9, 932f53e: `TelegramBotTransport` (getUpdates timeout 30, allowed_updates message, the offset tracked by the transport; sendMessage reply; `BotTransportError`; a 409 logged by status); the redaction imported from telegram.py (`redact_token`, `mask_token_in_httpx_log`, …); 43 tests; the landscape gains `http:telegram-getUpdates` and `sendMessage` towards `telegram-bot`; combined tree of wave 3a: 1563 passed + 4 known, ruff/mypy clean, ci rc 0 |
| BEAD-07 | Done | ht-xad, ebcdc31: AbsenceService (add refuses overlaps naming the id, edit keeps the id, delete/not found, list), BotLoop (chat filter first, one reply per message, internal error → reply, backoff on poll errors), `horizon bot`; nodes `absence-service`, `bot-loop` + SPECs; test support `bot_api.py` |
| BEAD-08 | Done | ht-ekd, 0a55b20: `absences:` check after `chrome` (ok none / n entered + next or none ahead / failed on an unreadable file), both languages; `absence_span` shared with the notice; the store built in `_probe` until BEAD-05 moves it into `Adapters`; `HT_STATE_DIR` points at tmp in the test environments; 17 tests; 494/496 mutants (2 segfaults in schedule, pre-existing) |
| BEAD-09 | Done | ht-3lc, 0362801: `horizon-bot.service` (simple, Restart=always, KillSignal=SIGINT), bootstrap lists it and creates the state dir 0700, release.yml installs five units and enables the bot, the summary shows its status (`--lines=0`); `/state/` ignored; deployment.md 2.4 + 6.5 (no RUNBOOK exists); 19 contract tests, the enable-line sabotage red |
| BEAD-10 | Done | ht-h0l, ae322d8: the risk-table and decision edge cases pinned; no stub left; 1982 passed in the room |
| BEAD-11 | Done | ht-3fz: PASSED, 0/0/6/4; fix beads ht-t28.1 (minors 4, 5, 7) and ht-t28.2 (re-review) opened under the epic |
| BEAD-12 | Done | ht-mr9, 1adeb93: 13 files, sync-check 46/46 |
| BEAD-13 | Done | ht-1t7: v1.1.0 on ba1e032, Release run green, GitHub Release published, portal 13/13 confirmed |
| BEAD-14 | Open | ht-pwp: the owner's live check on the host (bot commands, the next skipped-day notice) |

## Notes

- Branch `features/HT-012`, one PR to `main`; the tag `v1.1.0` on its merge commit releases HT-010, HT-013 and this item together.
- The PRD's ten scenarios enter the suite as SKIP stubs in BEAD-01 (as HT-004/HT-007 did), otherwise `scenario-coverage` keeps the gate red before the first commit.
- Owner's rulings: one notice in the morning on any day-level skip, the evening silent; text commands only.
