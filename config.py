"""트래커 설정값."""
import os

# ─── 사용자 ───
USER_ID = "son"
DEVICE = "pc"

# ─── 자동 추적 ───
IDLE_THRESHOLD_SEC = 300       # 자리비움 판정 (5분)
HEARTBEAT_INTERVAL_SEC = 60    # 하트비트 주기 (1분)

# ─── Firebase ───
# 절대경로 사용 — 작업 스케줄러로 실행될 때 작업 디렉토리가 달라질 수 있음
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_CREDENTIALS_PATH = os.path.join(_BASE_DIR, "serviceAccountKey.json")

# Firestore 컬렉션
SESSIONS_COLLECTION = "sessions"
SELF_REPORTS_COLLECTION = "self_reports"
TAMPER_EVENTS_COLLECTION = "tamper_events"  # 종료/재시작/우회 시도 이력

# ─── GUI ───
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 680
WINDOW_TITLE = "내 컴퓨터 사용 기록"

# ─── 비밀번호 잠금 ───
# 첫 실행 시 비밀번호 설정 화면이 뜨고 여기 SHA-256 해시가 저장됨
PASSWORD_HASH_FILE = os.path.join(_BASE_DIR, ".password_hash")

# 비밀번호 시도 제한
MAX_PASSWORD_ATTEMPTS = 5
LOCKOUT_DURATION_SEC = 300  # 5분간 잠금

# ─── 워치독 ───
# 워치독은 트래커가 살아있는지 주기적으로 체크.
# 트래커가 죽었으면 자동 재실행하고 tamper_events에 기록.
WATCHDOG_CHECK_INTERVAL_SEC = 60   # 1분마다 체크
TRACKER_HEARTBEAT_FILE = os.path.join(_BASE_DIR, ".tracker_alive")
TRACKER_STOPPED_FLAG = os.path.join(_BASE_DIR, ".tracker_stopped")
WATCHDOG_HEARTBEAT_FILE = os.path.join(_BASE_DIR, ".watchdog_alive")

# 트래커가 마지막 신호 보낸 후 이 시간 지나면 죽었다고 판단
TRACKER_DEAD_THRESHOLD_SEC = 180  # 3분
