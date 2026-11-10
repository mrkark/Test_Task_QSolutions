import os
import re
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, g, render_template_string
import psycopg2
from psycopg2.extras import RealDictCursor
from apply_zoom import apply_zoom, find_sidecar

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))

DB_HOST = os.environ.get("DB_HOST", "db")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "videos")
DB_USER = os.environ.get("DB_USER", "video_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "video_pass")

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
    )


def wait_for_db(max_retries=30, delay=1.0):
    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=3,
            )
            conn.close()
            print(f"Connected to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}")
            return True
        except Exception as exc:
            print(f"Waiting for database ({attempt}/{max_retries}): {exc}")
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to PostgreSQL at {DB_HOST}:{DB_PORT} after {max_retries} attempts.")


def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    wait_for_db()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    id SERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    processed_video_url TEXT,
                    sidecar_path TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
                ALTER TABLE videos ADD COLUMN IF NOT EXISTS processed_video_url TEXT;
                ALTER TABLE videos ADD COLUMN IF NOT EXISTS sidecar_path TEXT;
                """
            )
        conn.commit()
    finally:
        conn.close()


def get_db():
    if "db" not in g:
        g.db = get_db_connection()
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


def process_video_job(video_id: int, base_url: str) -> dict:
    """Executes zoom post-processing on a stored video and updates PostgreSQL."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, company_name, file_path, video_url, processed_video_url, sidecar_path FROM videos WHERE id = %s",
            (video_id,),
        )
        row = cur.fetchone()

    if not row:
        raise ValueError(f"Video with id {video_id} not found")

    file_path = row["file_path"]
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found at: {file_path}")

    sidecar_path = row["sidecar_path"]
    if not sidecar_path or not os.path.exists(sidecar_path):
        sidecar_path = find_sidecar(file_path)

    base, ext = os.path.splitext(file_path)
    zoomed_filename = f"{os.path.basename(base)}.zoomed{ext or '.webm'}"
    zoomed_path = os.path.join(UPLOAD_FOLDER, zoomed_filename)

    code, msg = apply_zoom(
        video_path=file_path,
        sidecar_path=sidecar_path,
        output_path=zoomed_path,
        dry_run=False,
    )
    if code != 0:
        raise RuntimeError(f"apply_zoom failed with exit code {code}: {msg}")

    processed_video_url = f"{base_url}/media/{zoomed_filename}"

    with db.cursor() as cur:
        cur.execute(
            """
            UPDATE videos
            SET processed_video_url = %s, sidecar_path = %s, updated_at = NOW()
            WHERE id = %s;
            """,
            (processed_video_url, sidecar_path, video_id),
        )
    db.commit()

    return {
        "id": video_id,
        "company_name": row["company_name"],
        "status": "completed",
        "video_url": row["video_url"],
        "processed_video_url": processed_video_url,
    }


