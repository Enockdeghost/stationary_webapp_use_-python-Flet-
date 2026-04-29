from typing import List, Optional
from database.repositories.base import BaseRepository
from database.models import Item
from database.connection import fetch_all


class ItemRepository(BaseRepository[Item]):
    model_class = Item
    table_name = "items"

    def search(self, name: str = None, category: str = None) -> List[Item]:
        query = "SELECT * FROM items WHERE 1=1"
        params = []
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        if category and category != "All":
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY name"
        rows = fetch_all(query, tuple(params))
        return [Item.from_row(row) for row in rows]

    def get_low_stock(self) -> List[Item]:
        query = "SELECT * FROM items WHERE quantity <= low_stock_threshold ORDER BY (low_stock_threshold * 2 - quantity) DESC"
        rows = fetch_all(query)
        return [Item.from_row(row) for row in rows]

    def update_quantity(self, item_id: int, change: int) -> bool:
        item = self.get_by_id(item_id)
        if not item:
            return False
        new_qty = max(0, item.quantity + change)
        self.update(item_id, {"quantity": new_qty})
        return True