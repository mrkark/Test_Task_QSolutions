@echo off
@chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
echo ====================================================
echo Starting Browser Automation Video Recorder
echo ====================================================

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

echo [1/3] Checking and installing Python dependencies...
python -m pip install -r requirements.txt

echo [2/3] Ensuring Playwright Chromium browser is installed...
python -m playwright install chromium

echo [3/3] Running automation recorder...
python capture_video.py %*

echo ====================================================
echo Finished! Check the ./video folder for results.
echo ====================================================
pause
