# QSolutions: Apache + PostgreSQL Web Service with Camtasia Zoom in Docker

Веб-сервис для автоматизации записи, хранения, зумирования (Camtasia-style zoom effect) и предпросмотра видео в изолированных Docker-контейнерах:
- **`web`**: Apache 2.4 + `mod_wsgi` + Flask + FFmpeg (порт 80 внутри контейнера -> 8000 на хосте).
- **`db`**: PostgreSQL 16 (данные сохраняются в Docker-томе `db_data`).

---

## Архитектура эффекта зумирования (Camtasia-style Zoom)

1. **Захват событий зума при записи (`qscript.py`)**:
   - Горячая клавиша **F5**: первое нажатие включает приближение в текущей точке курсора мыши, второе — отдаление.
   - Программный хук **`window.__zoomAt(x, y)`**: позволяет сценарию автоматизации управлять приближением/отдалением без нажатия F5.
   - Визуальный индикатор (анимированное цветное кольцо на экране) показывает оператору статус зума.
   - События сохраняются в sidecar JSON файл `<video>.zoom.json` только при наличии хотя бы одного события.

2. **Постобработка видео (`apply_zoom.py` + FFmpeg)**:
   - Применяет фильтр `zoompan` с плавным сглаживанием (smoothstep easing: zoom-in -> hold -> zoom-out).
   - Точное центрирование по координатам мыши с ограничением по границам кадра (`clamp`).
   - Поддержка нескольких непересекающихся пар in/out и открытого зума (open-ended zoom — удержание до конца видео).
   - При отсутствии событий выполняется путь «copy unchanged» без перекодирования.
   - Флаги `--dry-run` (вывод команды FFmpeg без запуска) и `--ffmpeg <path>` (указание кастомного бинарника).

3. **Интеграция в Docker-сервис**:
   - `ffmpeg` установлен в образ веб-сервера (`Dockerfile`).
   - Эндпоинт `POST /jobs/<id>/process` (и `POST /process`) запускает зумирование сохраненного видео.
   - URL обработанного видео сохраняется в PostgreSQL в колонке `processed_video_url`.
   - Веб-дашборд (`http://localhost:8000`) позволяет переключаться между оригинальным и зумированным видео в плеере.

---

## Быстрый запуск

### 1-клик запуск:
- **Windows**: запустите `docker_setup.bat`
- **Linux / macOS**:
  ```bash
  chmod +x docker_setup.sh
  ./docker_setup.sh
  ```

### Запуск через Docker Compose:
```bash
# Сборка и запуск контейнеров в фоне
docker compose up --build -d

# Статус контейнеров
docker compose ps

# Остановка контейнеров
docker compose down
```

Дашборд доступен по адресу: **`http://localhost:8000`**

---

## Команды постобработки (CLI)

```bash
# Обработка видео с автоматическим поиском sidecar JSON
python apply_zoom.py --video video/Alpha_Magento_Solutions.webm

# Превью команды FFmpeg без выполнения кодирования
python apply_zoom.py --video video/Alpha_Magento_Solutions.webm --dry-run
```

---

## API эндпоинты

- **`POST /upload`** — загрузка видео и опционального sidecar (`multipart/form-data`: `file`, `company_name`, `sidecar`).
- **`POST /jobs/<id>/process`** — запуск зумирования видео по его ID через FFmpeg.
- **`POST /process`** — универсальный эндпоинт обработки (по `video_id` или `company_name`).
- **`GET /get_video_url?company_name=<name>`** — возвращает оригинальный `video_url` и `processed_video_url`.
- **`GET /media/<filename>`** — раздача видеофайлов из хранилища (через Apache Alias с поддержкой Range).
- **`GET /videos`** — список всех записей из базы данных PostgreSQL.
- **`GET /`** — веб-интерфейс с плеером (переключение Original / Zoomed) и кнопками запуска обработки.

---

## Тестирование

Запуск всех тестов проекта:
- **Windows**: `run_tests.bat`
- **Linux / macOS**: `./run_tests.sh`

Либо вручную:
```bash
# 1. Тесты логики зума, парсинга sidecar и математики фильтров (pytest)
pytest test_zoom.py -v

# 2. Интеграционные тесты веб-сервиса и API
python test_service.py -v
```
