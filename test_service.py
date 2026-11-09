import os
import json
import tempfile
import unittest
import requests
import video_client

SERVER_URL = os.environ.get("SERVER_URL", "http://127.0.0.1:8000").rstrip("/")


class TestWebService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print(f"\n[INFO] Connecting tests to web service at: {SERVER_URL}")
        try:
            resp = requests.get(f"{SERVER_URL}/", timeout=5)
            print(f"[INFO] Server responded with status {resp.status_code}, Server header: {resp.headers.get('Server')}")
        except Exception as e:
            raise RuntimeError(f"Web service is not reachable at {SERVER_URL}. Ensure docker-compose is running: {e}")

    def _log_response(self, method: str, path: str, response: requests.Response):
        try:
            body = response.json()
            body_repr = json.dumps(body, indent=2, ensure_ascii=False)
        except Exception:
            body_repr = f"<Binary / HTML {response.headers.get('Content-Type')}, {len(response.content)} bytes>"
        print(f"\n{'='*60}\n>>> {method} {path}\n<<< Status Code: {response.status_code}\n<<< Content-Type: {response.headers.get('Content-Type')}\n<<< Response Body:\n{body_repr}\n{'='*60}")

    def test_01_server_health_and_apache_header(self):
        print("\n--- Running: test_01_server_health_and_apache_header ---")
        resp = requests.get(f"{SERVER_URL}/")
        self._log_response("GET", "/", resp)
        self.assertEqual(resp.status_code, 200)
        server_header = resp.headers.get("Server", "")
        self.assertIn("Apache", server_header, "Server header should indicate Apache")
        resp.close()

    def test_02_upload_video_endpoint(self):
        print("\n--- Running: test_02_upload_video_endpoint ---")
        test_video_content = b"\x1a\x45\xdf\xa3 mock webm video payload for postgres"
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(test_video_content)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                resp = requests.post(
                    f"{SERVER_URL}/upload",
                    data={"company_name": "ACME_Postgres_GmbH"},
                    files={"file": ("ACME_Postgres_GmbH.webm", f, "video/webm")},
                )
            self._log_response("POST", "/upload", resp)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["company_name"], "ACME_Postgres_GmbH")
            self.assertTrue(data["video_url"].endswith("/media/ACME_Postgres_GmbH.webm"))
            resp.close()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_03_upload_video_upsert(self):
        print("\n--- Running: test_03_upload_video_upsert ---")
        for i in range(1, 3):
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
                tmp.write(f"video payload version {i}".encode())
                tmp_path = tmp.name

            try:
                with open(tmp_path, "rb") as f:
                    resp = requests.post(
                        f"{SERVER_URL}/upload",
                        data={"company_name": "Upsert_Corp"},
                        files={"file": ("Upsert_Corp.webm", f, "video/webm")},
                    )
                self._log_response("POST", f"/upload (attempt {i})", resp)
                self.assertEqual(resp.status_code, 200)
                resp.close()
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        # Check records to ensure only 1 row exists for Upsert_Corp
        list_resp = requests.get(f"{SERVER_URL}/videos")
        records = [r for r in list_resp.json() if r.get("company_name") == "Upsert_Corp"]
        self.assertEqual(len(records), 1, "Upsert must update existing row without duplicates")
        list_resp.close()

    def test_04_get_video_url_found(self):
        print("\n--- Running: test_04_get_video_url_found ---")
        resp = requests.get(f"{SERVER_URL}/get_video_url", params={"company_name": "ACME_Postgres_GmbH"})
        self._log_response("GET", "/get_video_url?company_name=ACME_Postgres_GmbH", resp)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["company_name"], "ACME_Postgres_GmbH")
        self.assertTrue(data["video_url"].endswith("/media/ACME_Postgres_GmbH.webm"))
        resp.close()

    def test_05_get_video_url_not_found(self):
        print("\n--- Running: test_05_get_video_url_not_found ---")
        resp = requests.get(f"{SERVER_URL}/get_video_url", params={"company_name": "UnknownCompany12345"})
        self._log_response("GET", "/get_video_url?company_name=UnknownCompany12345", resp)
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertIn("error", data)
        resp.close()

    def test_06_serve_media(self):
        print("\n--- Running: test_06_serve_media ---")
        media_url = f"{SERVER_URL}/media/ACME_Postgres_GmbH.webm"
        resp = requests.get(media_url)
        self._log_response("GET", "/media/ACME_Postgres_GmbH.webm", resp)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"\x1a\x45\xdf\xa3 mock webm video payload for postgres")
        resp.close()

    def test_07_list_videos(self):
        print("\n--- Running: test_07_list_videos ---")
        resp = requests.get(f"{SERVER_URL}/videos")
        self._log_response("GET", "/videos", resp)
        self.assertEqual(resp.status_code, 200)
        records = resp.json()
        self.assertIsInstance(records, list)
        self.assertGreaterEqual(len(records), 1)
        resp.close()

    def test_08_upload_validation_errors(self):
        print("\n--- Running: test_08_upload_validation_errors ---")
        # Missing file
        r1 = requests.post(f"{SERVER_URL}/upload", data={"company_name": "NoFileCorp"})
        self._log_response("POST", "/upload (missing file)", r1)
        self.assertEqual(r1.status_code, 400)
        r1.close()

        # Missing company_name
        r2 = requests.post(f"{SERVER_URL}/upload", files={"file": ("f.webm", b"content", "video/webm")})
        self._log_response("POST", "/upload (missing company_name)", r2)
        self.assertEqual(r2.status_code, 400)
        r2.close()

        # Missing query parameter
        r3 = requests.get(f"{SERVER_URL}/get_video_url")
        self._log_response("GET", "/get_video_url (no parameter)", r3)
        self.assertEqual(r3.status_code, 400)
        r3.close()

    def test_09_live_http_client_functions(self):
        print("\n--- Running: test_09_live_http_client_functions ---")
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(b"client webm payload 987654321")
            tmp_path = tmp.name

        try:
            uploaded_url = video_client.UploadVideo(SERVER_URL, tmp_path, "ClientCorp")
            print(f"[LIVE CLIENT] UploadVideo succeeded -> URL: {uploaded_url}")
            self.assertTrue(uploaded_url.startswith(SERVER_URL))
            self.assertTrue(uploaded_url.endswith("/media/ClientCorp.webm"))

            fetched_url = video_client.GetVideoURL(SERVER_URL, "ClientCorp")
            print(f"[LIVE CLIENT] GetVideoURL succeeded -> URL: {fetched_url}")
            self.assertEqual(uploaded_url, fetched_url)

            media_resp = requests.get(uploaded_url)
            self.assertEqual(media_resp.status_code, 200)
            self.assertEqual(media_resp.content, b"client webm payload 987654321")
            media_resp.close()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_10_index_dashboard_single_video_player(self):
        print("\n--- Running: test_10_index_dashboard_single_video_player ---")
        resp = requests.get(f"{SERVER_URL}/")
        self.assertEqual(resp.status_code, 200)
        html_text = resp.text
        self.assertIn('id="playerSection"', html_text)
        self.assertIn('id="playerVideo"', html_text)
        self.assertIn('id="queryCompanyInput"', html_text)
        self.assertIn('closePlayer()', html_text)
        print("Dashboard contains dedicated single video player element and controls.")
        resp.close()

    def test_11_upload_with_sidecar_and_auto_process(self):
        print("\n--- Running: test_11_upload_with_sidecar_and_auto_process ---")
        sidecar_data = {
            "viewport": {"width": 1280, "height": 720},
            "fps": 25,
            "zoom_factor": 2.0,
            "ramp_sec": 0.5,
            "events": [
                {"t": 1.0, "x": 640, "y": 360, "type": "in"},
                {"t": 3.0, "x": 640, "y": 360, "type": "out"},
            ],
        }

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as vid_tmp:
            vid_tmp.write(b"mock video bytes for sidecar test")
            vid_path = vid_tmp.name

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as sc_tmp:
            sc_tmp.write(json.dumps(sidecar_data).encode("utf-8"))
            sc_path = sc_tmp.name

        try:
            with open(vid_path, "rb") as vf, open(sc_path, "rb") as sf:
                resp = requests.post(
                    f"{SERVER_URL}/upload",
                    data={"company_name": "SidecarZoomCorp", "auto_process": "1"},
                    files={
                        "file": ("SidecarZoomCorp.webm", vf, "video/webm"),
                        "sidecar": ("SidecarZoomCorp.webm.zoom.json", sf, "application/json"),
                    },
                )
            self._log_response("POST", "/upload (with sidecar)", resp)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["company_name"], "SidecarZoomCorp")
            self.assertIn("video_url", data)
            self.assertIn("id", data)
            resp.close()
        finally:
            if os.path.exists(vid_path):
                os.remove(vid_path)
            if os.path.exists(sc_path):
                os.remove(sc_path)

    def test_12_jobs_process_endpoint(self):
        print("\n--- Running: test_12_jobs_process_endpoint ---")
        # First query video ID for SidecarZoomCorp or ACME_Postgres_GmbH
        list_resp = requests.get(f"{SERVER_URL}/videos")
        records = list_resp.json()
        target = next((r for r in records if r["company_name"] == "SidecarZoomCorp"), records[0])
        list_resp.close()

        video_id = target["id"]
        resp = requests.post(f"{SERVER_URL}/jobs/{video_id}/process")
        self._log_response("POST", f"/jobs/{video_id}/process", resp)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "completed")
        self.assertIn("processed_video_url", data)
        self.assertTrue(data["processed_video_url"].endswith(".zoomed.webm"))
        resp.close()

    def test_13_get_video_url_includes_processed_url(self):
        print("\n--- Running: test_13_get_video_url_includes_processed_url ---")
        resp = requests.get(f"{SERVER_URL}/get_video_url", params={"company_name": "SidecarZoomCorp"})
        self._log_response("GET", "/get_video_url?company_name=SidecarZoomCorp", resp)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["company_name"], "SidecarZoomCorp")
        self.assertIn("video_url", data)
        self.assertIn("processed_video_url", data)
        self.assertIsNotNone(data["processed_video_url"])
        resp.close()

    def test_14_process_video_client_function(self):
        print("\n--- Running: test_14_process_video_client_function ---")
        processed_url = video_client.ProcessVideo(SERVER_URL, "SidecarZoomCorp")
        print(f"[LIVE CLIENT] ProcessVideo returned: {processed_url}")
        self.assertIsNotNone(processed_url)
        self.assertTrue(processed_url.endswith(".zoomed.webm"))


if __name__ == "__main__":
    unittest.main()
