from typing import TypeVar, Generic, Type, Optional, List, Any
from database.connection import fetch_one, fetch_all, execute_query

T = TypeVar("T")


class BaseRepository(Generic[T]):
    model_class: Type[T]
    table_name: str
    id_column: str = "id"

    def __init__(self):
        if not self.model_class:
            raise ValueError("model_class must be set")

    def get_by_id(self, id: int) -> Optional[T]:
        row = fetch_one(
            f"SELECT * FROM {self.table_name} WHERE {self.id_column} = ?",
            (id,)
        )
        return self.model_class.from_row(row) if row else None

    def get_all(self, order_by: str = None) -> List[T]:
        query = f"SELECT * FROM {self.table_name}"
        if order_by:
            query += f" ORDER BY {order_by}"
        rows = fetch_all(query)
        return [self.model_class.from_row(row) for row in rows]

    def create(self, data: dict) -> int:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        cursor = execute_query(query, tuple(data.values()))
        return cursor.lastrowid

    def update(self, id: int, data: dict) -> bool:
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE {self.id_column} = ?"
        params = tuple(data.values()) + (id,)
        execute_query(query, params)
        return True

    def delete(self, id: int) -> bool:
        execute_query(f"DELETE FROM {self.table_name} WHERE {self.id_column} = ?", (id,))
        return True