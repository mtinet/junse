"""
비밀번호 잠금 관리.

비밀번호는 SHA-256 해시로 저장 (평문 저장 안 함).
파일이 없으면 첫 실행 = 비밀번호 미설정 상태.
"""
import hashlib
import os
import time
from typing import Optional

import config


# salt를 코드에 박아둠 - 이게 새어나가도 큰 문제는 아님
# (해시를 풀어도 비번을 알아내려면 brute force 필요)
_SALT = b"son_tracker_2026_salt_v1"


def _hash(password: str) -> str:
    h = hashlib.sha256()
    h.update(_SALT)
    h.update(password.encode("utf-8"))
    return h.hexdigest()


def is_password_set() -> bool:
    """비밀번호가 설정되어 있는지."""
    return os.path.exists(config.PASSWORD_HASH_FILE)


def set_password(password: str) -> bool:
    """새 비밀번호 설정."""
    if not password or len(password) < 4:
        return False
    try:
        with open(config.PASSWORD_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(_hash(password))
        return True
    except Exception as e:
        print(f"[ERR] 비밀번호 저장 실패: {e}")
        return False


def verify_password(password: str) -> bool:
    """비밀번호 검증."""
    if not is_password_set():
        return False
    try:
        with open(config.PASSWORD_HASH_FILE, "r", encoding="utf-8") as f:
            stored_hash = f.read().strip()
        return stored_hash == _hash(password)
    except Exception as e:
        print(f"[ERR] 비밀번호 읽기 실패: {e}")
        return False


# ─── 시도 제한 (메모리 기반, 프로세스 살아있는 동안만 유지) ───

_failed_attempts = 0
_lockout_until: Optional[float] = None  # monotonic time


def is_locked_out() -> bool:
    if _lockout_until is None:
        return False
    return time.monotonic() < _lockout_until


def lockout_remaining_sec() -> int:
    if _lockout_until is None:
        return 0
    remaining = _lockout_until - time.monotonic()
    return max(0, int(remaining))


def record_failed_attempt():
    """실패 시도 기록. 한도 초과하면 잠금."""
    global _failed_attempts, _lockout_until
    _failed_attempts += 1
    if _failed_attempts >= config.MAX_PASSWORD_ATTEMPTS:
        _lockout_until = time.monotonic() + config.LOCKOUT_DURATION_SEC
        _failed_attempts = 0  # 카운터 리셋


def record_successful_attempt():
    """성공 시 카운터 리셋."""
    global _failed_attempts, _lockout_until
    _failed_attempts = 0
    _lockout_until = None


def get_failed_count() -> int:
    return _failed_attempts
