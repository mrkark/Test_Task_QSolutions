@echo off
setlocal

echo ====================================================
echo  Running Unit Tests for Web Service and API
echo ====================================================

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

python test_service.py -v

echo.
echo ====================================================
echo  Tests finished. Press any key to exit.
echo ====================================================
pause >nul
