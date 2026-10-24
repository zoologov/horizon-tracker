# The GitHub Environment `horizon-vps`

The GitHub Environment the Release workflow's `deploy` job runs in. An external system:
the repository holds the workflow that reads it, never a value of it.

## Source

None in this repository. The node's `source` in `.beadloom/_graph/landscape.yml` is this
file, so the graph has no sourceless node. The reader is the `deploy` job of
`.github/workflows/release.yml`. The procedure is `docs/guides/deployment.md`, section 3.

## Specification

### Purpose

Every per-host setting and every credential of the service lives here, entered by a
person in GitHub's interface or through `gh`. A deploy turns them into the host's `.env`,
so the Environment, not the host, is where a setting is changed for good.

The Environment admits deployments only from the branch `main` and the tags `v*`: a run
started from another branch reaches none of its secrets.

### Contracts

#### `env:github-environment` — github-environment → vps-host

Declared from both ends in `landscape.yml`. The portal's map shows it as a dependency
with a presence verdict. The surface is the list of names the `deploy` job reads. No
value appears in this document.

**Secrets** (`secrets.<NAME>` in the job):

| Name | Required | Where it goes |
|------|----------|---------------|
| `VPS_HOST` | yes | the SSH host alias `vps` |
| `VPS_USER` | yes | the SSH user |
| `VPS_SSH_KEY` | yes | the deploy's private key, written `0600` on the runner |
| `VPS_KNOWN_HOSTS` | yes | the pinned host key, `StrictHostKeyChecking yes` |
| `HORIZON_USERNAME` | yes | `.env` |
| `HORIZON_PASSWORD` | yes | `.env` |
| `TELEGRAM_BOT_TOKEN` | yes | `.env` |
| `TELEGRAM_CHAT_ID` | yes | `.env` |
| `HT_JITTER_SEED` | no | `.env`, only when defined |

**Variables** (`vars.<NAME>` in the job):

| Name | Required | Where it goes |
|------|----------|---------------|
| `HORIZON_URL` | yes, the preflight refuses the run without it | `.env` |
| `HORIZON_DESKTOP` | yes, the preflight refuses the run without it | `.env` |
| `HT_TIMEZONE` | no, `UTC` when unset, and it must equal the timers' zone | `.env` |
| `HT_LANGUAGE` | no, left out of `.env` when unset | `.env` |

**What the job adds itself.** The schedule values are literals of the workflow's
`Build .env` step, not Environment entries: `HT_CHECKIN_RANGE=07:30-08:10`,
`HT_CHECKOUT_RANGE=16:30-17:10`, `HT_SESSION_LENGTH_MINUTES=540`,
`HT_SESSION_EXTRA_MAX_MINUTES=10`, `HT_WINDOW_GRACE_MINUTES=5`, `HT_HOLD_SECONDS=120`,
`HT_CHROME_PATH=/usr/bin/google-chrome`, `HT_ARTIFACTS_DIR=/opt/horizon-tracker/artifacts`.

**What it produces on the host.** `/opt/horizon-tracker/.env`, `horizon:horizon` `0600`,
written next to the target and renamed over it, so a service never reads a half-written
file. An empty required name stops the job before anything is written, with an error that
names it.

## Invariants

- A value never reaches a commit, an issue, a chat, a log or a document.
- The deploy reads this Environment and nothing else. A merge to `main` deploys nothing,
  and a release tag does.
- `tests/unit/deploy` holds the workflow's `.env` block, the deployment guide's `.env`
  contract and the timers equal.

## Dependencies

Declared in `.beadloom/_graph/landscape.yml` as contract edges, not derived from
imports: an external system has no code here.

- Produces: `env:github-environment` for `vps-host`
- Consumes: (none)

## Parent

None: an external system, not part of `horizon-tracker`. The consumer is `vps-host`.
