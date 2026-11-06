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
    <title>Video Service Dashboard</title>
    <style>
        :root {
            --bg: #0d1117;
            --surface: #161b22;
            --surface-hover: #1f242c;
            --border: #30363d;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --btn-bg: #21262d;
            --btn-border: #363b42;
            --btn-hover: #30363d;
            --accent: #238636;
            --accent-hover: #2ea043;
            --blue: #1f6feb;
            --blue-hover: #388bfd;
        }

        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text-primary);
            margin: 0;
            padding: 24px;
            font-size: 14px;
            line-height: 1.5;
        }

        .container {
            max-width: 960px;
            margin: 0 auto;
        }

        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 20px;
        }

        .header h1 {
            font-size: 20px;
            font-weight: 600;
            margin: 0;
            letter-spacing: -0.2px;
        }

        .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            background-color: var(--accent);
            border-radius: 50%;
            margin-right: 6px;
        }

        .section {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 16px;
        }

        .section-title {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0 0 12px 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .btn {
            appearance: none;
            cursor: pointer;
            background: var(--btn-bg);
            border: 1px solid var(--btn-border);
            color: var(--text-primary);
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            font-family: inherit;
            transition: 0.15s cubic-bezier(0.3, 0, 0.5, 1);
        }

        .btn:hover {
            background: var(--btn-hover);
            border-color: #8b949e;
        }

        .btn-primary {
            background: var(--accent);
            border-color: rgba(240, 246, 252, 0.1);
            color: #ffffff;
        }

        .btn-primary:hover {
            background: var(--accent-hover);
        }

        .btn-blue {
            background: var(--blue);
            border-color: rgba(240, 246, 252, 0.1);
            color: #ffffff;
        }

        .btn-blue:hover {
            background: var(--blue-hover);
        }

        .btn-sm {
            padding: 3px 8px;
            font-size: 12px;
        }

        .tag-btn {
            cursor: pointer;
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-secondary);
            border-radius: 20px;
            padding: 3px 10px;
            font-size: 12px;
            font-family: ui-monospace, SFMono-Regular, monospace;
        }

        .tag-btn:hover {
            border-color: #8b949e;
            color: var(--text-primary);
        }

        .form-grid {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 8px;
        }

        .upload-grid {
            display: grid;
            grid-template-columns: 1fr 1fr auto;
            gap: 8px;
        }

        input[type="text"], input[type="file"] {
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 13px;
            font-family: inherit;
            width: 100%;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: #58a6ff;
            box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.3);
        }

        .response-panel {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px;
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
            font-size: 12px;
            color: #c9d1d9;
            margin-top: 12px;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 240px;
            overflow-y: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            text-align: left;
            padding: 8px 10px;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            border-bottom: 1px solid var(--border);
            background: rgba(0, 0, 0, 0.1);
        }

        td {
            padding: 8px 10px;
            border-bottom: 1px solid var(--border);
            font-size: 13px;
            vertical-align: middle;
        }

        tr:hover {
            background: var(--surface-hover);
        }

        video {
            width: 180px;
            height: 100px;
            border-radius: 4px;
            border: 1px solid var(--border);
            background: #000;
            display: block;
        }

        a {
            color: #58a6ff;
            text-decoration: none;
        }

        a:hover {
            text-decoration: underline;
        }

        .quick-tags {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-bottom: 8px;
        }

        .muted {
            color: var(--text-secondary);
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1><span class="status-dot"></span>Video Service</h1>
                <span class="muted">Internal automation recording and media registry</span>
            </div>
            <div>
                <button class="btn btn-sm" onclick="fetchRecords()">List Records (/videos)</button>
            </div>
        </div>

        <div class="section">
            <div class="section-title">
                <span>Query Video URL</span>
                <span class="muted">GET /get_video_url</span>
            </div>
            <div class="quick-tags">
                <button type="button" class="tag-btn" onclick="selectCompany('Alpha_Magento_Solutions')">Alpha_Magento_Solutions</button>
                <button type="button" class="tag-btn" onclick="selectCompany('Beta_Commerce_Lab')">Beta_Commerce_Lab</button>
                <button type="button" class="tag-btn" onclick="selectCompany('Gamma_Web_Services')">Gamma_Web_Services</button>
            </div>
            <div class="form-grid">
                <input type="text" id="queryCompanyInput" placeholder="Enter company name..." onkeydown="if(event.key==='Enter') queryVideoURL()">
                <button class="btn btn-blue" onclick="queryVideoURL()">Query</button>
            </div>
        </div>

        <div class="section" id="playerSection" style="display: none; border-color: #388bfd;">
            <div class="section-title">
                <span id="playerTitle">Video Preview</span>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <a id="playerDirectLink" class="btn btn-sm" href="#" target="_blank">Open in New Tab</a>
                    <button class="btn btn-sm" onclick="closePlayer()">Close</button>
                </div>
            </div>
            <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
                <video id="playerVideo" controls playsinline style="width: 100%; max-width: 720px; max-height: 420px; border-radius: 6px; border: 1px solid var(--border); background: #000;">
                    Your browser does not support HTML5 video.
                </video>
                <div style="width: 100%; display: flex; justify-content: space-between; font-size: 12px;" class="muted">
                    <span id="playerMetaCompany">Company: <code></code></span>
                    <span id="playerMetaUrl">URL: <code id="playerMetaUrlCode"></code></span>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">
                <span>Upload Video</span>
                <span class="muted">POST /upload</span>
            </div>
            <form onsubmit="submitUpload(event)" class="upload-grid">
                <input type="text" id="uploadCompanyInput" placeholder="Company name" required>
                <input type="file" id="uploadFileInput" accept=".webm,.mp4" required>
                <button type="submit" class="btn btn-primary">Upload</button>
            </form>
        </div>

        <div class="section" id="terminalSection" style="display: none;">
            <div class="section-title">
                <span>Server Response</span>
                <button class="btn btn-sm" onclick="document.getElementById('terminalSection').style.display='none'">Clear</button>
            </div>
            <div class="response-panel" id="terminalOutput"></div>
        </div>

        <div class="section">
            <div class="section-title">
                <span>Stored Records</span>
                <span class="muted">{{ count }} record(s)</span>
            </div>
            {% if rows %}
            <table>
                <thead>
                    <tr>
                        <th style="width: 40px;">ID</th>
                        <th>Company Name</th>
                        <th style="width: 200px;">Media</th>
                        <th>Actions</th>
                        <th style="width: 140px;">Updated</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in rows %}
                    <tr>
                        <td class="muted">{{ row.id }}</td>
                        <td><code>{{ row.company_name }}</code></td>
                        <td>
                            <video controls preload="metadata">
                                <source src="{{ row.video_url }}" type="video/webm">
                            </video>
                        </td>
                        <td>
                            <div style="display: flex; gap: 6px;">
                                <button class="btn btn-sm" onclick="selectCompany('{{ row.company_name }}')">Lookup API</button>
                                <a class="btn btn-sm" href="{{ row.video_url }}" target="_blank">Direct Link</a>
                            </div>
                        </td>
                        <td class="muted">{{ row.updated_at }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p class="muted" style="margin: 8px 0;">No records found. Run recorder: <code>python capture_video.py --server http://127.0.0.1:8000</code></p>
            {% endif %}
        </div>
    </div>

    <script>
        function showResponse(text) {
            const sec = document.getElementById('terminalSection');
            const out = document.getElementById('terminalOutput');
            sec.style.display = 'block';
            out.textContent = text;
        }

        function selectCompany(name) {
            document.getElementById('queryCompanyInput').value = name;
            queryVideoURL();
        }

        function closePlayer() {
            const playerVid = document.getElementById('playerVideo');
            playerVid.pause();
            playerVid.removeAttribute('src');
            playerVid.load();
            document.getElementById('playerSection').style.display = 'none';
        }

        async function queryVideoURL() {
            const name = document.getElementById('queryCompanyInput').value.trim();
            if (!name) return;
            showResponse(`--> GET /get_video_url?company_name=${encodeURIComponent(name)}`);
            try {
                const res = await fetch(`/get_video_url?company_name=${encodeURIComponent(name)}`);
                const data = await res.json();
                showResponse(`<-- HTTP ${res.status} ${res.statusText}\n` + JSON.stringify(data, null, 2));
                if (res.ok && data.video_url) {
                    const playerSec = document.getElementById('playerSection');
                    const playerVid = document.getElementById('playerVideo');
                    document.getElementById('playerTitle').textContent = `Video Preview: ${data.company_name}`;
                    document.getElementById('playerMetaCompany').innerHTML = `Company: <code>${data.company_name}</code>`;
                    document.getElementById('playerMetaUrlCode').textContent = data.video_url;
                    document.getElementById('playerDirectLink').href = data.video_url;
                    playerVid.src = data.video_url;
                    playerVid.load();
                    playerSec.style.display = 'block';
                    playerVid.play().catch(() => {});
                    playerSec.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                } else {
                    closePlayer();
                }
            } catch (err) {
                showResponse(`<-- Network error: ${err}`);
                closePlayer();
            }
        }

        async function fetchRecords() {
            showResponse('--> GET /videos');
            try {
                const res = await fetch('/videos');
                const data = await res.json();
                showResponse(`<-- HTTP ${res.status} ${res.statusText}\n` + JSON.stringify(data, null, 2));
            } catch (err) {
                showResponse(`<-- Network error: ${err}`);
            }
        }

        async function submitUpload(e) {
            e.preventDefault();
            const company = document.getElementById('uploadCompanyInput').value.trim();
            const fileInput = document.getElementById('uploadFileInput');
            if (!company || fileInput.files.length === 0) return;

            const fd = new FormData();
            fd.append('company_name', company);
            fd.append('file', fileInput.files[0]);

            showResponse(`--> POST /upload [company=${company}, file=${fileInput.files[0].name}]`);
            try {
                const res = await fetch('/upload', { method: 'POST', body: fd });
                const data = await res.json();
                showResponse(`<-- HTTP ${res.status} ${res.statusText}\n` + JSON.stringify(data, null, 2));
                if (res.ok) {
                    setTimeout(() => location.reload(), 1000);
                }
            } catch (err) {
                showResponse(`<-- Upload failed: ${err}`);
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
