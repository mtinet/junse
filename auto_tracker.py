"""
자동 추적 백그라운드 스레드.
"""
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Callable

import config
import firebase_client
from activity_monitor import is_user_active


class AutoTracker:
    def __init__(self, status_callback: Optional[Callable[[dict], None]] = None):
        self._callback = status_callback
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock() # 추가: 스레드 경합 방지용

        self._session_id: Optional[str] = None
        self._accumulated_sec: int = 0
        self._last_heartbeat_monotonic: float = 0.0
        self._last_status_heartbeat_monotonic: float = 0.0
        self._last_alive_file_write: float = 0.0
        self._self_active = False

    def set_self_active(self, active: bool):
        self._self_active = active
        # 자가 보고 시작 시 이미 진행 중인 자동 세션이 있다면 마감
        if active and self._session_id is not None:
            self._end_session_if_active(reason="normal")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="AutoTracker")
        self._thread.start()

    def stop(self, reason: str = "normal", fast: bool = False):
        if getattr(self, "_stopped", False):
            return
        self._stopped = True
        self._stop_event.set()

        # 시스템 종료(fast=True) 시에는 네트워크 마감(Firestore)을 최우선으로 실행.
        # thread.join을 먼저 하면 0.5~1초를 그냥 버리게 되어 OS가 프로세스를 죽일 위험이 커짐.
        if fast:
            self._end_session_if_active(reason=reason)
            if self._thread:
                self._thread.join(timeout=0.1) # 아주 짧게만 대기
        else:
            if self._thread:
                self._thread.join(timeout=3)
            self._end_session_if_active(reason=reason)
        
        # 프로그램 종료 시 즉시 오프라인 상태로 업데이트
        try:
            firebase_client.update_device_status(False)
        except Exception:
            pass

        try:
            if os.path.exists(config.TRACKER_HEARTBEAT_FILE):
                os.remove(config.TRACKER_HEARTBEAT_FILE)
        except Exception:
            pass

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._update_alive_file()
                self._status_heartbeat_if_due()
                user_is_moving = is_user_active(config.IDLE_THRESHOLD_SEC)

                if user_is_moving:
                    # [제안된 개선안 적용] 자가 보고 중이 아닐 때만 카운트 및 기록
                    if not self._self_active:
                        self._accumulated_sec += 1
                        if self._session_id is None:
                            self._start_session()
                        else:
                            self._heartbeat_if_due()
                    else:
                        # 자가 보고가 시작되면 진행 중인 AUTO 세션은 즉시 마감
                        if self._session_id is not None:
                            self._end_session_if_active(reason="normal")
                else:
                    # 자리비움이면 모두 종료 및 초기화
                    if self._session_id is not None:
                        self._end_session_if_active(reason="normal")
                    self._accumulated_sec = 0

                # 자가 보고 중이면 active여도 GUI에는 대기 중으로 보이게 함
                display_active = user_is_moving and not self._self_active
                self._notify(active=display_active)
            except Exception as e:
                print(f"[AutoTracker ERR] {e}")

            self._stop_event.wait(timeout=1.0)

    def _update_alive_file(self):
        now = time.monotonic()
        if now - self._last_alive_file_write < 5.0:
            return
        try:
            with open(config.TRACKER_HEARTBEAT_FILE, "w") as f:
                f.write(str(time.time()))
            self._last_alive_file_write = now
        except Exception:
            pass

    def _status_heartbeat_if_due(self):
        now = time.monotonic()
        if self._last_status_heartbeat_monotonic == 0 or (now - self._last_status_heartbeat_monotonic >= 60.0):
            threading.Thread(target=firebase_client.update_device_status, args=(True,), daemon=True).start()
            self._last_status_heartbeat_monotonic = now

    def _start_session(self):
        now = datetime.now(timezone.utc)
        # _accumulated_sec 리셋 제거 (연속성 유지)
        self._session_id = firebase_client.create_auto_session(now)
        self._last_heartbeat_monotonic = time.monotonic()
        print(f"[Auto] ▶ 활동 감지: 자동 기록 시작")

    def _heartbeat_if_due(self):
        if self._session_id is None:
            return
        elapsed = time.monotonic() - self._last_heartbeat_monotonic
        if elapsed < config.HEARTBEAT_INTERVAL_SEC:
            return
        firebase_client.update_auto_heartbeat(
            self._session_id, datetime.now(timezone.utc), self._accumulated_sec
        )
        self._last_heartbeat_monotonic = time.monotonic()

    def _end_session_if_active(self, reason: str = "normal"):
        with self._lock:
            if self._session_id is None:
                return
            firebase_client.end_auto_session(
                self._session_id, datetime.now(timezone.utc), self._accumulated_sec, reason=reason
            )
            print(f"[Auto] ⏹ 세션 종료 (총 {self._accumulated_sec}초)")
            self._session_id = None

    def _notify(self, active: bool):
        if self._callback:
            try:
                self._callback({"active": active, "duration_sec": self._accumulated_sec})
            except Exception:
                pass
