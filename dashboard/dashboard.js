// Firestore 연결 및 차트 관리자
let db;
let mainChart, userShareChart;
let currentPeriod = 'weekly'; // 'daily', 'weekly', 'monthly'
let selectedUser = 'total';   // 'total' 또는 특정 userName

const SESSIONS_COL = "sessions";
const SELF_REPORTS_COL = "self_reports";
const TAMPER_COL = "tamper_events";
const HEARTBEAT_THRESHOLD_MS = 180000; // 3분

// 실시간 데이터를 담을 변수
let latestStatus = null;
let todayLogs = [];   // 오늘 전체 로그 (실시간)
let historyLogs = []; // 30일치 전체 로그 (통계 및 차트용)
let alertLogs = [];   // 보안 경고 로그

document.addEventListener("DOMContentLoaded", () => {
    initFirebase();
});

function initFirebase() {
    if (typeof firebase === "undefined" || !firebaseConfig.apiKey) {
        document.getElementById("connection-status").innerHTML = `
            <span class="w-2 h-2 rounded-full bg-red-500"></span>
            설정 필요 (firebase-config.js)
        `;
        return;
    }

    firebase.initializeApp(firebaseConfig);
    db = firebase.firestore();
    initCharts();
    startListening();
}

// UI 전체 업데이트
function updateUI() {
    try {
        const statusEl = document.getElementById("connection-status");
        const statusVal = document.getElementById("current-status-val");
        const userVal = document.getElementById("current-user-val");
        const now = Date.now();

        // 1. 데이터 통합 및 정렬 (오늘 로그 기준)
        const allTodayLogs = [...todayLogs].sort((a, b) => {
            const timeA = (a.startTime && typeof a.startTime.toMillis === 'function') ? a.startTime.toMillis() : 0;
            const timeB = (b.startTime && typeof b.startTime.toMillis === 'function') ? b.startTime.toMillis() : 0;
            return timeB - timeA;
        });

        // 2. 상태 판정 (실제 기기 상태 + 활성 세션)
        const activeLog = allTodayLogs.find(log => {
            if (log.status !== "active") return false;
            // 마지막 하트비트 시각 확인
            const hb = log.lastHeartbeat || log.startTime;
            if (!hb || typeof hb.toMillis !== 'function') return false;
            // 하트비트가 끊긴지 3분 이상 지났으면 더 이상 Active로 보지 않음 (강제종료 대비)
            return (now - hb.toMillis()) < HEARTBEAT_THRESHOLD_MS;
        });
        
        let isOnline = false;
        if (latestStatus && latestStatus.lastHeartbeat && typeof latestStatus.lastHeartbeat.toMillis === 'function') {
            isOnline = latestStatus.isActive && (now - latestStatus.lastHeartbeat.toMillis()) < HEARTBEAT_THRESHOLD_MS;
        }
        
        const inUse = !!activeLog || isOnline;

        // 3. 상단 상태바 갱신
        if (inUse) {
            statusEl.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> 추적기 동작 중`;
            statusEl.className = "flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-50 text-emerald-600 text-sm font-medium border border-emerald-100";
            statusVal.innerText = "현재 사용 중";
            statusVal.className = "text-xl font-bold text-emerald-600";
            
            const displayData = activeLog || latestStatus;
            if (displayData && displayData.startTime) {
                userVal.innerText = formatTime(displayData.startTime) + "부터 " + (displayData.userName || "사용자") + " 기록 중";
            } else if (displayData && displayData.lastHeartbeat) {
                userVal.innerText = "현재 컴퓨터 활동 감지됨";
            } else {
                userVal.innerText = "컴퓨터 활동 감지됨";
            }
        } else {
            statusEl.innerHTML = `<span class="w-2 h-2 rounded-full bg-slate-400"></span> 추적기 꺼짐`;
            statusEl.className = "flex items-center gap-2 px-4 py-2 rounded-full bg-slate-100 text-slate-500 text-sm font-medium border border-slate-200";
            statusVal.innerText = "사용 안 함";
            statusVal.className = "text-xl font-bold text-slate-400";
            
            const lastLog = allTodayLogs[0];
            if (lastLog) {
                const lastTime = lastLog.lastHeartbeat || lastLog.endTime || lastLog.startTime;
                userVal.innerText = "마지막 기록: " + formatTime(lastTime);
            } else {
                userVal.innerText = "기록된 데이터 없음";
            }
        }

        // 4. 로그 테이블 갱신 (최근 15개)
        updateLogTable(allTodayLogs.slice(0, 15));

        // 5. 실시간 통계 및 드롭다운 갱신
        updateUserDropdown();
        updateStatsSummary();
    } catch (err) {
        console.error("Error in updateUI:", err);
    }
}

// 사용자 드롭다운 메뉴 갱신
function updateUserDropdown() {
    try {
        const select = document.getElementById("user-filter");
        if (!select) return;
        const currentVal = select.value;
        
        // 유니크한 사용자 이름 추출
        const users = new Set();
        [...historyLogs, ...todayLogs].forEach(log => {
            if (log.userName) users.add(log.userName);
        });

        // 기본 옵션 유지하고 새 옵션 추가
        let html = '<option value="total">전체 컴퓨터 사용</option>';
        Array.from(users).sort().forEach(user => {
            html += `<option value="${user}" ${user === currentVal ? 'selected' : ''}>${user}</option>`;
        });
        
        // 내용이 바뀔 때만 갱신 (무한 루프 방지)
        if (select.innerHTML !== html) {
            select.innerHTML = html;
        }
    } catch (err) {
        console.error("Error in updateUserDropdown:", err);
    }
}

// 드롭다운 변경 핸들러
function handleUserFilterChange() {
    selectedUser = document.getElementById("user-filter").value;
    
    // 카드 제목 업데이트
    const labelSuffix = selectedUser === 'total' ? '총 사용' : `(${selectedUser}) 사용`;
    document.getElementById("label-daily-total").innerText = `오늘 ${labelSuffix}`;
    document.getElementById("label-weekly-total").innerText = `주간 ${labelSuffix}`;
    document.getElementById("label-monthly-total").innerText = `월간 ${labelSuffix}`;
    
    updateStatsSummary();
}

// 일별/주별/월별 합계 계산 (선택된 사용자 기준)
function updateStatsSummary() {
    const now = new Date();
    const todayStr = now.toLocaleDateString();
    const sevenDaysAgo = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000));
    const thirtyDaysAgo = new Date(now.getTime() - (30 * 24 * 60 * 60 * 1000));

    // 데이터 통합 및 중복 제거
    const logMap = new Map();
    [...historyLogs, ...todayLogs].forEach(log => {
        const id = log.startTime ? log.startTime.toMillis() : Math.random();
        logMap.set(id, log);
    });
    let logs = Array.from(logMap.values());

    // 사용자 필터링
    if (selectedUser !== 'total') {
        logs = logs.filter(log => log.userName === selectedUser);
    }

    const dailyTotal = logs
        .filter(log => log.startTime && log.startTime.toDate().toLocaleDateString() === todayStr)
        .reduce((sum, log) => sum + (log.durationSec || 0), 0);

    const weeklyTotal = logs
        .filter(log => log.startTime && log.startTime.toDate() >= sevenDaysAgo)
        .reduce((sum, log) => sum + (log.durationSec || 0), 0);

    const monthlyTotal = logs
        .filter(log => log.startTime && log.startTime.toDate() >= thirtyDaysAgo)
        .reduce((sum, log) => sum + (log.durationSec || 0), 0);

    document.getElementById("stats-daily-total").innerText = formatDuration(dailyTotal);
    document.getElementById("stats-weekly-total").innerText = formatDuration(weeklyTotal);
    document.getElementById("stats-monthly-total").innerText = formatDuration(monthlyTotal);
}

// 보안 경고 UI 업데이트
function updateAlertsUI() {
    const container = document.getElementById("alerts-container");
    const countEl = document.getElementById("alert-count");
    
    if (!alertLogs || alertLogs.length === 0) {
        container.innerHTML = '<p class="text-center text-slate-400 py-10 text-sm">최근 경고가 없습니다.</p>';
        countEl.innerText = "0건";
        return;
    }

    countEl.innerText = `${alertLogs.length}건`;
    container.innerHTML = alertLogs.map(alert => {
        let title = "알 수 없는 이벤트";
        let icon = "alert-circle";
        let color = "slate";

        switch(alert.type) {
            case "tracker_started": title = "트래커 앱 실행됨"; icon = "play"; color = "emerald"; break;
            case "tracker_normal_exit": title = "트래커 정상 종료"; icon = "log-out"; color = "slate"; break;
            case "tracker_crashed": title = "비정상 종료 감지"; icon = "zap"; color = "red"; break;
            case "password_failed": title = "비밀번호 시도 실패"; icon = "lock"; color = "orange"; break;
            case "password_lockout": title = "비밀번호 잠금 발생"; icon = "shield-off"; color = "red"; break;
            case "watchdog_revived": title = "프로그램 강제 재실행"; icon = "refresh-cw"; color = "blue"; break;
            case "shutdown_signal": title = "시스템 종료 신호"; icon = "power"; color = "amber"; break;
        }

        return `
            <div class="flex items-start gap-3 p-3 rounded-lg bg-${color}-50 border border-${color}-100">
                <div class="mt-0.5 p-1.5 rounded-md bg-${color}-100 text-${color}-600">
                    <i data-lucide="${icon}" class="w-3.5 h-3.5"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <p class="text-xs font-bold text-${color}-900 truncate">${title}</p>
                    <p class="text-[10px] text-${color}-600 mt-0.5">${formatDate(alert.timestamp)}</p>
                </div>
            </div>
        `;
    }).join('');
    
    lucide.createIcons();
}

function startListening() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // 1. 기기 상태 실시간
    db.collection("status").doc("son_pc").onSnapshot(doc => {
        if (doc.exists) {
            latestStatus = doc.data();
            updateUI();
        }
    });

    // 2. 세션 실시간 (오늘)
    db.collection(SESSIONS_COL).where("startTime", ">=", today).onSnapshot(snap => {
        const logs = snap.docs.map(d => ({ ...d.data(), type: 'auto' }));
        const otherLogs = todayLogs.filter(l => l.type !== 'auto');
        todayLogs = [...logs, ...otherLogs];
        updateUI();
    });

    db.collection(SELF_REPORTS_COL).where("startTime", ">=", today).onSnapshot(snap => {
        const logs = snap.docs.map(d => ({ ...d.data(), type: 'self' }));
        const otherLogs = todayLogs.filter(l => l.type !== 'self');
        todayLogs = [...logs, ...otherLogs];
        updateUI();
    });

    // 3. 보안 경고 실시간 (최근 10개)
    db.collection(TAMPER_COL).orderBy("timestamp", "desc").limit(10).onSnapshot(snap => {
        alertLogs = snap.docs.map(d => d.data());
        updateAlertsUI();
    });

    // 4. 차트 및 통계용 과거 데이터 (30일)
    const loadHistory = async () => {
        const thirtyDaysAgo = new Date(Date.now() - (30 * 24 * 60 * 60 * 1000));
        const [sessSnap, selfSnap] = await Promise.all([
            db.collection(SESSIONS_COL).where("startTime", ">=", thirtyDaysAgo).get(),
            db.collection(SELF_REPORTS_COL).where("startTime", ">=", thirtyDaysAgo).get()
        ]);
        
        let logs = [];
        sessSnap.forEach(d => logs.push({ ...d.data(), type: 'auto' }));
        selfSnap.forEach(d => logs.push({ ...d.data(), type: 'self' }));
        
        historyLogs = logs;
        processChartData(logs);
        updateStatsSummary();
        updateUserDropdown();
    };

    loadHistory();
    setInterval(loadHistory, 300000);
    // 추가: 1분마다 UI를 강제로 갱신하여 하트비트 타임아웃(3분)을 체크함
    setInterval(updateUI, 60000);
}

function processChartData(logs) {
    const now = new Date();
    const userMap = {};
    const hourlyData = new Array(24).fill(0);
    const weeklyData = new Array(7).fill(0);
    const monthlyData = {};

    logs.forEach(log => {
        if (!log.startTime) return;
        const d = log.startTime.toDate();
        const durationMin = (log.durationSec || 0) / 60;
        const name = log.userName || "시스템";
        userMap[name] = (userMap[name] || 0) + durationMin;

        if (d.toDateString() === now.toDateString()) {
            hourlyData[d.getHours()] += durationMin;
        }
        const weekDiff = Math.floor((now - d) / (7 * 24 * 60 * 60 * 1000));
        if (weekDiff === 0) {
            const dayIdx = (d.getDay() + 6) % 7;
            weeklyData[dayIdx] += durationMin;
        }
        if (d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()) {
            const date = d.getDate();
            monthlyData[date] = (monthlyData[date] || 0) + durationMin;
        }
    });

    window.chartStorage = { hourlyData, weeklyData, monthlyData, userMap };
    renderMainChart();
    renderUserChart(userMap);
}

function renderMainChart() {
    if (!window.chartStorage || !mainChart) return;
    const { hourlyData, weeklyData, monthlyData } = window.chartStorage;
    let labels, data, label;

    if (currentPeriod === 'daily') {
        labels = Array.from({length: 24}, (_, i) => `${i}시`);
        data = hourlyData;
        label = '오늘 시간별 사용 (분)';
    } else if (currentPeriod === 'weekly') {
        labels = ['월', '화', '수', '목', '금', '토', '일'];
        data = weeklyData;
        label = '이번 주 요일별 사용 (분)';
    } else {
        const lastDay = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate();
        labels = Array.from({length: lastDay}, (_, i) => `${i+1}일`);
        data = Array.from({length: lastDay}, (_, i) => monthlyData[i+1] || 0);
        label = '이번 달 일별 사용 (분)';
    }

    mainChart.data.labels = labels;
    mainChart.data.datasets[0].data = data;
    mainChart.data.datasets[0].label = label;
    mainChart.update();
}

function renderUserChart(userMap) {
    if (!userShareChart) return;
    const names = Object.keys(userMap);
    if (names.length > 0) {
        userShareChart.data.labels = names;
        userShareChart.data.datasets[0].data = Object.values(userMap);
        userShareChart.update();
    }
}

function changeChartPeriod(p) {
    currentPeriod = p;
    document.querySelectorAll('.btn-period').forEach(btn => btn.classList.remove('bg-white', 'shadow-sm'));
    document.getElementById(`btn-${p}`).classList.add('bg-white', 'shadow-sm');
    document.getElementById('main-chart-title').innerText = p === 'daily' ? '일간 사용량' : p === 'weekly' ? '주간 사용량' : '월간 사용량';
    renderMainChart();
}

function initCharts() {
    const mainEl = document.getElementById('mainChart');
    if (mainEl) {
        const ctxMain = mainEl.getContext('2d');
        mainChart = new Chart(ctxMain, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{ label: '', data: [], backgroundColor: 'rgba(99, 102, 241, 0.8)', borderRadius: 4 }]
            },
            options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
        });
    }

    const userEl = document.getElementById('userShareChart');
    if (userEl) {
        const ctxUser = userEl.getContext('2d');
        userShareChart = new Chart(ctxUser, {
            type: 'doughnut',
            data: {
                labels: ['데이터 없음'],
                datasets: [{ data: [1], backgroundColor: ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#e2e8f0'] }]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
        });
    }
}

function updateLogTable(logs) {
    const tbody = document.getElementById("log-table-body");
    if (!tbody) return;
    const now = Date.now();
    tbody.innerHTML = logs.map(log => {
        let statusText = log.status === 'active' ? 'Active' : 'Ended';
        let statusColor = log.status === 'active' ? 'text-emerald-500' : 'text-slate-400';
        let bulletColor = log.status === 'active' ? 'bg-emerald-500' : 'bg-slate-300';

        // Active 세션인데 하트비트가 끊겼다면 Ended로 표시
        if (log.status === 'active') {
            const hb = log.lastHeartbeat || log.startTime;
            if (hb && typeof hb.toMillis === 'function' && (now - hb.toMillis()) >= HEARTBEAT_THRESHOLD_MS) {
                statusText = 'Ended';
                statusColor = 'text-slate-400';
                bulletColor = 'bg-slate-300';
            }
        }

        return `
            <tr class="hover:bg-slate-50 border-b last:border-0">
                <td class="py-3 px-1 font-medium text-slate-700">${log.userName || log.userId || '시스템'}</td>
                <td class="py-3 px-1">
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase ${log.type === 'self' ? 'bg-amber-100 text-amber-700' : 'bg-indigo-100 text-indigo-700'}">
                        ${log.type === 'self' ? 'Self' : 'Auto'}
                    </span>
                </td>
                <td class="py-3 px-1 text-slate-500 text-xs">${formatDate(log.startTime)}</td>
                <td class="py-3 px-1 text-slate-600 font-mono text-xs">${formatDuration(log.durationSec)}</td>
                <td class="pb-3 px-1">
                    <span class="flex items-center gap-1 text-xs ${statusColor}">
                        <span class="w-1.5 h-1.5 rounded-full ${bulletColor}"></span>
                        ${statusText}
                    </span>
                </td>
            </tr>
        `;
    }).join('');
}

function formatDuration(sec) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function formatDate(ts) {
    if (!ts) return "-";
    const d = ts.toDate();
    return `${d.getMonth()+1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, '0')}`;
}

function formatTime(ts) {
    if (!ts) return "-";
    const d = ts.toDate();
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}
