@echo off
@chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
title QSolutions - Set DeepSeek API Key

echo ======================================================================
echo   QSolutions: Сохранение DeepSeek API Key в .env для Docker
echo ======================================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в переменной PATH.
    echo Пожалуйста, установите Python 3.9+ с https://python.org
    pause
    exit /b 1
)

python set_deepseek_key.py %*

echo.
pause
