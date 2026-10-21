# Deploying horizon-tracker

This guide takes a host from nothing to a service that checks in to a VMware Horizon
desktop every working morning and checks out every working evening. It covers the first
install, which is done once by hand, and the operations after it: every later release
reaches the host automatically, on a push to `main`, through the deploy workflow
(`.github/workflows/deploy.yml`).

The commands, exit codes and variables of the `horizon` CLI are specified in
`docs/services/cli.md`; this guide quotes them where an operator needs them.

The first install, in order:

1. prepare the host (section 2);
2. create the GitHub Environment `horizon-vps` and run the first deploy, which writes
   `.env` (sections 3 and 4.1);
3. run `horizon probe` (section 4.3);
4. run `horizon checkin --force` and `horizon checkout --force` during working hours and
   confirm both outside the service (section 4.4);
5. enable the timers (section 5).

Until step 5 the timers stay disabled: neither the host preparation nor a deploy enables
them.

---

## 1. Requirements

| What | Why |
|------|-----|
| A host running Ubuntu (or another apt-based distribution) with systemd, reachable over SSH | the service runs as two systemd timers and their oneshot services |
| Python 3.12 (`python3.12`, `python3.12-venv`) | the runtime; `deploy/bootstrap.sh` installs both from apt |
| `uv` at `/usr/local/bin/uv` | builds the locked environment; `bootstrap.sh` installs it when missing and the deploy calls it by this path |
| Google Chrome at `/usr/bin/google-chrome`, installed from Google's `.deb` (not the snap) | Playwright drives the system Chrome; `bootstrap.sh` checks it and never installs it |
| A dedicated system user `horizon`, home `/opt/horizon-tracker` | the units name this user and this home; `bootstrap.sh` creates both |
| A GitHub repository with Actions, and the rights to create an Environment | the deploy workflow reads its secrets and variables from the Environment `horizon-vps` |
| Outbound network from the host to the Horizon portal, `isdayoff.ru`, `api.telegram.org` and `github.com` | the portal is the subject; the production calendar decides working days; Telegram carries the reports; GitHub serves the code |
| A Horizon account, the title of its desktop, a Telegram bot token and a chat id | the service logs in as this account, opens this desktop and reports to this chat |

The user, the home and the Environment name `horizon-vps` are fixed: the units, the
workflow and the tests name them. Everything specific to one host - its address, the
portal, the desktop, the time zone, the language - is configuration held in the
Environment (section 3).

If other services share the host, nothing below touches them: the service has its own
user and home, and shares only `uv` and Chrome, which it never reinstalls.

---

## 2. Preparing the host

`deploy/bootstrap.sh` performs the first install. It is idempotent: every step checks or
converges its own state, so a second run changes nothing. Run as root, it

- refuses to run without root, and refuses before any change when Chrome is missing at
  `HT_CHROME_PATH` (default `/usr/bin/google-chrome`) or when it has no repository to
  clone;
- creates the system user `horizon` (`nologin`, home `/opt/horizon-tracker`);
- installs the apt packages `python3.12 python3.12-venv git curl ca-certificates`;
- clones the repository into `/opt/horizon-tracker` unless a clone is already there, and
  gives it to `horizon`. The repository is `HT_REPO` when set, otherwise the `origin` of
  the clone the script runs from - there is no built-in default;
- installs `uv` into `/usr/local/bin` when it is not there;
- runs `uv sync --locked` as `horizon`, which builds `.venv` with the `horizon` command;
- creates `/opt/horizon-tracker/artifacts/` (0750, the screenshots);
- installs the four units into `/etc/systemd/system` and runs `systemctl daemon-reload`.

What it does **not** do, and says so in its last lines:

- it does not write `/opt/horizon-tracker/.env` - the deploy writes it (section 3.3);
- it does not enable the timers - that is section 5, after the manual runs.

An earlier one-shot setup script assumed password SSH on the host and a public HTTPS
clone; both assumptions were false on the first host this service was installed on, so
this guide gives the manual steps instead, which hold on any host.

### 2.1. A public repository

```bash
# on the host
git clone https://github.com/<owner>/<repo>.git /tmp/horizon-src
sudo bash /tmp/horizon-src/deploy/bootstrap.sh
rm -rf /tmp/horizon-src
```

