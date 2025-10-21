
"""
This module handles the persistence layer (the "database") for the app using MySQL.
"""

# --------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------

from app.utils.exceptions import NotFoundException, ForbiddenException
import mysql.connector
from mysql.connector import errorcode
from pydantic import BaseModel
from typing import List, Optional

# --------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------

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


# --------------------------------------------------------------------------------
# MySQLStorage Class
# --------------------------------------------------------------------------------

class MySQLStorage:
    def __init__(self, owner: str, db_config: dict):
        self.owner = owner
        self.db_config = db_config
        self.db_name = db_config['database']
        
        try:
            # Connect without specifying the database
            temp_config = self.db_config.copy()
            temp_config.pop('database', None)
            self.conn = mysql.connector.connect(**temp_config)
            self.cursor = self.conn.cursor(dictionary=True)
            self._create_database()
            self.conn.database = self.db_name
            self._create_tables()
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                print("Something is wrong with your user name or password")
            else:
                print(err)
            raise err

    def _create_database(self):
        try:
            self.cursor.execute(
                f"CREATE DATABASE {self.db_name} DEFAULT CHARACTER SET 'utf8'"
            )
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_DB_CREATE_EXISTS:
                pass
            else:
                print(err.msg)

    def _create_tables(self):
        TABLES = {}
        TABLES['reminder_lists'] = (
            "CREATE TABLE `reminder_lists` ("
            "  `id` int(11) NOT NULL AUTO_INCREMENT,"
            "  `owner` varchar(255) NOT NULL,"
            "  `name` varchar(255) NOT NULL,"
            "  PRIMARY KEY (`id`)"
            ") ENGINE=InnoDB")

        TABLES['reminder_items'] = (
            "CREATE TABLE `reminder_items` ("
            "  `id` int(11) NOT NULL AUTO_INCREMENT,"
            "  `list_id` int(11) NOT NULL,"
            "  `description` text NOT NULL,"
            "  `completed` boolean NOT NULL DEFAULT 0,"
            "  PRIMARY KEY (`id`),"
            "  FOREIGN KEY (`list_id`) REFERENCES `reminder_lists` (`id`) ON DELETE CASCADE"
            ") ENGINE=InnoDB")

        TABLES['selected_lists'] = (
            "CREATE TABLE `selected_lists` ("
            "  `owner` varchar(255) NOT NULL,"
            "  `list_id` int(11),"
            "  PRIMARY KEY (`owner`),"
            "  FOREIGN KEY (`list_id`) REFERENCES `reminder_lists` (`id`) ON DELETE SET NULL"
            ") ENGINE=InnoDB")

        for table_name in TABLES:
            table_description = TABLES[table_name]
            try:
                self.cursor.execute(table_description)
            except mysql.connector.Error as err:
                if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
                    pass
                else:
                    print(err.msg)

    def close(self):
        self.cursor.close()
        self.conn.close()

    # Private Methods

    def _get_raw_list(self, list_id: int) -> dict:
        query = "SELECT * FROM reminder_lists WHERE id = %s"
        self.cursor.execute(query, (list_id,))
        reminder_list = self.cursor.fetchone()

        if not reminder_list:
            raise NotFoundException()
        elif reminder_list["owner"] != self.owner:
            raise ForbiddenException()
        
        return reminder_list

    def _verify_list_exists(self, list_id: int) -> None:
        # Just get the list and make sure no exceptions happen
        self._get_raw_list(list_id)

    # Reminder Lists

    def create_list(self, name: str) -> int:
        query = "INSERT INTO reminder_lists (name, owner) VALUES (%s, %s)"
        self.cursor.execute(query, (name, self.owner))
        self.conn.commit()
        return self.cursor.lastrowid

    def delete_list(self, list_id: int) -> None:
        self._verify_list_exists(list_id)
        query = "DELETE FROM reminder_lists WHERE id = %s"
        self.cursor.execute(query, (list_id,))
        self.conn.commit()

    def delete_lists(self) -> None:
        for rem_list in self.get_lists():
            self.delete_list(rem_list.id)

    def get_list(self, list_id: int) -> ReminderList:
        reminder_list = self._get_raw_list(list_id)
        return ReminderList(**reminder_list)

    def get_lists(self) -> List[ReminderList]:
        query = "SELECT * FROM reminder_lists WHERE owner = %s"
        self.cursor.execute(query, (self.owner,))
        reminder_lists = self.cursor.fetchall()
        return [ReminderList(**row) for row in reminder_lists]

    def update_list_name(self, list_id: int, new_name: str) -> None:
        self._verify_list_exists(list_id)
        query = "UPDATE reminder_lists SET name = %s WHERE id = %s"
        self.cursor.execute(query, (new_name, list_id))
        self.conn.commit()

    # Reminder Items

    def _get_raw_item(self, item_id: int) -> dict:
        query = "SELECT * FROM reminder_items WHERE id = %s"
        self.cursor.execute(query, (item_id,))
        item = self.cursor.fetchone()
        if not item:
            raise NotFoundException()
        
        self._verify_list_exists(item['list_id'])
        return item

    def _verify_item_exists(self, item_id: int) -> None:
        # Just get the item and make sure no exceptions happen
        self._get_raw_item(item_id)

    def add_item(self, list_id: int, description: str) -> int:
        self._verify_list_exists(list_id)
        query = "INSERT INTO reminder_items (list_id, description, completed) VALUES (%s, %s, %s)"
        self.cursor.execute(query, (list_id, description, False))
        self.conn.commit()
        return self.cursor.lastrowid

    def delete_item(self, item_id: int) -> None:
        self._verify_item_exists(item_id)
        query = "DELETE FROM reminder_items WHERE id = %s"
        self.cursor.execute(query, (item_id,))
        self.conn.commit()

    def get_item(self, item_id: int) -> ReminderItem:
        item = self._get_raw_item(item_id)
        return ReminderItem(**item)

    def get_items(self, list_id: int) -> List[ReminderItem]:
        self._verify_list_exists(list_id)
        query = "SELECT * FROM reminder_items WHERE list_id = %s"
        self.cursor.execute(query, (list_id,))
        items = self.cursor.fetchall()
        return [ReminderItem(**row) for row in items]

    def strike_item(self, item_id: int) -> None:
        item = self._get_raw_item(item_id)
        query = "UPDATE reminder_items SET completed = %s WHERE id = %s"
        self.cursor.execute(query, (not item['completed'], item_id))
        self.conn.commit()

    def update_item_description(self, item_id: int, new_description: str) -> None:
        self._verify_item_exists(item_id)
        query = "UPDATE reminder_items SET description = %s WHERE id = %s"
        self.cursor.execute(query, (new_description, item_id))
        self.conn.commit()

    # Selected Lists

    def get_selected_list_id(self) -> Optional[int]:
        query = "SELECT list_id FROM selected_lists WHERE owner = %s"
        self.cursor.execute(query, (self.owner,))
        selected_list = self.cursor.fetchone()
        if not selected_list:
            return None
        
        return selected_list['list_id']

    def get_selected_list(self) -> Optional[SelectedList]:
        list_id = self.get_selected_list_id()
        if list_id is None:
            return None

        try:
            reminder_list = self.get_list(list_id)
            reminder_items = self.get_items(list_id)
        except NotFoundException:
            self.set_selected_list(None)
            return None

        return SelectedList(
            id=reminder_list.id,
            owner=reminder_list.owner,
            name=reminder_list.name,
            items=reminder_items)

    def set_selected_list(self, list_id: Optional[int]) -> None:
        query = "INSERT INTO selected_lists (owner, list_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE list_id = %s"
        self.cursor.execute(query, (self.owner, list_id, list_id))
        self.conn.commit()

    def reset_selected_after_delete(self, deleted_id: int) -> None:
        selected_list_id = self.get_selected_list_id()

        if selected_list_id == deleted_id:
            lists = self.get_lists()
            list_id = lists[0].id if lists else None
            self.set_selected_list(list_id)
