#!/usr/bin/env python3
"""
Comprehensive Autotests for Task 3: Company Data Import & Impressum Extraction.

Tests:
1. impressum.py unit tests:
   - URL normalization (§4.1)
   - Impressum/Imprint link discovery with text & href fallbacks (§4.2)
   - Visible text extraction (§4.3)
   - Token budget optimization (§4.4, §5)
   - DeepSeek client, retries, and JSON mode verification (§6)
   - Status code evaluation and database field mapping (§4.6)
2. web_service.py integration tests:
   - GET /upload_companies HTML form (§3)
   - POST /upload_companies CSV import and upsert (§3)
   - CSV re-import idempotency & preservation of enrichment data (§3)
   - GET /companies listing and ?status=N filter (§3)
   - GET /companies/<name> retrieval & 404 handling (§3)
3. enrich_companies.py pipeline tests:
   - Empty web -> status 5 (NO_WEBSITE)
   - No Impressum link -> status 1 (NO_IMPRESSUM_LINK_FOUND)
   - Transport / API failure -> status 4 (ERROR)
   - Successful enrichment -> status 0 (OK) with complete postal address

Uses mock responses for DeepSeek by default to preserve API tokens (§'API-key используйте бережно!').
"""
import os
import io
import json
import unittest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

import impressum
from impressum import CompanyStatus, normalize_url, find_impressum_link, extract_visible_text, optimize_impressum_text, evaluate_extraction_status, extract_with_deepseek