The clone's `origin` is the HTTPS URL, so the deploy's `git fetch` needs no credentials.

### 2.2. A private repository: a read-only deploy key and an SSH origin

An HTTPS clone of a private repository needs a credential stored on the host, which is
not acceptable. Instead the user `horizon` gets its own read-only deploy key, the clone's
`origin` is the SSH URL, and the clone is made by `horizon` before `bootstrap.sh` runs -
the script then skips its clone step.

```bash
# on the host, as an administrator
sudo apt-get install -y git

# 1. the user and its home (bootstrap.sh would create the same and skips an existing user)
sudo useradd -r -m -d /opt/horizon-tracker -s /usr/sbin/nologin horizon

# 2. a key pair of horizon's own, without a passphrase
sudo -u horizon install -d -m 700 /opt/horizon-tracker/.ssh
sudo -u horizon ssh-keygen -t ed25519 -N '' -C "horizon-tracker deploy key" \
  -f /opt/horizon-tracker/.ssh/id_ed25519
sudo cat /opt/horizon-tracker/.ssh/id_ed25519.pub
```

Register the printed public key in the repository: Settings -> Deploy keys -> Add deploy
key, with "Allow write access" left unchecked.

```bash
# 3. pin github.com's host key; compare the fingerprint with the one GitHub publishes
sudo -u horizon sh -c 'ssh-keyscan -t ed25519 github.com >> /opt/horizon-tracker/.ssh/known_hosts'
sudo -u horizon ssh-keygen -lf /opt/horizon-tracker/.ssh/known_hosts
sudo -u horizon ssh -T git@github.com    # "successfully authenticated"; exits 1 by design

# 4. clone into the home, which is not empty (skeleton files, .ssh), as horizon
sudo -u horizon git -C /opt/horizon-tracker init -q -b main
sudo -u horizon git -C /opt/horizon-tracker remote add origin git@github.com:<owner>/<repo>.git
sudo -u horizon git -C /opt/horizon-tracker fetch origin
sudo -u horizon git -C /opt/horizon-tracker checkout -f main

# 5. keep the home's own files out of the clone's status
printf '%s\n' /.bashrc /.bash_logout /.profile /.ssh/ \
  | sudo -u horizon tee -a /opt/horizon-tracker/.git/info/exclude >/dev/null
sudo -u horizon git -C /opt/horizon-tracker status --short    # prints nothing

# 6. the rest of the install
sudo bash /opt/horizon-tracker/deploy/bootstrap.sh
```

Every later deploy runs `git fetch` as `horizon` over this SSH origin with this key.

### 2.3. The deploy's own SSH access

The deploy workflow logs in to the host as `VPS_USER` with a key of its own. It installs
units into `/etc/systemd/system`, writes `.env` owned by `horizon` and runs `systemctl`
and `systemd-run` without `sudo`, so `VPS_USER` is `root` or an account with root's
rights; it uses `sudo -n -u horizon` for the repository and the environment, so that
`sudo` must not ask for a password.

```bash
# on your workstation: a key pair used by the deploy and nothing else
ssh-keygen -t ed25519 -N '' -C "horizon-tracker deploy" -f ~/.ssh/horizon-tracker-deploy
```

Append `~/.ssh/horizon-tracker-deploy.pub` to `VPS_USER`'s `~/.ssh/authorized_keys` on
the host, through whatever administrative access you already have. Then take the host's
key line for `VPS_KNOWN_HOSTS` and check it against the host itself:

```bash
ssh-keyscan -t ed25519 <host>                         # on your workstation
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub # on the host: the same fingerprint
```

### 2.4. The units

| Unit | What it does |
|------|--------------|
| `horizon-checkin.timer` | every day at the start of the check-in range (shipped: `07:30:00 Europe/Moscow`) starts `horizon-checkin.service` |
| `horizon-checkin.service` | `Type=oneshot`, as `horizon`: `/opt/horizon-tracker/.venv/bin/horizon checkin` |
| `horizon-checkout.timer` | every day at the start of the check-out range (shipped: `16:30:00 Europe/Moscow`) starts `horizon-checkout.service` |
| `horizon-checkout.service` | `Type=oneshot`, as `horizon`: `/opt/horizon-tracker/.venv/bin/horizon checkout` |

