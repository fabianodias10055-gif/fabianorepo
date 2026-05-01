@echo off
cd /d "%~dp0"

if not exist ".env" (
    echo ERROR: .env file not found.
    echo Copy .env.example to .env and fill in your ADMIN_SECRET.
    pause
    exit /b 1
)

if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo Starting LocoDev Link Shortener...
echo Admin dashboard: http://localhost:8080/adminlocoILco
echo Press Ctrl+C to stop.
echo.

python server.py
pause
