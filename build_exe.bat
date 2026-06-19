@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  WhoLikedIt? - PyInstaller Build Script
echo ============================================================
echo.

:: Check venv
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo         Please run install_dependencies.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

:: Verify PyInstaller
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller not found. Run install_dependencies.bat.
    pause
    exit /b 1
)

:: Clean previous build
echo [INFO] Cleaning previous build artifacts...
if exist "dist\" rmdir /s /q "dist"
if exist "build\" rmdir /s /q "build"
if exist "WhoLikedIt.spec" del "WhoLikedIt.spec"
echo [OK] Cleaned.

:: Create assets dir if missing
if not exist "assets\" mkdir assets

echo.
echo [INFO] Running PyInstaller...
echo       This may take several minutes...
echo.

pyinstaller ^
    --name "WhoLikedIt" ^
    --onefile ^
    --windowed ^
    --add-data "assets;assets" ^
    --hidden-import "PyQt6.QtSvg" ^
    --hidden-import "PyQt6.QtSvgWidgets" ^
    --hidden-import "PyQt6.QtNetwork" ^
    --hidden-import "cryptography.hazmat.primitives.kdf.pbkdf2" ^
    --hidden-import "cryptography.hazmat.backends.openssl" ^
    --hidden-import "urllib.request" ^
    --hidden-import "http.server" ^
    --collect-submodules "cryptography" ^
    --collect-submodules "PyQt6" ^
    --collect-submodules "database" ^
    --collect-submodules "game" ^
    --collect-submodules "models" ^
    --collect-submodules "network" ^
    --collect-submodules "services" ^
    --collect-submodules "tiktok" ^
    --collect-submodules "ui" ^
    --collect-submodules "utils" ^
    --noconfirm ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed! Check the output above for details.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build successful!
echo  Executable: dist\WhoLikedIt.exe
echo ============================================================
echo.

:: Check file size
for %%F in ("dist\WhoLikedIt.exe") do (
    set /a SIZE_MB=%%~zF / 1048576
    echo  File size: !SIZE_MB! MB
)

pause
exit /b 0
