import os
import json
import socket
import tempfile
import sqlite3
import threading
import unittest
from werkzeug.serving import make_server

import web_service
from web_service import app, init_db
import video_client
import requests


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestWebService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="test_qsolutions_")
        cls.test_db = os.path.join(cls.test_dir, "test_videos.db")
        cls.test_uploads = os.path.join(cls.test_dir, "test_uploads")

        web_service.DATABASE_PATH = cls.test_db
        web_service.UPLOAD_FOLDER = cls.test_uploads
        app.config["UPLOAD_FOLDER"] = cls.test_uploads
        app.config["TESTING"] = True

        init_db()
        cls.client = app.test_client()

        # Start a real live HTTP server on a background thread for live requests testing
        cls.live_port = get_free_port()
        cls.live_server_url = f"http://127.0.0.1:{cls.live_port}"
        cls.server = make_server("127.0.0.1", cls.live_port, app)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server_thread.join()

    def setUp(self):
        conn = sqlite3.connect(self.test_db)
        conn.execute("DELETE FROM videos;")
        conn.commit()
        conn.close()

    def _log_response(self, method: str, path: str, response):
        try:
            body = response.get_json()
            if body is not None:
                body_repr = json.dumps(body, indent=2, ensure_ascii=False)
            else:
                body_repr = f"<Binary {response.content_type}, {len(response.data)} bytes>"
        except Exception:
            body_repr = f"<Binary data, {len(response.data)} bytes>"
        print(f"\n{'='*60}\n>>> {method} {path}\n<<< Status Code: {response.status_code}\n<<< Content-Type: {response.content_type}\n<<< Response Body:\n{body_repr}\n{'='*60}")

    def test_01_init_db_schema(self):
        print("\n--- Running: test_01_init_db_schema ---")
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(videos);")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        expected_columns = ["id", "company_name", "file_path", "video_url", "created_at", "updated_at"]
        for col in expected_columns:
            self.assertIn(col, columns)
        print(f"Database schema verified: columns={list(columns.keys())}")

    def test_02_upload_video_endpoint(self):
        print("\n--- Running: test_02_upload_video_endpoint ---")
        data = {
            "company_name": "ACME GmbH",
            "file": (tempfile.SpooledTemporaryFile(), "ACME_GmbH.webm"),
        }
        data["file"][0].write(b"\x1a\x45\xdf\xa3 mock webm video bytes")
        data["file"][0].seek(0)

        response = self.client.post("/upload", data=data, content_type="multipart/form-data")
        self._log_response("POST", "/upload", response)

        self.assertEqual(response.status_code, 200)
        res_json = response.get_json()
        self.assertEqual(res_json["company_name"], "ACME GmbH")
        self.assertTrue(res_json["video_url"].endswith("/media/ACME_GmbH.webm"))

        saved_file = os.path.join(self.test_uploads, "ACME_GmbH.webm")
        self.assertTrue(os.path.exists(saved_file))

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT company_name, file_path, video_url FROM videos WHERE company_name = ?", ("ACME GmbH",))
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "ACME GmbH")
        self.assertEqual(row[1], os.path.abspath(saved_file))
        self.assertEqual(row[2], res_json["video_url"])
        response.close()

    def test_03_upload_video_upsert(self):
        print("\n--- Running: test_03_upload_video_upsert ---")
        for i in range(1, 3):
            file_obj = tempfile.SpooledTemporaryFile()
            file_obj.write(f"video version {i}".encode())
            file_obj.seek(0)
            data = {
                "company_name": "RepeatCorp",
                "file": (file_obj, "repeat.webm"),
            }
            resp = self.client.post("/upload", data=data, content_type="multipart/form-data")
            self._log_response("POST", f"/upload (attempt {i})", resp)
            self.assertEqual(resp.status_code, 200)
            resp.close()

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM videos WHERE company_name = 'RepeatCorp'")
        count = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(count, 1, "Upsert should not create duplicate rows for the same company_name")

    def test_04_get_video_url_found(self):
        print("\n--- Running: test_04_get_video_url_found ---")
        file_obj = tempfile.SpooledTemporaryFile()
        file_obj.write(b"sample video bytes")
        file_obj.seek(0)
        up_resp = self.client.post(
            "/upload",
            data={"company_name": "Berlin_Agency", "file": (file_obj, "berlin.webm")},
            content_type="multipart/form-data",
        )
        up_resp.close()

        response = self.client.get("/get_video_url?company_name=Berlin_Agency")
        self._log_response("GET", "/get_video_url?company_name=Berlin_Agency", response)

        self.assertEqual(response.status_code, 200)
        res_json = response.get_json()
        self.assertEqual(res_json["company_name"], "Berlin_Agency")
        self.assertTrue(res_json["video_url"].endswith("/media/Berlin_Agency.webm"))
        response.close()

    def test_05_get_video_url_not_found(self):
        print("\n--- Running: test_05_get_video_url_not_found ---")
        response = self.client.get("/get_video_url?company_name=NonExistentCorp")
        self._log_response("GET", "/get_video_url?company_name=NonExistentCorp", response)
        self.assertEqual(response.status_code, 404)
        res_json = response.get_json()
        self.assertIn("error", res_json)
        response.close()

    def test_06_serve_media(self):
        print("\n--- Running: test_06_serve_media ---")
        file_obj = tempfile.SpooledTemporaryFile()
        video_payload = b"test webm streaming binary payload 12345"
        file_obj.write(video_payload)
        file_obj.seek(0)
        upload_resp = self.client.post(
            "/upload",
            data={"company_name": "MediaTestCorp", "file": (file_obj, "media_test.webm")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_resp.status_code, 200)
        upload_resp.close()

        response = self.client.get("/media/MediaTestCorp.webm")
        self._log_response("GET", "/media/MediaTestCorp.webm", response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, video_payload)
        response.close()

    def test_07_list_videos(self):
        print("\n--- Running: test_07_list_videos ---")
        for name in ["Company_A", "Company_B"]:
            f = tempfile.SpooledTemporaryFile()
            f.write(b"content")
            f.seek(0)
            u_resp = self.client.post(
                "/upload",
                data={"company_name": name, "file": (f, f"{name}.webm")},
                content_type="multipart/form-data",
            )
            u_resp.close()

        response = self.client.get("/videos")
        self._log_response("GET", "/videos", response)
        self.assertEqual(response.status_code, 200)
        records = response.get_json()
        self.assertGreaterEqual(len(records), 2)
        response.close()

    def test_08_upload_validation_errors(self):
        print("\n--- Running: test_08_upload_validation_errors ---")
        resp1 = self.client.post("/upload", data={"company_name": "NoFileCorp"})
        self._log_response("POST", "/upload (missing file)", resp1)
        self.assertEqual(resp1.status_code, 400)
        resp1.close()

        f = tempfile.SpooledTemporaryFile()
        f.write(b"content")
        f.seek(0)
        resp2 = self.client.post("/upload", data={"file": (f, "test.webm")}, content_type="multipart/form-data")
        self._log_response("POST", "/upload (missing company_name)", resp2)
        self.assertEqual(resp2.status_code, 400)
        resp2.close()

        resp3 = self.client.get("/get_video_url")
        self._log_response("GET", "/get_video_url (no parameter)", resp3)
        self.assertEqual(resp3.status_code, 400)
        resp3.close()

    def test_09_live_http_client_functions(self):
        print("\n--- Running: test_09_live_http_client_functions (Real HTTP Socket) ---")
        sample_video_path = os.path.join(self.test_dir, "live_client_test.webm")
        with open(sample_video_path, "wb") as f:
            f.write(b"live http client webm video bytes 1234567890")

        # Call real UploadVideo over live HTTP socket
        uploaded_url = video_client.UploadVideo(self.live_server_url, sample_video_path, "LiveClientCorp")
        print(f"\n[LIVE CLIENT] UploadVideo succeeded -> URL: {uploaded_url}")
        self.assertTrue(uploaded_url.startswith(self.live_server_url))
        self.assertTrue(uploaded_url.endswith("/media/LiveClientCorp.webm"))

        # Verify live GET to /media/<filename>
        media_resp = requests.get(uploaded_url, timeout=10)
        print(f"[LIVE CLIENT] GET {uploaded_url} -> Status: {media_resp.status_code}, Bytes: {len(media_resp.content)}")
        self.assertEqual(media_resp.status_code, 200)
        self.assertEqual(media_resp.content, b"live http client webm video bytes 1234567890")

        # Call real GetVideoURL over live HTTP socket
        fetched_url = video_client.GetVideoURL(self.live_server_url, "LiveClientCorp")
        print(f"[LIVE CLIENT] GetVideoURL succeeded -> URL: {fetched_url}")
        self.assertEqual(uploaded_url, fetched_url)


if __name__ == "__main__":
    unittest.main()
