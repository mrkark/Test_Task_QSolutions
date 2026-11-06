# QSolutions: Browser Automation & Video Web Service

Проект объединяет автоматизацию браузера с записью видео (Playwright) и веб-сервис для хранения и предпросмотра видео (Flask + SQLite).

## Быстрый запуск

### Автоматическая настройка через Docker (в 1 клик для заказчика)
- **`docker_setup.bat`** (Windows) / **`./docker_setup.sh`** (Linux/macOS) — полностью автоматически соберет Docker-контейнеры, запустит веб-сервис на `http://localhost:8000`, выполнит юнит-тесты и выведет список запущенных контейнеров.

### Локальный запуск (Windows)
- **`quick_start.bat`** — интерактивное меню (запуск веб-сервиса, юнит-тестов, рекордера).
- **`run_tests.bat`** — запуск 10 юнит-тестов с выводом ответов сервера.
- **`run.bat`** — запуск рекордера видео.

### Локальный запуск (Linux / macOS)
- **`./run_tests.sh`** — запуск юнит-тестов.
- **`./run.sh`** — запуск рекордера.

---

## Установка

Требуется **Python 3.9+**:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

---

## Запуск компонентов

### 1. Веб-сервис (Flask + SQLite)
```bash
python web_service.py
```
- Доступен по адресу: `http://127.0.0.1:8000` (порт и хост настраиваются через `FLASK_HOST` и `FLASK_PORT`).
- **Главная страница (`GET /`)**: темный интерфейс разработчика, кнопки быстрого выбора компаний, отдельное окно предпросмотра одного найденного видео (`Video Preview`), форма загрузки и вывод ответов API.
- **База данных**: SQLite `videos.db` (режим WAL, локальное время).

#### API:
- `POST /upload` — загрузка видео (`multipart/form-data`: `file`, `company_name`). Возвращает `{"company_name": "...", "video_url": "..."}`.
- `GET /get_video_url?company_name=<name>` — возвращает URL видео (200) или ошибку 404.
- `GET /media/<filename>` — раздача видеофайла из папки `uploads/`.
- `GET /videos` — список всех записей в формате JSON.

### 2. Запись видео (Playwright)
```bash
# Локальная запись видео по input.csv:
python capture_video.py

# Запись с автоматической загрузкой на сервер и превью в браузере:
python capture_video.py --server http://127.0.0.1:8000 --view-seconds 5
```
- Видео сохраняются в папку `./video/` в формате `.webm`.
- Дополнительный CSV можно передать аргументом: `python capture_video.py custom.csv`.

### 3. Юнит-тесты
```bash
python test_service.py -v
```
10 тестов проверяют схему БД, загрузку, upsert, 404, отдачу файлов, валидацию, клиентские функции через реальный HTTP-сокет и веб-дашборд. Каждый тест логирует метод, статус-код и JSON-ответ.

---

## Клиентские функции (Python)

Используются из модуля `video_client.py`:

```python
from video_client import UploadVideo, GetVideoURL

# Загрузка видео
video_url = UploadVideo("http://127.0.0.1:8000", "video/Alpha_Magento_Solutions.webm", "Alpha_Magento_Solutions")

# Получение URL
found_url = GetVideoURL("http://127.0.0.1:8000", "Alpha_Magento_Solutions")
```

---

## Запуск в Docker

Скрипт автоматической настройки:
```bash
# Windows
docker_setup.bat

# Linux / macOS
chmod +x docker_setup.sh
./docker_setup.sh
```

Или вручную через docker compose:
```bash
# Сборка и запуск веб-сервиса в фоне
docker compose up -d web-service

# Запуск юнит-тестов внутри Docker
docker compose run --rm tests

# Просмотр запущенных контейнеров
docker ps

# Остановка контейнеров
docker compose down
```
