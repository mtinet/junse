"""
Windows에서 마지막 키보드/마우스 입력 시각을 감지합니다.

GetLastInputInfo()는 시스템 전역 입력을 감지하므로
어떤 프로그램(게임, 브라우저 등)을 쓰든 동작합니다.
관리자 권한도 필요 없습니다.
"""
import ctypes
from ctypes import wintypes


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


def get_idle_seconds() -> float:
    """
    마지막 키보드/마우스 입력 이후 경과한 초.
    0에 가까우면 방금 입력이 있었다는 뜻.
    """
    last_input = _LASTINPUTINFO()
    last_input.cbSize = ctypes.sizeof(_LASTINPUTINFO)

    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input)):
        return 0.0

    # GetTickCount: 시스템 부팅 후 경과한 밀리초
    current_tick = ctypes.windll.kernel32.GetTickCount()
    idle_ms = current_tick - last_input.dwTime
    return idle_ms / 1000.0


def is_user_active(idle_threshold_sec: float) -> bool:
    """idle_threshold_sec보다 입력이 최근에 있었으면 True."""
    return get_idle_seconds() < idle_threshold_sec