The timers fire every day, weekends included: whether a day is a working day is decided by
the service (the `isdayoff.ru` production calendar, falling back to Monday-Friday when it
does not answer), which reports a skipped day in Telegram.

A timer is not the moment of a run. It fires at the **start of the range**, and the
service draws the day's moment itself - a random minute of `HT_CHECKIN_RANGE` for the
check-in, and for the check-out the check-in moment plus `HT_SESSION_LENGTH_MINUTES` plus
0 to `HT_SESSION_EXTRA_MAX_MINUTES` minutes, kept inside `HT_CHECKOUT_RANGE` - and waits
for it inside its own process, up to the length of the range. The draw is derived from the
date, so the morning and the evening of one day agree, also after a reboot. The browser
is not started before the moment.

- `Persistent=no`: a run missed while the host was down is not caught up - a late
  check-in is worse than none. A reboot **during** the wait loses that day's run too;
  repeat it by hand with `--force` (section 4.4).
- `AccuracySec=1s`: the moment can be the range start itself, and the window of attempts
  from the moment is `HT_WINDOW_GRACE_MINUTES` long; without it systemd may fire up to a
  minute late.
- `TimeoutStartSec=60min`: the wait (at most the 40-minute range), the 5-minute window and
  the run itself, with margin. A hung Chrome is killed and the unit is marked `failed`. A
  wider range needs a longer timeout; `tests/unit/deploy/test_units.py` checks the sum.

---

## 3. The GitHub Environment `horizon-vps`

Settings -> Environments -> New environment -> `horizon-vps`. The deploy job runs in this
Environment and reads nothing else. Values are entered only by a person, in GitHub's
interface or through `gh`; they never go into a chat, an issue, a commit or a log.

### 3.1. Secrets

| Secret | Required | What it is |
|--------|----------|------------|
| `VPS_HOST` | yes | the host's address |
| `VPS_USER` | yes | the SSH user the deploy logs in as (section 2.3) |
| `VPS_SSH_KEY` | yes | that user's private key, the whole file including the BEGIN/END lines |
| `VPS_KNOWN_HOSTS` | yes | the host's `known_hosts` line from `ssh-keyscan`, checked by fingerprint |
| `HORIZON_USERNAME` | yes | the Horizon (AD) account |
| `HORIZON_PASSWORD` | yes | its password |
| `TELEGRAM_BOT_TOKEN` | yes | the token of the Telegram bot that sends the reports |
| `TELEGRAM_CHAT_ID` | yes | the chat the reports go to |
| `HT_JITTER_SEED` | no | the seed of the daily draw. Unset, the seed is `HORIZON_USERNAME`. Set it only when the account changes and the schedule should keep its minutes: then set it to the previous account name. Any other new seed draws other minutes |

### 3.2. Variables

Environment variables, not secrets: the values are not secret, but they belong to one
host, so they are not literals of the workflow.

| Variable | Required | What it is |
|----------|----------|------------|
| `HORIZON_URL` | yes | the HTML Access web client, e.g. `https://horizon.example.com/portal/webclient/`. The deploy's preflight refuses the run when it is unset |
| `HORIZON_DESKTOP` | yes | the title of the desktop's tile, e.g. `DEV desktop`. The preflight refuses the run when it is unset |
| `HT_TIMEZONE` | no | the IANA zone of every wall time (the ranges, the drawn moments, the report), e.g. `Europe/Moscow`. Unset, the deploy writes `UTC`. It must be the zone the timers' `OnCalendar` names, or the deploy refuses the run (section 3.4) |
| `HT_LANGUAGE` | no | the language of the notifications and of the `horizon` output: `en` or `ru`. Unset, English. The journal stays English whatever it says; any other value fails the deploy's smoke with `configuration error: HT_LANGUAGE: expected one of en, ru, got '...'` |

With `gh`, from a clone of the repository:

