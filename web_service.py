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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Video Recorder Web Service</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; color: #1e293b; margin: 0; padding: 24px; }
        .container { max-width: 900px; margin: 0 auto; }
        .card { background: white; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); padding: 24px; margin-bottom: 24px; }
        h1 { color: #0f172a; margin-top: 0; display: flex; align-items: center; gap: 10px; }
        .badge { background: #22c55e; color: white; font-size: 12px; padding: 4px 10px; border-radius: 9999px; font-weight: bold; }
        pre { background: #f1f5f9; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 13px; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #e2e8f0; font-size: 14px; }
        th { background: #f8fafc; color: #64748b; font-weight: 600; }
        a { color: #2563eb; text-decoration: none; font-weight: 500; }
        a:hover { text-decoration: underline; }
        video { max-width: 240px; border-radius: 6px; border: 1px solid #cbd5e1; }
        .endpoint { display: inline-block; font-weight: bold; padding: 2px 6px; border-radius: 4px; font-size: 12px; margin-right: 6px; }
        .get { background: #dbeafe; color: #1d4ed8; }
        .post { background: #dcfce7; color: #15803d; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>Video Recorder Web Service <span class="badge">ONLINE</span></h1>
            <p>The web service is operational and ready to receive video uploads and queries.</p>
            <h3>Available Endpoints:</h3>
            <ul>
                <li><span class="endpoint post">POST</span> <code>/upload</code> — Upload a video (multipart/form-data: <code>file</code>, <code>company_name</code>)</li>
                <li><span class="endpoint get">GET</span> <code>/get_video_url?company_name=&lt;name&gt;</code> — Look up video URL by company</li>
                <li><span class="endpoint get">GET</span> <code>/media/&lt;filename&gt;</code> — Stream uploaded video file</li>
                <li><span class="endpoint get">GET</span> <a href="/videos"><code>/videos</code></a> — List all records as JSON</li>
            </ul>
        </div>

        <div class="card">
            <h2>Uploaded Videos ({{ count }})</h2>
            {% if rows %}
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Company</th>
                        <th>Video Preview</th>
                        <th>Video URL</th>
                        <th>Updated At</th>
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
                                Your browser does not support webm video.
                            </video>
                        </td>
                        <td><a href="{{ row.video_url }}" target="_blank">Open Video</a></td>
                        <td>{{ row.updated_at }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="color: #64748b;">No videos uploaded yet. Run <code>python capture_video.py --server http://127.0.0.1:8000</code> to record and upload videos.</p>
            {% endif %}
        </div>
    </div>
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
