# Registers "FluidQ US Daily Refresh" in Windows Task Scheduler.
# Runs at 07:00 IST, which is comfortably after the previous US close
# (16:00 ET = 01:30 IST), so it always picks up a settled session.
#
#   Run once:      powershell -ExecutionPolicy Bypass -File .\install-daily-task.ps1
#   Remove later:  Unregister-ScheduledTask -TaskName "FluidQ US Daily Refresh" -Confirm:$false

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root "refresh.ps1"
$name = "FluidQ US Daily Refresh"

if (-not (Test-Path $script)) { throw "refresh.ps1 not found next to this script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Daily -At 7:00am

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings $settings -Description "Refreshes the Fluid Q US screener data after the US close." `
    -Force | Out-Null

Write-Host "Registered '$name' - runs daily at 07:00, catching up on next login if the PC was off."
Write-Host "Run it now with:  Start-ScheduledTask -TaskName '$name'"