```bash
gh api -X PUT "repos/<owner>/<repo>/environments/horizon-vps" >/dev/null

gh secret set VPS_HOST --env horizon-vps            # prompts for the value
gh secret set VPS_USER --env horizon-vps
gh secret set VPS_SSH_KEY --env horizon-vps < ~/.ssh/horizon-tracker-deploy
ssh-keyscan -t ed25519 <host> 2>/dev/null | gh secret set VPS_KNOWN_HOSTS --env horizon-vps
gh secret set HORIZON_USERNAME --env horizon-vps    # typed by the account's holder
gh secret set HORIZON_PASSWORD --env horizon-vps
gh secret set TELEGRAM_BOT_TOKEN --env horizon-vps
gh secret set TELEGRAM_CHAT_ID --env horizon-vps

gh variable set HORIZON_URL --env horizon-vps --body "https://horizon.example.com/portal/webclient/"
gh variable set HORIZON_DESKTOP --env horizon-vps --body "DEV desktop"
gh variable set HT_TIMEZONE --env horizon-vps --body "Europe/Moscow"

gh secret list --env horizon-vps      # eight names, nine with HT_JITTER_SEED
gh variable list --env horizon-vps
```

A bot token is `<digits>:<string>`, without quotes or spaces. The Telegram adapter refuses
a token with a trailing newline, so a token piped from a file goes through
`tr -d '\n\r"'` first. A `gh secret set` that answers 404 means the Environment does not
exist yet.

### 3.3. What the deploy writes: the `.env` contract

Every deploy writes `/opt/horizon-tracker/.env`, owner `horizon:horizon`, mode `0600`,
from the Environment above and from the schedule values in the workflow's `Build .env`
step. The resulting file:

```ini
HORIZON_URL=<variable HORIZON_URL>
HORIZON_USERNAME=<secret HORIZON_USERNAME>
HORIZON_PASSWORD=<secret HORIZON_PASSWORD>
HORIZON_DESKTOP=<variable HORIZON_DESKTOP>
TELEGRAM_BOT_TOKEN=<secret TELEGRAM_BOT_TOKEN>
TELEGRAM_CHAT_ID=<secret TELEGRAM_CHAT_ID>
HT_TIMEZONE=<variable HT_TIMEZONE, UTC when it is unset>
HT_CHECKIN_RANGE=07:30-08:10
HT_CHECKOUT_RANGE=16:30-17:10
HT_SESSION_LENGTH_MINUTES=540
HT_SESSION_EXTRA_MAX_MINUTES=10
HT_WINDOW_GRACE_MINUTES=5
# HT_JITTER_SEED=<secret HT_JITTER_SEED> - present only when the secret is defined
HT_HOLD_SECONDS=120
HT_CHROME_PATH=/usr/bin/google-chrome
HT_ARTIFACTS_DIR=/opt/horizon-tracker/artifacts
# HT_LANGUAGE=<variable HT_LANGUAGE> - present only when the variable is defined
```

- **The format is systemd's `EnvironmentFile`, not shell.** systemd reads the file, not
  `bash`. The deploy writes every value in double quotes with `\`, `"`, `` ` `` and `$`
  escaped by a backslash - exactly the four characters systemd unescapes inside double
  quotes - so a password arrives literally, whatever it contains. A file written by hand
  must follow the same rule.
- **The deploy rewrites `.env` every time.** A hand edit on the host lasts until the next
  deploy. A per-host setting therefore lives in a GitHub variable or secret, never only
  in `.env`.
- `HT_CHECKIN_WINDOW` and `HT_CHECKOUT_WINDOW` belong to an older schedule and are
  refused: if either is present in `.env`, even blank, **every** `horizon` command exits
  1 with `configuration error: HT_CHECKIN_WINDOW: ...`, the deploy's smoke included.
- `bootstrap.sh` and the units never write `.env`; it is in `.gitignore` and survives
  every checkout.
- The `tests/unit/deploy` suite holds this block, the workflow and the timers equal.

Check the file without printing a value:

```bash
sudo stat -c '%U:%G %a' /opt/horizon-tracker/.env    # horizon:horizon 600
sudo cut -d= -f1 /opt/horizon-tracker/.env           # the names only
```

In an emergency, without a deploy, the same file can be written by hand; the next deploy
overwrites it, so its values must match the Environment:

```bash
sudo install -o horizon -g horizon -m 600 /dev/null /opt/horizon-tracker/.env
sudo -u horizon nano /opt/horizon-tracker/.env       # the block above, values quoted as described
```

### 3.4. The schedule: time zone and ranges

