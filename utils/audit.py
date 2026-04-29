import sqlite3
from datetime import datetime

from config import DB_FILE


def log_audit(user_id: int, action: str, details: str = ""):
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO audit_log (user_id, action, details) VALUES (?, ?, ?)",
        (user_id, action, details)
    )
    conn.commit()
    conn.close()