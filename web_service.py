import os
import re
import sqlite3
from flask import Flask, request, jsonify, send_from_directory, g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "videos.db"))
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL UNIQUE,
                file_path TEXT NOT NULL,
                video_url TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_PATH, timeout=10.0)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL;")
        g.db.execute("PRAGMA busy_timeout=5000;")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def sanitize_filename(company_name: str, original_filename: str = "") -> str:
    ext = os.path.splitext(original_filename)[1] if original_filename else ".webm"
    if not ext:
        ext = ".webm"
    safe_name = re.sub(r"[^\w\-.]", "_", company_name).strip("_")
    if not safe_name:
        safe_name = "video"
    return f"{safe_name}{ext}"


@app.route("/", methods=["GET"])
def index():
    db = get_db()
    cursor = db.execute("SELECT id, company_name, file_path, video_url, created_at, updated_at FROM videos ORDER BY id DESC")
    rows = [dict(row) for row in cursor.fetchall()]

    html = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Video Recorder Web Service Dashboard</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
        h1 { margin: 0; font-size: 24px; display: flex; align-items: center; gap: 12px; }
        .badge { background: #22c55e; color: #022c22; font-size: 12px; padding: 4px 10px; border-radius: 9999px; font-weight: bold; }
        .card { background: #1e293b; border-radius: 12px; border: 1px solid #334155; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }
        .card h2 { margin-top: 0; font-size: 18px; color: #38bdf8; display: flex; align-items: center; gap: 8px; }
        .btn-group { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
        .btn { cursor: pointer; background: #3b82f6; color: white; border: none; border-radius: 8px; padding: 8px 16px; font-size: 14px; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; transition: background 0.2s, transform 0.1s; }
        .btn:hover { background: #2563eb; }
        .btn:active { transform: scale(0.98); }
        .btn-success { background: #10b981; }
        .btn-success:hover { background: #059669; }
        .btn-purple { background: #8b5cf6; }
        .btn-purple:hover { background: #7c3aed; }
        .btn-secondary { background: #475569; }
        .btn-secondary:hover { background: #334155; }
        .btn-sm { padding: 6px 12px; font-size: 12px; border-radius: 6px; }
        .chip { cursor: pointer; background: #334155; color: #cbd5e1; border: 1px solid #475569; border-radius: 9999px; padding: 4px 12px; font-size: 12px; transition: all 0.2s; }
        .chip:hover { background: #38bdf8; color: #0f172a; border-color: #38bdf8; font-weight: bold; }
        .form-row { display: flex; gap: 10px; margin-top: 12px; align-items: center; }
        input[type="text"], input[type="file"] { background: #0f172a; border: 1px solid #475569; color: white; border-radius: 8px; padding: 8px 12px; font-size: 14px; flex: 1; outline: none; }
        input[type="text"]:focus { border-color: #38bdf8; }
        .console { background: #020617; border: 1px solid #1e293b; border-radius: 8px; padding: 14px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 13px; color: #38bdf8; margin-top: 14px; min-height: 50px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #334155; font-size: 14px; }
        th { color: #94a3b8; font-weight: 600; }
        video { max-width: 220px; border-radius: 6px; border: 1px solid #475569; }
        a { color: #38bdf8; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Video Recorder Service <span class="badge">ONLINE</span></h1>
            <div>
                <button class="btn btn-secondary" onclick="fetchVideos()">📋 Показать все видео (/videos)</button>
            </div>
        </div>

        <div class="card">
            <h2>🔍 Проверить URL видео по компании (GET /get_video_url)</h2>
            <p style="color: #94a3b8; font-size: 13px; margin: 0 0 10px 0;">Нажмите на компанию ниже или введите название, затем нажмите кнопку запроса:</p>
            <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px;">
                <span class="chip" onclick="setCompany('Alpha_Magento_Solutions')">Alpha_Magento_Solutions</span>
                <span class="chip" onclick="setCompany('Beta_Commerce_Lab')">Beta_Commerce_Lab</span>
                <span class="chip" onclick="setCompany('Gamma_Web_Services')">Gamma_Web_Services</span>
            </div>
            <div class="form-row">
                <input type="text" id="companyInput" placeholder="Введите название компании (например, Alpha_Magento_Solutions)">
                <button class="btn" onclick="lookupVideo()">Найти видео</button>
            </div>
        </div>

        <div class="card">
            <h2>📤 Загрузить видео вручную (POST /upload)</h2>
            <form id="uploadForm" onsubmit="handleUpload(event)">
                <div class="form-row">
                    <input type="text" id="uploadCompany" placeholder="Название компании" required>
                    <input type="file" id="uploadFile" accept=".webm,.mp4" required>
                    <button type="submit" class="btn btn-success">Загрузить видео</button>
                </div>
            </form>
        </div>

        <div class="card" id="consoleCard" style="display: none;">
            <h2>⚡ Ответ от сервера в реальном времени:</h2>
            <div class="console" id="consoleOutput">Ожидание действий...</div>
        </div>

        <div class="card">
            <h2>📁 Записанные видео в базе данных ({{ count }})</h2>
            {% if rows %}
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Компания</th>
                        <th>Видео</th>
                        <th>Действия</th>
                        <th>Дата</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in rows %}
                    <tr>
                        <td>{{ row.id }}</td>
                        <td><strong>{{ row.company_name }}</strong></td>
                        <td>
                            <video controls preload="metadata">
                                <source src="{{ row.video_url }}" type="video/webm">
                            </video>
                        </td>
                        <td>
                            <div class="btn-group">
                                <button class="btn btn-sm btn-purple" onclick="testLookup('{{ row.company_name }}')">API Ссылка</button>
                                <a class="btn btn-sm btn-secondary" href="{{ row.video_url }}" target="_blank">Открыть напрямую</a>
                            </div>
                        </td>
                        <td style="color: #94a3b8; font-size: 13px;">{{ row.updated_at }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="color: #94a3b8;">Пока нет загруженных видео. Вы можете загрузить видео кнопкой выше или запустить скрипт:<br><code>python capture_video.py --server http://127.0.0.1:8000</code></p>
            {% endif %}
        </div>
    </div>

    <script>
        function logResponse(text) {
            const card = document.getElementById('consoleCard');
            const output = document.getElementById('consoleOutput');
            card.style.display = 'block';
            output.textContent = text;
            card.scrollIntoView({ behavior: 'smooth' });
        }

        function setCompany(name) {
            document.getElementById('companyInput').value = name;
            lookupVideo();
        }

        async function lookupVideo() {
            const company = document.getElementById('companyInput').value.trim();
            if (!company) {
                alert('Пожалуйста, введите или выберите название компании');
                return;
            }
            logResponse(`>>> GET /get_video_url?company_name=${encodeURIComponent(company)}\nОтправка запроса...`);
            try {
                const res = await fetch(`/get_video_url?company_name=${encodeURIComponent(company)}`);
                const json = await res.json();
                logResponse(`<<< HTTP Статус: ${res.status} ${res.statusText}\n<<< JSON Ответ сервера:\n` + JSON.stringify(json, null, 2));
            } catch (err) {
                logResponse(`<<< Ошибка выполнения запроса: ${err}`);
            }
        }

        function testLookup(name) {
            document.getElementById('companyInput').value = name;
            lookupVideo();
        }

        async function fetchVideos() {
            logResponse('>>> GET /videos\nЗапрос списка записей...');
            try {
                const res = await fetch('/videos');
                const json = await res.json();
                logResponse(`<<< HTTP Статус: ${res.status} ${res.statusText}\n<<< Список всех записей в базе данных:\n` + JSON.stringify(json, null, 2));
            } catch (err) {
                logResponse(`<<< Ошибка: ${err}`);
            }
        }

        async function handleUpload(e) {
            e.preventDefault();
            const company = document.getElementById('uploadCompany').value.trim();
            const fileInput = document.getElementById('uploadFile');
            if (!company || fileInput.files.length === 0) return;

            const formData = new FormData();
            formData.append('company_name', company);
            formData.append('file', fileInput.files[0]);

            logResponse(`>>> POST /upload (company: ${company}, file: ${fileInput.files[0].name})\nЗагрузка файла...`);
            try {
                const res = await fetch('/upload', { method: 'POST', body: formData });
                const json = await res.json();
                logResponse(`<<< HTTP Статус: ${res.status} ${res.statusText}\n<<< JSON Ответ сервера:\n` + JSON.stringify(json, null, 2));
                if (res.ok) {
                    setTimeout(() => location.reload(), 1500);
                }
            } catch (err) {
                logResponse(`<<< Ошибка загрузки: ${err}`);
            }
        }
    </script>
</body>
</html>"""
    from flask import render_template_string
    return render_template_string(html, rows=rows, count=len(rows)), 200


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    return "", 204


@app.route("/upload", methods=["POST"])
def upload_video():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    uploaded_file = request.files["file"]
    company_name = request.form.get("company_name", "").strip()

    if not company_name:
        return jsonify({"error": "company_name is required"}), 400

    if not uploaded_file or uploaded_file.filename == "":
        return jsonify({"error": "No file selected for uploading"}), 400

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = sanitize_filename(company_name, uploaded_file.filename)
    absolute_file_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, filename))
    uploaded_file.save(absolute_file_path)

    base_url = request.host_url.rstrip("/")
    video_url = f"{base_url}/media/{filename}"

    db = get_db()
    db.execute(
        """
        INSERT INTO videos (company_name, file_path, video_url, created_at, updated_at)
        VALUES (?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(company_name) DO UPDATE SET
            file_path = excluded.file_path,
            video_url = excluded.video_url,
            updated_at = datetime('now');
        """,
        (company_name, absolute_file_path, video_url),
    )
    db.commit()

    return jsonify({"company_name": company_name, "video_url": video_url}), 200


@app.route("/get_video_url", methods=["GET"])
def get_video_url():
    company_name = request.args.get("company_name", "").strip()
    if not company_name:
        return jsonify({"error": "company_name query parameter is required"}), 400

    db = get_db()
    cursor = db.execute(
        "SELECT company_name, video_url FROM videos WHERE company_name = ?",
        (company_name,),
    )
    row = cursor.fetchone()

    if not row:
        return jsonify({"error": f"Company '{company_name}' not found"}), 404

    return jsonify({"company_name": row["company_name"], "video_url": row["video_url"]}), 200


@app.route("/media/<path:filename>", methods=["GET"])
def serve_media(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/videos", methods=["GET"])
def list_videos():
    db = get_db()
    cursor = db.execute("SELECT id, company_name, file_path, video_url, created_at, updated_at FROM videos ORDER BY id ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    return jsonify(rows), 200


init_db()

def main():
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "8000"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
