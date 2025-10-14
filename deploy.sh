#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/vboxuser/Desktop/DevOps/catty-reminders-app"
VENV="$APP_DIR/.venv"
LOG="$APP_DIR/deploy.log"

# Логирование: используем абсолютный путь к tee
#   (НЕ выполняем sudo здесь — эту замену делаем один раз вручную при установке)
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

# Пытаемся перезапустить сервис через sudo. Ожидается правило NOPASSWD в sudoers для этой команды.
if sudo -n /usr/bin/systemctl restart catty-reminders; then
  echo "[SYSTEMD] restart command completed"
else
  echo "[ERROR] Failed to restart catty-reminders via sudo. Check sudoers (NOPASSWD) or run manually."
  # Возвращаем код ошибки 3 — это можно обработать выше уровнем (webhook)
  exit 3
fi

# Показать статус (не аварийно)
sudo -n /usr/bin/systemctl status catty-reminders --no-pager || true

echo "===== $(date '+%F %T') | DEPLOYMENT COMPLETED ====="
exit 0