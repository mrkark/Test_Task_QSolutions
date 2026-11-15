#!/usr/bin/env python3
"""
Standalone Company Enrichment Script with DeepSeek API (§4).

Connects to PostgreSQL, iterates companies, fetches homepages, locates Impressum links,
extracts and optimizes visible text to minimize LLM token usage (§5), calls DeepSeek
to extract structured company data (§6), and saves results back to PostgreSQL.

Usage:
    python enrich_companies.py [--company "ACME GmbH"] [--limit N] [--status 0] [--force]
"""
import os
import sys
import argparse
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

import impressum
from impressum import CompanyStatus

load_dotenv()

# PostgreSQL connection defaults (matches Task 1 container & local setups)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "videos")
DB_USER = os.environ.get("DB_USER", "video_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "video_pass")


def get_connection():
    """Connects to PostgreSQL using Task 1 settings."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
    )


def ensure_table_exists(conn):
    """Ensures companies table exists idempotently (§2)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                company_name TEXT NOT NULL UNIQUE,
                language TEXT,
                country TEXT,
                postcode TEXT,
                city TEXT,
                street TEXT,
                house_no TEXT,
                web TEXT,
                status INTEGER,
                impressum_url TEXT,
                legal_name TEXT,
                postal_address TEXT,
                handelsregister TEXT,
                vat_number TEXT,
                phone TEXT,
                email TEXT,
                responsible_person TEXT,
                raw_json JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_companies_status ON companies (status);
            """
        )
    conn.commit()


def enrich_companies(
    company_filter: str = None,
    limit: int = None,
    status_filter: int = None,
    force: bool = False,
    api_key: str = None,
    model: str = None,
    dry_run: bool = False,
) -> list:
    """
    Main enrichment routine iterating companies in order of id (§4):
    - 4.1 Normalize URL (status = 5 if blank)
    - 4.2 Fetch homepage & find Impressum link (status = 1 if none found)
    - 4.3 Fetch Impressum & extract text
    - 4.4 Optimize text (token budget §5)
    - 4.5 Call DeepSeek (§6)
    - 4.6 Decide status & write back to PostgreSQL
    """
    conn = get_connection()
    ensure_table_exists(conn)

    effective_api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")

    print("=" * 76)
    print("  QSolutions: Company Impressum / Imprint Enrichment with DeepSeek")
    print("=" * 76)
    print(f"  Database:        {DB_HOST}:{DB_PORT}/{DB_NAME} (user: {DB_USER})")
    print(f"  DeepSeek Model:  {model or os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')}")
    print(f"  API Key Present: {'YES' if effective_api_key else 'NO (DEEPSEEK_API_KEY unset)'}")
    print(f"  Dry Run:         {'YES' if dry_run else 'NO'}")
    print("=" * 76)

    # Build query per §4
    query = "SELECT * FROM companies "
    params = []
    clauses = []

    if company_filter:
        clauses.append("company_name = %s")
        params.append(company_filter)
    elif status_filter is not None:
        clauses.append("status = %s")
        params.append(status_filter)
    elif not force:
        # Default per §4: rows not yet OK (status IS NULL OR status <> 0)
        clauses.append("(status IS NULL OR status <> 0)")

    if clauses:
        query += "WHERE " + " AND ".join(clauses) + " "

    query += "ORDER BY id ASC"

    if limit and limit > 0:
        query += " LIMIT %s"
        params.append(limit)

    with conn.cursor() as cur:
        cur.execute(query, tuple(params))
        companies = cur.fetchall()

    if not companies:
        print("[*] No companies found matching the selection criteria.")
        conn.close()
        return []

    print(f"[*] Processing {len(companies)} company row(s) in order of ID...\n")

    results = []

    for idx, comp in enumerate(companies, start=1):
        c_id = comp["id"]
        c_name = comp["company_name"]
        raw_web = comp.get("web")

        print(f"[{idx}/{len(companies)}] Company #{c_id}: '{c_name}'")

        # 4.1 Normalize URL
        norm_url = impressum.normalize_url(raw_web)
        if not norm_url:
            print(f"    [-] web column is empty -> status = {CompanyStatus.NO_WEBSITE} (NO_WEBSITE)")
            _update_company(
                conn, c_id,
                status=CompanyStatus.NO_WEBSITE,
                updated_at_now=True
            )
            results.append({"id": c_id, "name": c_name, "status": CompanyStatus.NO_WEBSITE})
            continue

        print(f"    [+] Normalized Web URL: {norm_url}")

        # 4.2 Fetch homepage and find Impressum link
        try:
            impressum_url = impressum.find_impressum_link(norm_url)
        except Exception as net_err:
            print(f"    [!] Error reaching homepage {norm_url}: {net_err} -> status = {CompanyStatus.ERROR}")
            _update_company(conn, c_id, status=CompanyStatus.ERROR)
            results.append({"id": c_id, "name": c_name, "status": CompanyStatus.ERROR, "error": str(net_err)})
            continue

        if not impressum_url:
            print(f"    [-] No Impressum link found on homepage -> status = {CompanyStatus.NO_IMPRESSUM_LINK_FOUND}")
            _update_company(conn, c_id, status=CompanyStatus.NO_IMPRESSUM_LINK_FOUND)
            results.append({"id": c_id, "name": c_name, "status": CompanyStatus.NO_IMPRESSUM_LINK_FOUND})
            continue

        print(f"    [+] Found Impressum URL: {impressum_url}")

        # 4.3 Fetch Impressum page and extract visible text
        try:
            import requests
            resp = requests.get(
                impressum_url,
                headers={"User-Agent": impressum.DEFAULT_USER_AGENT},
                timeout=20,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code} fetching Impressum page")
            raw_text = impressum.extract_visible_text(resp.text)
        except Exception as imp_err:
            print(f"    [!] Transport failure fetching {impressum_url}: {imp_err} -> status = {CompanyStatus.ERROR}")
            _update_company(conn, c_id, status=CompanyStatus.ERROR, impressum_url=impressum_url)
            results.append({"id": c_id, "name": c_name, "status": CompanyStatus.ERROR, "error": str(imp_err)})
            continue

        # 4.4 Optimize text (token budget §5)
        optimized_text, stats = impressum.optimize_impressum_text(raw_text)
        b_tok = stats["before_tokens"]
        a_tok = stats["after_tokens"]
        red = stats["reduction_pct"]
        if stats["optimized"]:
            print(f"    [+] Token Optimization: {stats['before_chars']} -> {stats['after_chars']} chars (~{b_tok} -> ~{a_tok} tokens, -{red}%)")
        else:
            print(f"    [i] Page within token budget: {stats['before_chars']} chars (~{b_tok} tokens, no cut needed)")

        # 4.5 Call DeepSeek for structured extraction (§6)
        if dry_run:
            print("    [~] Dry run: skipping DeepSeek API call.")
            results.append({"id": c_id, "name": c_name, "status": "dry_run", "impressum_url": impressum_url})
            continue

        if not effective_api_key:
            print("    [!] DEEPSEEK_API_KEY is not set! Run 'set_deepseek_key.bat' or pass --api-key.")
            _update_company(conn, c_id, status=CompanyStatus.ERROR, impressum_url=impressum_url)
            results.append({"id": c_id, "name": c_name, "status": CompanyStatus.ERROR, "error": "Missing API Key"})
            continue

        try:
            parsed_json = impressum.extract_with_deepseek(
                optimized_text=optimized_text,
                api_key=effective_api_key,
                model=model,
            )
        except Exception as ds_err:
            print(f"    [!] DeepSeek API error: {ds_err} -> status = {CompanyStatus.ERROR}")
            _update_company(conn, c_id, status=CompanyStatus.ERROR, impressum_url=impressum_url)
            results.append({"id": c_id, "name": c_name, "status": CompanyStatus.ERROR, "error": str(ds_err)})
            continue

        # 4.6 Decide status and write back to PostgreSQL
        status, fields = impressum.evaluate_extraction_status(parsed_json, fallback_company_name=c_name)

        status_name = status.name
        print(f"    [+] Extraction Status: {status.value} ({status_name})")
        print(f"        * Legal Name:     {fields['legal_name']}")
        print(f"        * Address:        {fields['postal_address']}")
        print(f"        * Register:       {fields['handelsregister']}")
        print(f"        * VAT:            {fields['vat_number']}")
        print(f"        * Phone / Email:  {fields['phone']} | {fields['email']}")
        print(f"        * Responsible:    {fields['responsible_person']}")

        _update_company(
            conn,
            c_id,
            status=status.value,
            impressum_url=impressum_url,
            legal_name=fields["legal_name"],
            postal_address=fields["postal_address"],
            handelsregister=fields["handelsregister"],
            vat_number=fields["vat_number"],
            phone=fields["phone"],
            email=fields["email"],
            responsible_person=fields["responsible_person"],
            raw_json=fields["raw_json"],
        )
        results.append({
            "id": c_id,
            "name": c_name,
            "status": status.value,
            "status_name": status_name,
            "legal_name": fields["legal_name"],
            "address": fields["postal_address"],
            "vat": fields["vat_number"],
            "register": fields["handelsregister"],
        })
        print()

    conn.close()

    print("=" * 76)
    print("  ENRICHMENT BATCH SUMMARY:")
    print("=" * 76)
    for r in results:
        st = r.get("status_name", str(r.get("status")))
        print(f"  #{r['id']:<3} {r['name']:<28} [{st:<18}] {r.get('address') or r.get('error', '')}")
    print("=" * 76 + "\n")
    return results


def _update_company(conn, company_id: int, status: int = None, impressum_url: str = None, **fields):
    """Updates company enrichment fields and status in PostgreSQL."""
    updates = ["updated_at = NOW()"]
    vals = []

    if status is not None:
        updates.append("status = %s")
        vals.append(status)

    if impressum_url is not None:
        updates.append("impressum_url = %s")
        vals.append(impressum_url)

    for col in ("legal_name", "postal_address", "handelsregister", "vat_number", "phone", "email", "responsible_person"):
        if col in fields:
            updates.append(f"{col} = %s")
            vals.append(fields[col])

    if "raw_json" in fields:
        updates.append("raw_json = %s")
        vals.append(json.dumps(fields["raw_json"]))

    vals.append(company_id)
    sql = f"UPDATE companies SET {', '.join(updates)} WHERE id = %s;"

    with conn.cursor() as cur:
        cur.execute(sql, tuple(vals))
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Enrich company records in PostgreSQL using Impressum parsing and DeepSeek (§4)")
    parser.add_argument("--company", type=str, default=None, help="Process only this one company name")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N rows")
    parser.add_argument("--status", type=int, default=None, help="Process only rows with this status (default: rows not yet OK)")
    parser.add_argument("--force", action="store_true", help="Re-process even rows already marked status=0 (OK)")
    parser.add_argument("--api-key", type=str, default=None, help="DeepSeek API Key (defaults to DEEPSEEK_API_KEY env)")
    parser.add_argument("--model", type=str, default=None, help="DeepSeek model name (default: deepseek-chat)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch & optimize text without calling DeepSeek or writing to DB")

    args = parser.parse_args()

    enrich_companies(
        company_filter=args.company,
        limit=args.limit,
        status_filter=args.status,
        force=args.force,
        api_key=args.api_key,
        model=args.model,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
