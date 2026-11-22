@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===================================================
echo  Tokyo Ariake Arena Flight Tracker (Local Server)
echo  Browser: http://localhost:8000
echo  종료하려면 이 창에서 Ctrl + C 를 누르세요.
echo ===================================================
start "" http://localhost:8000
python -m http.server 8000
if errorlevel 1 (
    py -m http.server 8000
)
pause
