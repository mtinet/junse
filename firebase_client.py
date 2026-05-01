"""
Firestore 연동.

컬렉션:
  - sessions       : 자동 추적이 1분마다 갱신
  - self_reports   : 자가 보고 시작/종료 버튼 기록
  - tamper_events  : 강제 종료/워치독 재시작/비번 시도 등 이력

serviceAccountKey.json이 없으면 더미 모드로 동작.
"""
import os
import socket
from datetime import datetime, timezone
from typing import Optional, List, Dict

import config

_db = None
_dummy = False


def init() -> bool:
    """Returns True = 실제 연결, False = 더미 모드."""
    global _db, _dummy

    if not os.path.exists(config.FIREBASE_CREDENTIALS_PATH):
        print(f"[!] {config.FIREBASE_CREDENTIALS_PATH} 없음. 더미 모드.")
        _dummy = True
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        cred = credentials.Certificate(config.FIREBASE_CREDENTIALS_PATH)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
        print("[OK] Firebase 연결 성공")
        return True
    except Exception as e:
        print(f"[!] Firebase 초기화 실패: {e}. 더미 모드 전환.")
        _dummy = True
        return False


def is_dummy() -> bool:
    return _dummy


# ─────────── 자동 추적 (sessions) ───────────

def create_auto_session(start_time: datetime, user_name: Optional[str] = None) -> Optional[str]:
    """
    새 세션 생성.

    endTime을 startTime과 같은 값으로 미리 채워둠. 첫 하트비트가
    도착하기 전에 프로세스가 죽어도 endTime이 비어있지 않게 하려는
    안전장치. 이후 하트비트가 갱신할 것.
    """
    data = {
        "userId": config.USER_ID,
        "userName": user_name or config.USER_ID,
        "device": config.DEVICE,
        "source": "auto",
        "startTime": start_time,
        "endTime": start_time,        # 미리 채워둠
        "lastHeartbeat": start_time,
        "durationSec": 0,
        "status": "active",
        "endReason": None,
        "hostname": socket.gethostname(),
    }
    if _dummy:
        sid = f"dummy_auto_{start_time.timestamp():.0f}"
        print(f"[DUMMY] auto session created: {sid} for {user_name}")
        return sid
    try:
        ref = _db.collection(config.SESSIONS_COLLECTION).document()
        ref.set(data)
        return ref.id
    except Exception as e:
        print(f"[ERR] create_auto_session: {e}")
        return None


def update_auto_heartbeat(session_id: str, now: datetime, duration_sec: int):
    """
    하트비트 갱신.

    핵심: endTime도 같이 갱신함. 이게 비정상 종료(정전, 강제 종료)
    대비책. 만약 다음 하트비트가 안 와도 endTime이 마지막 하트비트
    시각으로 이미 채워져 있으니까, 데이터 손실이 최대 1분으로 제한됨.

    status는 여전히 'active'로 둠. 정상 종료 시 'ended'로 바뀜.
    """
    if _dummy:
        return
    try:
        ref = _db.collection(config.SESSIONS_COLLECTION).document(session_id)
        ref.update({
            "lastHeartbeat": now,
            "endTime": now,           # 미리 채워둠 — 비정상 종료 대비
            "durationSec": duration_sec,
        })
    except Exception as e:
        print(f"[ERR] update_auto_heartbeat: {e}")


def end_auto_session(session_id: str, end_time: datetime, duration_sec: int, reason: str = "normal"):
    """
    reason 값:
      - "normal"       : 정상 (자리비움 등)
      - "shutdown"     : Windows 종료/로그오프
      - "crashed"      : 비정상 종료 후 재시작 시 발견
    """
    if _dummy:
        print(f"[DUMMY] auto session ended: {session_id}, {duration_sec}s, reason={reason}")
        return
    try:
        ref = _db.collection(config.SESSIONS_COLLECTION).document(session_id)
        ref.update({
            "endTime": end_time,
            "lastHeartbeat": end_time,
            "durationSec": duration_sec,
            "status": "ended",
            "endReason": reason,
        })
    except Exception as e:
        print(f"[ERR] end_auto_session: {e}")


def find_orphan_sessions(collection_name: str = config.SESSIONS_COLLECTION) -> List[Dict]:
    """
    이전 실행에서 endTime 없이 남은 세션을 찾아 반환.
    이 세션들은 비정상 종료된 것으로 간주.
    """
    if _dummy:
        return []
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
        q = (_db.collection(collection_name)
             .where(filter=FieldFilter("userId", "==", config.USER_ID))
             .where(filter=FieldFilter("status", "==", "active")))
        docs = q.stream()
        result = []
        for doc in docs:
            d = doc.to_dict()
            d["_id"] = doc.id
            result.append(d)
        return result
    except Exception as e:
        print(f"[ERR] find_orphan_sessions ({collection_name}): {e}")
        return []


def close_orphan_session(session_id: str, last_heartbeat: datetime, duration_sec: int, collection_name: str = config.SESSIONS_COLLECTION, end_reason: str = "crashed"):
    """비정상 종료된 세션을 lastHeartbeat 기준으로 마감."""
    if _dummy:
        return
    try:
        ref = _db.collection(collection_name).document(session_id)
        ref.update({
            "endTime": last_heartbeat,
            "durationSec": duration_sec,
            "status": "ended",
            "endReason": end_reason,
        })
    except Exception as e:
        print(f"[ERR] close_orphan_session ({collection_name}): {e}")


