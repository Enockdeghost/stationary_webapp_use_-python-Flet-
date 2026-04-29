# services/auth_service.py
from typing import Optional, Tuple
from database.repositories.user_repository import UserRepository
from security.auth import (
    verify_password,
    check_rate_limit,
    record_failed_attempt,
    clear_failed_attempts,
    upgrade_hash_if_legacy,
    hash_password
)
from security.validation import sanitize
from utils.audit import log_audit
from config import MAX_LOGIN_ATTEMPTS, LOCKOUT_SECONDS
from security.auth import _login_attempts
import time
from security.validation import validate_password_strength



class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()

    def authenticate(self, username: str, password: str) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
        """
        Returns: (user_id, username, role, error_message)
        If successful, error_message is None.
        """
        username = sanitize(username)
        password = (password or "").strip()

        if not username or not password:
            return None, None, None, "Please enter username and password"

        allowed, seconds = check_rate_limit(username)
        if not allowed:
            mins = seconds // 60
            return None, None, None, f"Too many failed attempts. Try again in {mins}m {seconds % 60}s."

        user = self.user_repo.get_by_username(username)
        if user and verify_password(password, user.password_hash):
            clear_failed_attempts(username)
            upgrade_hash_if_legacy(user.id, password, user.password_hash)
            log_audit(user.id, "LOGIN", f"User {username} logged in")
            return user.id, user.username, user.role, None
        else:
            record_failed_attempt(username)
            # Count remaining attempts
            
            key = f"login:{username.lower()}"
            attempts = [t for t in _login_attempts.get(key, []) if time.time() - t < LOCKOUT_SECONDS]
            attempts_left = MAX_LOGIN_ATTEMPTS - len(attempts)
            if attempts_left <= 0:
                return None, None, None, f"Account locked for {LOCKOUT_SECONDS//60} minutes."
            return None, None, None, f"Invalid username or password. {attempts_left} attempt(s) remaining."

    def change_password(self, user_id: int, old_password: str, new_password: str) -> Tuple[bool, str]:
      

        user = self.user_repo.get_by_id(user_id)
        if not user:
            return False, "User not found"

        if not verify_password(old_password, user.password_hash):
            return False, "Current password is incorrect"

        strength_error = validate_password_strength(new_password)
        if strength_error:
            return False, strength_error

        new_hash = hash_password(new_password)
        self.user_repo.update(user_id, {"password_hash": new_hash})
        log_audit(user_id, "CHANGE_PWD", "Password changed")
        return True, "Password changed successfully"