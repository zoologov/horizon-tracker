# Security policy

## Supported versions

Only the latest release receives security fixes. The releases are listed at
<https://github.com/zoologov/horizon-tracker/releases>; a fix ships as a new release, and the
host is updated by deploying it.

## Reporting a vulnerability

Report a vulnerability privately, through GitHub's private vulnerability reporting: open the
repository's **Security** tab and choose **Report a vulnerability**
(<https://github.com/zoologov/horizon-tracker/security/advisories/new>). Do not open a public
issue, a discussion or a pull request for it, because each of those is public the moment it is
created.

A useful report names the version or commit, what an attacker can do, and the steps that show
it. Never include a real credential: a token, a password or a chat id in a report is a leak of
its own.

The owner ([@zoologov](https://github.com/zoologov)) answers within a few days. The report
stays private until a release fixes it.

## Scope

- the service: the `horizon` command and the Python package under `src/horizon_tracker/`;
- the deploy: the Release workflow (`.github/workflows/release.yml`) and the way it carries
  secrets to the host;
- the host files the project ships: the systemd units and `deploy/bootstrap.sh` in `deploy/`.

The VMware Horizon portal, isdayoff.ru, Telegram and GitHub themselves are out of scope;
report their vulnerabilities to their vendors.

## How the project handles credentials

The service holds three credentials: the Active Directory account it logs in to the portal
with, the Telegram bot token and the chat id the reports go to.

- They exist in two places only: the GitHub Environment `horizon-vps` and the file
  `/opt/horizon-tracker/.env` on the host, owned by the `horizon` user with mode `0600` and
  written by the deploy.
- They never appear in a log, a screenshot, a Telegram report, a bead comment or a commit. A
  credential found in any of these is a vulnerability; report it as above.
- The deploy passes secrets to its steps through `env:` only; no command line and no log line
  carries one, and the runner's copies are removed at the end of the job.
- CI and the development agents never log in to the portal. They read only the
  unauthenticated client bundle, to take its selectors; every run against the live portal
  happens on the host.
- The screenshot in a notification is taken after the login page has been left, on the
  desktop list or the opened desktop, so a typed password cannot end up in one.
