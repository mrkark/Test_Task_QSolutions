# QSolutions: Apache + PostgreSQL Web Service in Docker

Веб-сервис для хранения и предпросмотра видео в двух изолированных Docker-контейнерах:
- **`web`**: Apache 2.4 + `mod_wsgi` + Flask (порт 80 внутри контейнера -> 8000 на хосте).
- **`db`**: PostgreSQL 16 (данные сохраняются в Docker-томе `db_data`).

---

## Файлы конфигурации и запуска Docker в репозитории

- **`docker-compose.yml`** — конфигурация сервисов `web` и `db`, томов `db_data` и `uploads`, переменных окружения и healthcheck.
- **`Dockerfile`** — сборка образа веб-сервера (Debian, Apache 2.4, Python 3.11, `mod_wsgi`).
- **`apache.conf`** — конфигурация Apache VirtualHost, mod_wsgi демон-процесса и псевдонима `/media`.
- **`app.wsgi`** — точка входа WSGI для Flask-приложения.
- **`entrypoint.sh`** — скрипт инициализации прав директории `/app/uploads`.
- **`docker_setup.bat`** — скрипт автоматической настройки и запуска в 1 клик для Windows.
- **`docker_setup.sh`** — скрипт автоматической настройки и запуска для Linux / macOS.

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
docker ps

# Остановка контейнеров
docker compose down
```

Дашборд доступен по адресу: **`http://localhost:8000`**

---

## API эндпоинты

- **`POST /upload`** — загрузка видео (`multipart/form-data`: `file`, `company_name`). Сохраняет файл и делает upsert в PostgreSQL.
- **`GET /get_video_url?company_name=<name>`** — возвращает URL видео (200) или ошибку 404.
- **`GET /media/<filename>`** — раздача видеофайла из хранилища.
- **`GET /videos`** — список всех сохраненных записей в JSON.
- **`GET /`** — темный веб-интерфейс с отдельным окном предпросмотра найденного видео (`Video Preview`).

---

## Юнит-тесты

Для проверки запущенного сервиса:
```bash
python test_service.py -v
```
Или двойным кликом по `run_tests.bat`. Все 10 тестов проверяют заголовки Apache, PostgreSQL upsert, валидацию и клиентские функции со статус-кодами и телами ответов.