@app.route("/", methods=["GET"])
def index():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id, company_name, file_path, video_url, processed_video_url, sidecar_path, created_at, updated_at FROM videos ORDER BY id DESC")
        raw_rows = [dict(row) for row in cur.fetchall()]

    rows = []
    for r in raw_rows:
        orig_file = os.path.basename(r.get("video_url") or "")
        zoom_file = os.path.basename(r.get("processed_video_url") or "")
        r["rel_video_url"] = f"/media/{orig_file}" if orig_file else ""
        r["rel_processed_url"] = f"/media/{zoom_file}" if zoom_file else ""
        r["display_url"] = r["rel_processed_url"] or r["rel_video_url"]
        rows.append(r)

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
            --purple: #8957e5;
            --purple-hover: #a371f7;
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
            max-width: 1000px;
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

        .btn-purple {
            background: var(--purple);
            border-color: rgba(240, 246, 252, 0.1);
            color: #ffffff;
        }

        .btn-purple:hover {
            background: var(--purple-hover);
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

        .badge {
            display: inline-block;
            padding: 2px 7px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-success {
            background: rgba(35, 134, 54, 0.2);
            color: #3fb950;
            border: 1px solid rgba(63, 185, 80, 0.4);
        }
        .badge-muted {
            background: rgba(110, 118, 129, 0.2);
            color: #8b949e;
            border: 1px solid rgba(110, 118, 129, 0.4);
        }

        .form-grid {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 8px;
        }

        .upload-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr auto;
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
            width: 160px;
            height: 90px;
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
                <h1><span class="status-dot"></span>Video Service (Apache + PostgreSQL + Zoom Engine)</h1>
                <span class="muted">Containerized video registry with Camtasia-style FFmpeg zoompan processing</span>
            </div>
            <div style="display: flex; gap: 8px;">
                <button class="btn btn-sm btn-blue" onclick="syncLocalVideos()">🔄 Sync Videos (/sync)</button>
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
                    <button id="toggleZoomBtn" class="btn btn-sm btn-purple" style="display: none;" onclick="togglePlayerSource()">Switch to Zoomed</button>
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
                <span>Upload Video & Sidecar</span>
                <span class="muted">POST /upload</span>
            </div>
            <form onsubmit="submitUpload(event)" class="upload-grid">
                <input type="text" id="uploadCompanyInput" placeholder="Company name" required>
                <div>
                    <label class="muted" style="display:block; margin-bottom:2px;">Video File (.webm)</label>
                    <input type="file" id="uploadFileInput" accept=".webm,.mp4" required>
                </div>
                <div>
                    <label class="muted" style="display:block; margin-bottom:2px;">Sidecar (.zoom.json, optional)</label>
                    <input type="file" id="uploadSidecarInput" accept=".json">
                </div>
                <div style="align-self: flex-end;">
                    <button type="submit" class="btn btn-primary" style="height: 32px;">Upload</button>
                </div>
            </form>
        </div>

        <div class="section" style="border-left: 4px solid var(--accent);">
            <div class="section-title">
                <span>🎥 Interactive Screen Recorder (Test F5 Zoom Live)</span>
                <span class="muted">Live operator capture</span>
            </div>
            <div style="background: rgba(35, 134, 54, 0.1); border: 1px solid rgba(46, 160, 67, 0.3); border-radius: 6px; padding: 12px; margin-bottom: 12px;">
                <div style="font-weight: 600; color: #3fb950; margin-bottom: 6px;">Как записать видео с эффектом зума по клавише F5:</div>
                <ol style="margin: 0; padding-left: 20px; line-height: 1.7; font-size: 13px;">
                    <li>На хосте Windows запустите скрипт в 1 клик: <code style="background: rgba(0,0,0,0.4); padding: 2px 6px; border-radius: 4px; color: #58a6ff;">record_interactive.bat</code> (или команду <code style="background: rgba(0,0,0,0.4); padding: 2px 6px; border-radius: 4px; color: #58a6ff;">python record_interactive.py</code>).</li>
                    <li>Откроется видимое окно браузера Chromium с открытым сайтом.</li>
                    <li>Перемещайте курсор мыши и нажимайте клавишу <b>F5</b> (или кликайте экранную кнопку <b>[Zoom (F5)]</b> в верхнем правом углу) — появится анимированное кольцо и зафиксируется точка курсора. Повторное нажатие F5 плавно возвращает камеру.</li>
                    <li>Закройте окно браузера — видео и sidecar автоматически сохранятся в папку <code style="background: rgba(0,0,0,0.4); padding: 2px 6px; border-radius: 4px;">./video</code>, обработаются через FFmpeg и загрузятся прямо в этот дашборд!</li>
                </ol>
            </div>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <input type="text" id="interactiveUrlInput" placeholder="URL сайта (например: https://duckduckgo.com)" value="https://duckduckgo.com" style="flex: 1; min-width: 260px;">
                <input type="text" id="interactiveNameInput" placeholder="Имя записи (например: My_F5_Test)" value="My_F5_Test" style="width: 180px;">
                <button class="btn btn-primary" onclick="launchInteractiveRecord()">Запустить запись</button>
            </div>
            <div id="interactiveStatus" style="margin-top: 8px; font-size: 12px;" class="muted"></div>
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
                        <th style="width: 35px;">ID</th>
                        <th>Company Name</th>
                        <th style="width: 170px;">Media</th>
                        <th>Status</th>
                        <th>Actions</th>
                        <th style="width: 130px;">Updated</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in rows %}
                    <tr>
                        <td class="muted">{{ row.id }}</td>
                        <td><code>{{ row.company_name }}</code></td>
                        <td>
                            <video controls preload="metadata" style="width: 160px; height: 90px; border-radius: 4px; background: #000;">
                                <source src="{{ row.display_url }}" type="video/webm">
                            </video>
                        </td>
                        <td>
                            {% if row.processed_video_url %}
                                <span class="badge badge-success">Zoomed Ready</span>
                            {% else %}
                                <span class="badge badge-muted">Original</span>
                            {% endif %}
                        </td>
                        <td>
                            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                                <button class="btn btn-sm btn-primary" onclick="playRecord('{{ row.company_name }}', '{{ row.rel_video_url }}', '{{ row.rel_processed_url }}')">Play</button>
                                <a class="btn btn-sm" href="{{ row.display_url }}" target="_blank">Open</a>
                                {% if not row.processed_video_url %}
                                <button class="btn btn-sm btn-purple" onclick="triggerProcess({{ row.id }})">Process Zoom</button>
                                {% endif %}
                                <button class="btn btn-sm" onclick="selectCompany('{{ row.company_name }}')">API</button>
                            </div>
                        </td>
                        <td class="muted">{{ row.updated_at.strftime('%Y-%m-%d %H:%M:%S') if row.updated_at and row.updated_at.strftime else row.updated_at }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p class="muted" style="margin: 8px 0;">No records found. Upload a video above or via <code>video_client.py</code>.</p>
            {% endif %}
        </div>
    </div>

    <script>
        let currentOrigUrl = '';
        let currentZoomUrl = '';
        let isShowingZoomed = false;

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

        function playRecord(company, origUrl, zoomUrl) {
            currentOrigUrl = origUrl;
            currentZoomUrl = zoomUrl;
            isShowingZoomed = !!zoomUrl;
            updatePlayerView(company);
        }

        function updatePlayerView(company) {
            const playerSec = document.getElementById('playerSection');
            const playerVid = document.getElementById('playerVideo');
            const toggleBtn = document.getElementById('toggleZoomBtn');
            const activeUrl = isShowingZoomed ? currentZoomUrl : currentOrigUrl;

            document.getElementById('playerTitle').textContent = `Video Preview: ${company} (${isShowingZoomed ? 'Zoomed' : 'Original'})`;
            document.getElementById('playerMetaCompany').innerHTML = `Company: <code>${company}</code>`;
            document.getElementById('playerMetaUrlCode').textContent = activeUrl;
            document.getElementById('playerDirectLink').href = activeUrl;

            if (currentOrigUrl && currentZoomUrl) {
                toggleBtn.style.display = 'inline-block';
                toggleBtn.textContent = isShowingZoomed ? 'Switch to Original' : 'Switch to Zoomed';
            } else {
                toggleBtn.style.display = 'none';
            }

            playerVid.src = activeUrl;
            playerVid.load();
            playerSec.style.display = 'block';
            playerVid.play().catch(() => {});
            playerSec.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        function togglePlayerSource() {
            if (!currentOrigUrl || !currentZoomUrl) return;
            isShowingZoomed = !isShowingZoomed;
            const company = document.getElementById('playerMetaCompany').textContent.replace('Company:', '').trim();
            updatePlayerView(company);
        }

        function closePlayer() {
            const playerVid = document.getElementById('playerVideo');
            playerVid.pause();
            playerVid.removeAttribute('src');
            playerVid.load();
            document.getElementById('playerSection').style.display = 'none';
        }

        async function triggerProcess(id) {
            showResponse(`--> POST /jobs/${id}/process`);
            try {
                const res = await fetch(`/jobs/${id}/process`, { method: 'POST' });
                const data = await res.json();
                showResponse(`<-- HTTP ${res.status} ${res.statusText}\n` + JSON.stringify(data, null, 2));
                if (res.ok) {
                    setTimeout(() => location.reload(), 1500);
                }
            } catch (err) {
                showResponse(`<-- Process error: ${err}`);
            }
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
                    playRecord(data.company_name, data.video_url, data.processed_video_url);
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
            const sidecarInput = document.getElementById('uploadSidecarInput');
            if (!company || fileInput.files.length === 0) return;

            const fd = new FormData();
            fd.append('company_name', company);
            fd.append('file', fileInput.files[0]);
            if (sidecarInput.files.length > 0) {
                fd.append('sidecar', sidecarInput.files[0]);
            }

            showResponse(`--> POST /upload [company=${company}, file=${fileInput.files[0].name}]`);
            try {
                const res = await fetch('/upload', { method: 'POST', body: fd });
                const data = await res.json();
                showResponse(`<-- HTTP ${res.status} ${res.statusText}\n` + JSON.stringify(data, null, 2));
                if (res.ok) {
                    setTimeout(() => location.reload(), 1500);
                }
            } catch (err) {
                showResponse(`<-- Upload failed: ${err}`);
            }
        }

        async function launchInteractiveRecord() {
            const url = document.getElementById('interactiveUrlInput').value.trim() || 'https://duckduckgo.com';
            const name = document.getElementById('interactiveNameInput').value.trim() || 'My_F5_Test';
            const statusEl = document.getElementById('interactiveStatus');
            statusEl.innerHTML = '<span style="color:#58a6ff;">Запуск... Ожидайте</span>';

            try {
                const res = await fetch('/record/interactive', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ url: url, company_name: name })
                });
                const data = await res.json();
                if (data.status === 'host_launch_required') {
                    statusEl.innerHTML = `<span style="color:#f0883e;">ℹ️ ${data.message}</span>`;
                } else if (data.status === 'completed') {
                    statusEl.innerHTML = `<span style="color:#3fb950;">✅ Запись завершена! Видео обработано и добавлено в список.</span>`;
                    setTimeout(() => location.reload(), 1000);
                } else {
                    statusEl.innerHTML = `<span style="color:#f85149;">${data.error || JSON.stringify(data)}</span>`;
                }
            } catch (err) {
                statusEl.innerHTML = `<span style="color:#f0883e;">ℹ️ Сервер запущен в контейнере Docker. Для записи с окном браузера на Windows запустите <b>record_interactive.bat</b></span>`;
            }
        }
        async function syncLocalVideos() {
            showResponse('--> POST /sync [Syncing recorded videos into Docker database...]');
            try {
                const res = await fetch('/sync', { method: 'POST' });
                const data = await res.json();
                showResponse(`<-- HTTP ${res.status}\n` + JSON.stringify(data, null, 2));
                if (res.ok) {
                    setTimeout(() => location.reload(), 1500);
                }
            } catch (err) {
                showResponse(`<-- Sync error: ${err}`);
            }
        }
    </script>
