# app/utils/mysql_storage.py
"""
Совместимая реализация MySQLStorage.
Поддерживает вызов:
    MySQLStorage(owner, db_config=...)
или
    MySQLStorage(owner, host=..., user=..., password=..., database=..., port=...)
Если db_config задан, он может быть dict с ключами:
  host, port, user, password, database
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import os

try:
    import mysql.connector
    from mysql.connector import pooling
except Exception as e:
    # Отложенная ошибка при отсутствии зависимости — чтобы импорт модуля не крашил весь процесс сразу
    mysql = None
    pooling = None
    mysql_import_err = e
else:
    mysql_import_err = None

from app.utils.exceptions import NotFoundException, ForbiddenException

class ReminderItem(BaseModel):
    id: int
    list_id: int
    description: str
    completed: bool

class ReminderList(BaseModel):
    id: int
    owner: str
    name: str

class SelectedList(BaseModel):
    id: int
    owner: str
    name: str
    items: List[ReminderItem]

class MySQLStorage:
    def __init__(self, owner: str, db_config: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        """
        owner: имя владельца (username)
        db_config: словарь с keys: host, port, user, password, database
        kwargs: альтернативный способ передачи host/user/password/database/port
        """
        if mysql_import_err is not None:
            raise RuntimeError("mysql-connector-python is required but not installed") from mysql_import_err

        self.owner = owner

        # Сначала берем параметры из db_config (если есть), затем из kwargs, затем из env/defaults
        cfg = {}
        if db_config and isinstance(db_config, dict):
            cfg.update(db_config)

        # поддержка старых вызовов, где параметрами могли передавать host/user/... напрямую
        for k in ("host", "port", "user", "password", "database"):
            if k in kwargs and kwargs[k] is not None:
                cfg[k] = kwargs[k]

        # подмена из окружения, если не указано
        cfg.setdefault("host", os.getenv("MYSQL_HOST", "127.0.0.1"))
        cfg.setdefault("port", int(os.getenv("MYSQL_PORT", "3306")))
        cfg.setdefault("user", os.getenv("MYSQL_USER", "catty"))
        cfg.setdefault("password", os.getenv("MYSQL_PASSWORD", "secret"))
        cfg.setdefault("database", os.getenv("MYSQL_DATABASE", "cattydb"))

        self._host = cfg["host"]
        self._port = int(cfg["port"])
        self._user = cfg["user"]
        self._password = cfg["password"]
        self._database = cfg["database"]

        # Пул соединений (autocommit=True)
        pool_name = f"pool_{self.owner}"
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name=pool_name,
                pool_size=5,
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
                autocommit=True,
            )
        except Exception as e:
            # если не получилось создать пул (например база не существует), пробуем создать простое соединение
            raise

        # Создадим схему (таблицы) при инициализации
        self._ensure_schema()

    # -------------------------
    # Вспомогательные методы
    # -------------------------
    def _get_conn(self):
        return self._pool.get_connection()

    def _ensure_schema(self) -> None:
        ddl = [
            """
            CREATE TABLE IF NOT EXISTS reminder_lists (
              id INT AUTO_INCREMENT PRIMARY KEY,
              owner VARCHAR(255) NOT NULL,
              name TEXT NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            """
            CREATE TABLE IF NOT EXISTS reminder_items (
              id INT AUTO_INCREMENT PRIMARY KEY,
              list_id INT NOT NULL,
              description TEXT NOT NULL,
completed TINYINT(1) NOT NULL DEFAULT 0,
              FOREIGN KEY (list_id) REFERENCES reminder_lists(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            """
            CREATE TABLE IF NOT EXISTS selected_lists (
              id INT AUTO_INCREMENT PRIMARY KEY,
              owner VARCHAR(255) NOT NULL UNIQUE,
              list_id INT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
        ]
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            for sql in ddl:
                cur.execute(sql)
            cur.close()
        finally:
            conn.close()

    def _fetchone(self, query: str, params: tuple = ()):
        conn = self._get_conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(query, params)
            row = cur.fetchone()
            cur.close()
            return row
        finally:
            conn.close()

    def _fetchall(self, query: str, params: tuple = ()):
        conn = self._get_conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            return rows
        finally:
            conn.close()

    def _execute(self, query: str, params: tuple = ()):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            lastid = cur.lastrowid
            cur.close()
            conn.commit()
            return lastid
        finally:
            conn.close()

    # -------------------------
    # API (аналог storage.py)
    # -------------------------
    def _get_raw_list(self, list_id: int):
        row = self._fetchone("SELECT * FROM reminder_lists WHERE id = %s", (list_id,))
        if not row:
            raise NotFoundException()
        if row["owner"] != self.owner:
            raise ForbiddenException()
        return row

    def _get_raw_item(self, item_id: int):
        row = self._fetchone("SELECT * FROM reminder_items WHERE id = %s", (item_id,))
        if not row:
            raise NotFoundException()
        self._verify_list_exists(row["list_id"])
        return row

    def _verify_list_exists(self, list_id: int) -> None:
        self._get_raw_list(list_id)

    def _verify_item_exists(self, item_id: int) -> None:
        self._get_raw_item(item_id)

    def create_list(self, name: str) -> int:
        lastid = self._execute(
            "INSERT INTO reminder_lists (owner, name) VALUES (%s, %s)",
            (self.owner, name),
        )
        return int(lastid)

    def delete_list(self, list_id: int) -> None:
        self._verify_list_exists(list_id)
        self._execute("DELETE FROM reminder_lists WHERE id = %s", (list_id,))

    def delete_lists(self) -> None:
        lists = self.get_lists()
        for lst in lists:
            self.delete_list(lst.id)

    def get_list(self, list_id: int) -> ReminderList:
        row = self._get_raw_list(list_id)
        return ReminderList(id=int(row["id"]), owner=row["owner"], name=row["name"])

    def get_lists(self) -> List[ReminderList]:
        rows = self._fetchall(
            "SELECT id, owner, name FROM reminder_lists WHERE owner = %s", (self.owner,)
        )
        return [ReminderList(id=int(r["id"]), owner=r["owner"], name=r["name"]) for r in rows]

    def update_list_name(self, list_id: int, new_name: str) -> None:
        self._get_raw_list(list_id)
        self._execute("UPDATE reminder_lists SET name = %s WHERE id = %s", (new_name, list_id))

    def add_item(self, list_id: int, description: str) -> int:
        self._verify_list_exists(list_id)
        lastid = self._execute(
            "INSERT INTO reminder_items (list_id, description, completed) VALUES (%s, %s, %s)",
            (list_id, description, 0),
        )
        return int(lastid)

    def delete_item(self,
item_id: int) -> None:
        self._verify_item_exists(item_id)
        self._execute("DELETE FROM reminder_items WHERE id = %s", (item_id,))

    def get_item(self, item_id: int) -> ReminderItem:
        row = self._get_raw_item(item_id)
        return ReminderItem(
            id=int(row["id"]),
            list_id=int(row["list_id"]),
            description=row["description"],
            completed=bool(row["completed"]),
        )

    def get_items(self, list_id: int) -> List[ReminderItem]:
        self._verify_list_exists(list_id)
        rows = self._fetchall(
            "SELECT id, list_id, description, completed FROM reminder_items WHERE list_id = %s",
            (list_id,),
        )
        return [
            ReminderItem(
                id=int(r["id"]),
                list_id=int(r["list_id"]),
                description=r["description"],
                completed=bool(r["completed"]),
            )
            for r in rows
        ]

    def strike_item(self, item_id: int) -> None:
        row = self._get_raw_item(item_id)
        new_val = 0 if row["completed"] else 1
        self._execute("UPDATE reminder_items SET completed = %s WHERE id = %s", (new_val, item_id))

    def update_item_description(self, item_id: int, new_description: str) -> None:
        self._get_raw_item(item_id)
        self._execute("UPDATE reminder_items SET description = %s WHERE id = %s", (new_description, item_id))

    def get_selected_list_id(self) -> Optional[int]:
        row = self._fetchone(
            "SELECT list_id FROM selected_lists WHERE owner = %s LIMIT 1", (self.owner,)
        )
        if not row:
            return None
        return int(row["list_id"]) if row["list_id"] is not None else None

    def get_selected_list(self) -> Optional[SelectedList]:
        list_id = self.get_selected_list_id()
        if list_id is None:
            return None
        try:
            reminder_list = self.get_list(list_id)
            reminder_items = self.get_items(list_id)
        except (NotFoundException, ForbiddenException):
            self._execute("UPDATE selected_lists SET list_id = NULL WHERE owner = %s", (self.owner,))
            return None

        return SelectedList(
            id=reminder_list.id,
            owner=reminder_list.owner,
            name=reminder_list.name,
            items=reminder_items,
        )

    def set_selected_list(self, list_id: Optional[int]) -> None:
        existing = self._fetchone("SELECT id FROM selected_lists WHERE owner = %s", (self.owner,))
        if existing:
            self._execute("UPDATE selected_lists SET list_id = %s WHERE owner = %s", (list_id, self.owner))
        else:
            self._execute("INSERT INTO selected_lists (owner, list_id) VALUES (%s, %s)", (self.owner, list_id))

    def reset_selected_after_delete(self, deleted_id: int) -> None:
        row = self._fetchone("SELECT list_id FROM selected_lists WHERE owner = %s", (self.owner,))
        if row and row.get("list_id") == deleted_id:
            first = self._fetchone("SELECT id FROM reminder_lists WHERE owner = %s ORDER BY id LIMIT 1", (self.owner,))
            list_id = int(first["id"]) if first else None
            self.set_selected_list(list_id)