@echo off
chcp 65001 >nul
title 电机项目管理平台 v2.0
cd /d D:\AI\motor-pm

set PY=C:\Users\qianjia\AppData\Local\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python

echo ========================================
echo   电机项目管理平台 v2.0
echo ========================================
echo.

:: Step 1: Kill ALL existing python/ngrok processes
echo [1/4] 清理旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5002" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM ngrok.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo   旧进程已清理

:: Step 2: Start server via watchdog (which auto-restarts on crash)
echo [2/4] 启动服务器+守护进程...
start "MotorPM_Server" "%PY%" server_watchdog.py
timeout /t 8 /nobreak >nul

:: Check server
"%PY%" -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:5002/api/health',timeout=5); print(r.read().decode())" 2>nul
if %errorlevel% neq 0 (
    echo   [ERROR] 服务器启动失败，查看 data\server.log
    pause
    exit /b 1
)
echo   [OK] 服务器已就绪

:: Step 3: Start ngrok tunnel
echo [3/4] 启动外网隧道...
start "MotorPM_Tunnel" ngrok.exe http 5002 --log=stdout
timeout /t 6 /nobreak >nul

:: Get tunnel URL
"%PY%" -c "import urllib.request,json; r=json.loads(urllib.request.urlopen('http://127.0.0.1:4040/api/tunnels',timeout=3).read()); t=r['tunnels'][0]; print(t['public_url'])" > "%TEMP%\ngrok_url.txt" 2>nul
set TUNNEL_URL=
for /f "delims=" %%a in (%TEMP%\ngrok_url.txt) do set TUNNEL_URL=%%a

if "%TUNNEL_URL%"=="" (
    echo   [WARN] 隧道启动中，稍后可用
) else (
    echo   [OK] 外网地址: %TUNNEL_URL%
)

:: Step 4: Get local IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4" ^| findstr "10."') do set LOCAL_IP=%%a
set LOCAL_IP=%LOCAL_IP: =%
if "%LOCAL_IP%"=="" set LOCAL_IP=10.136.101.192

echo [4/4] 访问地址:
echo.
echo   == 内网 ==
echo   本机:  http://127.0.0.1:5002
echo   内网:  http://%LOCAL_IP%:5002
echo.
echo   == 外网 ==
if not "%TUNNEL_URL%"=="" (
    echo   %TUNNEL_URL%
) else (
    echo   隧道启动中（约10秒），请稍后刷新
)
echo.
echo   账号: admin / admin123
echo ========================================
echo.
echo 关闭此窗口不影响服务运行
echo.
pause
