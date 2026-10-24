# isdayoff.ru

The isdayoff.ru production calendar, a public service that answers whether a date is a
working day by the Russian production calendar. An external system: this repository
holds no code of it and declares only the surface the service reads.

## Source

None in this repository. The node's `source` in `.beadloom/_graph/landscape.yml` is this
file, so the graph has no sourceless node.

## Specification

### Purpose

Holidays fall on weekdays and some Saturdays are working, so the Monday-Friday rule alone
would check in on a holiday. isdayoff.ru gives the verdict for one date; when it gives no
clean answer, the domain falls back to the Monday-Friday rule and the report says so.

### Contracts

#### `http:isdayoff-day` — isdayoff → isdayoff-calendar

Declared from both ends in `landscape.yml`; the portal's map shows it as a dependency
with a presence verdict, and the surface below is the one `isdayoff-calendar` reads.

- **Request.** `GET https://isdayoff.ru/YYYYMMDD` (for example `/20261026`), no
  authentication, no query, a 5-second timeout. One request per run: the run loop asks
  the calendar once, and the probe asks it once for today.
- **Answer.** Status 200 with a one-character body:

| Body | Meaning | The adapter's answer |
|------|---------|----------------------|
| `0` | working day | `True` |
| `1` | non-working day | `False` |
| `2` | shortened pre-holiday day, still working | `True` |

- **Everything else is no answer.** A network error, the timeout, a status other than
  200 or any other body is `None`, logged as a warning that names the date, and never
  raised. On `None` the report's calendar line reads "unreachable, the Mon-Fri rule
  decided", and the probe's calendar check is `degraded`, not `failed`.

## Invariants

- The calendar is a source of verdicts, never of failures: no answer of it fails a run.
- Tests never reach isdayoff.ru: the adapter is tested on `httpx.MockTransport`, and the
  acceptance scenarios run on a fake calendar.

## Dependencies

Declared in `.beadloom/_graph/landscape.yml` as contract edges, not derived from
imports: an external system has no code here.

- Produces: `http:isdayoff-day` for `isdayoff-calendar`
- Consumes: (none)

## Parent

None: an external system, not part of `horizon-tracker`. The consumer is
`isdayoff-calendar`.
