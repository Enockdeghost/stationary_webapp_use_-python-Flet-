# security/auth.py
import hashlib
import hmac as _hmac
import secrets
import time
from collections import defaultdict

from config import MAX_LOGIN_ATTEMPTS, LOCKOUT_SECONDS

_login_attempts: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(username: str) -> tuple[bool, int]:
    key = f"login:{username.lower().strip()}"
    now = time.time()
    _login_attempts[key] = [t for t in _login_attempts[key] if now - t < LOCKOUT_SECONDS]
    if len(_login_attempts[key]) >= MAX_LOGIN_ATTEMPTS:
        remaining = int(LOCKOUT_SECONDS - (now - min(_login_attempts[key])))
        return False, remaining
    return True, 0


def record_failed_attempt(username: str):
    _login_attempts[f"login:{username.lower().strip()}"].append(time.time())


def clear_failed_attempts(username: str):
    _login_attempts.pop(f"login:{username.lower().strip()}", None)


def hash_password(pwd: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 200_000)
    return f"pbkdf2:{salt}:{dk.hex()}"


def _sha256(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def verify_password(pwd: str, stored: str) -> bool:
    if stored.startswith("pbkdf2:"):
        try:
            _, salt, dk_stored = stored.split(":", 2)
            dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 200_000)
            return _hmac.compare_digest(dk.hex(), dk_stored)
        except Exception:
            return False
    return _hmac.compare_digest(_sha256(pwd), stored)


def upgrade_hash_if_legacy(user_id: int, pwd: str, stored: str):
    if not stored.startswith("pbkdf2:"):
        import sqlite3
        from config import DB_FILE
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(pwd), user_id)
        )
        conn.commit()
        conn.close()