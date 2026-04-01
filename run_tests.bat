@echo off
REM Run all Kyst Simulator tests
echo.
echo ==========================================
echo  Kyst Simulator — Test Suite
echo ==========================================
echo.
python -m pytest tests/ -v
pause
