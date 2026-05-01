"""
컴퓨터 사용 시간 트래커 - 진입점.

데이터 무결성 전략:
  1. 하트비트 시 endTime을 미리 채움 → 비정상 종료해도 데이터 손실 ≤ 1분
  2. signal 핸들러로 SIGTERM/SIGBREAK 캐치 → 대부분의 종료 케이스 정리
  3. sys.excepthook으로 unhandled exception 캐치
  4. atexit으로 마지막 정리

이 4중 안전장치로 부팅 시 orphan cleanup이 거의 필요 없게 됨.
다만 정전이나 BSOD 같은 극단적 상황 대비로 cleanup은 남겨둠.
"""
import atexit
import signal
import socket
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import firebase_client


# 전역 참조 — signal 핸들러에서 접근하기 위함
_app_ref = None
_lock_socket = None


def check_singleton():
    """
    포트 바인딩을 이용한 싱글톤 체크.
    프로세스가 종료되면 OS가 포트를 자동으로 해제함.
    """
    global _lock_socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 50382는 'son'을 숫자로 대략 변환한 임의의 포트
        _lock_socket.bind(('127.0.0.1', 50382))
        return True
    except socket.error:
        return False


def cleanup_orphan_sessions():
    """
    이전 실행에서 status='active'로 남은 세션을 'ended'로 마감.
    (sessions 및 self_reports 두 컬렉션 모두 확인)
    """
    import config
    import os
    
    # 정상 종료 플래그 확인
    stopped_cleanly = os.path.exists(config.TRACKER_STOPPED_FLAG)
    if stopped_cleanly:
        print("[Info] 정상 종료 흔적 발견. 미마감 세션이 있다면 시스템 종료로 인해 발생했을 가능성이 높음.")

    collections = [config.SESSIONS_COLLECTION, config.SELF_REPORTS_COLLECTION]
    total_count = 0

    for coll in collections:
        try:
            orphans = firebase_client.find_orphan_sessions(coll)
            if not orphans:
                continue

            for orphan in orphans:
                sid = orphan["_id"]
                last_hb = orphan.get("lastHeartbeat") or orphan.get("startTime")
                duration = orphan.get("durationSec", 0)
                if last_hb is None:
                    continue
                
                # 정상 종료 플래그가 있으면 'shutdown'으로, 없으면 'crashed'로 마감
                end_reason = "shutdown" if stopped_cleanly else "crashed"
                firebase_client.close_orphan_session(
                    sid, last_hb, duration, collection_name=coll, end_reason=end_reason
                )
                
                # 자동 추적 세션인 경우에만 변조 이벤트 기록
                if coll == config.SESSIONS_COLLECTION:
                    # 비정상 종료(crashed)인 경우에만 보안 경고(tamper event) 기록
                    if not stopped_cleanly:
                        firebase_client.log_tamper_event("tracker_crashed", {
                            "session_id": sid,
                            "duration_sec": duration,
                            "type": "auto_session",
                            "note": "비정상 종료 - 하트비트 시점까지의 데이터는 보존됨",
                        })
                else:
                    # 자가 보고는 경고까지는 아니지만 crashed인 경우만 기록
                    if not stopped_cleanly:
                        firebase_client.log_tamper_event("tracker_crashed", {
                            "session_id": sid,
                            "duration_sec": duration,
                            "type": "self_report",
                            "note": "자가 보고 비정상 종료 마감",
                        })
                total_count += 1
        except Exception as e:
            print(f"[ERR] cleanup_orphan_sessions for {coll}: {e}")

    # 처리가 끝난 후 플래그 삭제 (이미 삭제되었을 수도 있지만 확인 사살)
    if stopped_cleanly:
        try:
            os.remove(config.TRACKER_STOPPED_FLAG)
        except Exception:
            pass

    if total_count > 0:
        print(f"[!] 미마감 세션/보고 {total_count}건 정리 완료")
    return total_count


def emergency_cleanup(reason: str = "unknown"):
    """
    프로세스가 종료될 때 마지막으로 호출되는 정리 함수.

    여러 경로에서 중복 호출될 수 있지만, GUI._do_close()와
    AutoTracker.stop()이 idempotent하게 짜여있어서 안전.
    """
    global _app_ref
    if _app_ref is None:
        return
    try:
        _app_ref._do_close(reason=reason)
        print(f"[Emergency] cleanup 완료 (reason={reason})")
    except Exception as e:
        print(f"[Emergency ERR] {e}")
    finally:
        _app_ref = None


def setup_signal_handlers():
    """
    OS가 보내는 종료 신호를 모두 캐치.

    Windows에서 받을 수 있는 신호:
      - SIGINT (Ctrl+C) — 거의 안 옴 (콘솔 없음)
      - SIGTERM — 시스템 종료, 작업 관리자 "작업 끝내기"
      - SIGBREAK — Ctrl+Break, 일부 Windows 종료 시나리오
    """
    def handler(signum, frame):
        sig_name = signal.Signals(signum).name
        print(f"[Signal] {sig_name} 수신 → 정리 후 종료")
        emergency_cleanup(reason="shutdown")
        sys.exit(0)

    for sig_name in ["SIGINT", "SIGTERM", "SIGBREAK"]:
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                # 일부 환경에서는 못 잡는 시그널이 있을 수 있음
                pass


def setup_exception_hook():
    """
    잡히지 않은 예외 발생 시에도 세션을 마감하도록.
    """
    original_hook = sys.excepthook

    def hook(exc_type, exc_value, exc_tb):
        # 에러 로그 파일에 기록
        try:
            log_path = Path(__file__).parent / "tracker_error.log"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().isoformat()}] 예외 발생: {exc_value}\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:
            pass

        # 세션 마감 시도
        try:
            emergency_cleanup(reason="exception")
        except Exception:
            pass

        # 원래 hook도 호출 (콘솔 출력 등)
        original_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = hook


def register_app(app):
    """GUI 앱 인스턴스를 전역으로 등록 (signal 핸들러용)."""
    global _app_ref
    _app_ref = app


def main():
    print("=" * 50)
    print(" 컴퓨터 사용 시간 트래커")
    print("=" * 50)

    # 0. 중복 실행 방지
    if not check_singleton():
        print("[!] 이미 프로그램이 실행 중입니다. 중복 실행을 방지하기 위해 종료합니다.")
        sys.exit(0)

    # 1. 안전장치 먼저 설치 (GUI 만들기 전에)
    setup_signal_handlers()
    setup_exception_hook()
    atexit.register(emergency_cleanup, reason="atexit")

    # 2. Firebase 초기화
    firebase_ok = firebase_client.init()

    # 3. 이전 비정상 종료 흔적 정리 (드물게 발생)
    if firebase_ok:
        try:
            cleanup_orphan_sessions()
        except Exception as e:
            print(f"[ERR] orphan cleanup: {e}")

    # 4. GUI 시작
    # GUI를 import here로 늦게 임포트 — customtkinter 초기화가 무거움
    from gui import TrackerApp
    app = TrackerApp(firebase_ok=firebase_ok)
    register_app(app)
    app.mainloop()

    print("프로그램 종료")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        emergency_cleanup(reason="keyboard_interrupt")
        sys.exit(0)
    except Exception as e:
        # 마지막 안전장치
        try:
            log_path = Path(__file__).parent / "tracker_error.log"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().isoformat()}] {e}\n")
                f.write(traceback.format_exc())
        except Exception:
            pass
        emergency_cleanup(reason="top_level_exception")
        raise
