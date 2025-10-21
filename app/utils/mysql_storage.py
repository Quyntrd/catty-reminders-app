"""
MySQLStorage — реализация хранилища на MySQL/MariaDB, совместимая с API
ReminderStorage из storage.py. Использует mysql-connector-python.
Автоматически создаёт таблицы при инициализации.
"""

from typing import List, Optional
from pydantic import BaseModel
import mysql.connector
from mysql.connector import pooling, Error as MySQLError
from app.utils.exceptions import NotFoundException, ForbiddenException

# Используем те же Pydantic-модели как в storage.py
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
    def init(
        self,
        owner: str,
        host: str = "127.0.0.1",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "cattydb",
        pool_name: str = "mypool",
        pool_size: int = 5,
    ) -> None:
        self.owner = owner
        self._pool = pooling.MySQLConnectionPool(
            pool_name=pool_name,
            pool_size=pool_size,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            autocommit=True,
        )
        # Создадим таблицы, если их нет
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

    # -------------------------
    # Private helpers
    # -------------------------
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
    # Реализация API (аналог storage.py)
    # -------------------------
    # Private getters that raise the same exceptions
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
        # verify list exists (and owner)
        self._verify_list_exists(row["list_id"])
        return row

    def _verify_list_exists(self, list_id: int) -> None:
        self._get_raw_list(list_id)

    def _verify_item_exists(self, item_id: int) -> None:
        self._get_raw_item(item_id)

    # ----- Lists -----
    def create_list(self, name: str) -> int:
        lastid = self._execute(
            "INSERT INTO reminder_lists (owner, name) VALUES (%s, %s)",
            (self.owner, name),
        )
        return int(lastid)

    def delete_list(self, list_id: int) -> None:
        # verify and then delete (items cascade)
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

    # ----- Items -----
    def add_item(self, list_id: int, description: str) -> int:
        # ensure list exists & owner matches
        self._verify_list_exists(list_id)
        lastid = self._execute(
            "INSERT INTO reminder_items (list_id, description, completed) VALUES (%s, %s, %s)",
            (list_id, description, 0),
        )
        return int(lastid)

    def delete_item(self, item_id: int) -> None:
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
# ----- Selected lists -----
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
            # reset selected to null if not valid
            self._execute("UPDATE selected_lists SET list_id = NULL WHERE owner = %s", (self.owner,))
            return None

        return SelectedList(
            id=reminder_list.id,
            owner=reminder_list.owner,
            name=reminder_list.name,
            items=reminder_items,
        )

    def set_selected_list(self, list_id: Optional[int]) -> None:
        # upsert by owner
        existing = self._fetchone("SELECT id FROM selected_lists WHERE owner = %s", (self.owner,))
        if existing:
            self._execute("UPDATE selected_lists SET list_id = %s WHERE owner = %s", (list_id, self.owner))
        else:
            self._execute("INSERT INTO selected_lists (owner, list_id) VALUES (%s, %s)", (self.owner, list_id))

    def reset_selected_after_delete(self, deleted_id: int) -> None:
        row = self._fetchone("SELECT list_id FROM selected_lists WHERE owner = %s", (self.owner,))
        if row and row.get("list_id") == deleted_id:
            # pick first list if exists
            first = self._fetchone("SELECT id FROM reminder_lists WHERE owner = %s ORDER BY id LIMIT 1", (self.owner,))
            list_id = int(first["id"]) if first else None
            self.set_selected_list(list_id)