# 💻 컴퓨터 사용 시간 트래커 (Son Tracker)

컴퓨터 사용 시간을 자동으로 기록하고, 필요할 때 수동으로 작업 내용을 보고할 수 있는 데스크탑 애플리케이션입니다. 모든 데이터는 Firebase Firestore에 실시간으로 저장되며, 웹 대시보드를 통해 어디서든 확인할 수 있습니다.

## ✨ 주요 기능

*   **자동 활동 추적 (Auto Tracking):** 키보드/마우스 움직임을 감지하여 실제 사용 시간을 1분 단위로 기록합니다. (5분 이상 미사용 시 자동 중단)
*   **자가 보고 (Self Report):** 특정 프로젝트나 공부 시간을 별도로 기록하고 싶을 때 버튼 클릭으로 상세 내용을 남길 수 있습니다.
*   **보안 및 잠금:** 프로그램 종료나 설정 변경 시 비밀번호 확인이 필요하며, 강제 종료 시도 시 보안 이벤트를 기록합니다.
*   **윈도우 종료 감지:** 컴퓨터가 꺼질 때 진행 중인 기록을 안전하게 마감하고 Firestore에 업로드합니다.
*   **실시간 웹 대시보드:** 오늘 사용량, 주간/월간 통계, 현재 기기 상태를 아름다운 그래프와 함께 확인할 수 있습니다.
*   **워치독 (Watchdog):** 프로그램이 예기치 않게 종료되면 자동으로 재실행하여 기록 누락을 방지합니다.

## 🚀 설치 방법

### 1. 사전 준비
*   [Python 3.10 이상](https://www.python.org/) 설치
*   [Firebase 프로젝트](https://console.firebase.google.com/) 생성 및 서비스 계정 키(`serviceAccountKey.json`) 다운로드

### 2. 저장소 복제 및 라이브러리 설치
```powershell
# 프로젝트 폴더로 이동
cd son-tracker

# 필요한 라이브러리 설치
pip install -r requirements.txt
```

### 3. Firebase 설정

이 프로젝트는 데이터 저장을 위해 Firebase Firestore를 사용합니다. 다음 두 가지 설정이 필수입니다.

#### A. 파이썬 앱용 서비스 계정 키 (Admin SDK)
1.  [Firebase Console](https://console.firebase.google.com/)에 접속하여 프로젝트를 선택합니다.
2.  **프로젝트 설정(톱니바퀴 아이콘) > 서비스 계정** 탭으로 이동합니다.
3.  **'새 비공개 키 생성'** 버튼을 클릭하여 JSON 파일을 다운로드합니다.
4.  다운로드한 파일의 이름을 `serviceAccountKey.json`으로 변경하여 프로젝트 루트(최상위) 폴더에 복사합니다.
    *   *주의: 이 파일은 보안상 절대 GitHub 등 외부에 공개해서는 안 됩니다.*

#### B. 웹 대시보드용 설정 (Web SDK)
1.  **프로젝트 설정 > 일반** 탭의 하단 '내 앱' 섹션에서 **웹 앱(</> 아이콘)**을 추가합니다.
2.  앱 등록 후 나타나는 `firebaseConfig` 객체 내용을 복사합니다.
3.  `dashboard/firebase-config.js` 파일을 열고 복사한 내용을 붙여넣습니다.
    ```javascript
    const firebaseConfig = {
        apiKey: "...",
        authDomain: "...",
        projectId: "...",
        // ... 나머지 내용
    };
    ```

#### C. Firestore 데이터베이스 생성
1.  Firebase 메뉴에서 **Build > Firestore Database**를 클릭합니다.
2.  **데이터베이스 생성**을 누르고 위치를 설정합니다.
3.  **테스트 모드**로 시작하거나, 규칙(Rules) 탭에서 읽기/쓰기 권한을 허용 설정해야 데이터가 기록됩니다.

### 4. 자동 실행 등록 (선택 사항)

컴퓨터가 켜질 때마다 자동으로 트래커가 실행되도록 설정하려면 포함된 PowerShell 스크립트를 사용하세요. **이 작업은 윈도우 작업 스케줄러에 등록하기 위해 반드시 '관리자 권한'이 필요합니다.**

1.  **시작** 메뉴에서 'PowerShell'을 검색합니다.
2.  **'관리자 권한으로 실행'**을 클릭하여 창을 엽니다.
3.  프로젝트 폴더로 이동한 후 아래 명령어를 입력합니다.
    ```powershell
    .\install_autostart.ps1
    ```
4.  (참고) 만약 스크립트 실행 권한 에러가 발생한다면 `Set-ExecutionPolicy RemoteSigned -Scope Process`를 먼저 입력한 뒤 실행하세요.


## 📖 사용 방법

### 트래커 실행
`main.py`를 실행하면 시스템 트레이와 함께 메인 창이 나타납니다.
```bash
python main.py
```

*   **자동 기록:** 마우스를 움직이면 자동으로 '기록 중' 상태가 되며 기록이 시작됩니다.
*   **자가 보고:** 하단의 입력창에 작업 내용을 적고 '기록 시작'을 누르면 별도의 세션으로 기록됩니다.
*   **비밀번호:** 처음 실행 시 비밀번호를 설정하게 됩니다. 이후 종료 시 이 비밀번호가 필요합니다.

### 대시보드 확인
`dashboard/index.html` 파일을 브라우저로 열면 실시간 통계를 확인할 수 있습니다. (서버에 업로드하여 호스팅하는 것을 권장합니다.)

## 🛠 기술 스택
*   **Language:** Python 3.11
*   **GUI:** CustomTkinter (Modern UI)
*   **Database:** Firebase Firestore
*   **Monitoring:** Windows API (WndProc Hooking)
*   **Dashboard:** HTML5, Tailwind CSS, Chart.js

## 📄 라이선스
이 프로젝트는 개인 학습 및 용도에 최적화되어 있습니다.
