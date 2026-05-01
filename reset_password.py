"""
비밀번호 리셋 도구.

비밀번호를 잊어버렸을 때 이 스크립트를 실행하면
.password_hash 파일을 삭제해서 다음 실행 시 다시 설정할 수 있게 함.

사용법:
  python reset_password.py

주의:
  - 트래커가 실행 중이면 먼저 작업 스케줄러에서 중지 후 실행
  - 이 스크립트는 누구나 실행할 수 있으므로 부모만 알 만한 곳에 두기
"""
import os
import sys

import config


def main():
    if not os.path.exists(config.PASSWORD_HASH_FILE):
        print("[!] 비밀번호가 설정되어 있지 않습니다.")
        return

    print("⚠️  주의: 비밀번호를 리셋합니다.")
    print(f"파일: {config.PASSWORD_HASH_FILE}")
    print()
    confirm = input("정말 리셋하시겠습니까? (yes 입력): ").strip().lower()

    if confirm != "yes":
        print("취소됨.")
        return

    try:
        os.remove(config.PASSWORD_HASH_FILE)
        print("[OK] 비밀번호 리셋 완료. 다음 트래커 실행 시 새로 설정하세요.")
    except Exception as e:
        print(f"[ERR] 리셋 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
