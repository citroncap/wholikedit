@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  WhoLikedIt? - Dependency Installer
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Download Python 3.12+ from https://python.org
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set PY_VER=%%V
echo [OK] Python %PY_VER% found.

:: Create virtual environment
if not exist "venv\" (
    echo.
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

:: Activate venv
echo.
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo [OK] Virtual environment activated.

:: Upgrade pip
echo.
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip upgraded.

:: Install requirements
echo.
echo [INFO] Installing dependencies from requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install one or more dependencies.
    pause
    exit /b 1
)

:: Verify key packages
echo.
echo [INFO] Verifying installations...
python -c "from PyQt6.QtCore import PYQT_VERSION_STR; print('[OK] PyQt6', PYQT_VERSION_STR)"
if errorlevel 1 ( echo [FAIL] PyQt6 & goto :fail )

python -c "from PyQt6.QtWebEngineWidgets import QWebEngineView; print('[OK] PyQt6-WebEngine')"
if errorlevel 1 ( echo [FAIL] PyQt6-WebEngine & goto :fail )

python -c "import cryptography; print('[OK] cryptography', cryptography.__version__)"
if errorlevel 1 ( echo [FAIL] cryptography & goto :fail )

python -c "import PIL; print('[OK] Pillow', PIL.__version__)"
if errorlevel 1 ( echo [FAIL] Pillow & goto :fail )

python -c "import websockets; print('[OK] websockets', websockets.__version__)"
if errorlevel 1 ( echo [FAIL] websockets & goto :fail )

:: Add Windows Firewall rule for multiplayer
echo.
echo [INFO] Adding Windows Firewall rule for multiplayer (ports 45100-45200)...
netsh advfirewall firewall show rule name="WhoLikedIt" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="WhoLikedIt" ^
        dir=in action=allow protocol=TCP localport=45100-45200 ^
        description="WhoLikedIt multiplayer game" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Could not add firewall rule automatically.
        echo        To fix connection issues, run this as Administrator:
        echo        netsh advfirewall firewall add rule name="WhoLikedIt" dir=in action=allow protocol=TCP localport=45100-45200
    ) else (
        echo [OK] Firewall rule added.
    )
) else (
    echo [OK] Firewall rule already exists.
)

echo.
echo ============================================================
echo  All dependencies installed successfully!
echo  Run launch.bat to start the application.
echo ============================================================
pause
exit /b 0

:fail
echo.
echo [ERROR] Verification failed. Please re-run this script.
pause
exit /b 1
