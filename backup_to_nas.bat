@echo off
chcp 65001 >nul
echo ==============================
echo   MotorPM 数据备份到 NAS
echo ==============================
echo.

set NAS_PATH=\\10.136.101.13\easitech\个人文件夹\qianjia\麦克斯韦-AI项目管理平台工具后台资料存放
set LOCAL_DATA=D:\AI\motor-pm\data
set DATE_STR=%date:~0,4%%date:~5,2%%date:~8,2%

echo 备份日期: %DATE_STR%
echo 源: %LOCAL_DATA%
echo 目标: %NAS_PATH%\backup_%DATE_STR%
echo.

echo 正在备份...
robocopy "%LOCAL_DATA%" "%NAS_PATH%\backup_%DATE_STR%" /E /XO /R:2 /W:5 /NP /NFL /NDL

if %ERRORLEVEL% LEQ 3 (
    echo [OK] 备份完成
) else (
    echo [FAIL] 备份失败，请检查 NAS 连接
)

echo.
echo 保留最近 30 天的备份...
forfiles /P "%NAS_PATH%" /M "backup_*" /D -30 /C "cmd /c rmdir /s /q @path" 2>nul
echo [OK] 清理完成
echo.
pause
