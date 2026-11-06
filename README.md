# Test_Task_QSolutions

## Быстрый запуск в 1 клик

### Windows:
Просто запустите файл `run.bat` двойным кликом (скрипт сам проверит зависимости, установит Chromium и запустит запись видео).

### Linux / macOS:
```bash
chmod +x run.sh
./run.sh
```

---

## Стандартная установка

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

---

## Запуск веб-сервиса (Test Task 2)

Сервис сохраняет видео в папку `uploads/` и фиксирует записи в базе данных SQLite `videos.db`.

```bash
python web_service.py
```
По умолчанию сервис слушает на `0.0.0.0:8000`.

---

## Запуск записи видео

### Стандартный запуск без сервера:
```bash
python capture_video.py
```

### Запуск с автоматической загрузкой на сервер и предпросмотром в браузере:
```bash
python capture_video.py --server http://127.0.0.1:8000 --view-seconds 5
```

Параметры:
- `--server <URL>`: адрес сервера для загрузки каждого видео.
- `--view-seconds <N>`: время показа превью в Chromium (если `> 0` — закрывается через N секунд, если `0` — ожидает нажатия Enter).
- Путь к кастомному CSV можно передать позиционным аргументом, например: `python capture_video.py custom.csv --server http://127.0.0.1:8000`.

---

## Запуск юнит-тестов

Запуск тестов с подробным отображением запросов и ответов сервера (JSON, заголовки, статус-коды):
```bash
python test_service.py -v
```

---

## Запуск через Docker

```bash
docker build -t video-recorder .
docker run --rm -v ${PWD}/video:/app/video video-recorder
```