# ─────────── 자가 보고 (self_reports) ───────────

def create_self_report(start_time: datetime, user_name: Optional[str] = None) -> Optional[str]:
    data = {
        "userId": config.USER_ID,
        "userName": user_name or config.USER_ID, # 이름이 없으면 기본 ID 사용
        "device": config.DEVICE,
        "source": "self",
        "startTime": start_time,
        "endTime": start_time,        # 미리 채워둠 (자동 추적과 동일한 안전장치)
        "lastHeartbeat": start_time,  # 추가: 대시보드 상태 확인용
        "durationSec": 0,
        "status": "active",
        "hostname": socket.gethostname(), # 추가: 대시보드 표시용
    }
    if _dummy:
        sid = f"dummy_self_{start_time.timestamp():.0f}"
        print(f"[DUMMY] self report created: {sid} for {user_name}")
        return sid
    try:
        ref = _db.collection(config.SELF_REPORTS_COLLECTION).document()
        ref.set(data)
        return ref.id
    except Exception as e:
        print(f"[ERR] create_self_report: {e}")
        return None


def end_self_report(report_id: str, end_time: datetime, duration_sec: int):
    if _dummy:
        print(f"[DUMMY] self report ended: {report_id}, {duration_sec}s")
        return
    try:
        ref = _db.collection(config.SELF_REPORTS_COLLECTION).document(report_id)
        ref.update({
            "endTime": end_time,
            "lastHeartbeat": end_time, # 종료 시에도 갱신
            "durationSec": duration_sec,
            "status": "ended",
        })
    except Exception as e:
        print(f"[ERR] end_self_report: {e}")


def update_self_report_heartbeat(report_id: str, now: datetime, duration_sec: int):
    """
    자가 보고 진행 중 하트비트.
    endTime을 미리 갱신해서 비정상 종료에 대비.
    """
    if _dummy:
        return
    try:
        ref = _db.collection(config.SELF_REPORTS_COLLECTION).document(report_id)
        ref.update({
            "endTime": now,           # 미리 채워둠
            "lastHeartbeat": now,     # 추가: 대시보드 상태 확인용
            "durationSec": duration_sec,
        })
    except Exception as e:
        print(f"[ERR] update_self_report_heartbeat: {e}")


# ─────────── 기기 상태 (status) ───────────

def update_device_status(is_active: bool):
    """
    컴퓨터가 켜져 있는지 여부를 별도로 기록.
    세션 기록과 별개로 '컴퓨터 전원' 상태를 대시보드에 보여주기 위함.
    """
    if _dummy:
        return
    try:
        doc_id = f"{config.USER_ID}_{config.DEVICE}"
        ref = _db.collection("status").document(doc_id)
        ref.set({
            "userId": config.USER_ID,
            "device": config.DEVICE,
            "hostname": socket.gethostname(),
            "lastHeartbeat": datetime.now(timezone.utc),
            "isActive": is_active, # 프로그램 실행 중이면 True
        }, merge=True)
    except Exception as e:
        print(f"[ERR] update_device_status: {e}")


def log_tamper_event(event_type: str, details: Optional[Dict] = None, skip_cleanup: bool = False):
    """
    event_type 예시:
      - "tracker_started"        : 트래커 시작 (정상)
      - "tracker_normal_exit"    : 정상 종료 (비번 입력 후)
      - "tracker_crashed"        : 비정상 종료 발견 (재시작 시)
      - "watchdog_revived"       : 워치독이 트래커 재실행
      - "password_failed"        : 비밀번호 시도 실패
      - "password_lockout"       : 5회 실패로 잠금
      - "shutdown_signal"        : Windows 종료 신호 받음
    """
    data = {
        "userId": config.USER_ID,
        "device": config.DEVICE,
        "type": event_type,
        "timestamp": datetime.now(timezone.utc),
        "hostname": socket.gethostname(),
        "details": details or {},
    }
    if _dummy:
        print(f"[DUMMY] tamper event: {event_type} {details or ''}")
        return
    try:
        _db.collection(config.TAMPER_EVENTS_COLLECTION).add(data)

        # 시스템 종료 시에는 시간이 부족하므로 정리 로직 건너뜀
        if skip_cleanup:
            return

        # 이벤트 기록 후 오래된 데이터 정리 (최근 100개만 유지)
        cleanup_tamper_events(limit=100)
    except Exception as e:
        print(f"[ERR] log_tamper_event: {e}")

def cleanup_tamper_events(limit: int = 100):
    """오래된 보안 이벤트를 삭제하여 최신 N개만 유지."""
    if _dummy:
        return
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
        from firebase_admin import firestore
        # 100개 이후의 문서들을 가져옴
        docs = (_db.collection(config.TAMPER_EVENTS_COLLECTION)
                .where(filter=FieldFilter("userId", "==", config.USER_ID))
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .offset(limit)
                .stream())
        
        count = 0
        batch = _db.batch()
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
            if count >= 50: # 한 번에 최대 50개씩 (Firestore 일괄 처리 제한)
                break
        
        if count > 0:
            batch.commit()
            print(f"[Cleanup] 오래된 보안 이벤트 {count}건 삭제됨")
    except Exception as e:
        print(f"[ERR] cleanup_tamper_events: {e}")