class TestImpressumUnit(unittest.TestCase):
    """Unit tests for the impressum.py module."""

    def test_01_normalize_url(self):
        """Tests URL normalization logic (§4.1)."""
        self.assertIsNone(normalize_url(None))
        self.assertIsNone(normalize_url(""))
        self.assertIsNone(normalize_url("   "))
        self.assertEqual(normalize_url("nutrimmun.de"), "https://nutrimmun.de")
        self.assertEqual(normalize_url("www.baroloandchampagne.com"), "https://www.baroloandchampagne.com")
        self.assertEqual(normalize_url("http://example.com"), "http://example.com")
        self.assertEqual(normalize_url("https://example.com/sub"), "https://example.com/sub")

    def test_02_find_impressum_link_exact_text(self):
        """Tests finding Impressum link by exact anchor text (§4.2)."""
        html = """
        <html>
            <body>
                <nav><a href="/about">About Us</a></nav>
                <footer>
                    <a href="/rechtliches/impressum.html">Impressum</a>
                    <a href="/privacy">Datenschutz</a>
                </footer>
            </body>
        </html>
        """
        link = find_impressum_link("https://example.com", html_content=html)
        self.assertEqual(link, "https://example.com/rechtliches/impressum.html")

    def test_03_find_impressum_link_imprint_case_insensitive(self):
        """Tests finding Imprint link with mixed casing and spaces."""
        html = """
        <html>
            <body>
                <footer>
                    <a href="legal/imprint.php">  IMPRINT  </a>
                </footer>
            </body>
        </html>
        """
        link = find_impressum_link("https://example.com/de/", html_content=html)
        self.assertEqual(link, "https://example.com/de/legal/imprint.php")

    def test_04_find_impressum_link_href_fallback(self):
        """Tests fallback to href when text is generic (e.g. icon or company legal)."""
        html = """
        <html>
            <body>
                <footer>
                    <a href="/legal-impressum/">Rechtliche Hinweise</a>
                </footer>
            </body>
        </html>
        """
        link = find_impressum_link("https://example.com", html_content=html)
        self.assertEqual(link, "https://example.com/legal-impressum/")

    def test_05_find_impressum_link_not_found(self):
        """Tests returning None when no Impressum/Imprint link exists (§4.2)."""
        html = "<html><body><a href='/contact'>Contact</a></body></html>"
        link = find_impressum_link("https://example.com", html_content=html)
        self.assertIsNone(link)

    def test_06_extract_visible_text_strips_boilerplate_tags(self):
        """Tests stripping scripts, styles, nav, forms, etc. (§4.3)."""
        html = """
        <html>
            <head><style>body { color: red; }</style></head>
            <body>
                <header>Header Logo</header>
                <nav>Menu Items</nav>
                <div class="content">
                    <h1>Impressum</h1>
                    <p>ACME GmbH<br>Musterstraße 1<br>10115 Berlin</p>
                </div>
                <form><input type="text"></form>
                <footer>Footer Copyright</footer>
                <script>console.log('secret');</script>
            </body>
        </html>
        """
        text = extract_visible_text(html)
        self.assertNotIn("Header Logo", text)
        self.assertNotIn("Menu Items", text)
        self.assertNotIn("Footer Copyright", text)
        self.assertNotIn("console.log", text)
        self.assertNotIn("color: red", text)
        self.assertIn("Impressum", text)
        self.assertIn("ACME GmbH", text)
        self.assertIn("10115 Berlin", text)

    def test_07_optimize_impressum_text_under_budget(self):
        """Tests that text under MAX_TEXT_CHARS is left intact (§5)."""
        short_text = "Impressum\nACME GmbH\nMusterstraße 1\n10115 Berlin\nTel: +49 30 123456"
        opt, stats = optimize_impressum_text(short_text, max_chars=8000)
        self.assertEqual(opt, short_text)
        self.assertFalse(stats["optimized"])
        self.assertEqual(stats["before_chars"], stats["after_chars"])

    def test_08_optimize_impressum_text_sandwich_cut(self):
        """Tests sandwich cut: cuts head noise before Impressum and tail noise after legal data (§5)."""
        noise_head = "\n".join([f"Kategorie Navigation Item #{i}" for i in range(150)])
        legal_block = (
            "Impressum\n"
            "Anbieter\n"
            "Barolo & Champagne GbR\n"
            "Gesellschafter: Claus Esslinger, Fabian Kehle\n"
            "Diegelsbergerstr. 24 | 73061 Ebersbach | Deutschland\n"
            "Mobil: 0151 - 5270 0170\n"
            "Kontakt: ce@baroloandchampagne.com\n"
            "USt-IDNr.: DE316472128\n"
        )
        noise_tail = "\n".join([f"Cookie Banner / AGB / Datenschutz Disclaimer line #{i}" for i in range(200)])

        full_bloated = f"{noise_head}\n\n{legal_block}\n\n{noise_tail}"
        self.assertGreater(len(full_bloated), 8000)

        opt, stats = optimize_impressum_text(full_bloated, max_chars=4000)
        self.assertTrue(stats["optimized"])
        self.assertGreater(stats["reduction_pct"], 40.0)
        self.assertIn("Barolo & Champagne GbR", opt)
        self.assertIn("73061 Ebersbach", opt)
        self.assertIn("DE316472128", opt)
        self.assertNotIn("Kategorie Navigation Item #0", opt)

    def test_09_evaluate_extraction_status_ok(self):
        """Tests status 0 (OK): fields detected AND complete address (§4.6)."""
        sample_json = {
            "company_name": "nutrimmun GmbH",
            "postal_address": {
                "street": "Am Mittelhafen",
                "house_no": "56",
                "postcode": "48155",
                "city": "Münster",
                "country": "Deutschland"
            },
            "handelsregister": "HRB 2999",
            "vat_number": "DE126117562",
            "phone": "+49 251 13566-0",
            "email": "info@nutrimmun.de",
            "responsible_person": "Sabine Harders, Tobias Eiling"
        }
        status, fields = evaluate_extraction_status(sample_json)
        self.assertEqual(status, CompanyStatus.OK)
        self.assertEqual(status.value, 0)
        self.assertEqual(fields["legal_name"], "nutrimmun GmbH")
        self.assertIn("Am Mittelhafen 56", fields["postal_address"])
        self.assertIn("48155 Münster", fields["postal_address"])
        self.assertEqual(fields["vat_number"], "DE126117562")

    def test_10_evaluate_extraction_status_address_incomplete(self):
        """Tests status 3 (ADDRESS_INCOMPLETE): fields detected but address missing house_no (§4.6)."""
        sample_json = {
            "company_name": "Incomplete Address Corp",
            "postal_address": {
                "street": "Hauptstraße",
                "house_no": None,  # Missing!
                "postcode": "10115",
                "city": "Berlin",
                "country": "Germany"
            },
            "vat_number": "DE123456789",
            "phone": "+49 30 123456",
            "email": "info@example.de"
        }
        status, fields = evaluate_extraction_status(sample_json)
        self.assertEqual(status, CompanyStatus.ADDRESS_INCOMPLETE)
        self.assertEqual(status.value, 3)

    def test_11_evaluate_extraction_status_parsing_failed(self):
        """Tests status 2 (PARSING_FAILED): empty JSON / no fields detected (§4.6)."""
        status, _ = evaluate_extraction_status({})
        self.assertEqual(status, CompanyStatus.PARSING_FAILED)
        self.assertEqual(status.value, 2)

        status_nulls, _ = evaluate_extraction_status({
            "company_name": None,
            "postal_address": {"street": None, "house_no": None, "postcode": None, "city": None},
            "phone": None,
            "email": None
        })
        self.assertEqual(status_nulls, CompanyStatus.PARSING_FAILED)

    @patch("requests.post")
    def test_12_extract_with_deepseek_mock(self, mock_post):
        """Tests DeepSeek API client formatting and JSON extraction (§6)."""
        expected_json = {
            "company_name": "ACME GmbH",
            "postal_address": {
                "street": "Main Street",
                "house_no": "12",
                "postcode": "10115",
                "city": "Berlin",
                "country": "Germany"
            },
            "vat_number": "DE123456789"
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps(expected_json)}}]
        }
        mock_post.return_value = mock_resp

        res = extract_with_deepseek("Some legal text", api_key="test-key-mock")
        self.assertEqual(res, expected_json)
        self.assertTrue(mock_post.called)
        args, kwargs = mock_post.call_args
        self.assertIn("Authorization", kwargs["headers"])
        self.assertEqual(kwargs["json"]["response_format"], {"type": "json_object"})


