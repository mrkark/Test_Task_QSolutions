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

## Стандартная установка и запуск

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### Запуск (использует `input.csv`):
```bash
python capture_video.py
```

### Запуск с указанием своего CSV-файла:
```bash
python capture_video.py path/to/custom_input.csv
```

---

## Запуск через Docker

```bash
docker build -t video-recorder .
docker run --rm -v ${PWD}/video:/app/video video-recorder
```