The ranges, the session length, the extra minutes and the window are literals of the
workflow's `Build .env` step, the same for every host of one repository; the shipped
values are examples. The time zone is the Environment variable `HT_TIMEZONE`.

The timers carry the same facts a second time, because systemd cannot read `.env`: each
`OnCalendar` names the start of its range and a zone. To change the schedule, change all
of them together:

- a range: `HT_CHECKIN_RANGE` / `HT_CHECKOUT_RANGE` in `deploy.yml`, the start time in the
  matching `deploy/horizon-*.timer`, and the contract block above. The tests in
  `tests/unit/deploy` fail when the three disagree.
- the zone: the variable `HT_TIMEZONE` and the zone at the end of both `OnCalendar`
  lines. The deploy's step `Check the timers' time zone` refuses a run when they differ,
  because timers in one zone and a draw in another start every run outside its range and
  no run would ever act - silently.

For example, a host checking in between 08:00 and 08:40 Berlin time has
`OnCalendar=*-*-* 08:00:00 Europe/Berlin` in `horizon-checkin.timer`, the range
`08:00-08:40` in the workflow, and `HT_TIMEZONE` set to `Europe/Berlin`.

---

## 4. First deploy and verification

### 4.1. The first deploy

Merge to `main`, or run it by hand: Actions -> Deploy -> Run workflow, on `main`. A run
started from another branch passes the CI gate but never reaches the host. Section 6.3
describes each step.

After a green run, `.env` exists, the units are installed, and the deploy's summary shows
the answer of `horizon probe` and the (still inactive) timers.

### 4.2. Running `horizon` by hand

Manual runs go through `systemd-run`: the same user, the same `.env`, read by the same
parser as the timers'. `source .env` in a shell is not a substitute - it reads the file
by shell rules and can alter a password.

```bash
# on the host: a wrapper for the session
ht() {
  # Not --pipe: when the SSH connection drops during a long run (a check-in holds the
  # desktop for two minutes) the output is lost and the unit reports exit code 120 - an
  # artefact of the dead pipe, not a verdict. The output goes to a file, read afterwards.
  local out="/tmp/ht-$1-$(date +%H%M%S).log"
  sudo systemd-run --quiet --wait --collect \
    --uid=horizon --gid=horizon \
    --working-directory=/opt/horizon-tracker \
    -p EnvironmentFile=/opt/horizon-tracker/.env \
    -p StandardOutput=append:"$out" -p StandardError=append:"$out" \
    /opt/horizon-tracker/.venv/bin/horizon "$@"
  local rc=$?
  sudo cat "$out"; echo "exit=$rc"
  return $rc
}