</body>
</html>"""
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

    sidecar_path = None
    if "sidecar" in request.files:
        uploaded_sidecar = request.files["sidecar"]
        if uploaded_sidecar and uploaded_sidecar.filename:
            sidecar_filename = f"{filename}.zoom.json"
            sidecar_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, sidecar_filename))
            uploaded_sidecar.save(sidecar_path)

    base_url = request.host_url.rstrip("/")
    video_url = f"{base_url}/media/{filename}"

    processed_video_url = None
    if "processed_file" in request.files:
        uploaded_processed = request.files["processed_file"]
        if uploaded_processed and uploaded_processed.filename:
            base, ext = os.path.splitext(filename)
            proc_filename = f"{base}.zoomed{ext or '.webm'}"
            proc_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, proc_filename))
            uploaded_processed.save(proc_path)
            processed_video_url = f"{base_url}/media/{proc_filename}"

    auto_process = request.form.get("auto_process", "1").lower() in ("1", "true", "yes")

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO videos (company_name, file_path, video_url, processed_video_url, sidecar_path, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (company_name) DO UPDATE SET
                file_path = EXCLUDED.file_path,
                video_url = EXCLUDED.video_url,
                processed_video_url = COALESCE(EXCLUDED.processed_video_url, videos.processed_video_url),
                sidecar_path = COALESCE(EXCLUDED.sidecar_path, videos.sidecar_path),
                updated_at = NOW()
            RETURNING id;
            """,
            (company_name, absolute_file_path, video_url, processed_video_url, sidecar_path),
        )
        row = cur.fetchone()
        video_id = row["id"]
    db.commit()

    if not processed_video_url and auto_process and (sidecar_path or find_sidecar(absolute_file_path)):
        try:
            res = process_video_job(video_id, base_url)
            processed_video_url = res.get("processed_video_url")
        except Exception as p_err:
            print(f"Notice: auto-process failed: {p_err}")

    return jsonify({
        "id": video_id,
        "company_name": company_name,
        "video_url": video_url,
        "processed_video_url": processed_video_url,
        "sidecar_path": sidecar_path,
    }), 200


