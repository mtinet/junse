"""CustomTkinter 기반 모던 GUI + 비밀번호 잠금."""
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import customtkinter as ctk

import config
import firebase_client
import password_lock
from auto_tracker import AutoTracker
from password_dialog import PasswordSetupDialog, PasswordPromptDialog
from watchdog_monitor import WatchdogMonitor


# ─── 색상 ───
COLOR_BG = "#F7F6F2"
COLOR_CARD = "#FFFFFF"
COLOR_BORDER = "#E5E4DD"
COLOR_TEXT_PRIMARY = "#2C2C2A"
COLOR_TEXT_SECONDARY = "#7A7975"

COLOR_ACTIVE_BG = "#E1F5EE"
COLOR_ACTIVE_FG = "#0F6E56"
COLOR_IDLE_BG = "#F1EFE8"
COLOR_IDLE_FG = "#5F5E5A"

COLOR_START = "#1D9E75"
COLOR_START_HOVER = "#0F6E56"
COLOR_END = "#D85A30"
COLOR_END_HOVER = "#993C1D"

COLOR_OK = "#0F6E56"
COLOR_WARN = "#BA7517"
COLOR_LOCK = "#7F77DD"


def fmt_hms(total_sec: int) -> str:
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class TrackerApp(ctk.CTk):
    def __init__(self, firebase_ok: bool):
        super().__init__()

        ctk.set_appearance_mode("light")
        self.title(config.WINDOW_TITLE)
        self.geometry(f"{config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT}")
        self.minsize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.configure(fg_color=COLOR_BG)

        self.firebase_ok = firebase_ok
        self.app_start_time = datetime.now() # 앱 시작 시간 기록
        self.auto_active = False
        self.auto_duration_sec = 0

        self.self_report_id: Optional[str] = None
        self.self_report_start: Optional[datetime] = None
        self._self_timer_job = None
        self._total_timer_job = None

        self._allow_close = False  # 비번 통과 시에만 True

        # 시작 시 혹시 남아있을 종료 플래그 삭제
        if os.path.exists(config.TRACKER_STOPPED_FLAG):
            try:
                os.remove(config.TRACKER_STOPPED_FLAG)
            except Exception:
                pass

        # 첫 실행이면 비밀번호 설정 강제
        if not password_lock.is_password_set():
            self.after(100, self._force_password_setup)

        self._build_header()
        self._build_lock_card()
        self._build_total_card() # 추가: 총 사용 시간
        self._build_auto_card()
        self._build_self_card()
        self._build_footer()

        # ... (rest of init)
        self._tick_total_timer() # 총 시간 타이머 시작

        # Windows 종료/로그오프 시그널 캐치
        self._register_shutdown_handlers()

        self.auto_tracker = AutoTracker(status_callback=self._on_auto_status)
        self.auto_tracker.start()

        # 워치독 감시자 시작 (워치독이 죽으면 트래커가 살림)
        self.watchdog_monitor = WatchdogMonitor()
        self.watchdog_monitor.start()

        # 시작 이벤트 기록
        firebase_client.log_tamper_event("tracker_started")

        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

    # ─── 비밀번호 첫 설정 ───

    def _force_password_setup(self):
        dlg = PasswordSetupDialog(self)
        self.wait_window(dlg)
        if not dlg.result_set:
            # 설정 안 했으면 앱 종료 (이론상 불가능 - 다이얼로그가 안 닫힘)
            self._allow_close = True
            self.destroy()

    # ─── UI ───

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="📚 내 컴퓨터 사용 기록",
            font=("Malgun Gothic", 18, "bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w")

        status_text = "● Firebase 연결됨" if self.firebase_ok else "● 더미 모드 (콘솔 출력만)"
        status_color = COLOR_OK if self.firebase_ok else COLOR_WARN
        ctk.CTkLabel(
            header,
            text=status_text,
            font=("Malgun Gothic", 11),
            text_color=status_color,
        ).pack(anchor="w", pady=(2, 0))

    def _build_lock_card(self):
        """잠금 안내 (작은 인포 박스)."""
        bar = ctk.CTkFrame(
            self,
            fg_color="#EEEDFE",
            corner_radius=8,
            border_color="#CECBF6",
            border_width=1,
        )
        bar.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(
            bar,
            text="🔒  종료하려면 보호자 비밀번호가 필요해요",
            font=("Malgun Gothic", 11),
            text_color="#3C3489",
        ).pack(pady=8)

    def _build_total_card(self):
        """프로그램 시작 후 총 누적 시간."""
        card = ctk.CTkFrame(
            self, fg_color="#F8F9FF", border_color="#E0E4FF",
            border_width=1, corner_radius=12,
        )
        card.pack(fill="x", padx=20, pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(
            inner, text="총 가동 시간 (컴퓨터 켜진 후)",
            font=("Malgun Gothic", 11, "bold"), text_color="#5C677D",
        ).pack(side="left")

        self.total_duration_label = ctk.CTkLabel(
            inner, text="00:00:00",
            font=("Consolas", 16, "bold"), text_color="#3F4EAD",
        )
        self.total_duration_label.pack(side="right")

    def _build_auto_card(self):
        card = ctk.CTkFrame(
            self, fg_color=COLOR_CARD, border_color=COLOR_BORDER,
            border_width=1, corner_radius=12,
        )
        card.pack(fill="x", padx=20, pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        ctk.CTkLabel(
            inner, text="자동 추적",
            font=("Malgun Gothic", 11), text_color=COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        self.auto_status_frame = ctk.CTkFrame(
            inner, fg_color=COLOR_IDLE_BG, corner_radius=8, height=70,
        )
        self.auto_status_frame.pack(fill="x", pady=(8, 0))
        self.auto_status_frame.pack_propagate(False)

        status_inner = ctk.CTkFrame(self.auto_status_frame, fg_color="transparent")
        status_inner.place(relx=0.5, rely=0.5, anchor="center")

        self.auto_status_label = ctk.CTkLabel(
            status_inner, text="대기 중",
            font=("Malgun Gothic", 13, "bold"), text_color=COLOR_IDLE_FG,
        )
        self.auto_status_label.pack()

        self.auto_duration_label = ctk.CTkLabel(
            status_inner, text="00:00:00",
            font=("Consolas", 20, "bold"), text_color=COLOR_IDLE_FG,
        )
        self.auto_duration_label.pack(pady=(2, 0))

        ctk.CTkLabel(
            inner, text="키보드/마우스 입력이 있어야 시간이 쌓여요",
            font=("Malgun Gothic", 10), text_color=COLOR_TEXT_SECONDARY,
        ).pack(anchor="w", pady=(8, 0))

    def _build_self_card(self):
        card = ctk.CTkFrame(
            self, fg_color=COLOR_CARD, border_color=COLOR_BORDER,
            border_width=1, corner_radius=12,
        )
        card.pack(fill="x", padx=20, pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        ctk.CTkLabel(
            inner, text="자가 보고",
            font=("Malgun Gothic", 11), text_color=COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        self.self_duration_label = ctk.CTkLabel(
            inner, text="00:00:00",
            font=("Consolas", 28, "bold"), text_color=COLOR_TEXT_PRIMARY,
        )
        self.self_duration_label.pack(pady=(8, 4))

        self.self_status_label = ctk.CTkLabel(
            inner, text="시작 버튼을 눌러 기록을 시작해요",
            font=("Malgun Gothic", 11), text_color=COLOR_TEXT_SECONDARY,
        )
        self.self_status_label.pack(pady=(0, 12))

        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 5))

        self.start_btn = ctk.CTkButton(
            btn_frame, text="▶  시작", command=self._on_start_click,
            fg_color=COLOR_START, hover_color=COLOR_START_HOVER,
            text_color="white", font=("Malgun Gothic", 16, "bold"),
            height=64, corner_radius=12,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.end_btn = ctk.CTkButton(
            btn_frame, text="⏹  종료", command=self._on_end_click,
            fg_color=COLOR_END, hover_color=COLOR_END_HOVER,
            text_color="white", font=("Malgun Gothic", 16, "bold"),
            height=64, corner_radius=12, state="disabled",
        )
        self.end_btn.pack(side="left", expand=True, fill="x", padx=(8, 0))

    def _build_footer(self):
        ctk.CTkLabel(
            self, text="이 창은 닫지 말고 최소화만 해줘 :)",
            font=("Malgun Gothic", 10), text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="bottom", pady=(10, 25))

    # ─── 자동 추적 콜백 ───

    def _on_auto_status(self, status: dict):
        self.after(0, self._apply_auto_status, status)

    def _apply_auto_status(self, status: dict):
        active = status["active"]
        duration = status["duration_sec"]

        if active:
            self.auto_status_frame.configure(fg_color=COLOR_ACTIVE_BG)
            self.auto_status_label.configure(text="● 사용 중", text_color=COLOR_ACTIVE_FG)
            self.auto_duration_label.configure(text=fmt_hms(duration), text_color=COLOR_ACTIVE_FG)
        else:
            self.auto_status_frame.configure(fg_color=COLOR_IDLE_BG)
            self.auto_status_label.configure(text="대기 중", text_color=COLOR_IDLE_FG)
            self.auto_duration_label.configure(text=fmt_hms(duration), text_color=COLOR_IDLE_FG)

    # ─── 자가 보고 ───

    def _on_start_click(self):
        # 이름 입력받기
        dialog = ctk.CTkInputDialog(text="사용자 이름을 입력하세요:", title="시작하기")
        # 부모 창 중앙에 띄우기 위해 위치 계산 (선택 사항이나 권장)
        user_name = dialog.get_input()
        
        if user_name is None or user_name.strip() == "":
            return # 취소하거나 빈 칸이면 시작 안 함

        self.start_btn.configure(state="disabled")
        threading.Thread(target=self._do_start, args=(user_name.strip(),), daemon=True).start()

    def _do_start(self, user_name: str):
        try:
            now = datetime.now(timezone.utc)
            report_id = firebase_client.create_self_report(now, user_name=user_name)
            if report_id is None:
                self.after(0, self._show_error, "시작 기록 실패")
                return
            self.after(0, self._on_started, report_id, now, user_name)
        except Exception as e:
            self.after(0, self._show_error, f"오류: {e}")

    def _on_started(self, report_id: str, start_time: datetime, user_name: str):
        self.self_report_id = report_id
        self.self_report_start = start_time
        self.start_btn.configure(state="disabled")
        self.end_btn.configure(state="normal")
        self.self_status_label.configure(text=f"● {user_name} 기록 중 — 즐겁게 보내!", text_color=COLOR_ACTIVE_FG)
        self.self_duration_label.configure(text_color=COLOR_ACTIVE_FG)
        
        # 자가 보고 시작됨을 알림 (이후 AUTO 기록은 중단됨)
        self.auto_tracker.set_self_active(True)
        
        self._tick_self_timer()

    def _on_end_click(self):
        if self.self_report_id is None:
            return
        self.end_btn.configure(state="disabled")
        threading.Thread(target=self._do_end, daemon=True).start()

    def _do_end(self):
        try:
            now = datetime.now(timezone.utc)
            elapsed = int((now - self.self_report_start).total_seconds())
            firebase_client.end_self_report(self.self_report_id, now, elapsed)
            self.after(0, self._on_ended, elapsed)
        except Exception as e:
            self.after(0, self._show_error, f"오류: {e}")

    def _on_ended(self, elapsed_sec: int):
        if self._self_timer_job:
            self.after_cancel(self._self_timer_job)
            self._self_timer_job = None
        mins = elapsed_sec // 60
        self.self_report_id = None
        self.self_report_start = None

        # 자가 보고 종료됨을 알림 (이후 다시 AUTO 추적 활성화)
        self.auto_tracker.set_self_active(False)

        self.start_btn.configure(state="normal")
        self.end_btn.configure(state="disabled")
        self.self_duration_label.configure(text="00:00:00", text_color=COLOR_TEXT_PRIMARY)
        self.self_status_label.configure(
            text=f"기록 종료 ({mins}분 사용) - 대기 중", text_color=COLOR_TEXT_SECONDARY
        )

    def _tick_self_timer(self):
        """
        1초마다 호출되어 화면의 시간 표시를 갱신.
        추가로 60초마다 Firestore에 endTime을 미리 갱신(하트비트)해서
        비정상 종료 대비.
        """
        if self.self_report_start is None:
            return
        elapsed = int((datetime.now(timezone.utc) - self.self_report_start).total_seconds())
        self.self_duration_label.configure(text=fmt_hms(elapsed))

        # 60초마다 Firestore에 하트비트 (endTime 미리 갱신)
        if elapsed > 0 and elapsed % 60 == 0 and self.self_report_id:
            now = datetime.now(timezone.utc)
            # 백그라운드 스레드로 보내기 (UI 안 멈추게)
            threading.Thread(
                target=firebase_client.update_self_report_heartbeat,
                args=(self.self_report_id, now, elapsed),
                daemon=True,
            ).start()

        self._self_timer_job = self.after(1000, self._tick_self_timer)

    def _tick_total_timer(self):
        """앱 시작 후 전체 경과 시간 표시."""
        elapsed = int((datetime.now() - self.app_start_time).total_seconds())
        self.total_duration_label.configure(text=fmt_hms(elapsed))
        self._total_timer_job = self.after(1000, self._tick_total_timer)

    def _show_error(self, msg: str):
        self.self_status_label.configure(text=msg, text_color=COLOR_END)
        self.start_btn.configure(state="normal")

    # ─── Windows 종료 시그널 처리 ───

    def _register_shutdown_handlers(self):
        """
        Windows 종료/로그오프 신호를 캐치.
        WM_QUERYENDSESSION이 오면 비밀번호 없이 정상 종료를 허용해야 함
        (그래야 진행 중 세션이 깔끔하게 마감됨).
        """
        try:
            import ctypes
            from ctypes import wintypes

            # WndProc 후킹을 통해 WM_QUERYENDSESSION 감지
            GWL_WNDPROC = -4
            WM_QUERYENDSESSION = 0x0011
            WM_ENDSESSION = 0x0016

            # 콜백 타입 정의 (LRESULT는 c_ssize_t와 호환)
            WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)

            # tkinter 창의 HWND 가져오기
            hwnd = self.winfo_id()

            # WinAPI 함수 시그니처 정의 (64비트 호환성 핵심)
            user32 = ctypes.windll.user32
            
            # GetWindowLongPtrW / SetWindowLongPtrW
            # 64비트에서는 Ptr 버전이 필수이며, restype을 c_ssize_t로 설정해야 주소가 안 잘림.
            GetWindowLongPtr = getattr(user32, 'GetWindowLongPtrW', None)
            if GetWindowLongPtr is None:
                GetWindowLongPtr = user32.GetWindowLongW
            GetWindowLongPtr.restype = ctypes.c_ssize_t
            GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]

            SetWindowLongPtr = getattr(user32, 'SetWindowLongPtrW', None)
            if SetWindowLongPtr is None:
                SetWindowLongPtr = user32.SetWindowLongW
            SetWindowLongPtr.restype = ctypes.c_ssize_t
            SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

            # CallWindowProcW
            user32.CallWindowProcW.restype = ctypes.c_ssize_t
            user32.CallWindowProcW.argtypes = [ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]

            # ShutdownBlockReasonCreate / Destroy
            user32.ShutdownBlockReasonCreate.restype = wintypes.BOOL
            user32.ShutdownBlockReasonCreate.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
            user32.ShutdownBlockReasonDestroy.restype = wintypes.BOOL
            user32.ShutdownBlockReasonDestroy.argtypes = [wintypes.HWND]

            # 기존 WndProc 저장
            self._old_wndproc = GetWindowLongPtr(hwnd, GWL_WNDPROC)

            def _wndproc_hook(hwnd, msg, wparam, lparam):
                if msg == WM_QUERYENDSESSION:
                    print(f"[GUI] Windows 종료 신호(WM_QUERYENDSESSION) 감지 → 즉시 마감 시작")
                    # 종료 차단 사유 등록 (사용자에게 보임)
                    try:
                        user32.ShutdownBlockReasonCreate(hwnd, "사용 기록을 안전하게 저장하고 있습니다...")
                    except Exception:
                        pass
                    
                    # 종료 허용 및 마감 프로세스 트리거
                    self._allow_close = True
                    self._do_close(reason="shutdown")
                    
                    # 마감 완료 후 사유 제거
                    try:
                        user32.ShutdownBlockReasonDestroy(hwnd)
                    except Exception:
                        pass
                        
                    return 1  # TRUE 반환하여 종료 허용
                
                if msg == WM_ENDSESSION:
                    if wparam == 1: # TRUE: 시스템이 진짜 종료됨
                        print(f"[GUI] Windows 종료 확정(WM_ENDSESSION) → 최종 정리")
                        self._allow_close = True
                        self._do_close(reason="shutdown")
                    return 0

                return user32.CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam)

            # 함수 참조가 가비지 컬렉션되지 않도록 속성으로 보관
            self._wndproc_hook_ref = WNDPROC(_wndproc_hook)
            
            # 후킹 등록
            SetWindowLongPtr(hwnd, GWL_WNDPROC, ctypes.cast(self._wndproc_hook_ref, ctypes.c_void_p).value)
            
            # atexit은 여전히 보험용으로 남겨둠
            import atexit
            atexit.register(self._emergency_cleanup)
            print("[GUI] Windows 종료 감지 후크 및 ShutdownBlockReason 등록 완료")
        except Exception as e:
            print(f"[GUI] shutdown handler 등록 실패: {e}")
            # 폴백: atexit만이라도 등록
            import atexit
            atexit.register(self._emergency_cleanup)

    def _emergency_cleanup(self):
        """
        프로세스 강제 종료/시스템 종료 시에 호출.
        진행 중인 세션을 마감하고 종료 사유 기록.
        """
        try:
            # 이미 _do_close가 진행 중이면 중복 실행 방지
            if getattr(self, "_closing", False):
                return

            if self.self_report_id and self.self_report_start:
                now = datetime.now(timezone.utc)
                elapsed = int((now - self.self_report_start).total_seconds())
                firebase_client.end_self_report(self.self_report_id, now, elapsed)

            try:
                # 빠른 종료 모드로 중지
                self.auto_tracker.stop(reason="shutdown", fast=True)
            except Exception:
                pass

            # 시스템 종료 시에는 데이터 정리(cleanup) 건너뜀
            firebase_client.log_tamper_event("shutdown_signal", skip_cleanup=True)
        except Exception as e:
            print(f"[GUI] emergency cleanup 실패: {e}")

    # ─── 종료 시도 처리 (비밀번호 잠금) ───

    def _on_close_attempt(self):
        """
        X 버튼/Alt+F4 클릭 시 비밀번호 다이얼로그 표시.
        맞으면 종료, 틀리면 그대로 유지.
        """
        if self._allow_close:
            self._do_close(reason="normal")
            return

        dlg = PasswordPromptDialog(self)
        self.wait_window(dlg)

        if dlg.result_ok:
            self._allow_close = True
            firebase_client.log_tamper_event("tracker_normal_exit")
            self._do_close(reason="normal")

    def _do_close(self, reason: str = "normal"):
        """
        세션 마감 + 종료 처리.
        """
        # 중복 호출 방지
        if getattr(self, "_closing", False):
            return
        self._closing = True
        
        # 시스템 종료 여부
        is_shutdown = (reason == "shutdown")

        # 정상 종료 또는 시스템 종료 시 워치독에게 알림 (플래그 파일 생성)
        # 윈도우 종료 시에도 플래그를 만들어야 워치독이 트래커를 다시 살리려 하지 않음
        if reason in ("normal", "shutdown"):
            try:
                with open(config.TRACKER_STOPPED_FLAG, "w") as f:
                    f.write(str(time.time()))
            except Exception as e:
                print(f"[GUI ERR] 종료 플래그 생성 실패: {e}")

        # 자가 보고 진행 중이면 마감
        if self.self_report_id and self.self_report_start:
            try:
                now = datetime.now(timezone.utc)
                elapsed = int((now - self.self_report_start).total_seconds())
                firebase_client.end_self_report(self.self_report_id, now, elapsed)
            except Exception as e:
                print(f"[GUI ERR] 자가 보고 마감 실패: {e}")
            finally:
                self.self_report_id = None
                self.self_report_start = None

        # 자동 추적 정리 (auto_tracker.stop도 idempotent)
        try:
            if hasattr(self, "auto_tracker"):
                # 시스템 종료 시에는 fast=True로 신속 마감
                self.auto_tracker.stop(reason=reason, fast=is_shutdown)
        except Exception as e:
            print(f"[GUI ERR] AutoTracker stop: {e}")

        # 시스템 종료 시 로그 기록
        if is_shutdown:
            try:
                firebase_client.log_tamper_event("shutdown_signal", skip_cleanup=True)
            except Exception:
                pass

        # 워치독 감시자 정리
        try:
            if hasattr(self, "watchdog_monitor"):
                # 시스템 종료 시에는 스레드 join 시간을 짧게 함
                if is_shutdown:
                    self.watchdog_monitor._stopped = True
                    self.watchdog_monitor._stop_event.set()
                else:
                    self.watchdog_monitor.stop()
        except Exception as e:
            print(f"[GUI ERR] WatchdogMonitor stop: {e}")

        # GUI 파괴
        try:
            self.destroy()
        except Exception:
            pass
