# QSolutions: Browser Automation Recorder & Video Web Service

Объединенный проект, реализующий **Test Task 1** (автоматизация браузера Playwright и запись видео по данным CSV) и **Test Task 2** (веб-сервис Flask, база данных SQLite, загрузка видео, API получения URL и предпросмотр в браузере).

---

## Быстрый запуск в 1 клик

### Windows:
Запустите файл **`run.bat`** (двойным кликом или из терминала).  
Скрипт автоматически проверит Python, установит необходимые зависимости (`requirements.txt`), скачает Playwright Chromium и откроет интерактивное меню:
```text
====================================================
 Select Run Mode:
====================================================
 [1] Full Pipeline (Auto-start server + record + upload + preview)
 [2] Web Service Dashboard (Start server at http://127.0.0.1:8000)
 [3] Video Recorder Only (Task 1 local recording)
 [4] Run Unit Tests (Task 2 API verification with server responses)
 [5] Exit
====================================================
```

### Linux / macOS:
```bash
chmod +x run.sh
./run.sh
```

---

## Архитектура проекта

```text
Test_Task_QSolutions/
├── capture_video.py    # Главная точка входа: обработка CSV, запись, вызов загрузки и превью
├── qscript.py          # Реализация Test Task 1: Playwright скрипт с визуализацией курсора
├── web_service.py      # Реализация Test Task 2: Flask API + SQLite база данных + Dashboard
├── video_client.py     # Клиентские функции: UploadVideo(...) и GetVideoURL(...)
├── test_service.py     # Юнит-тесты с выводом ответов сервера (JSON, заголовки, коды)
├── input.csv           # Входной CSV-файл с разделителем ';'
├── requirements.txt    # Зависимости: playwright, flask, requests
├── pyproject.toml      # Спецификация пакета и CLI-команды
├── run.bat             # Интерактивный раннер для Windows
├── run.sh              # Интерактивный раннер для Linux/macOS
├── Dockerfile          # Сборка в изолированном контейнере
├── video/              # Каталог для локально записанных .webm видео
└── uploads/            # Каталог для загруженных на сервер видео
```

---

## Ручная установка и окружение

Требования: **Python 3.9+**

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

---

## Режимы запуска

### 1. Единый пайплайн (Full Pipeline: запись + загрузка + превью)
Автоматически поднимает фоновый веб-сервис, построчно выполняет автоматизацию в браузере, записывает видео, загружает его на сервер и сразу показывает превью в Chromium:
```bash
python capture_video.py --auto-server --view-seconds 5
```
Либо с предварительно запущенным внешним сервером:
```bash
python capture_video.py --server http://127.0.0.1:8000 --view-seconds 5
```
Параметры:
- `--server <URL>` — адрес сервера (например, `http://127.0.0.1:8000`).
- `--auto-server` — автоматически запустить встроенный веб-сервер в фоне.
- `--view-seconds <N>` — длительность показа превью (`> 0` секунд, либо `0` для ожидания нажатия Enter).
- `csv_file` — путь к произвольному CSV (по умолчанию `input.csv`). Например:
  ```bash
  python capture_video.py custom_tasks.csv --auto-server
  ```

---

### 2. Веб-сервис и Дашборд (Test Task 2)
```bash
python web_service.py
```
Сервис слушает на `http://127.0.0.1:8000` (переопределяется через переменные окружения `FLASK_HOST` и `FLASK_PORT`).

#### Возможности веб-интерфейса (`GET /`):
- Строгий темный дизайн в стиле разработчика (без лишних элементов и эмодзи).
- **Кнопки быстрого запроса**: не нужно вручную вводить названия компаний или URL — достаточно кликнуть по тегу компании (`Alpha_Magento_Solutions`, `Beta_Commerce_Lab`, `Gamma_Web_Services`) или нажать кнопку **"Lookup API"** рядом с нужной записью.
- Встроенный плеер для каждого загруженного видео.
- Форма для ручной загрузки видео (`POST /upload`).
- Интерактивная терминальная панель, отображающая точные HTTP-запросы и JSON-ответы сервера.

#### API эндпоинты:
- **`POST /upload`** — принимает `multipart/form-data` (`file` и `company_name`). Сохраняет файл в `uploads/`, выполняет upsert в SQLite (`videos.db`) и возвращает JSON:
  ```json
  {
    "company_name": "Alpha_Magento_Solutions",
    "video_url": "http://127.0.0.1:8000/media/Alpha_Magento_Solutions.webm"
  }
  ```
- **`GET /get_video_url?company_name=<name>`** — возвращает URL видео по названию компании (HTTP 200) или HTTP 404, если запись не найдена.
- **`GET /media/<filename>`** — отдает видеофайл для воспроизведения в браузере.
- **`GET /videos`** — возвращает JSON-список всех записей в базе данных.

---

### 3. Только запись видео (Test Task 1 Standalone)
Запись видео без обращения к серверу:
```bash
python capture_video.py
```
Все видео сохраняются в папку `video/`.

---

### 4. Юнит-тесты (Верификация API и сервера)
Тесты проверяют структуру SQLite, `POST /upload`, предотвращение дубликатов (upsert), `GET /get_video_url` (найдено / 404), раздачу медиафайлов через `GET /media/<filename>`, валидацию входных данных, а также живое сетевое взаимодействие через клиентские функции `UploadVideo` и `GetVideoURL`:
```bash
python test_service.py -v
```
*Каждый тест выводит подробный лог HTTP-запроса и полный ответ сервера (статус-код, Content-Type, тело JSON/бинарные данные).*

---

### 5. Запуск через Docker
```bash
docker build -t video-recorder .
docker run --rm -v ${PWD}/video:/app/video video-recorder
```

---

## Клиентские функции (Python SDK)

В файле `video_client.py` реализованы функции с точными сигнатурами из спецификации:
```python
from video_client import UploadVideo, GetVideoURL

# 1. Загрузка видео
video_url = UploadVideo("http://127.0.0.1:8000", "video/Alpha_Magento_Solutions.webm", "Alpha_Magento_Solutions")
print(video_url)

# 2. Получение URL видео
url = GetVideoURL("http://127.0.0.1:8000", "Alpha_Magento_Solutions")
print(url)
```

---

## Чек-лист соответствия требованиям (Acceptance Checklist)

- [x] Чистая установка через `pip install -r requirements.txt` и `python -m playwright install chromium`.
- [x] Автоматическое создание `videos.db` и каталога `uploads/`.
- [x] `POST /upload` возвращает статус 200 и рабочий `video_url`.
- [x] `GET /media/<filename>` отдает видеофайл с корректным воспроизведением в браузере.
- [x] `GET /get_video_url?company_name=...` возвращает URL видео и 404 для неизвестных компаний.
- [x] База данных SQLite сохраняет `company_name`, `file_path` и `video_url` (режим WAL, таймаут ожидания).
- [x] Повторная загрузка для существующей компании обновляет запись (upsert без дубликатов).
- [x] `capture_video.py --server <URL>` загружает видео и открывает предпросмотр в Chromium.
- [x] Опция `--view-seconds` корректно управляет временем показа окна превью.
- [x] Ошибки при загрузке или превью отдельной строки не прерывают обработку всего CSV.
- [x] Модуль `requests` импортируется лениво (скрипт может выполняться без `requests`, если `--server` не передан).
