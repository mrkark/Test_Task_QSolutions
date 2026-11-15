@echo off
@chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion

echo ====================================================
echo   PostgreSQL Companies Table Viewer (Task 3)
echo ====================================================

py -3.13 view_companies.py %*
if %ERRORLEVEL% neq 0 (
    python view_companies.py %*
)

echo.
pause
