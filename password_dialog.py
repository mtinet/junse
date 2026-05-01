"""
비밀번호 입력/설정 다이얼로그.

화면:
  - PasswordSetupDialog: 첫 실행 시 비밀번호 설정
  - PasswordPromptDialog: 종료 시 비밀번호 입력 요구
"""
import customtkinter as ctk

import config
import password_lock
import firebase_client


COLOR_BG = "#F7F6F2"
COLOR_TEXT_PRIMARY = "#2C2C2A"
COLOR_TEXT_SECONDARY = "#7A7975"
COLOR_DANGER = "#D85A30"
COLOR_PRIMARY = "#1D9E75"
COLOR_PRIMARY_HOVER = "#0F6E56"


class PasswordSetupDialog(ctk.CTkToplevel):
    """첫 실행 시 비밀번호 설정 화면. 설정 안 하면 앱 실행 거부."""

    def __init__(self, parent):
        super().__init__(parent)
        self.result_set = False

        self.title("비밀번호 설정")
        self.geometry("360x340")
        self.configure(fg_color=COLOR_BG)
        self.resizable(False, False)

        # 모달처럼 동작
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        self._build()

    def _build(self):
        ctk.CTkLabel(
            self,
            text="🔒 보호자 비밀번호 설정",
            font=("Malgun Gothic", 16, "bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            self,
            text="이 비밀번호가 있어야 트래커를 종료할 수 있어요.\n잊어버리면 재설정이 번거로우니 잘 기억해주세요.",
            font=("Malgun Gothic", 11),
            text_color=COLOR_TEXT_SECONDARY,
            justify="center",
        ).pack(pady=(0, 16))

        self.pw_entry = ctk.CTkEntry(
            self, placeholder_text="비밀번호 (4자 이상)", show="●", width=280, height=36
        )
        self.pw_entry.pack(pady=4)

        self.pw_confirm = ctk.CTkEntry(
            self, placeholder_text="비밀번호 확인", show="●", width=280, height=36
        )
        self.pw_confirm.pack(pady=4)

        self.error_label = ctk.CTkLabel(
            self, text="", font=("Malgun Gothic", 10), text_color=COLOR_DANGER
        )
        self.error_label.pack(pady=(6, 0))

        ctk.CTkButton(
            self,
            text="설정하기",
            command=self._on_submit,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            font=("Malgun Gothic", 13, "bold"),
            width=280,
            height=40,
        ).pack(pady=(14, 8))

        self.pw_entry.focus()
        self.bind("<Return>", lambda e: self._on_submit())

    def _on_submit(self):
        pw = self.pw_entry.get()
        confirm = self.pw_confirm.get()

        if len(pw) < 4:
            self.error_label.configure(text="비밀번호는 4자 이상이어야 해요")
            return
        if pw != confirm:
            self.error_label.configure(text="두 비밀번호가 일치하지 않아요")
            return

        if password_lock.set_password(pw):
            self.result_set = True
            self.grab_release()
            self.destroy()
        else:
            self.error_label.configure(text="저장 실패. 다시 시도해주세요")

    def _on_close_attempt(self):
        # X 눌러도 닫히지 않음 (비번 설정이 필수)
        self.error_label.configure(text="비밀번호를 꼭 설정해야 해요")


class PasswordPromptDialog(ctk.CTkToplevel):
    """종료 시 비밀번호 입력 요구. 맞으면 result_ok = True."""

    def __init__(self, parent):
        super().__init__(parent)
        self.result_ok = False

        self.title("비밀번호 확인")
        self.geometry("360x260")
        self.configure(fg_color=COLOR_BG)
        self.resizable(False, False)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._build()

    def _build(self):
        if password_lock.is_locked_out():
            remaining = password_lock.lockout_remaining_sec()
            ctk.CTkLabel(
                self,
                text="🔒 잠금 상태",
                font=("Malgun Gothic", 16, "bold"),
                text_color=COLOR_DANGER,
            ).pack(pady=(20, 4))
            mins = remaining // 60
            secs = remaining % 60
            ctk.CTkLabel(
                self,
                text=f"비밀번호를 너무 여러 번 틀렸어요.\n{mins}분 {secs}초 후에 다시 시도하세요.",
                font=("Malgun Gothic", 11),
                text_color=COLOR_TEXT_SECONDARY,
                justify="center",
            ).pack(pady=(0, 12))
            ctk.CTkButton(
                self,
                text="확인",
                command=self._on_cancel,
                fg_color=COLOR_PRIMARY,
                hover_color=COLOR_PRIMARY_HOVER,
                width=280,
                height=40,
            ).pack(pady=10)
            return

        ctk.CTkLabel(
            self,
            text="🔒 종료하려면 비밀번호 입력",
            font=("Malgun Gothic", 16, "bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            self,
            text=f"남은 시도: {config.MAX_PASSWORD_ATTEMPTS - password_lock.get_failed_count()}회",
            font=("Malgun Gothic", 10),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(pady=(0, 12))

        self.pw_entry = ctk.CTkEntry(
            self, placeholder_text="비밀번호", show="●", width=280, height=36
        )
        self.pw_entry.pack(pady=4)
        self.pw_entry.focus()

        self.error_label = ctk.CTkLabel(
            self, text="", font=("Malgun Gothic", 10), text_color=COLOR_DANGER
        )
        self.error_label.pack(pady=(6, 0))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10)

        ctk.CTkButton(
            btn_frame,
            text="취소",
            command=self._on_cancel,
            fg_color="transparent",
            border_width=1,
            border_color="#D3D1C7",
            text_color=COLOR_TEXT_SECONDARY,
            hover_color="#EAEAE5",
            width=130,
            height=38,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_frame,
            text="종료",
            command=self._on_submit,
            fg_color=COLOR_DANGER,
            hover_color="#993C1D",
            width=130,
            height=38,
        ).pack(side="left", padx=4)

        self.bind("<Return>", lambda e: self._on_submit())
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _on_submit(self):
        if password_lock.is_locked_out():
            return
        pw = self.pw_entry.get()
        if password_lock.verify_password(pw):
            password_lock.record_successful_attempt()
            self.result_ok = True
            self.grab_release()
            self.destroy()
        else:
            password_lock.record_failed_attempt()
            firebase_client.log_tamper_event("password_failed", {
                "remaining_attempts": config.MAX_PASSWORD_ATTEMPTS - password_lock.get_failed_count(),
            })

            if password_lock.is_locked_out():
                firebase_client.log_tamper_event("password_lockout")
                self.error_label.configure(text="너무 여러 번 틀렸어요. 잠금 상태입니다.")
                # 1초 후 자동으로 닫기 (다음 시도 시 잠금 화면 보임)
                self.after(1500, self._on_cancel)
            else:
                remaining = config.MAX_PASSWORD_ATTEMPTS - password_lock.get_failed_count()
                self.error_label.configure(text=f"비밀번호가 틀려요. (남은 시도 {remaining}회)")
                self.pw_entry.delete(0, "end")

    def _on_cancel(self):
        self.result_ok = False
        self.grab_release()
        self.destroy()