ht --version
ht probe
```

For a run that may outlast your SSH connection, start it inside `tmux` or `screen`, or
read the log file later.

### 4.3. `horizon probe`

The probe never logs in to the portal. A healthy host prints four lines
`<check>: ok - ...` and a fifth, `schedule:`, without a status. The lines below are the
English output; with `HT_LANGUAGE=ru` the same lines are printed in Russian, and a
configuration error on stderr is repeated in Russian under the English journal line.

| Line | Healthy | Otherwise |
|------|---------|-----------|
| `settings:` | `ok - portal <HORIZON_URL>, desktop '<HORIZON_DESKTOP>', check-in <range>, check-out <range>, <zone>, language en` | no probe lines; `configuration error: <VAR>: <problem>` on stderr, exit 1 - fix the secret, the variable or the workflow; no secret value is printed |
| `portal:` | `ok - client bundles: <file names>` - the portal served `index.html` naming the HTML Access client bundles | `failed - no answer: portal_unreachable`, exit 1 - the host's network to the portal or `HORIZON_URL`; `failed - no answer: unexpected`, exit 1 - the portal answered without client bundles: `HORIZON_URL` is not the web client |
| `calendar:` | `ok - isdayoff.ru: <date> is a working day` (or `a day off`) | `degraded`, exit 0 - runs fall back to Monday-Friday; not a failure |
| `chrome:` | `ok - Chrome <version> started from /usr/bin/google-chrome` | `failed - not found at ...`, exit 1 - `HT_CHROME_PATH` or Chrome itself; `failed - found at ... but did not start: unexpected`, exit 1 - see section 7 |
| `schedule:` | `today HH:MM / HH:MM` - today's drawn check-in and check-out moments, the same draw the scheduled runs make; information, never a failure | absent only when `settings:` failed |

The probe reads no portal version and no password: a wrong password shows only in a real
check-in (section 4.4).

### 4.4. Check-in and check-out by hand (`--force`)

`--force` runs at once: no wait for the day's moment, no window, no calendar; the report
says the calendar was not asked. To see the plan first without touching anything:
`ht checkin --dry-run` prints the day's moments (`schedule: today HH:MM / HH:MM`) and,
when a scheduled run would wait now, `would wait until: HH:MM`.

During working hours:

```bash
ht checkin --force     # log in, open the desktop, hold it HT_HOLD_SECONDS, disconnect
# confirm the session outside the service (below)
ht checkout --force    # log off the Windows session
# confirm again
```

- A check-in takes about two and a half minutes and exits 0; its log names the login,
  the tile, the opened desktop and the hold. A check-out exits 0 and logs
  `Horizon kill-session answered: <status> after <ms> ms`.
- **Disconnect** in the morning closes the client and keeps the Windows session; **Log
  off** in the evening ends the Windows session. They are different actions.
- Exit code 1 only when the run's report is FAILED; 0 for a success and for every
  deliberate skip.
- Each run sends one report to the Telegram chat. A failed run leaves a screenshot in
  `/opt/horizon-tracker/artifacts/`, kept for 14 days.
- **The screenshot never shows the login page.** It is taken only on the desktop list and
  on the opened desktop, so a typed password cannot end up in an artefact. A screenshot
  of the login page is a defect, not a setting - report it.

**Confirming the session state.** Only the broker knows whether a session exists, and
only the HTML Access web client shows its answer: in the desktop list, open the `...`
menu on the desktop's tile. **Connect** and **Log off** mean a session exists; **Connect**
alone means there is none. A second desktop of the same account without a session is a
useful control. A native Horizon client is not reliable for this: it was observed to
offer Log off for a desktop that had no session. Where an attendance system records the
Windows logon, it is the final confirmation.

If the desktop did not open or the check-in was not recorded, do **not** enable the
timers; investigate first (section 7).

---

## 5. Enabling the timers

Only after section 4.4 confirmed both the check-in and the check-out:

```bash
sudo systemctl enable --now horizon-checkin.timer horizon-checkout.timer
systemctl list-timers 'horizon-*' --no-pager
```

`NEXT` shows the next range starts in the timers' zone (displayed in the host's own time
zone, which may differ), not the moments of the runs. The day's moments are the
`schedule:` line of `ht probe`. The first scheduled run reports in Telegram at its drawn
moment plus the run's duration, not at the range start.

To stop the schedule (a holiday, a portal outage):

```bash
sudo systemctl disable --now horizon-checkin.timer horizon-checkout.timer
```

---

## 6. Operations

### 6.1. The journal

Scheduled runs log to the journal of their unit (the service's stderr; there is no log
file).

```bash
sudo journalctl -u horizon-checkin --since today --no-pager
sudo journalctl -u horizon-checkout -n 100 --no-pager
sudo journalctl -u horizon-checkin -f                   # follow a run live
systemctl status horizon-checkin.service --no-pager      # the last run's outcome
systemctl list-timers 'horizon-*' --no-pager             # the next start
```

How to read it:

- **Waiting for the moment.** The timer fires at the range start and the first attempt
  comes at the drawn moment, up to the range's length later. Meanwhile the journal holds
  one line, `Starting horizon-checkin.service - ...`, and nothing from the service: the
  process sleeps, no browser runs, Telegram is silent. `systemctl status` shows
  `Active: activating (start)` - normal, not a hang. The service's own lines appear once
  the run starts; the last one is `checkin run <outcome> (<reason>)`. The Telegram report
  follows the run and names both the actual and the planned time
  (`Time: HH:MM, planned for HH:MM`).
- **A deploy during the wait** does not cut it short: the deploy restarts timers, not
  services, and the sleeping run reaches its moment.
- `Deactivated successfully` - exit 0: a success **or** a deliberate skip (a day off, a
  missed moment, too early). The lines above it and the Telegram report say which.
- `Main process exited, code=exited, status=1/FAILURE` and the unit `failed` - the run's
  report is FAILED. The reason is in the log and in Telegram, the screenshot in
  `artifacts/`.
- `failed` with `Result: timeout` - the run was killed by `TimeoutStartSec=60min` after
  the wait and the window were over: Chrome hung. A Telegram report may be missing then;
  the journal is the record.
- A password, a token, a chat id or the account name never appear in the journal; one
  that does is a defect.
- Manual runs through `ht` write to their own file; in the journal they are transient
  `run-u*` units.

After investigating a `failed` unit: `sudo systemctl reset-failed horizon-checkin.service`.

### 6.2. Manual runs

Use the `ht` wrapper of section 4.2: `ht probe`, `ht checkin --dry-run`,
`ht checkin --force`, `ht checkout --force`. A scheduled run lost to a reboot during its
wait is repeated with `--force`.

### 6.3. Updating: the deploy workflow

`.github/workflows/deploy.yml` ("Deploy") runs on every push to `main` and by hand
(Actions -> Deploy -> Run workflow). Only `refs/heads/main` reaches the host. Two deploys
never run at once and never cancel each other: the next one waits, and of several waiting
runs GitHub keeps the newest.

1. **`gate`** - the full CI (`.github/workflows/ci.yml` through `workflow_call`): lint,
   types and workflow lint; then the tests and the architecture gate; then `ci-ok`, red
   unless everything before it succeeded. What reaches the host passed what a pull
   request passes. The mutation workflow is not part of the gate.
2. **`deploy`**, in the Environment `horizon-vps`:

| Step | What it does on the host | Red means |
|------|--------------------------|-----------|
| `Set up SSH` | nothing: key and `known_hosts` from the secrets onto the runner, alias `vps`, `StrictHostKeyChecking yes` | - |
| `Preflight: reach the VPS` | nothing: refuses first when `HORIZON_URL` or `HORIZON_DESKTOP` is unset, then `ssh vps true`, the clone `/opt/horizon-tracker/.git` exists, `sudo -n -u horizon true` | a missing variable (named); the host unreachable, a wrong key or `known_hosts`, no clone, `sudo` asking for a password - before any change |
| `Update the code` | `git fetch --prune origin` and `checkout --detach <the run's commit>` as `horizon`, then `uv sync --locked` as `horizon` | no access to the host or the repository; a local edit in the clone; a stale `uv.lock` |
| `Check the timers' time zone` | nothing: reads the `OnCalendar` lines of the timers just checked out | the timers fire in another zone than `HT_TIMEZONE` (both named) |
| `Build .env` | nothing: the file is built on the runner | an empty required value - the step names the variable, never its value |
| `Write .env` | `install -m 600 -o horizon -g horizon` from ssh's stdin into `.env.new`, then `mv -f` over `.env`; logs `horizon:horizon 600 .../.env` | - |
| `Install the units` | the four units into `/etc/systemd/system` (0644), `daemon-reload`, `systemctl try-restart` of the timers, `list-timers` | - |
| `Smoke: horizon probe` | `horizon probe` as `horizon` through `systemd-run` with the `EnvironmentFile`, as in section 4.3; Chrome really starts | the probe's exit code: 1 on a configuration error or a FAILED `portal` or `chrome` |
| `Deploy summary` | `systemctl list-timers 'horizon-*'`; the run's summary names the commit, the probe's answer (or that it did not run) and the timers; written after a red step too, not after a cancellation | no SSH to the host |

