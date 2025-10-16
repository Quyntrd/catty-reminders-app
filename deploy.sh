#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/vboxuser/Desktop/DevOps/catty-reminders-app"
VENV="$APP_DIR/.venv"
LOG="$APP_DIR/deploy.log"

exec > >(/usr/bin/tee -a "$LOG") 2>&1

echo "===== $(date '+%F %T') | START DEPLOY ====="

cd "$APP_DIR"

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
echo "[GIT] current branch: $BRANCH"

git fetch origin "$BRANCH" --tags --prune
git reset --hard "origin/$BRANCH"

if [ -x "$VENV/bin/pip" ]; then
  echo "[PIP] Using venv pip: $VENV/bin/pip"
  "$VENV/bin/pip" install --upgrade pip
  [ -f requirements.txt ] && "$VENV/bin/pip" install -r requirements.txt
  [ -f requirements-test.txt ] && "$VENV/bin/pip" install -r requirements-test.txt || true
else
  echo "[WARNING] Virtualenv pip not found at $VENV/bin/pip. Skipping pip install."
fi

echo "[SYSTEMD] restart catty-reminders"

if sudo -n /usr/bin/systemctl restart catty-reminders; then
  echo "[SYSTEMD] restart command completed"
else
  echo "[ERROR] Failed to restart catty-reminders via sudo. Check sudoers (NOPASSWD) or run manually."
  exit 3
fi

echo "===== $(date '+%F %T') | DEPLOYMENT COMPLETED ====="
exit 0