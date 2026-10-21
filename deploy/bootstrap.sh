#!/usr/bin/env bash
# bootstrap.sh - idempotent first install of horizon-tracker on the host.
#
# Target: Ubuntu/Debian (apt) with systemd. Its own system user `horizon`, home
# /opt/horizon-tracker; nothing outside that home, the units and the packages
# below is touched, so other services on the host are left as they are. Run as
# root. Every step checks or converges its own state, so a second run changes
# nothing and rolls nothing back.
#
# Does NOT write /opt/horizon-tracker/.env: the deploy workflow writes it from
# GitHub Environment `horizon-vps` (see docs/guides/deployment.md).
# Does NOT enable the timers: the operator enables them after the first manual
# run (`horizon probe`, `checkin --force`, `checkout --force`).
set -euo pipefail

# --- Fixed by the units: they name this user and this home -------------------
readonly HT_USER="horizon"
readonly HT_HOME="/opt/horizon-tracker"
readonly UV="/usr/local/bin/uv"
readonly UNIT_DIR="/etc/systemd/system"
readonly UNITS=(
  horizon-checkin.service
  horizon-checkin.timer
  horizon-checkout.service
  horizon-checkout.timer
)

# --- Overridable from the environment ----------------------------------------
# The repository cloned when the home holds no clone yet. Unset, it is the origin
# of the clone this script runs from; there is no built-in default, so a fork
# never clones someone else's repository.
HT_REPO="${HT_REPO:-}"
# Must agree with HT_CHROME_PATH in .env; Chrome belongs to the host.
HT_CHROME_PATH="${HT_CHROME_PATH:-/usr/bin/google-chrome}"
APT_PACKAGES="${APT_PACKAGES:-python3.12 python3.12-venv git curl ca-certificates}"

# The directory of this script (deploy/ inside a clone): the source of the units.
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '\033[1;32m[bootstrap]\033[0m %s\n' "$*"; }
skip() { printf '\033[1;34m[bootstrap]\033[0m (already done) %s\n' "$*"; }
die() {
  printf '\033[1;31m[bootstrap]\033[0m %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    die "run as root: sudo bash deploy/bootstrap.sh"
  fi
}

# Checked, never installed: the browser belongs to the host (the Google Chrome
# .deb). Checked before any change, so a missing Chrome leaves the host as it was.
require_chrome() {
  if [ ! -x "$HT_CHROME_PATH" ]; then
    die "Chrome not found at $HT_CHROME_PATH - install google-chrome-stable (.deb, not snap) and rerun"
  fi
  skip "Chrome present at $HT_CHROME_PATH"
}

# The URL to clone, settled before any change so a missing one leaves the host as
# it was. Not needed once the home holds a clone (made by hand for a private
# repository, see the guide).
resolve_repo() {
  if [ -d "$HT_HOME/.git" ]; then
    return
  fi
  if [ -z "$HT_REPO" ]; then
    HT_REPO="$(git -C "$DEPLOY_DIR" remote get-url origin 2>/dev/null)" || HT_REPO=""
  fi
  if [ -z "$HT_REPO" ]; then
    die "no repository to clone: run this script from a clone that has an origin, or set HT_REPO"
  fi
}

# 1. System user without a login shell, home in /opt (getent makes it idempotent).
ensure_user() {
  if getent passwd "$HT_USER" >/dev/null; then
    skip "user $HT_USER exists"
  else
    log "creating system user $HT_USER (home $HT_HOME)"
    useradd -r -m -d "$HT_HOME" -s /usr/sbin/nologin "$HT_USER"
  fi
}

# 2. apt packages (apt-get install leaves current packages as they are).
ensure_packages() {
  log "installing apt packages: $APT_PACKAGES"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  # shellcheck disable=SC2086 # the package list is split on purpose
  apt-get install -y $APT_PACKAGES
}

# 3. Clone into the home (skipped once .git exists; the deploy workflow updates it).
ensure_repo() {
  if [ -d "$HT_HOME/.git" ]; then
    skip "repository already cloned into $HT_HOME"
  else
    log "cloning $HT_REPO -> $HT_HOME"
    # useradd -m already created the home, and git clone wants an empty target,
    # so clone beside it and copy in.
    local tmp="${HT_HOME}.clone.$$"
    git clone "$HT_REPO" "$tmp"
    cp -rfT "$tmp" "$HT_HOME"
    rm -rf "$tmp"
  fi
  chown -R "$HT_USER:$HT_USER" "$HT_HOME"
}

# 4. uv system-wide at the path the deploy workflow calls (kept if already there).
ensure_uv() {
  if [ -x "$UV" ]; then
    skip "uv installed ($UV)"
  else
    log "installing uv into /usr/local/bin"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
  fi
}

# 5. The locked runtime environment, built by its owner (uv sync is a no-op when current).
ensure_venv() {
  log "uv sync --locked in $HT_HOME (as $HT_USER)"
  sudo -u "$HT_USER" bash -lc "cd '$HT_HOME' && $UV sync --locked"
}

# 6. Working directories (HT_ARTIFACTS_DIR in .env points here).
ensure_dirs() {
  log "creating $HT_HOME/artifacts"
  install -d -o "$HT_USER" -g "$HT_USER" -m 0750 "$HT_HOME/artifacts"
}

# 7. systemd units from deploy/, then daemon-reload. Installed, never enabled.
ensure_units() {
  log "installing systemd units from $DEPLOY_DIR"
  local unit
  for unit in "${UNITS[@]}"; do
    install -m 0644 "$DEPLOY_DIR/$unit" "$UNIT_DIR/$unit"
  done
  systemctl daemon-reload
}

main() {
  require_root
  require_chrome
  resolve_repo
  ensure_user
  ensure_packages
  ensure_repo
  ensure_uv
  ensure_venv
  ensure_dirs
  ensure_units
  log "done. Left untouched: $HT_HOME/.env - the deploy workflow writes it (0600 $HT_USER:$HT_USER)."
  log "Not enabled: the timers. First run by hand (docs/guides/deployment.md: probe, checkin --force,"
  log "checkout --force), then enable them:"
  log "  systemctl enable --now horizon-checkin.timer horizon-checkout.timer"
}

main "$@"
