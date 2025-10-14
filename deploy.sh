#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/vboxuser/Desktop/DevOps/catty-reminders-app"
VENV="$APP_DIR/.venv"
LOG="/home/vboxuser/Desktop/DevOps/catty-reminders-app/deploy.log"

exec > >(tee -a "$LOG") 2>&1
echo "===== $(date '+%F %T') | START DEPLOY ====="

cd "$APP_DIR"

BRANCH="$(git rev-parse --abbrev-ref HEAD || echo main)"
echo "[GIT] current branch: $BRANCH"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

"$VENV/bin/pip" install --upgrade pip
[ -f requirements.txt ] && "$VENV/bin/pip" install -r requirements.txt
[ -f requirements-test.txt ] && "$VENV/bin/pip" install -r requirements-test.txt || true

echo "[SYSTEMD] restart catty-reminders"
sudo -n /usr/bin/systemctl restart catty-reminders

sudo -n /usr/bin/systemctl status catty-reminders --no-pager || true

echo "===== $(date '+%F %T') | DEPLOYMENT COMPLETED ====="
