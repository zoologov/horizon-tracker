# Deploying horizon-tracker

This guide takes a host from nothing to a service that checks in to a VMware Horizon
desktop every working morning and checks out every working evening, and whose bot takes the
owner's absences (a vacation, a sick leave, a day off) in the report chat. It covers the first
install, which is done once by hand, and the operations after it: every release reaches the
host automatically, when its tag `vX.Y.Z` is pushed, through the `deploy` job of the Release
workflow (`.github/workflows/release.yml`). A push to `main` runs CI and deploys nothing.
What a release is and how one is cut is in [`releasing.md`](releasing.md).

The commands, exit codes and variables of the `horizon` CLI are specified in
`docs/services/cli.md`; this guide quotes them where an operator needs them.

The first install, in order:

1. prepare the host (section 2);
2. create the GitHub Environment `horizon-vps` and deploy a release tag for the first
   time, which writes `.env` (sections 3 and 4.1);
3. run `horizon probe` (section 4.3);
4. run `horizon checkin --force` and `horizon checkout --force` during working hours and
   confirm both outside the service (section 4.4);
5. enable the timers (section 5).

Until step 5 the timers stay disabled: neither the host preparation nor a deploy enables
them. The bot is different: it never reaches the portal, so the first deploy enables and
starts `horizon-bot.service`, and every later deploy restarts it (section 2.4).

---

## 1. Requirements

| What | Why |
|------|-----|
| A host running Ubuntu (or another apt-based distribution) with systemd, reachable over SSH | the service runs as two systemd timers and their oneshot services, and the bot as one long-running service |
| Python 3.12 (`python3.12`, `python3.12-venv`) | the runtime; `deploy/bootstrap.sh` installs both from apt |
| `uv` at `/usr/local/bin/uv` | builds the locked environment; `bootstrap.sh` installs it when missing and the deploy calls it by this path |
| Google Chrome at `/usr/bin/google-chrome`, installed from Google's `.deb` (not the snap) | Playwright drives the system Chrome; `bootstrap.sh` checks it and never installs it |
| A dedicated system user `horizon`, home `/opt/horizon-tracker` | the units name this user and this home; `bootstrap.sh` creates both |
| A GitHub repository with Actions, and the rights to create an Environment | the Release workflow's `deploy` job reads its secrets and variables from the Environment `horizon-vps` |
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
- creates `/opt/horizon-tracker/artifacts/` (0750, the screenshots) and
  `/opt/horizon-tracker/state/` (0700, `horizon:horizon`, the absences: section 3.3);
- installs the five units into `/etc/systemd/system` and runs `systemctl daemon-reload`.

What it does **not** do, and says so in its last lines:

- it does not write `/opt/horizon-tracker/.env` - the deploy writes it (section 3.3);
- it does not start `horizon-bot.service` - without `.env` the bot could only fail, so the
  first deploy, which writes `.env`, enables it;
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

The Release workflow's `deploy` job logs in to the host as `VPS_USER` with a key of its own. It
installs units into `/etc/systemd/system`, writes `.env` owned by `horizon` and runs
`systemctl` and `systemd-run` without `sudo`, so `VPS_USER` is `root` or an account with root's
rights; it uses `sudo -n -u horizon` for the repository and the environment, so that `sudo`
must not ask for a password.

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
| `horizon-bot.service` | `Type=simple`, as `horizon`: `/opt/horizon-tracker/.venv/bin/horizon bot`, `Restart=always`, `RestartSec=10`, `KillSignal=SIGINT`, `WantedBy=multi-user.target`; enabled and restarted by every deploy |

The timers fire every day, weekends included: whether a day is a working day is decided by
the service (the `isdayoff.ru` production calendar, falling back to Monday-Friday when it
does not answer), and an absence the owner entered through the bot skips the day before
the calendar is asked. The morning run reports a skipped day in one Telegram notice; the
evening run of that day sends nothing (section 6.1).

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

The bot is the one unit that runs all the time. `horizon bot` long-polls the bot's
`getUpdates`, answers each message from `TELEGRAM_CHAT_ID` and ignores every other chat; it
never exits on its own. Its unit holds three facts:

- **One poller.** Telegram serves a bot's updates to one `getUpdates` caller at a time, and
  `horizon-bot.service` is that caller. A second one - a `horizon bot` started by hand while
  the service runs - makes Telegram refuse one of the two with status 409, and both log
  `poll failed`. Stop the service before polling by hand (section 6.5).