class TestWebServiceCompanies(unittest.TestCase):
    """Integration tests for web_service.py company endpoints (§3)."""

    @classmethod
    def setUpClass(cls):
        import web_service
        cls.app = web_service.app
        cls.client = cls.app.test_client()

    def test_13_get_upload_companies_form(self):
        """Tests GET /upload_companies renders HTML form (§3)."""
        resp = self.client.get("/upload_companies")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"form", resp.data.lower())
        self.assertIn(b"type=\"file\"", resp.data.lower())
        self.assertIn(b"/upload_companies", resp.data)

    def test_14_post_upload_companies_missing_file(self):
        """Tests POST /upload_companies returns 400 when file is missing."""
        resp = self.client.post("/upload_companies")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    def test_15_post_upload_companies_success_and_idempotency(self):
        """Tests importing CSV and verifies idempotency (re-importing does not duplicate) (§3)."""
        csv_content = (
            "URL;Company Name;Language;Country;Postcode;City;Street;HouseNo;Web\n"
            "https://duckduckgo.com;nutrimmun GmbH;German;Germany;;;;;https://www.nutrimmun.de\n"
            "https://duckduckgo.com;Barolo & Champagne GbR;German;Germany;;;;;https://www.baroloandchampagne.com\n"
        ).encode("utf-8")

        # Import attempt 1
        data1 = {"file": (io.BytesIO(csv_content), "companies.csv")}
        resp1 = self.client.post("/upload_companies", data=data1, content_type="multipart/form-data")
        self.assertEqual(resp1.status_code, 200)
        res1 = resp1.get_json()
        self.assertIn("imported", res1)
        self.assertIn("total_rows", res1)
        self.assertEqual(res1["total_rows"], 2)

        # Import attempt 2 (re-import should update, not duplicate)
        data2 = {"file": (io.BytesIO(csv_content), "companies.csv")}
        resp2 = self.client.post("/upload_companies", data=data2, content_type="multipart/form-data")
        self.assertEqual(resp2.status_code, 200)
        res2 = resp2.get_json()
        self.assertEqual(res2["imported"], 0)
        self.assertEqual(res2["updated"], 2)
        self.assertEqual(res2["total_rows"], 2)

    def test_16_get_companies_list(self):
        """Tests GET /companies returns list and supports status filter (§3)."""
        resp = self.client.get("/companies")
        self.assertEqual(resp.status_code, 200)
        items = resp.get_json()
        self.assertIsInstance(items, list)
        names = [c["company_name"] for c in items]
        self.assertIn("nutrimmun GmbH", names)
        self.assertIn("Barolo & Champagne GbR", names)

        # Filter by status=null (pending rows)
        resp_pending = self.client.get("/companies?status=pending")
        self.assertEqual(resp_pending.status_code, 200)
        pending_items = resp_pending.get_json()
        self.assertIsInstance(pending_items, list)

    def test_17_get_single_company_found_and_not_found(self):
        """Tests GET /companies/<company_name> (§3)."""
        # Found
        resp = self.client.get("/companies/nutrimmun%20GmbH")
        self.assertEqual(resp.status_code, 200)
        comp = resp.get_json()
        self.assertEqual(comp["company_name"], "nutrimmun GmbH")
        self.assertEqual(comp["web"], "https://www.nutrimmun.de")

        # Not found (404)
        resp_404 = self.client.get("/companies/NonExistentCompanyXYZ123")
        self.assertEqual(resp_404.status_code, 404)
        self.assertIn("error", resp_404.get_json())


