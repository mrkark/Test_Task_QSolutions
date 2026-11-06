FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_HOST=0.0.0.0 \
    FLASK_PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "web_service.py"]
