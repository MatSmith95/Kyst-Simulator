@echo off
REM Kyst Simulator — Windows build script
REM Produces a standalone KystSimulator.exe in the dist/ folder

echo.
echo ==========================================
echo  Kyst Simulator — Build
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH
    pause
    exit /b 1
)

REM Install / upgrade dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet

echo.
echo Building executable...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "KystSimulator" ^
    --add-data "config/settings.json;config" ^
    --add-data "Manuals;Manuals" ^
    main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  Build complete: dist\KystSimulator.exe
echo ==========================================
pause
