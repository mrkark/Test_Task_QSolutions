@echo off
setlocal
title QSolutions - Interactive Screen Recorder (F5 Zoom)

echo ======================================================================
echo   QSolutions: Интерактивная запись экрана человеком (проверка F5 зума)
echo ======================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ОШИБКА] Python не найден в PATH!
    echo Установите Python 3.9+ с официального сайта https://python.org
    pause
    exit /b 1
)

set REC_NAME=Operator_Zoom_Test
set REC_URL=https://duckduckgo.com

set /p user_name="Введите название записи/компании (по умолчанию: %REC_NAME%): "
if not "%user_name%"=="" set REC_NAME=%user_name%

set /p user_url="Введите начальный URL (по умолчанию: %REC_URL%): "
if not "%user_url%"=="" set REC_URL=%user_url%

echo.
echo [*] Запуск браузера для записи...
echo [*] В открывшемся окне нажимайте F5 (или экранную кнопку [Zoom (F5)]) для зума к курсору.
echo [*] Чтобы завершить запись, просто закройте окно браузера или нажмите Enter здесь.
echo.

python record_interactive.py --name "%REC_NAME%" --url "%REC_URL%"

echo.
echo ======================================================================
echo Запись завершена! Все файлы сохранены в папке ./video
echo ======================================================================
pause
