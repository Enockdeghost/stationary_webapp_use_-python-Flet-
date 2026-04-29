import sqlite3
from contextlib import contextmanager

from config import DB_FILE


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def execute_query(query: str, params: tuple = ()):
    with get_db() as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor


def fetch_one(query: str, params: tuple = ()):
    with get_db() as conn:
        return conn.execute(query, params).fetchone()


def fetch_all(query: str, params: tuple = ()):
    with get_db() as conn:
        return conn.execute(query, params).fetchall()