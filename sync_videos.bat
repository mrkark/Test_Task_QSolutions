@echo off
@chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
title QSolutions - Sync Videos to Docker

echo ======================================================================
echo   QSolutions: Синхронизация записанных видео с базой данных Docker
echo ======================================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в переменной PATH.
    echo Пожалуйста, установите Python 3.9+ с https://python.org
    pause
    exit /b 1
)

python sync_videos.py %*

echo.
pause
