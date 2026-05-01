# ==========================================================
# Son Tracker - Autostart Uninstaller
# ==========================================================
# Usage:
#   1. Open PowerShell as Administrator
#   2. cd to this folder
#   3. Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   4. .\uninstall_autostart.ps1
# ==========================================================

$tasks = @("SonTracker", "SonTrackerWatchdog")

foreach ($taskName in $tasks) {
    try {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
        Write-Host "[OK] '$taskName' removed" -ForegroundColor Green
    } catch {
        Write-Host "[!] '$taskName' not found or removal failed" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Autostart removed." -ForegroundColor White
Write-Host "Currently running tracker processes still need to be ended manually (password required)." -ForegroundColor Gray