- **Always restarted.** Whatever ends the process - a crash, a configuration error (exit 1),
  a kill - systemd starts it again 10 s later. Starts that far apart never reach systemd's
  default start limit (5 within 10 s), so a bot broken by a bad `.env` recovers by itself
  once a deploy fixes the file.
- **A clean stop.** `systemctl stop` sends `SIGINT`, which `horizon bot` treats like Ctrl-C:
  it logs `bot stopped` and exits 0.

---

## 3. The GitHub Environment `horizon-vps`

Settings -> Environments -> New environment -> `horizon-vps`. The `deploy` job of
`release.yml` runs in this Environment and reads nothing else. Restrict its deployments to
the branch `main` and the release tags `v*` (Deployment branches and tags -> Selected branches
and tags): a release runs on a tag, and a redeploy by hand runs from `main`. A run started
from any other branch then reaches none of the Environment's secrets, even when that branch's
`release.yml` was edited to skip `verify`
([`releasing.md`](releasing.md#what-verify-refuses)). Values are entered only by a person, in
GitHub's interface or through `gh`; they never go into a chat, an issue, a commit or a log.

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
# the environment, with a deployment rule that admits only main and the release tags:
# a manual Release run started from another branch would execute that branch's
# release.yml, and this rule is what stops it (section 6.3)
gh api -X PUT "repos/<owner>/<repo>/environments/horizon-vps" \
  -F "deployment_branch_policy[protected_branches]=false" \
  -F "deployment_branch_policy[custom_branch_policies]=true" >/dev/null
gh api -X POST "repos/<owner>/<repo>/environments/horizon-vps/deployment-branch-policies" \
  -f name=main -f type=branch >/dev/null
gh api -X POST "repos/<owner>/<repo>/environments/horizon-vps/deployment-branch-policies" \
  -f name='v*' -f type=tag >/dev/null
# read the rule back: exactly these two entries, nothing else
gh api "repos/<owner>/<repo>/environments/horizon-vps/deployment-branch-policies" \
  --jq '.branch_policies[] | "\(.type) \(.name)"'

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
- **`HT_STATE_DIR` is optional, and the deploy does not write it.** Unset, the service keeps
  its state in `/opt/horizon-tracker/state`, the directory `bootstrap.sh` creates (0700,
  `horizon:horizon`). The absences the bot takes live there in `absences.json` (0600,
  written atomically), outside the checkout, so they survive every deploy, restart and
  reboot. When the directory is missing, the first absence creates it with mode 0700. A
  value set by hand in `.env` lasts only until the next deploy, like any hand edit.
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

- a range: `HT_CHECKIN_RANGE` / `HT_CHECKOUT_RANGE` in `release.yml`, the start time in the
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

Push a release tag (the steps are in [`releasing.md`](releasing.md#cutting-a-release)), or,
when the release already exists, deploy it by hand: Actions -> Release -> Run workflow, *Use
workflow from* `main`, and the current release tag in `tag`. A merge to `main` or a CI run
never reaches the host, and a tag whose commit is not on `main` is refused before the deploy.
Section 6.3 describes each step.

After a green run, `.env` exists, the units are installed, and the deploy's summary shows
the answer of `horizon probe`, the (still inactive) timers and `horizon-bot.service`
`active (running)`. From now on the bot answers in the report chat: send it `/help`.

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

The probe never logs in to the portal. A healthy host prints five lines
`<check>: ok - ...` (`settings`, `portal`, `calendar`, `chrome`, `absences`) and a sixth,
`schedule:`, without a status. The lines below are the
English output; with `HT_LANGUAGE=ru` the same lines are printed in Russian, and a
configuration error on stderr is repeated in Russian under the English journal line.

| Line | Healthy | Otherwise |
|------|---------|-----------|
| `settings:` | `ok - portal <HORIZON_URL>, desktop '<HORIZON_DESKTOP>', check-in <range>, check-out <range>, <zone>, language en` | no probe lines; `configuration error: <VAR>: <problem>` on stderr, exit 1 - fix the secret, the variable or the workflow; no secret value is printed |
| `portal:` | `ok - client bundles: <file names>` - the portal served `index.html` naming the HTML Access client bundles | `failed - no answer: portal_unreachable`, exit 1 - the host's network to the portal or `HORIZON_URL`; `failed - no answer: unexpected`, exit 1 - the portal answered without client bundles: `HORIZON_URL` is not the web client |
| `calendar:` | `ok - isdayoff.ru: <date> is a working day` (or `a day off`) | `degraded`, exit 0 - runs fall back to Monday-Friday; not a failure |
| `chrome:` | `ok - Chrome <version> started from /usr/bin/google-chrome` | `failed - not found at ...`, exit 1 - `HT_CHROME_PATH` or Chrome itself; `failed - found at ... but did not start: unexpected`, exit 1 - see section 7 |
| `absences:` | `ok - none (/opt/horizon-tracker/state/absences.json)` before the first absence; then `ok - <n> current or upcoming[, <m> finished], next: vacation 03.11–14.11 (<file>)` or `..., none ahead (<file>)` | `failed - <file>: <reason>`, exit 1 - the file cannot be read or is not valid (section 6.5); the runs treat it as empty meanwhile |
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
sudo journalctl -u horizon-bot --since today --no-pager  # the bot
systemctl status horizon-bot.service --no-pager          # the bot's state
```

How to read it:

- **Waiting for the moment.** The timer fires at the range start and the first attempt
  comes at the drawn moment, up to the range's length later. Meanwhile the journal holds
  one line, `Starting horizon-checkin.service - ...`, and nothing from the service: the
  process sleeps, no browser runs, Telegram is silent. `systemctl status` shows
  `Active: activating (start)` - normal, not a hang. The service's own lines appear once
  the run starts; the last one is `checkin run <outcome> (<reason>)`. The Telegram report
  follows the run and names both the actual and the planned time
  (`Time: 24.10.2026 07:43:12 MSK, planned for 07:43`).
- **A deploy during the wait** does not cut it short: the deploy restarts the timers and
  the bot, never a run's service, and the sleeping run reaches its moment.
- `Deactivated successfully` - exit 0: a success **or** a deliberate skip (a day off, an
  absence, a missed moment, too early). The lines above it and the Telegram report say which.
- **A skipped day.** On a day the calendar marks non-working, or one an absence covers, the
  morning run sends one notice and nothing else. Nothing was going to run that day, so the
  notice has no time line. An absence skip names the absence instead of the calendar, which was not
  asked:

  ```text
  Check-in skipped
  Production calendar: isdayoff.ru
  Reason: a day off
  ```

  ```text
  Check-in skipped
  Reason: vacation (03.11–14.11)
  ```

  With `HT_LANGUAGE=ru` the first reads `Вход пропущен`, `Производственный календарь:
  isdayoff.ru`, `Причина: выходной`. The evening run of such a day logs
  `checkout report not sent: the morning run reports a skipped day` and sends nothing. A
  run that starts too early or misses its window still sends its notice, in the evening too.
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
- **The bot's journal.** `bot started: answering one chat, absences in <file>` after every
  start, `bot stopped` after a `systemctl stop`. A message from another chat leaves
  `ignored update <n> from chat <id>: not the owner's` and never its text. `poll failed
  (<error>), retrying in <n> s` is a failed poll, retried after 5 s, doubling up to 300 s;
  preceded by `Telegram getUpdates refused with status 409`, it means a second poller
  (section 2.4).

After investigating a `failed` unit: `sudo systemctl reset-failed horizon-checkin.service`.

### 6.2. Manual runs

Use the `ht` wrapper of section 4.2: `ht probe`, `ht checkin --dry-run`,
`ht checkin --force`, `ht checkout --force`. A scheduled run lost to a reboot during its
wait is repeated with `--force`.

### 6.3. Updating: a release

A release updates the host. `.github/workflows/release.yml` ("Release") starts when a tag
`vX.Y.Z` is pushed, and by hand for an existing release tag (Actions -> Release -> Run
workflow, section 6.4). A push to `main` deploys nothing. Two releases never run at once and
never cancel each other: the next one waits, and of several waiting runs GitHub keeps the
newest. Cutting the tag, and what each job checks, is in [`releasing.md`](releasing.md).

1. **`verify`** - the tag is a strict SemVer release tag, its commit is an ancestor of `main`,
   `pyproject.toml` at that commit declares the tag's version, `uv.lock` locks the same
   version, and `CHANGELOG.md` holds the version's dated section. A run by hand started from
   any ref but `main` is refused. A refused tag reaches nothing below.
2. **`gate`** - the full CI (`.github/workflows/ci.yml` through `workflow_call`) on the tag's
   commit: lint, types and workflow lint; then the tests and the architecture gate; then
   `ci-ok`, red unless everything before it succeeded. What reaches the host passed what a
   pull request passes. `mutation-per-change` runs on a pull request only and is skipped
   here.
3. **`deploy`**, in the Environment `horizon-vps`, on the tag's commit as `verify` resolved
   it:

| Step | What it does on the host | Red means |
|------|--------------------------|-----------|
| `Set up SSH` | nothing: key and `known_hosts` from the secrets onto the runner, alias `vps`, `StrictHostKeyChecking yes` | - |
| `Preflight: reach the VPS` | nothing: refuses first when `HORIZON_URL` or `HORIZON_DESKTOP` is unset, then `ssh vps true`, the clone `/opt/horizon-tracker/.git` exists, `sudo -n -u horizon true` | a missing variable (named); the host unreachable, a wrong key or `known_hosts`, no clone, `sudo` asking for a password - before any change |
| `Update the code` | `git fetch --prune origin` and `checkout --detach <the tag's commit>` as `horizon`, then `uv sync --locked` as `horizon` | no access to the host or the repository; a local edit in the clone. A stale `uv.lock` stops earlier, at `verify` (`lock`) or at `gate` (CI's `uv sync --locked`). The sync here is a backstop |
| `Check the timers' time zone` | nothing: reads the `OnCalendar` lines of the timers just checked out | the timers fire in another zone than `HT_TIMEZONE` (both named) |
| `Build .env` | nothing: the file is built on the runner | an empty required value - the step names the variable, never its value |
| `Write .env` | `install -m 600 -o horizon -g horizon` from ssh's stdin into `.env.new`, then `mv -f` over `.env`; logs `horizon:horizon 600 .../.env` | - |
| `Install the units` | the five units into `/etc/systemd/system` (0644), `daemon-reload`, `systemctl try-restart` of the timers, `systemctl try-restart` then `enable --now` of `horizon-bot.service`, `list-timers` | - |
| `Smoke: horizon probe` | `horizon probe` as `horizon` through `systemd-run` with the `EnvironmentFile`, as in section 4.3; Chrome really starts | the probe's exit code: 1 on a configuration error or a FAILED `portal`, `chrome` or `absences` |
| `Deploy summary` | `systemctl list-timers 'horizon-*'` and `systemctl status horizon-bot.service --no-pager --lines=0`; the run's summary names the tag, the version, the commit, the probe's answer (or that it did not run), the timers and the bot's state with the status's exit code; written after a red step too, not after a cancellation | no SSH to the host |

- **Timers.** `try-restart` restarts only timers that are already enabled; a deploy never
  enables them. Before section 5, `list-timers` shows them inactive - normal.
- **The bot.** `try-restart` moves a running bot onto the code and the `.env` just written;
  `enable --now` starts it on the first deploy and leaves a running one as it is. The step
  does not wait for the bot: the smoke reads the same settings and fails the deploy on a
  configuration error, and the summary shows the bot's state. Its status is shown without
  journal lines, because the summary is as readable as the repository's runs and the
  journal names the chats that wrote to the bot.
- **Secrets.** They enter a step only through `env:`; no command line and no log line
  carries one, and no script uses `set -x`. `.env` travels as ssh's stdin. The runner's
  copy and the key are removed by the last step, whatever happened.
- **The smoke does not log in**: a wrong password passes the deploy and shows only in a
  check-in. An unreachable `isdayoff.ru` is `degraded` and does not fail it.
- A workflow that exists is not a deploy that happened: the proof is a real deploy after
  which `ht probe` on the host answers `settings: ok`, `portal: ok` and `chrome: ok`.

After a green `deploy`, `publish` creates (or, on a redeploy, edits) the GitHub Release of the
tag, and `portal-build` and `portal-deploy` publish the architecture portal to GitHub Pages
([`releasing.md`](releasing.md#the-portal)). A red deploy publishes neither.

### 6.4. Rotating secrets

- **Horizon password, bot token, chat id, any Environment value**: change it in `horizon-vps`,
  then redeploy the current release: Actions -> Release -> Run workflow, *Use workflow from*
  `main`, and the current release tag in `tag` (from a clone,
  `gh workflow run release.yml -f tag=vX.Y.Z`). The run rewrites `.env` without a new version.
  A changed Horizon password must reach the host before the next scheduled run, and only a
  `--force` check-in proves it.
- **Horizon account**: changing `HORIZON_USERNAME` changes the seed of the daily draw and
  therefore the minutes. To keep them, set `HT_JITTER_SEED` to the previous account name.
- **The deploy's SSH key**: add the new public key to `VPS_USER`'s `authorized_keys`,
  replace `VPS_SSH_KEY`, redeploy the current release, then remove the old public key from
  the host.
- **The host's key** (a reinstall): replace `VPS_KNOWN_HOSTS` with the new `ssh-keyscan`
  line, checked by fingerprint.
- **The repository deploy key** (private repository): generate a new pair as `horizon`
  (section 2.2, step 2, with a new file name, then point `~/.ssh/config` of `horizon` at
  it or replace `id_ed25519`), register it, check `sudo -u horizon git -C
  /opt/horizon-tracker fetch origin`, then delete the old key in GitHub.

### 6.5. The bot

`horizon-bot.service` runs from the first deploy on (section 2.4). The owner writes to it in
the report chat; `/help` lists the commands. The absences it takes are in
`/opt/horizon-tracker/state/absences.json`:

```bash
sudo -u horizon cat /opt/horizon-tracker/state/absences.json   # the absences entered
sudo stat -c '%U:%G %a' /opt/horizon-tracker/state             # horizon:horizon 700
```

- **To pause the bot**, `sudo systemctl stop horizon-bot.service`; a pause lasts until the
  next deploy or reboot. `disable --now` lasts until the next deploy, which enables it
  again. The runs still read the absences already entered while the bot is stopped.
- **To poll by hand** (a `horizon bot` started outside the service, for instance to try a
  new token), stop the service first and start it again afterwards: two pollers make
  Telegram refuse one of them with 409.
- **After editing `absences.json` by hand**, nothing needs a restart: the bot reads the file
  on every command, and the runs on every run. Keep it valid JSON: a file the store cannot
  read is reported by `ht probe` as `absences: failed`.

---

## 7. Troubleshooting

- **Preflight: `HORIZON_URL is not set` / `HORIZON_DESKTOP is not set`.** Define the
  variable in `horizon-vps` (section 3.2) and redeploy the release (section 6.4).
- **Preflight fails on `ssh`.** Check `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` and
  `VPS_KNOWN_HOSTS`; on the host, that the public key is in `authorized_keys`, that the
  clone exists, and that `sudo -n -u horizon true` succeeds for `VPS_USER`.
- **`the timers fire in <zone> but HT_TIMEZONE is <zone>`.** Set `HT_TIMEZONE` to the
  timers' zone, or change both timers' `OnCalendar` (section 3.4).
- **`Update the code` fails.** `sudo -u horizon git -C /opt/horizon-tracker status`: a
  local edit blocks the checkout. For a private repository, check the deploy key and that
  `origin` is the SSH URL (`git remote -v`). A stale `uv.lock` does not reach this step:
  `verify` refuses a lock that locks another version, and `gate` runs CI's
  `uv sync --locked` on the tag's commit. If `uv sync --locked` still refuses here, fix the
  lock in the repository, not on the host.
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
     update Playwright in the repository, release it, and run `ht probe` again.
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
- **`absences: failed - <file>: <reason>`.** The absences file cannot be read, or it is not
  the store's layout (the reason names the fault, e.g. `not valid JSON: ...` or
  `absence 1: kind 'holiday' is not one of vacation, sick_leave, day_off`). Until it is
  fixed the runs log `absences could not be read` and go on as if none were entered, so an
  absence does not stop a run, and the bot answers `/add`, `/list`, `/edit` and `/del` with
  `Something went wrong; the details are in the journal`. Correct the file by hand (section 6.5).
- **The bot does not answer.** `systemctl status horizon-bot.service --no-pager` and its
  journal (section 6.1). `activating (auto-restart)` with `status=1/FAILURE` is a
  configuration error, named in the journal: fix the variable and redeploy. `poll failed`
  after a 409 is a second poller - a `horizon bot` started by hand, or the same token used
  by another host. A message from a chat other than `TELEGRAM_CHAT_ID` gets no answer by
  design.
