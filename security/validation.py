import re

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize(text: str | None, max_len: int = 500) -> str:
    if not text:
        return ""
    return _CTRL.sub("", str(text))[:max_len].strip()


def safe_float(val, default=0.0, lo=0.0, hi=1e9) -> float:
    try:
        return max(lo, min(hi, float(val or default)))
    except (ValueError, TypeError):
        return default


def safe_int(val, default=0, lo=0, hi=10_000_000) -> int:
    try:
        return max(lo, min(hi, int(float(val or default))))
    except (ValueError, TypeError):
        return default


def validate_password_strength(pwd: str) -> str | None:
    if not pwd or len(pwd) < 6:
        return "Password must be at least 6 characters"
    if not re.search(r"[A-Za-z]", pwd):
        return "Must include at least one letter"
    if not re.search(r"[0-9]", pwd):
        return "Must include at least one digit"
    return None