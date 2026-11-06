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
