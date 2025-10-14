#!/usr/bin/env python3
"""
Webhook сервер для автоматического деплоя Catty Reminders (без UI-тестов)
"""

import sys
import json
import subprocess
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

PORT = 8080
APP_DIR = "/home/vboxuser/Desktop/DevOps/catty-reminders-app"
DEPLOY_SCRIPT = "/home/vboxuser/Desktop/DevOps/catty-reminders-app/deploy.sh"

class WebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"📡 [{ts}] {format % args}")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"""
        <html>
        <head><title>Catty Reminders Webhook</title></head>
        <body>
            <h1>🚀 Catty Reminders Webhook Server</h1>
            <p><b>Status:</b> 🟢 Active</p>
            <p><b>Port:</b> {PORT}</p>
            <p><b>Time:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>Send POST with GitHub payload to trigger deployment.</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            print("🎯 POST запрос получен")
            print(f"   Content-Length: {length}")

            payload = json.loads(body.decode("utf-8"))
            event = self.headers.get("X-GitHub-Event", "unknown")

            print(f"🔔 GitHub Event: {event}")
            print(
                f"📦 Репозиторий: {payload.get('repository', {}).get('full_name', 'unknown')}"
            )

            if event == "push":
                self.handle_push(payload)
            else:
                print(f"ℹ️  Игнорируем событие: {event}")

            self._ok()
        except Exception as e:
            print(f"❌ Ошибка обработки POST: {e}")
            self._err(500, str(e))

    def handle_push(self, payload):
        print("🚀 НАЧИНАЕМ ОБРАБОТКУ PUSH EVENT")
        branch = payload.get("ref", "").replace("refs/heads/", "")
        commits = len(payload.get("commits", []))
        clone = payload.get("repository", {}).get("clone_url", "")
        print(f"   Ветка: {branch}")
        print(f"   Коммитов: {commits}")
        print(f"   Clone URL: {clone}")

        if self.run_tests():
            self.run_deploy()
        else:
            print("❌ Тесты не пройдены, деплой отменен")

    def run_tests(self):
        print("🧪 ЗАПУСКАЕМ ТЕСТЫ...")
        test_files = [
            ("Unit тесты", "test_unit.py"),
            ("API тесты", "test_api.py"),
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{APP_DIR}:{os.path.join(APP_DIR,'tests')}"
        env.setdefault("BASE_URL", "http://127.0.0.1:8181")

        all_ok = True
        for name, fname in test_files:
            path = os.path.join(APP_DIR, "tests", fname)
            if not os.path.exists(path):
                print(f"   ⚠️  {name}: файл не найден - {path}")
                continue

            print(f"   🔍 Запускаем {name}...")
            try:
                cmd = [sys.executable, "-m", "pytest", path, "-v"]
                res = subprocess.run(
                    cmd,
                    cwd=APP_DIR,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=env,
                )
                if res.returncode == 0:
                    print(f"   ✅ {name}: ПРОЙДЕНЫ")
                else:
                    print(f"   ❌ {name}: ПРОВАЛЕНЫ")
                    snippet = (res.stderr or res.stdout or "")[-4000:]
                    print(snippet)
                    all_ok = False
            except subprocess.TimeoutExpired:
                print(f"   ⏰ {name}: ТАЙМАУТ")
                all_ok = False
            except Exception as e:
                print(f"   💥 {name}: ОШИБКА - {e}")
                all_ok = False

        return all_ok

    def run_deploy(self):
        print("🚀 ЗАПУСКАЕМ ДЕПЛОЙ...")
        if not os.path.exists(DEPLOY_SCRIPT):
            print(f"❌ Скрипт деплоя не найден: {DEPLOY_SCRIPT}")
            return False

        try:
            res = subprocess.run(
                ["/bin/bash", DEPLOY_SCRIPT],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if res.returncode == 0:
                print("✅ ДЕПЛОЙ УСПЕШНО ЗАВЕРШЕН!")
                print(f"   Вывод: {res.stdout}")
                return True
            else:
                print("❌ ОШИБКА ДЕПЛОЯ!")
                print(f"   Код: {res.returncode}")
                print(f"   Stderr: {res.stderr}")
                return False
        except subprocess.TimeoutExpired:
            print("⏰ ТАЙМАУТ ДЕПЛОЯ!")
            return False
        except Exception as e:
            print(f"💥 ОШИБКА ПРИ ДЕПЛОЕ: {e}")
            return False

    def _ok(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"success","message":"Webhook processed"}')

    def _err(self, code, msg):
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"status": "error", "message": msg}).encode("utf-8")
        )


def main():
    print("🚀 Запуск Catty Reminders Webhook Server")
    print(f"📍 Порт: {PORT}")
    print(f"⏰ Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 App directory: {APP_DIR}")
    print(f"🔧 Deploy script: {DEPLOY_SCRIPT}")
    print("\n👂 Ожидаем webhook запросы...\n")
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()