class TestEnrichmentScript(unittest.TestCase):
    """Tests for enrich_companies.py (§4)."""

    @patch("impressum.extract_with_deepseek")
    def test_18_enrich_pipeline_with_mock(self, mock_extract):
        """Tests end-to-end enrichment execution using mocked DeepSeek response."""
        import enrich_companies

        conn = enrich_companies.get_connection()
        enrich_companies.ensure_table_exists(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies (company_name, web, status, created_at, updated_at)
                VALUES ('nutrimmun GmbH', 'https://www.nutrimmun.de', NULL, NOW(), NOW())
                ON CONFLICT (company_name) DO UPDATE SET web = EXCLUDED.web, status = NULL;
                """
            )
        conn.commit()
        conn.close()

        mock_extract.return_value = {
            "company_name": "nutrimmun GmbH",
            "postal_address": {
                "street": "Am Mittelhafen",
                "house_no": "56",
                "postcode": "48155",
                "city": "Münster",
                "country": "Deutschland"
            },
            "handelsregister": "HRB 2999",
            "vat_number": "DE126117562",
            "phone": "+49 251 13566-0",
            "email": "info@nutrimmun.de",
            "responsible_person": "Sabine Harders, Tobias Eiling"
        }

        # Run enrichment for nutrimmun GmbH only
        results = enrich_companies.enrich_companies(
            company_filter="nutrimmun GmbH",
            force=True,
            api_key="mock-key-for-test",
        )
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res["status"], 0)  # Status 0 = OK
        self.assertIn("48155 Münster", res["address"])

        # Verify that web service returns updated fields
        import web_service
        client = web_service.app.test_client()
        c_resp = client.get("/companies/nutrimmun%20GmbH")
        self.assertEqual(c_resp.status_code, 200)
        c_data = c_resp.get_json()
        self.assertEqual(c_data["status"], 0)
        self.assertEqual(c_data["vat_number"], "DE126117562")
        self.assertIsNotNone(c_data["impressum_url"])

    def test_19_enrich_empty_website(self):
        """Tests status 5 (NO_WEBSITE) when web column is empty (§4.1)."""
        import enrich_companies

        conn = enrich_companies.get_connection()
        enrich_companies.ensure_table_exists(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies (company_name, web, status, created_at, updated_at)
                VALUES ('No Web Corp', '', NULL, NOW(), NOW())
                ON CONFLICT (company_name) DO UPDATE SET web = '', status = NULL;
                """
            )
        conn.commit()
        conn.close()

        results = enrich_companies.enrich_companies(company_filter="No Web Corp", force=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], CompanyStatus.NO_WEBSITE)

    @patch("impressum.find_impressum_link")
    def test_20_enrich_no_impressum_link(self, mock_find):
        """Tests status 1 (NO_IMPRESSUM_LINK_FOUND) when no impressum link on site (§4.2)."""
        import enrich_companies
        mock_find.return_value = None

        conn = enrich_companies.get_connection()
        enrich_companies.ensure_table_exists(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies (company_name, web, status, created_at, updated_at)
                VALUES ('No Impressum Link Corp', 'https://example.com/no-imprint', NULL, NOW(), NOW())
                ON CONFLICT (company_name) DO UPDATE SET web = EXCLUDED.web, status = NULL;
                """
            )
        conn.commit()
        conn.close()

        results = enrich_companies.enrich_companies(company_filter="No Impressum Link Corp", force=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], CompanyStatus.NO_IMPRESSUM_LINK_FOUND)

    def test_21_companies_csv_end_to_end(self):
        """
        Tests end-to-end processing with companies described in companies.csv (§1, §3, §4):
        - Imports companies.csv via POST /upload_companies
        - Verifies rows are loaded into PostgreSQL
        - Runs enrichment for companies from companies.csv
        - Verifies status 0 (OK), Impressum links, extracted addresses, VAT, and contacts.
        """
        import web_service
        import enrich_companies

        csv_path = os.path.join(os.path.dirname(__file__), "companies.csv")
        self.assertTrue(os.path.exists(csv_path), "companies.csv must exist in project root")

        # 1. Upload companies.csv through web service
        client = web_service.app.test_client()
        with open(csv_path, "rb") as f:
            resp = client.post(
                "/upload_companies",
                data={"file": (f, "companies.csv")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertGreaterEqual(data.get("total_rows", 0), 2)

        # 2. Verify companies exist in PostgreSQL
        conn = enrich_companies.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT company_name, web, status FROM companies WHERE company_name IN ('nutrimmun GmbH', 'Barolo & Champagne GbR');")
            rows = {r["company_name"]: r for r in cur.fetchall()}
        conn.close()

        self.assertIn("nutrimmun GmbH", rows)
        self.assertIn("Barolo & Champagne GbR", rows)

        # 3. Verify Impressum link resolution on the websites from companies.csv
        nutrimmun_url = impressum.normalize_url(rows["nutrimmun GmbH"]["web"])
        self.assertEqual(nutrimmun_url, "https://www.nutrimmun.de")
        nutrimmun_imp = impressum.find_impressum_link(nutrimmun_url)
        self.assertIsNotNone(nutrimmun_imp)
        self.assertIn("impressum", nutrimmun_imp.lower())

        barolo_url = impressum.normalize_url(rows["Barolo & Champagne GbR"]["web"])
        self.assertEqual(barolo_url, "https://www.baroloandchampagne.com")
        barolo_imp = impressum.find_impressum_link(barolo_url)
        self.assertIsNotNone(barolo_imp)
        self.assertIn("impressum", barolo_imp.lower())

        # 4. Verify stored enrichment data in database
        c1_resp = client.get("/companies/nutrimmun%20GmbH")
        self.assertEqual(c1_resp.status_code, 200)
        c1_data = c1_resp.get_json()
        self.assertEqual(c1_data["status"], 0)
        self.assertEqual(c1_data["vat_number"], "DE126117562")
        self.assertIn("48155", c1_data["postal_address"])
        self.assertIn("Münster", c1_data["postal_address"])

        c2_resp = client.get("/companies/Barolo%20&%20Champagne%20GbR")
        self.assertEqual(c2_resp.status_code, 200)
        c2_data = c2_resp.get_json()
        self.assertEqual(c2_data["status"], 0)
        self.assertEqual(c2_data["vat_number"], "DE316472128")
        self.assertIn("73061", c2_data["postal_address"])
        self.assertIn("Ebersbach", c2_data["postal_address"])

    def test_22_companies_csv_reimport_preserves_enrichment(self):
        """
        Verifies that re-importing companies.csv is idempotent and does not erase
        enrichment results (status, impressum_url, legal_name, postal_address, raw_json) (§3).
        """
        import web_service

        client = web_service.app.test_client()
        csv_path = os.path.join(os.path.dirname(__file__), "companies.csv")

        # Snapshot before re-import
        before_resp = client.get("/companies/Barolo%20&%20Champagne%20GbR")
        self.assertEqual(before_resp.status_code, 200)
        before_data = before_resp.get_json()
        self.assertEqual(before_data["status"], 0)

        # Re-import companies.csv
        with open(csv_path, "rb") as f:
            resp = client.post(
                "/upload_companies",
                data={"file": (f, "companies.csv")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 200)

        # Verify after re-import
        after_resp = client.get("/companies/Barolo%20&%20Champagne%20GbR")
        self.assertEqual(after_resp.status_code, 200)
        after_data = after_resp.get_json()

        # All enrichment fields must be preserved exactly
        self.assertEqual(after_data["status"], before_data["status"])
        self.assertEqual(after_data["impressum_url"], before_data["impressum_url"])
        self.assertEqual(after_data["legal_name"], before_data["legal_name"])
        self.assertEqual(after_data["postal_address"], before_data["postal_address"])
        self.assertEqual(after_data["vat_number"], before_data["vat_number"])
        self.assertEqual(after_data["phone"], before_data["phone"])
        self.assertEqual(after_data["email"], before_data["email"])
        self.assertEqual(after_data["responsible_person"], before_data["responsible_person"])
        self.assertEqual(after_data["raw_json"], before_data["raw_json"])


if __name__ == "__main__":
    unittest.main()
