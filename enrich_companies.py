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
DEFAULT_DB_HOST = os.environ.get("DB_HOST", "localhost")
DEFAULT_DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DEFAULT_DB_NAME = os.environ.get("DB_NAME", "videos")
DEFAULT_DB_USER = os.environ.get("DB_USER", "video_user")
DEFAULT_DB_PASSWORD = os.environ.get("DB_PASSWORD", "video_pass")


def get_connection(
    host: str = None,
    port: int = None,
    dbname: str = None,
    user: str = None,
    password: str = None,
):
    """Connects to PostgreSQL using configured parameters or environment variables."""
    return psycopg2.connect(
        host=host or os.environ.get("DB_HOST", DEFAULT_DB_HOST),
        port=int(port or os.environ.get("DB_PORT", DEFAULT_DB_PORT)),
        dbname=dbname or os.environ.get("DB_NAME", DEFAULT_DB_NAME),
        user=user or os.environ.get("DB_USER", DEFAULT_DB_USER),
        password=password or os.environ.get("DB_PASSWORD", DEFAULT_DB_PASSWORD),
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

            -- Backfill individual parsed address columns from raw_json if they were NULL
            UPDATE companies
            SET
                postcode = COALESCE(companies.postcode, raw_json->'postal_address'->>'postcode'),
                city = COALESCE(companies.city, raw_json->'postal_address'->>'city'),
                street = COALESCE(companies.street, raw_json->'postal_address'->>'street'),
                house_no = COALESCE(companies.house_no, raw_json->'postal_address'->>'house_no'),
                country = COALESCE(companies.country, raw_json->'postal_address'->>'country')
            WHERE raw_json IS NOT NULL
              AND (postcode IS NULL OR city IS NULL OR street IS NULL OR house_no IS NULL);
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
    db_host: str = None,
    db_port: int = None,
    db_name: str = None,
    db_user: str = None,
    db_password: str = None,
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
    conn = get_connection(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
    )
    ensure_table_exists(conn)

    effective_host = db_host or os.environ.get("DB_HOST", DEFAULT_DB_HOST)
    effective_port = db_port or os.environ.get("DB_PORT", DEFAULT_DB_PORT)
    effective_dbname = db_name or os.environ.get("DB_NAME", DEFAULT_DB_NAME)
    effective_user = db_user or os.environ.get("DB_USER", DEFAULT_DB_USER)
    effective_api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")

    print("=" * 76)
    print("  QSolutions: Company Impressum / Imprint Enrichment with DeepSeek")
    print("=" * 76)
    print(f"  Database:        {effective_host}:{effective_port}/{effective_dbname} (user: {effective_user})")
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
        print(f"        * Postal Address: {fields['postal_address']}")
        print(f"        * Parsed:         Street='{fields.get('street')}', HouseNo='{fields.get('house_no')}', Postcode='{fields.get('postcode')}', City='{fields.get('city')}'")
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
            postcode=fields.get("postcode"),
            city=fields.get("city"),
            street=fields.get("street"),
            house_no=fields.get("house_no"),
            country=fields.get("country"),
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
            "postcode": fields.get("postcode"),
            "city": fields.get("city"),
            "street": fields.get("street"),
            "house_no": fields.get("house_no"),
            "country": fields.get("country"),
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
        addr_summary = r.get('address') or r.get('error', '')
        if r.get("postcode") and r.get("city"):
            addr_summary = f"{r.get('street')} {r.get('house_no')}, {r.get('postcode')} {r.get('city')}"
        print(f"  #{r['id']:<3} {r['name']:<28} [{st:<18}] {addr_summary}")
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

    for col in (
        "legal_name",
        "postal_address",
        "postcode",
        "city",
        "street",
        "house_no",
        "country",
        "handelsregister",
        "vat_number",
        "phone",
        "email",
        "responsible_person",
    ):
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
    parser.add_argument("--db-host", type=str, default=None, help="PostgreSQL host (defaults to DB_HOST env or localhost)")
    parser.add_argument("--db-port", type=int, default=None, help="PostgreSQL port (defaults to DB_PORT env or 5432)")
    parser.add_argument("--db-name", type=str, default=None, help="PostgreSQL database name (defaults to DB_NAME env or videos)")
    parser.add_argument("--db-user", type=str, default=None, help="PostgreSQL username (defaults to DB_USER env or video_user)")
    parser.add_argument("--db-password", type=str, default=None, help="PostgreSQL password (defaults to DB_PASSWORD env or video_pass)")

    args = parser.parse_args()

    enrich_companies(
        company_filter=args.company,
        limit=args.limit,
        status_filter=args.status,
        force=args.force,
        api_key=args.api_key,
        model=args.model,
        dry_run=args.dry_run,
        db_host=args.db_host,
        db_port=args.db_port,
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=args.db_password,
    )


if __name__ == "__main__":
    main()
