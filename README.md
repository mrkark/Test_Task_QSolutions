# QSolutions: Apache + PostgreSQL Web Service in Docker

Решение задачи по контейнеризации:
- **Контейнер `web`**: веб-сервер **Apache 2.4** с модулем **`mod_wsgi`**, обслуживающий сервис на **Flask**.
- **Контейнер `db`**: база данных **PostgreSQL 16** (заменила SQLite).
- Управление обоими сервисами через **Docker Compose** с healthcheck и томами данных.

---

## Быстрый запуск

### 1-клик запуск для заказчика (Docker Compose)
Скрипты полностью автоматически собирают образы, запускают контейнеры, прогоняют тесты и выводят список запущенных контейнеров:

- **Windows**: запустите `docker_setup.bat` (или выберите пункт 5 в `quick_start.bat`).
- **Linux / macOS**:
  ```bash
  chmod +x docker_setup.sh
  ./docker_setup.sh
  ```

### Стандартный запуск через Docker Compose
```bash
# Сборка и запуск контейнеров web и db
docker compose up --build -d

# Просмотр статуса контейнеров
docker ps

# Просмотр логов Apache
docker compose logs -f web

# Остановка сервисов
docker compose down
```

После старта дашборд доступен по адресу: **`http://localhost:8000`**

---

## Архитектура контейнеров

```yaml
services:
  web:
    build: .             # Apache 2.4 + mod_wsgi + Flask
    ports:
      - "8000:80"        # Хост 8000 -> Apache порт 80 внутри контейнера
    volumes:
      - uploads:/app/uploads
    environment:
      DB_HOST: db
      DB_PORT: 5432
      DB_NAME: videos
      DB_USER: video_user
      DB_PASSWORD: video_pass
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16   # PostgreSQL 16
    environment:
      POSTGRES_DB: videos
      POSTGRES_USER: video_user
      POSTGRES_PASSWORD: video_pass
    volumes:
      - db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U video_user -d videos"]
      interval: 5s
      timeout: 5s
      retries: 10
```

- **Хранение данных**: постоянные тома `db_data` (данные PostgreSQL) и `uploads` (видеофайлы) сохраняют все данные между перезапусками контейнеров (`docker compose down` / `up`).
- **Ожидание готовности БД**: сервис `web` стартует только после прохождения healthcheck базы данных `db`, а также дополнительно проверяет доступность соединения через встроенный retry-цикл `wait_for_db()`.

---

## API эндпоинты

- **`POST /upload`** — загрузка видео (`multipart/form-data`: `file`, `company_name`). Сохраняет видео и выполняет upsert в PostgreSQL:
  ```json
  {
    "company_name": "ACME GmbH",
    "video_url": "http://127.0.0.1:8000/media/ACME_GmbH.webm"
  }
  ```
- **`GET /get_video_url?company_name=<name>`** — возвращает URL видео (200 OK) или 404, если компания не найдена.
- **`GET /media/<filename>`** — раздача сохраненного видеофайла из каталога `/app/uploads` (напрямую через Apache Alias и Flask).
- **`GET /videos`** — возвращает JSON-список всех записей в базе данных.
- **`GET /`** — веб-интерфейс с темной темой, окном предпросмотра найденного видео (`Video Preview`), быстрыми кнопками выбора и терминалом ответов сервера.

---

## Клиентские функции (Python SDK)

В файле `video_client.py`:
```python
from video_client import UploadVideo, GetVideoURL

# Загрузка видео
video_url = UploadVideo("http://127.0.0.1:8000", "video/Alpha_Magento_Solutions.webm", "Alpha_Magento_Solutions")
print("Uploaded URL:", video_url)

# Запрос URL по названию компании
found_url = GetVideoURL("http://127.0.0.1:8000", "Alpha_Magento_Solutions")
print("Found URL:", found_url)
```

---

## Юнит-тесты

Запуск тестов верификации сервиса:
```bash
python test_service.py -v
```
Или в 1 клик через `run_tests.bat`. Все 10 тестов проверяют заголовки Apache, PostgreSQL upsert, валидацию, стриминг видео и клиентские функции со статус-кодами и телами ответов.
