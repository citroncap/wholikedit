@echo off
setlocal

echo Starting WhoLikedIt?...

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo         Please run install_dependencies.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with an error.
    pause
)
