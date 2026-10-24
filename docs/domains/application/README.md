# Application

Use cases of horizon-tracker. A use case orders domain decisions and port calls;
it owns no transport and no browser detail. Beside the daily runs and the probe, the
application answers the owner's absence commands to the bot.

## Source

`src/horizon_tracker/application/`

## Modules

| Module | One responsibility |
|--------|--------------------|
| `checkin.py` | the morning check-in: open the desktop until Windows logs on, hold it, photograph it while it is still open, then disconnect; a confirmed check-in reports the path `capture_open_desktop` returned (`MorningCheckin(client, clock, runner, desktop, hold)` with `kind`, `run(force=...)` and `steps()`) |
| `checkout.py` | the evening check-out: log the desktop's Windows session off and confirm it ended; a desktop with no session is reported as already logged off; a confirmed check-out reports the client's screenshot of the launch list without the session (`EveningCheckout(client, clock, runner, desktop)` with `kind`, `run(force=...)` and `steps()`) |
| `windowed_run.py` | drives one daily run through its window: waits through `Clock.sleep` from the start of the range until the day's drawn moment, where the window opens, then decides each attempt with the domain, retries failures and sends exactly one report (`WindowedRun(calendar, clock, notifier, window, policy, moment, range_start)` with `run()`, `first_decision()` and `steps()`). A start before the range is reported as `Reason.TOO_EARLY` and a start after the window as `WINDOW_MISSED`. The report names the drawn moment as `planned_at`. |
| `probe.py` | checks whether the service could run without ever logging in: `Probe` (portal client bundles via `client_bundles()`, the calendar, Chrome found and started via `browser_version()`; the absences file read once, its count and the next absence named, FAILED when it cannot be read or parsed; an unreachable calendar is DEGRADED, not FAILED; given the day's drawn moments, a last `schedule` check names them; each `Check` carries its name and status as messages, made with it) and `DryRun(use_case, moments)` (plans the use case a run would execute from `WindowedRun.first_decision()`, including the moment it would wait until, and the steps of the use case and the loop; names the day's drawn moments; never touches the Horizon client) |
| `absence_service.py` | the owner's absences on command: `AbsenceService(store, clock, checkin_range)` with `add` (a new id, never reissued; an overlap refused naming the absence in the way), `list`, `delete` and `edit` (the id kept), each answering with a `Reply` of catalogue messages; an absence for today entered after the check-in range gets a note that a morning check-in stands |
| `bot_loop.py` | serves the owner's bot chat: `BotLoop(transport, service, owner_chat_id, language, clock)` with `run_once(offset)` (the chat filter first, another chat dropped with its text unlogged; parse, carry out, one reply per message; an internal error answered as such) and `run_forever()` (a failed poll backed off from 5 s, doubling, up to 300 s) |

The use cases call the ports only. Waiting goes through `Clock.sleep`. What a person
reads is handed out as `Message`s (a catalogue key and its fields, `domain/messages.py`):
`steps()` of each use case and of the loop, and the detail of every probe check. The
application never picks a language; the CLI renders the messages in `HT_LANGUAGE`. A failure
screenshot travels inside the adapter's error and from there into the `RunReport`; a
success screenshot is the path `capture_open_desktop` or `log_off` answers with, and
the use case puts it into the report of a confirmed run.

## Features

Each feature has a `SPEC.md` (Purpose, How it works, Invariants, API, Testing):

- **[Windowed run](features/windowed-run/SPEC.md)** — `windowed_run.py`: the run loop
  both use cases share; it waits for the drawn moment and sends one report per run.
- **[Morning check-in](features/morning-checkin/SPEC.md)** — `checkin.py`: open, hold,
  disconnect, confirm `CONNECTED` -> `DISCONNECTED`.
- **[Evening check-out](features/evening-checkout/SPEC.md)** — `checkout.py`: log off
  from the tile menu and confirm `NO_SESSION`.
- **[Probe and dry run](features/probe/SPEC.md)** — `probe.py`: the dependency probe and
  the plan of a run, both without logging in.
- **[Absence service](features/absence-service/SPEC.md)** — `absence_service.py`: add,
  list, delete and edit the absences, each with its reply.
- **[Bot loop](features/bot-loop/SPEC.md)** — `bot_loop.py`: the owner's chat only, one
  reply per message, a loop that rides out a failed poll.

## Dependencies

- Depends on: `domain`
- Used by: `cli`
