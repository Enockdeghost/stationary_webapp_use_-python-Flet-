from typing import Optional, List
from database.repositories.base import BaseRepository
from database.models import User
from database.connection import fetch_one, fetch_all


class UserRepository(BaseRepository[User]):
    model_class = User
    table_name = "users"

    def get_by_username(self, username: str) -> Optional[User]:
        row = fetch_one(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        )
        return User.from_row(row) if row else None

    def get_all_sorted(self) -> List[User]:
        return self.get_all(order_by="username")