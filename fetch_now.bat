@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".env" (
    echo [안내] .env 파일이 없습니다.
    echo .env.example 파일을 복사해서 .env 로 이름을 바꾼 뒤 SERPAPI_API_KEY 를 입력해 주세요.
    pause
    exit /b 1
)
echo SerpApi에서 최신 항공권 가격을 수집합니다 (6 크레딧 차감)...
python fetch_flights.py
if errorlevel 1 (
    py fetch_flights.py
)
pause
