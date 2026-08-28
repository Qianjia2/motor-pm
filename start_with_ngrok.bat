@echo off
echo ==========================================
echo   麦科斯韦 - 启动服务器 + ngrok 隧道
echo ==========================================
echo.
echo 启动后端服务...
start "Maxwell Server" python -m uvicorn backend_v2.main:app --host 0.0.0.0 --port 5002
timeout /t 3 /nobreak >nul

echo 启动 ngrok 隧道...
start "ngrok Tunnel" ngrok http 5002
timeout /t 5 /nobreak >nul

echo.
echo ==========================================
echo   服务已启动！
echo.
echo   本地访问: http://127.0.0.1:5002
echo.
echo   获取公网地址: 浏览器打开 http://localhost:4040
echo   或访问 http://127.0.0.1:5002/api/server-info
echo.
echo   外部客户将使用 ngrok 提供的 https:// 地址访问
echo ==========================================
echo.
echo 关闭此窗口不会停止服务。要停止服务，请关闭以下窗口：
echo   - Maxwell Server
echo   - ngrok Tunnel
echo.
pause
