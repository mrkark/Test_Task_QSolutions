# QSolutions: Browser Automation & Video Web Service

Комплексное решение тестовых заданий:
- **Test Task 1**: Автоматизация браузера через Playwright, чтение задач из CSV, визуализация плавного движения курсора с Cubic Easing, поиск компании в DuckDuckGo и запись видео взаимодействия в формате `.webm`.
- **Test Task 2**: Легковесный веб-сервис на Flask с локальной базой данных SQLite (`videos.db` в режиме WAL), загрузка видеофайлов (`UploadVideo`), выдача URL по названию компании (`GetVideoURL`), раздача медиафайлов (`/media/<filename>`) и интерактивный дашборд с отдельным окном предпросмотра найденного видео.
- **Юнит-тесты**: 10 автоматических тестов с подробным логированием каждого HTTP-запроса и форматированного ответа сервера.

---

## Быстрый запуск в 1 клик

Для максимального удобства подготовлены скрипты быстрого запуска:

| Файл | Назначение |
|---|---|
| **[`quick_start.bat`](file:///d:/Studing/Test_Task_QSolutions/quick_start.bat)** | Интерактивное меню: запуск веб-сервиса, юнит-тестов или рекордера |
| **[`run_tests.bat`](file:///d:/Studing/Test_Task_QSolutions/run_tests.bat)** | Запуск всех 10 юнит-тестов с полным выводом ответов сервера |
| **[`run.bat`](file:///d:/Studing/Test_Task_QSolutions/run.bat)** | Автоматическая проверка зависимостей и запуск рекордера видео |
| **[`run_tests.sh`](file:///d:/Studing/Test_Task_QSolutions/run_tests.sh)** / **[`run.sh`](file:///d:/Studing/Test_Task_QSolutions/run.sh)** | Скрипты запуска для систем Linux / macOS |

---

## Архитектура и структура проекта

```text
Test_Task_QSolutions/
├── web_service.py      # Flask API + SQLite (WAL-режим) + темный дашборд с видеоплеером
├── video_client.py     # Клиентские функции: UploadVideo(...) и GetVideoURL(...)
├── capture_video.py    # Пакетный обработчик CSV, интеграция с сервером и Chromium-превью
├── qscript.py          # Ядро Test Task 1: Playwright-сценарий, SVG-курсор, Cubic Easing
├── test_service.py     # 10 юнит-тестов с выводом статус-кодов, заголовков и JSON-ответов
├── input.csv           # Входной файл компаний (разделитель ';', кодировка UTF-8)
├── requirements.txt    # Зависимости: playwright, flask, requests (только разрешенные)
├── pyproject.toml      # Спецификация пакета и консольные точки входа
├── quick_start.bat     # Интерактивный launcher для Windows
├── run_tests.bat       # Быстрый запуск юнит-тестов для Windows
├── run_tests.sh        # Быстрый запуск юнит-тестов для Linux/macOS
├── run.bat             # Скрипт запуска рекордера для Windows
├── run.sh              # Скрипт запуска рекордера для Linux/macOS
├── Dockerfile          # Сборка и изолированный запуск в Docker
├── video/              # Каталог сохраненных локально видеозаписей (.webm)
└── uploads/            # Каталог загруженных на сервер видеофайлов
```

---

## Установка и подготовка окружения

Требования: **Python 3.9+**

```bash
# 1. Установка разрешенных зависимостей
pip install -r requirements.txt

# 2. Установка браузера Chromium для Playwright
python -m playwright install chromium
```

---

## Веб-сервис и Дашборд (Test Task 2)

### Запуск сервера
```bash
python web_service.py
```
Сервер слушает на `http://127.0.0.1:8000` (хост и порт можно переопределить переменными окружения `FLASK_HOST` и `FLASK_PORT`).

### Возможности интерфейса (`GET /`):
- **Строгий темный дизайн разработчика** (палитра `#0d1117` / `#161b22`, системные моноширинные шрифты, без лишних элементов).
- **Быстрые кнопки тегов**: можно не вводить название компании вручную, а кликнуть на тег (`Alpha_Magento_Solutions`, `Beta_Commerce_Lab`, `Gamma_Web_Services`) или нажать кнопку **«Lookup API»** в строке таблицы.
- **Отдельное окно предпросмотра найденного видео (`Video Preview`)**: при успешном поиске компании прямо на странице открывается окно с **одним найденным видео**, встроенным плеером с автовоспроизведением, названием компании и прямой ссылкой. При отсутствии записи окно автоматически закрывается.
- **Интерактивная панель ответа сервера**: отображает точный HTTP-метод, статус-код ответа и отформатированный JSON.
- **База данных SQLite**: файл `videos.db` создается автоматически, работает в режиме повышенной надежности **WAL (`journal_mode=WAL`)** с таймаутом `busy_timeout=5000` и отдельным подключением на каждый запрос через `flask.g`. Временные метки сохраняются в локальном часовом поясе.

### Эндпоинты API:
- `POST /upload` — загрузка видео (`multipart/form-data`: `file`, `company_name`). Сохраняет файл в `uploads/`, выполняет upsert в базе данных (исключая дубликаты) и возвращает 200 JSON:
  ```json
  {
    "company_name": "ACME GmbH",
    "video_url": "http://127.0.0.1:8000/media/ACME_GmbH.webm"
  }
  ```
- `GET /get_video_url?company_name=<name>` — возвращает JSON с `video_url` (200 OK) или ошибку 404, если компания не найдена.
- `GET /media/<filename>` — отдает видеофайл для воспроизведения в браузере с заголовком `Content-Type: video/webm`.
- `GET /videos` — возвращает список всех записей в базе данных в формате JSON.

---

## Клиентские функции (Python SDK)

В файле [`video_client.py`](file:///d:/Studing/Test_Task_QSolutions/video_client.py) реализованы клиентские функции со строгим соблюдением сигнатур из ТЗ:

```python
from video_client import UploadVideo, GetVideoURL

# Загрузка видео на сервер
video_url = UploadVideo("http://127.0.0.1:8000", "video/Alpha_Magento_Solutions.webm", "Alpha_Magento_Solutions")
print("Uploaded URL:", video_url)

# Запрос URL видео по названию компании
found_url = GetVideoURL("http://127.0.0.1:8000", "Alpha_Magento_Solutions")
print("Found URL:", found_url)
```

---

## Запуск записи видео (Test Task 1 & Интеграция)

### 1. Автономная локальная запись:
```bash
python capture_video.py
```
Скрипт построчно читает `input.csv`, выполняет сценарий в браузере и сохраняет видео в папку `video/`. Библиотека `requests` при этом не требуется (импортируется лениво).

### 2. Запись с автоматической выгрузкой на сервер и превью:
```bash
python capture_video.py --server http://127.0.0.1:8000 --view-seconds 5
```
Параметры:
- `--server <URL>` — адрес работающего веб-сервиса.
- `--view-seconds <N>` — длительность предпросмотра каждого загруженного видео в отдельном окне Chromium (`> 0` — закрыть через N сек, `0` — ждать нажатия Enter).
- Путь к CSV можно передать аргументом: `python capture_video.py my_data.csv --server http://127.0.0.1:8000`.

---

## Юнит-тестирование

### Запуск тестов:
Через командную строку:
```bash
python test_service.py -v
```
Или двойным кликом по файлу **`run_tests.bat`**.

### Что проверяют тесты:
1. `test_01_init_db_schema` — корректность структуры таблицы `videos` в SQLite (`id`, `company_name`, `file_path`, `video_url`, `created_at`, `updated_at`).
2. `test_02_upload_video_endpoint` — успешную загрузку видеофайла через `POST /upload`, сохранение на диск и запись в БД.
3. `test_03_upload_video_upsert` — повторную загрузку для существующей компании (upsert без появления строк-дубликатов).
4. `test_04_get_video_url_found` — получение URL существующего видео через `GET /get_video_url` (HTTP 200).
5. `test_05_get_video_url_not_found` — корректный возврат HTTP 404 и JSON-ошибки для несуществующей компании.
6. `test_06_serve_media` — отдачу видеофайла сервером через `GET /media/<filename>` с кодом 200 и типом `video/webm`.
7. `test_07_list_videos` — получение полного списка записей через `GET /videos`.
8. `test_08_upload_validation_errors` — валидацию входных данных (возврат HTTP 400 при отсутствии файла или названия).
9. `test_09_live_http_client_functions` — работу клиентских функций `UploadVideo` и `GetVideoURL` через **реальный HTTP-сокет** на фоновом сервере.
10. `test_10_index_dashboard_single_video_player` — наличие в веб-дашборде элементов отдельного видеоплеера, быстрого поиска и функций управления.

*Каждый тест выводит подробный лог HTTP-запроса, статус-код, Content-Type и тело ответа сервера.*

---

## Запуск в Docker

```bash
docker build -t qsolutions-video .
docker run --rm -v ${PWD}/video:/app/video qsolutions-video
```
