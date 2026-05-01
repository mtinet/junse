"""
워치독 감시자.

트래커가 별도 스레드로 워치독이 살아있는지 1분마다 체크하고
죽었으면 다시 띄움. 워치독은 이미 트래커를 감시하므로
이 모듈을 추가하면 상호 감시 체계가 완성됨.

상호 감시 흐름:
  - 워치독이 트래커 죽음 감지 → 트래커 부활
  - 트래커가 워치독 죽음 감지 → 워치독 부활
  - 둘 다 죽으면 → 5분 후 작업 스케줄러가 워치독 부활 → 위 흐름 시작
"""
import os
import subprocess
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import config


SCRIPT_DIR = Path(__file__).parent.absolute()
WATCHDOG_SCRIPT = SCRIPT_DIR / "watchdog.py"

CREATE_NO_WINDOW = 0x08000000


class WatchdogMonitor:
    """별도 스레드에서 워치독이 살아있는지 감시."""

    # 트래커 하트비트와 동일하게 3분 임계값
    DEAD_THRESHOLD_SEC = 180
    CHECK_INTERVAL_SEC = 60  # 1분마다 체크

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._stopped = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._stopped = False
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="WatchdogMonitor"
        )
        self._thread.start()

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        # 시작 직후 60초 대기 — 워치독이 시작할 시간 줌
        # (트래커가 먼저 실행되는 케이스 대비)
        if self._stop_event.wait(timeout=60):
            return

        while not self._stop_event.is_set():
            try:
                if not self._is_watchdog_alive():
                    self._log("워치독 사망 감지 → 재시작 시도")
                    self._revive_watchdog()
            except Exception as e:
                self._log(f"감시 에러 (계속 진행): {e}")
                self._log(traceback.format_exc())

            self._stop_event.wait(timeout=self.CHECK_INTERVAL_SEC)

    def _is_watchdog_alive(self) -> bool:
        """워치독 하트비트 파일 mtime 확인."""
        path = config.WATCHDOG_HEARTBEAT_FILE
        if not os.path.exists(path):
            return False
        try:
            age = time.time() - os.path.getmtime(path)
            return age < self.DEAD_THRESHOLD_SEC
        except Exception:
            return False

    def _revive_watchdog(self):
        """워치독을 새 프로세스로 시작."""
        try:
            subprocess.Popen(
                ["pythonw", str(WATCHDOG_SCRIPT)],
                cwd=str(SCRIPT_DIR),
                creationflags=CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._log("워치독 재시작됨")

            # tamper event 기록 (실패해도 무시)
            try:
                import firebase_client
                firebase_client.log_tamper_event("watchdog_revived_by_tracker", {
                    "reason": "watchdog heartbeat stale",
                })
            except Exception:
                pass
        except Exception as e:
            self._log(f"워치독 재시작 실패: {e}")

    def _log(self, msg: str):
        """파일에 로그 (트래커 콘솔도 없으니 파일로)."""
        try:
            log_path = SCRIPT_DIR / "watchdog_monitor.log"
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass
