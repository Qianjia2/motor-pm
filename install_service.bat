@echo off
chcp 65001 >nul
cd /d D:\AI\motor-pm

echo ========================================
echo   注册开机自启服务
echo ========================================
echo.

set PY=C:\Users\qianjia\AppData\Local\Programs\Python\Python312\python.exe

echo 正在创建计划任务...
schtasks /Create /SC ONSTART /TN "MotorPM_Server" /TR "\"%PY%\" run_v2.py" /RU %USERNAME% /F /DELAY 0001:00 >nul 2>&1

if %errorlevel%==0 (
    echo   [OK] 已注册开机自启
    echo   以后电脑启动后自动运行，不需要手动开
) else (
    echo   需要管理员权限，正在重试...
    powershell -Command "Start-Process cmd -ArgumentList '/c schtasks /Create /SC ONSTART /TN MotorPM_Server /TR \"\"%PY%\" run_v2.py\" /RU %USERNAME% /F /DELAY 0001:00' -Verb RunAs"
)

echo.
echo ========================================
echo 现在立即启动服务器...
"%PY%" -m uvicorn backend_v2.main:app --host 0.0.0.0 --port 5002 > data\server.log 2>&1 &
timeout /t 5 /nobreak >nul
echo 服务器已启动: http://localhost:5002
echo 账号: admin / admin123
echo ========================================
pause