@app.route("/sync", methods=["POST", "GET"])
def sync_endpoint():
    """Scans UPLOAD_FOLDER and registers any video files into PostgreSQL."""
    base_url = request.host_url.rstrip("/")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    synced = []

    for fn in os.listdir(UPLOAD_FOLDER):
        if not fn.endswith(".webm") or fn.endswith(".zoomed.webm"):
            continue
        company_name = os.path.splitext(fn)[0]
        abs_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, fn))
        video_url = f"{base_url}/media/{fn}"

        sidecar_fn = f"{fn}.zoom.json"
        sidecar_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, sidecar_fn))
        if not os.path.exists(sidecar_path):
            sidecar_path = None

        zoomed_fn = f"{company_name}.zoomed.webm"
        zoomed_path = os.path.join(UPLOAD_FOLDER, zoomed_fn)
        proc_url = f"{base_url}/media/{zoomed_fn}" if os.path.exists(zoomed_path) else None

        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO videos (company_name, file_path, video_url, processed_video_url, sidecar_path, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (company_name) DO UPDATE SET
                    file_path = EXCLUDED.file_path,
                    video_url = EXCLUDED.video_url,
                    processed_video_url = COALESCE(EXCLUDED.processed_video_url, videos.processed_video_url),
                    sidecar_path = COALESCE(EXCLUDED.sidecar_path, videos.sidecar_path),
                    updated_at = NOW()
                RETURNING id;
                """,
                (company_name, abs_path, video_url, proc_url, sidecar_path),
            )
            row = cur.fetchone()
        db.commit()
        synced.append({"id": row["id"], "company_name": company_name, "processed": bool(proc_url)})

    return jsonify({"status": "synced", "count": len(synced), "records": synced}), 200


@app.route("/jobs/<int:video_id>/process", methods=["POST"])
def process_job_endpoint(video_id):
    base_url = request.host_url.rstrip("/")
    try:
        if "sidecar" in request.files:
            sf = request.files["sidecar"]
            if sf and sf.filename:
                sc_name = f"{video_id}_{sf.filename}"
                sc_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, sc_name))
                sf.save(sc_path)
                db = get_db()
                with db.cursor() as cur:
                    cur.execute("UPDATE videos SET sidecar_path = %s WHERE id = %s", (sc_path, video_id))
                db.commit()

        result = process_video_job(video_id, base_url)
        return jsonify(result), 200
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/process", methods=["POST"])
def process_general_endpoint():
    base_url = request.host_url.rstrip("/")
    video_id = request.form.get("video_id") or (request.json.get("video_id") if request.is_json else None)
    company_name = request.form.get("company_name") or (request.json.get("company_name") if request.is_json else None)

    db = get_db()
    with db.cursor() as cur:
        if video_id:
            cur.execute("SELECT id FROM videos WHERE id = %s", (int(video_id),))
        elif company_name:
            cur.execute("SELECT id FROM videos WHERE company_name = %s", (company_name.strip(),))
        else:
            return jsonify({"error": "Either video_id or company_name must be provided"}), 400
        row = cur.fetchone()

    if not row:
        return jsonify({"error": "Video record not found"}), 404

    target_id = row["id"]
    try:
        result = process_video_job(target_id, base_url)
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/get_video_url", methods=["GET"])
def get_video_url():
    company_name = request.args.get("company_name", "").strip()
    if not company_name:
        return jsonify({"error": "company_name query parameter is required"}), 400

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, company_name, video_url, processed_video_url FROM videos WHERE company_name = %s",
            (company_name,),
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"error": f"Company '{company_name}' not found"}), 404

    return jsonify({
        "id": row["id"],
        "company_name": row["company_name"],
        "video_url": row["video_url"],
        "processed_video_url": row["processed_video_url"],
    }), 200


@app.route("/media/<path:filename>", methods=["GET"])
def serve_media(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/videos", methods=["GET"])
def list_videos():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id, company_name, file_path, video_url, processed_video_url, sidecar_path, created_at, updated_at FROM videos ORDER BY id ASC")
        raw_rows = cur.fetchall()

    rows = []
    for r in raw_rows:
        item = dict(r)
        if "created_at" in item and hasattr(item["created_at"], "strftime"):
            item["created_at"] = item["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if "updated_at" in item and hasattr(item["updated_at"], "strftime"):
            item["updated_at"] = item["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
        rows.append(item)

    return jsonify(rows), 200


@app.route("/record/interactive", methods=["POST"])
def record_interactive_endpoint():
    data = request.get_json(silent=True) or {}
    url = data.get("url") or "https://duckduckgo.com"
    company_name = data.get("company_name") or "Operator_Recording"

    # If running inside Docker without an X11 / Wayland DISPLAY, visible browser cannot be opened inside container
    if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
        return jsonify({
            "status": "host_launch_required",
            "message": "Контейнер Docker работает в headless-режиме (без графического дисплея). Для интерактивной записи с окном браузера запустите 'record_interactive.bat' или 'python record_interactive.py' на хосте Windows!"
        }), 200

    try:
        import qscript
        res = qscript.RecordInteractive(
            url=url,
            company_name=company_name,
            auto_apply_zoom=True,
            server_url=request.host_url.rstrip("/"),
        )
        return jsonify({
            "status": "completed",
            "result": res,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


try:
    init_db()
except Exception as init_err:
    print(f"Notice: init_db deferred or failed on import: {init_err}")


def main():
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "8000"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
