@echo off
@chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
title QSolutions - Interactive Screen Recorder

echo ======================================================================
echo   QSolutions: Interactive Screen Recorder (F5 Zoom)
echo ======================================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

set "REC_NAME=Operator_Zoom_Test"
set "REC_URL=https://duckduckgo.com"

echo Recording or company name [default: %REC_NAME%]:
set /p "user_name=> "
if defined user_name set "REC_NAME=%user_name%"

echo Starting URL [default: %REC_URL%]:
set /p "user_url=> "
if defined user_url set "REC_URL=%user_url%"

echo.
echo [*] Starting browser for recording...
echo [*] Press F5 in the browser to Zoom In / Zoom Out at mouse cursor.
echo [*] Close the browser window or press Enter here to finish.
echo.

python record_interactive.py --name "%REC_NAME%" --url "%REC_URL%"

echo.
echo ======================================================================
echo Recording complete. Files saved in ./video
echo ======================================================================
pause
