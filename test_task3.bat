@echo off
@chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion

echo ====================================================
echo  Running Task 3 Tests ONLY (Companies & DeepSeek)
echo ====================================================

py -3.13 -m unittest test_task3.py -v
if %ERRORLEVEL% neq 0 (
    python -m unittest test_task3.py -v
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Task 3 tests failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ====================================================
echo  Task 3 tests passed successfully!
echo ====================================================
pause
