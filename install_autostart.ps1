# ==========================================================
# Son Tracker - Autostart Installer
# ==========================================================
# Usage:
#   1. Open PowerShell as Administrator
#   2. cd to this folder
#   3. Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   4. .\install_autostart.ps1
# ==========================================================

$ErrorActionPreference = "Stop"

$TrackerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainScript = Join-Path $TrackerDir "main.py"
$WatchdogScript = Join-Path $TrackerDir "watchdog.py"

$Pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $Pythonw) {
    Write-Host "[ERROR] pythonw.exe not found. Is Python in PATH?" -ForegroundColor Red
    exit 1
}

Write-Host "Tracker folder: $TrackerDir" -ForegroundColor Cyan
Write-Host "Python path:    $Pythonw" -ForegroundColor Cyan
Write-Host ""

# ==========================================================
# 1. SonTracker - run at logon
# ==========================================================

$TrackerTaskName = "SonTracker"
Unregister-ScheduledTask -TaskName $TrackerTaskName -Confirm:$false -ErrorAction SilentlyContinue

$TrackerAction = New-ScheduledTaskAction `
    -Execute $Pythonw `
    -Argument "`"$MainScript`"" `
    -WorkingDirectory $TrackerDir

$TrackerTrigger = New-ScheduledTaskTrigger -AtLogOn

$TrackerSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

$TrackerPrincipal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TrackerTaskName `
    -Action $TrackerAction `
    -Trigger $TrackerTrigger `
    -Settings $TrackerSettings `
    -Principal $TrackerPrincipal `
    -Description "Son tracker - auto-start at logon" | Out-Null

Write-Host "[OK] '$TrackerTaskName' registered (runs at logon)" -ForegroundColor Green

# ==========================================================
# 2. SonTrackerWatchdog
# ==========================================================
# Watchdog has internal 1-min loop, so scheduler only needs to:
#   - Start it once at logon
#   - Re-spawn it every hour IF it died (IgnoreNew prevents duplicates)

$WatchdogTaskName = "SonTrackerWatchdog"
Unregister-ScheduledTask -TaskName $WatchdogTaskName -Confirm:$false -ErrorAction SilentlyContinue

$WatchdogAction = New-ScheduledTaskAction `
    -Execute $Pythonw `
    -Argument "`"$WatchdogScript`"" `
    -WorkingDirectory $TrackerDir

$WatchdogTrigger1 = New-ScheduledTaskTrigger -AtLogOn
$WatchdogTrigger2 = New-ScheduledTaskTrigger `
    -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)

$WatchdogSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$WatchdogPrincipal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive

Register-ScheduledTask `
    -TaskName $WatchdogTaskName `
    -Action $WatchdogAction `
    -Trigger @($WatchdogTrigger1, $WatchdogTrigger2) `
    -Settings $WatchdogSettings `
    -Principal $WatchdogPrincipal `
    -Description "Watchdog for tracker (ignores duplicate launches)" | Out-Null

Write-Host "[OK] '$WatchdogTaskName' registered (logon + every 5min revive)" -ForegroundColor Green

# ==========================================================
# Start now
# ==========================================================

Write-Host ""
Write-Host "Starting tasks now..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TrackerTaskName
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName $WatchdogTaskName

Write-Host ""
Write-Host "[DONE] Autostart installed." -ForegroundColor Green
Write-Host ""
Write-Host "Console flicker should be gone now." -ForegroundColor White
Write-Host "Verify: Task Scheduler Library -> SonTracker, SonTrackerWatchdog" -ForegroundColor Gray
