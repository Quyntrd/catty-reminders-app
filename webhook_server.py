#!/usr/bin/env python3
"""
Webhook сервер для автоматического деплоя Catty Reminders.
"""

import sys
import json
import subprocess
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path

PORT = 8080
APP_DIR = "/home/vboxuser/Desktop/DevOps/catty-reminders-app"
DEPLOY_SCRIPT = "/home/vboxuser/Desktop/DevOps/catty-reminders-app/deploy.sh"
VENV_PYTHON = os.path.join(APP_DIR, ".venv", "bin", "python")

class WebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"🔔 [{ts}] {format % args}")

    def _safe_write(self, b: bytes):
        try:
            self.wfile.write(b)
        except BrokenPipeError:
            return False
        return True

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        html = f"""
        <!doctype html>
        <html lang="ru">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <title>Catty Reminders — Webhook</title>
          <style>
            body {{ font-family: Inter, Tahoma, Arial, sans-serif; max-width: 720px; margin: 40px auto; color: #222; }}
            header {{ display:flex; align-items:center; gap:12px; }}
            h1 {{ margin:0; font-size:1.4rem; }}
            .meta {{ color:#555; margin-top:8px; }}
            .box {{ background:#f7fafc; border:1px solid #e2e8f0; padding:16px; border-radius:8px; margin-top:16px; }}
            a.small {{ color:#2563eb; text-decoration:none; font-size:0.9rem; }}
          </style>
        </head>
        <body>
          <header>
            <div style="font-size:28px;">🚀</div>
            <div>
              <h1>Catty Reminders — Webhook</h1>
              <div class="meta">Сервер готов принимать GitHub webhook'ы для автоматического деплоя.</div>
            </div>
          </header>

          <div class="box">
            <p><strong>Статус:</strong> активен</p>
            <p><strong>Порт:</strong> {PORT}</p>
            <p><strong>Время сервера:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>Отправьте POST-запрос с заголовком <code>X-GitHub-Event: push</code>, чтобы инициировать деплой.</p>
            <p style="margin-top:12px;"><a class="small" href="https://github.com/prafdin/catty-reminders-app">Исходный репозиторий</a></p>
          </div>
        </body>
        </html>
        """
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self._safe_write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            print("→ Получен POST-запрос")
            print(f"   Размер тела: {length} байт")

            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except json.JSONDecodeError as e:
                payload = {}
                print(f"⚠️ Ошибка разбора JSON: {e}")

            event = self.headers.get("X-GitHub-Event", "unknown")

            print(f"Событие от GitHub: {event}")
            print(f"Репозиторий: {payload.get('repository', {}).get('full_name', 'неизвестен')}")

            if event == "push":
                self.handle_push(payload)
            else:
                print(f"Пропускаем событие типа: {event}")

            self._ok()
        except Exception as e:
            print(f"‼️ Ошибка при обработке POST: {e}")
            self._err(500, str(e))

    def handle_push(self, payload):
        print("→ Обработка push-события начата")
        branch = payload.get("ref", "").replace("refs/heads/", "")
        commits = len(payload.get("commits", []))
        clone = payload.get("repository", {}).get("clone_url", "")
        print(f"   Ветка: {branch or '<не указана>'}")
        print(f"   Количество коммитов: {commits}")
        print(f"   URL для клона: {clone or '<не указана>'}")

        if self.run_tests():
            self.run_deploy()
        else:
            print("✖ Тесты не пройдены — деплой отменён")

    def run_tests(self):
        print("→ Запуск набора тестов")
        test_files = [
            ("Unit тесты", "test_unit.py"),
            ("API тесты", "test_api.py"),
        ]

        python_exec = VENV_PYTHON if Path(VENV_PYTHON).exists() else sys.executable
        print(f"Используем интерпретатор Python: {python_exec}")

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{APP_DIR}:{os.path.join(APP_DIR,'tests')}"
        env.setdefault("BASE_URL", "http://127.0.0.1:8181")

        all_ok = True
        for name, fname in test_files:
            path = os.path.join(APP_DIR, "tests", fname)
            if not os.path.exists(path):
                print(f"   ⚠ Файл для {name} не найден: {path}")
                continue

            print(f"   → Выполняем: {name}")
            try:
                cmd = [python_exec, "-m", "pytest", path, "-q", "-rA"]
                res = subprocess.run(
                    cmd,
                    cwd=APP_DIR,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=env,
                )
                if res.returncode == 0:
                    print(f"   ✓ {name}: Успешно")
                else:
                    print(f"   ✖ {name}: Завершились с кодом {res.returncode}")
                    snippet = (res.stderr or res.stdout or "")[-4000:]
                    print(snippet)
                    all_ok = False
            except subprocess.TimeoutExpired:
                print(f"   ⏰ {name}: Превышено время выполнения")
                all_ok = False
            except Exception as e:
                print(f"   💥 {name}: Исключение - {e}")
                all_ok = False

        return all_ok

    def run_deploy(self):
        print("→ Запускаем процедуру деплоя")
        if not os.path.exists(DEPLOY_SCRIPT):
            print(f"   ✖ Не найден скрипт деплоя: {DEPLOY_SCRIPT}")
            return False

        try:
            res = subprocess.run(
                ["/bin/bash", DEPLOY_SCRIPT],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if res.returncode == 0:
                print("✓ Деплой выполнен успешно")
                print("---- stdout деплоя ----")
                print(res.stdout)
                print("---- stderr деплоя ----")
                print(res.stderr)
                return True
            else:
                print("✖ Ошибка во время деплоя")
                print(f"   Код выхода: {res.returncode}")
                print("---- stdout деплоя ----")
                print(res.stdout)
                print("---- stderr деплоя ----")
                print(res.stderr)
                return False
        except subprocess.TimeoutExpired:
            print("⏰ Таймаут при выполнении деплоя")
            return False
        except Exception as e:
            print(f"💥 Исключение при деплое:{e}")
            return False

    def _ok(self):
        body = b'{"status":"success","message":"Webhook processed"}'
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self._safe_write(body)

    def _err(self, code, msg):
        payload = json.dumps({"status": "error", "message": msg}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self._safe_write(payload)

def main():
    print("Запуск сервера: Catty Reminders Webhook")
    print(f"Слушаем порт: {PORT}")
    print(f"Рабочая папка приложения: {APP_DIR}")
    print(f"Скрипт деплоя: {DEPLOY_SCRIPT}")
    print("Ожидаем входящие webhook-запросы...")
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Сервер остановлен вручную")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()