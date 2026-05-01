"""
워치독: 트래커가 살아있는지 감시하고 죽었으면 재시작.

강화된 버전:
  - 어떤 예외가 나도 절대 죽지 않음 (try/except로 모든 루프 감쌈)
  - 시작 시점부터 로그 파일에 기록 (디버깅용)
  - signal 핸들러로 종료 신호 무시 (Windows 종료 외에는)

판정 방식:
  - .tracker_alive 파일의 mtime이 최근이면 살아있음
  - 3분 이상 안 갱신되면 죽었다고 판단 → 재시작
"""
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import config


SCRIPT_DIR = Path(__file__).parent.absolute()
TRACKER_SCRIPT = SCRIPT_DIR / "main.py"
LOG_FILE = SCRIPT_DIR / "watchdog.log"

CREATE_NO_WINDOW = 0x08000000


def log(msg: str):
    """파일과 콘솔 둘 다에 기록 (콘솔 없을 수 있음)."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def is_tracker_alive() -> bool:
    """
    .tracker_alive 파일의 mtime이 최근이면 살아있음.
    """
    if not os.path.exists(config.TRACKER_HEARTBEAT_FILE):
        return False
    try:
        mtime = os.path.getmtime(config.TRACKER_HEARTBEAT_FILE)
        age = time.time() - mtime
        return age < config.TRACKER_DEAD_THRESHOLD_SEC
    except Exception:
        return False


def revive_tracker():
    """트래커를 새 프로세스로 시작 (콘솔 창 안 뜨게)."""
    try:
        subprocess.Popen(
            ["pythonw", str(TRACKER_SCRIPT)],
            cwd=str(SCRIPT_DIR),
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log("트래커 재시작됨")

        # Firebase 로깅은 실패할 수도 있으니 try로 감쌈
        try:
            import firebase_client
            firebase_client.log_tamper_event("watchdog_revived", {
                "reason": "tracker not alive",
            })
        except Exception as e:
            log(f"Firebase 로깅 실패 (무시): {e}")
    except Exception as e:
        log(f"트래커 재시작 실패: {e}")
        log(traceback.format_exc())


def update_self_heartbeat():
    """워치독 자기 하트비트 (트래커가 워치독 감시할 때 사용)."""
    try:
        with open(config.WATCHDOG_HEARTBEAT_FILE, "w") as f:
            f.write(str(time.time()))
    except Exception as e:
        log(f"워치독 하트비트 쓰기 실패: {e}")


def ignore_termination_signals():
    """
    종료 신호 일부를 무시하도록 설정.
    SIGINT만 무시. SIGTERM은 시스템 종료 시 정상 응답해야 함.
    """
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass


def main():
    log("=" * 50)
    log("워치독 시작")
    log(f"트래커 스크립트: {TRACKER_SCRIPT}")
    log(f"하트비트 파일: {config.TRACKER_HEARTBEAT_FILE}")
    log(f"체크 주기: {config.WATCHDOG_CHECK_INTERVAL_SEC}초")
    log("=" * 50)

    ignore_termination_signals()

    # Firebase 초기화는 실패해도 워치독은 계속 돌아야 함
    try:
        import firebase_client
        firebase_client.init()
    except Exception as e:
        log(f"Firebase 초기화 실패 (무시하고 계속): {e}")

    # 메인 루프 — 어떤 예외가 나도 절대 빠져나가지 않음
    while True:
        try:
            update_self_heartbeat()

            # 사용자가 비밀번호를 입력해 정상 종료했는지 확인
            if os.path.exists(config.TRACKER_STOPPED_FLAG):
                log("정상 종료 플래그 감지 → 워치독 감시 종료")
                # 플래그 파일 삭제 (다음 실행을 위해)
                try:
                    os.remove(config.TRACKER_STOPPED_FLAG)
                except Exception:
                    pass
                break # 루프 탈출 (워치독 종료)

            if not is_tracker_alive():
                log("트래커 사망 감지 → 재시작")
                revive_tracker()

        except Exception as e:
            # 절대 루프를 빠져나가지 않음
            log(f"루프 에러 (계속 진행): {e}")
            log(traceback.format_exc())

        try:
            time.sleep(config.WATCHDOG_CHECK_INTERVAL_SEC)
        except Exception:
            time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 최후의 안전장치 — main 자체가 죽어도 로그 남기고 끝
        log(f"치명적 오류: {e}")
        log(traceback.format_exc())