- **Timers.** `try-restart` restarts only timers that are already enabled; a deploy never
  enables them. Before section 5, `list-timers` shows them inactive - normal.
- **Secrets.** They enter a step only through `env:`; no command line and no log line
  carries one, and no script uses `set -x`. `.env` travels as ssh's stdin. The runner's
  copy and the key are removed by the last step, whatever happened.
- **The smoke does not log in**: a wrong password passes the deploy and shows only in a
  check-in. An unreachable `isdayoff.ru` is `degraded` and does not fail it.
- A workflow that exists is not a deploy that happened: the proof is a real deploy after
  which `ht probe` on the host answers `settings: ok`, `portal: ok` and `chrome: ok`.

### 6.4. Rotating secrets

- **Horizon password, bot token, chat id, any Environment value**: change it in
  `horizon-vps`, then run the deploy (Actions -> Deploy -> Run workflow, on `main`); it
  rewrites `.env`. A changed Horizon password must reach the host before the next
  scheduled run, and only a `--force` check-in proves it.
- **Horizon account**: changing `HORIZON_USERNAME` changes the seed of the daily draw and
  therefore the minutes. To keep them, set `HT_JITTER_SEED` to the previous account name.
- **The deploy's SSH key**: add the new public key to `VPS_USER`'s `authorized_keys`,
  replace `VPS_SSH_KEY`, run a deploy, then remove the old public key from the host.
- **The host's key** (a reinstall): replace `VPS_KNOWN_HOSTS` with the new `ssh-keyscan`
  line, checked by fingerprint.
- **The repository deploy key** (private repository): generate a new pair as `horizon`
  (section 2.2, step 2, with a new file name, then point `~/.ssh/config` of `horizon` at
  it or replace `id_ed25519`), register it, check `sudo -u horizon git -C
  /opt/horizon-tracker fetch origin`, then delete the old key in GitHub.

---

## 7. Troubleshooting

- **Preflight: `HORIZON_URL is not set` / `HORIZON_DESKTOP is not set`.** Define the
  variable in `horizon-vps` (section 3.2) and run the deploy again.
- **Preflight fails on `ssh`.** Check `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` and
  `VPS_KNOWN_HOSTS`; on the host, that the public key is in `authorized_keys`, that the
  clone exists, and that `sudo -n -u horizon true` succeeds for `VPS_USER`.
- **`the timers fire in <zone> but HT_TIMEZONE is <zone>`.** Set `HT_TIMEZONE` to the
  timers' zone, or change both timers' `OnCalendar` (section 3.4).
- **`Update the code` fails.** `sudo -u horizon git -C /opt/horizon-tracker status`: a
  local edit blocks the checkout. For a private repository, check the deploy key and that
  `origin` is the SSH URL (`git remote -v`). `uv sync --locked` refuses a stale `uv.lock`:
  fix it in the repository, not on the host.
- **`<NAME> is empty` in `Build .env`.** A required secret or variable is missing from the
  Environment.
- **The smoke fails with `configuration error: ...`.** The named variable is wrong. A
  `.env` written by hand from an older template may still carry `HT_CHECKIN_WINDOW` or
  `HT_CHECKOUT_WINDOW`; remove them (a deploy rewrites the file anyway).
- **`portal: failed - no answer: portal_unreachable`.** The host cannot reach the portal,
  or `HORIZON_URL` is wrong. `unexpected` means the URL answers but is not the web client.
- **`chrome: failed - found at ... but did not start`.** Scheduled runs fail too, and their
  report gives the reason "the Horizon portal is unreachable", because the browser starts
  inside the login step; only `ht probe` tells the two apart. Disable the timers until it
  is fixed. Then:
  1. stderr of the same `ht probe` has `Horizon step failed (unexpected): <type>` - the
     Playwright error type;
  2. `sudo -u horizon /usr/bin/google-chrome --version` - does Chrome start at all?
  3. if not, its installation is broken: repair it from Google's `.deb`, and if other
     services on the host use the same Chrome, check them afterwards;
  4. if it starts but Playwright cannot drive it, Chrome has moved past the Playwright
     version pinned in `uv.lock`. Do not downgrade a Chrome other services may share:
     update Playwright in the repository, deploy, and run `ht probe` again.
- **A manual run ended with exit code 120 and no output.** It ran with `--pipe` over an
  SSH connection that dropped. Use the `ht` wrapper of section 4.2, which writes to a file.
- **A password seems mangled.** Never `source .env` in a shell; run through `systemd-run`
  with `EnvironmentFile`, as the units do.
- **`bootstrap.sh` stops early.** `Chrome not found at ...`: install `google-chrome-stable`
  from Google's `.deb`, not the snap. `no repository to clone`: run it from a clone that
  has an `origin`, set `HT_REPO`, or make the clone by hand (section 2.2). `uv sync`
  fails: check `python3.12` and `/usr/local/bin/uv`.
- **The session state is unclear.** Ask the web client's tile menu (section 4.4), not a
  native client.
- **A unit is `failed` with `Result: timeout`.** Chrome hung after the wait; read the
  journal, then `systemctl reset-failed` the unit.
