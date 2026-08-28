$action = New-ScheduledTaskAction -Execute "python" -Argument "run_v2.py" -WorkingDirectory "D:\AI\motor-pm"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "MotorPM_AutoStart" -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "OK"
