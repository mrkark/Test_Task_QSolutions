#!/usr/bin/env python3
"""
Viewer script for PostgreSQL 'companies' table (Task 3).

Displays companies stored in PostgreSQL, their status codes, and all extracted
Impressum / Imprint data from DeepSeek.

Usage:
    python view_companies.py                  # Summary table of all companies
    python view_companies.py --detail         # Detailed cards for all companies
    python view_companies.py --company "name" # Full details of a specific company
    python view_companies.py --status 0       # Filter by status code
    python view_companies.py --json           # Output raw JSON
"""
import os
import sys
import json
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 on Windows stdout if possible
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_DB_HOST = os.environ.get("DB_HOST", "localhost")
DEFAULT_DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DEFAULT_DB_NAME = os.environ.get("DB_NAME", "videos")
DEFAULT_DB_USER = os.environ.get("DB_USER", "video_user")
DEFAULT_DB_PASSWORD = os.environ.get("DB_PASSWORD", "video_pass")

STATUS_NAMES = {
    None: "PENDING (NULL)",
    0: "0 (OK)",
    1: "1 (NO_IMPRESSUM_LINK)",
    2: "2 (PARSING_FAILED)",
    3: "3 (ADDRESS_INCOMPLETE)",
    4: "4 (ERROR)",
    5: "5 (NO_WEBSITE)",
}


def get_connection(host=None, port=None, dbname=None, user=None, password=None):
    return psycopg2.connect(
        host=host or os.environ.get("DB_HOST", DEFAULT_DB_HOST),
        port=int(port or os.environ.get("DB_PORT", DEFAULT_DB_PORT)),
        dbname=dbname or os.environ.get("DB_NAME", DEFAULT_DB_NAME),
        user=user or os.environ.get("DB_USER", DEFAULT_DB_USER),
        password=password or os.environ.get("DB_PASSWORD", DEFAULT_DB_PASSWORD),
        cursor_factory=RealDictCursor,
    )


def fetch_companies(company_filter=None, status_filter=None, host=None, port=None, dbname=None, user=None, password=None):
    conn = get_connection(host=host, port=port, dbname=dbname, user=user, password=password)
    try:
        with conn.cursor() as cur:
            query = "SELECT * FROM companies "
            params = []
            clauses = []

            if company_filter:
                clauses.append("company_name ILIKE %s")
                params.append(f"%{company_filter}%")
            if status_filter is not None:
                if status_filter.lower() in ("null", "pending", "none"):
                    clauses.append("status IS NULL")
                else:
                    clauses.append("status = %s")
                    params.append(int(status_filter))

            if clauses:
                query += "WHERE " + " AND ".join(clauses) + " "

            query += "ORDER BY id ASC;"
            cur.execute(query, tuple(params))
            return cur.fetchall()
    finally:
        conn.close()


def print_table(rows):
    if not rows:
        print("\n[!] No companies found in PostgreSQL.")
        return

    print("\n" + "=" * 140)
    print(f" {'ID':<4} | {'Company Name':<22} | {'Status':<16} | {'Street & HouseNo':<24} | {'Postcode & City':<22} | {'VAT / Register'}")
    print("=" * 140)

    status_counts = {}
    for r in rows:
        st = r["status"]
        st_name = STATUS_NAMES.get(st, f"Unknown ({st})")
        status_counts[st_name] = status_counts.get(st_name, 0) + 1

        cid = str(r["id"])
        cname = (r["company_name"] or "")[:22]
        cstatus = st_name[:16]

        street_no = " ".join(filter(None, [r.get("street"), r.get("house_no")])) or "-"
        post_city = " ".join(filter(None, [r.get("postcode"), r.get("city")])) or "-"

        cvat_reg = []
        if r.get("vat_number"):
            cvat_reg.append(r["vat_number"])
        if r.get("handelsregister"):
            cvat_reg.append(r["handelsregister"])
        extra = ", ".join(cvat_reg) if cvat_reg else "-"

        print(f" {cid:<4} | {cname:<22} | {cstatus:<16} | {street_no[:24]:<24} | {post_city[:22]:<22} | {extra}")

    print("=" * 140)
    print(f"Total companies in PostgreSQL: {len(rows)}")
    summary_parts = [f"{k}: {v}" for k, v in sorted(status_counts.items())]
    print(f"Breakdown: {', '.join(summary_parts)}")
    print("=" * 140 + "\n")


def print_detail_card(r):
    st = r["status"]
    st_name = STATUS_NAMES.get(st, f"Unknown ({st})")

    print("\n" + "─" * 78)
    print(f"  🏢 Company #{r['id']}: {r['company_name']}")
    print("─" * 78)
    print(f"  • Status:              {st_name}")
    print(f"  • Home Page (web):     {r.get('web') or '-'}")
    print(f"  • Impressum URL:       {r.get('impressum_url') or '-'}")
    print(f"  • Legal Name:          {r.get('legal_name') or '-'}")
    print(f"  • Postal Address:      {r.get('postal_address') or '-'}")
    print(f"  • Parsed Street:       {r.get('street') or '-'}")
    print(f"  • Parsed House No:     {r.get('house_no') or '-'}")
    print(f"  • Parsed Postcode:     {r.get('postcode') or '-'}")
    print(f"  • Parsed City:         {r.get('city') or '-'}")
    print(f"  • Country:             {r.get('country') or '-'}")
    print(f"  • Handelsregister:     {r.get('handelsregister') or '-'}")
    print(f"  • VAT Number:          {r.get('vat_number') or '-'}")
    print(f"  • Phone:               {r.get('phone') or '-'}")
    print(f"  • Email:               {r.get('email') or '-'}")
    print(f"  • Responsible Person:  {r.get('responsible_person') or '-'}")
    print(f"  • Timestamps:          Created: {r.get('created_at')} | Updated: {r.get('updated_at')}")

    if r.get("raw_json"):
        print("  • Raw DeepSeek JSON:")
        json_str = json.dumps(r["raw_json"], indent=4, ensure_ascii=False)
        for line in json_str.splitlines():
            print(f"      {line}")
    print("─" * 78)


def main():
    parser = argparse.ArgumentParser(description="View PostgreSQL 'companies' table for Task 3.")
    parser.add_argument("--company", "-c", help="Filter by company name (partial match)")
    parser.add_argument("--status", "-s", help="Filter by status code (e.g. 0, 1, 2, 3, 4, 5, or pending/null)")
    parser.add_argument("--detail", "-d", action="store_true", help="Show detailed view of all matched companies")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--db-host", type=str, default=None, help="PostgreSQL host (defaults to DB_HOST env or localhost)")
    parser.add_argument("--db-port", type=int, default=None, help="PostgreSQL port (defaults to DB_PORT env or 5432)")
    parser.add_argument("--db-name", type=str, default=None, help="PostgreSQL database name (defaults to DB_NAME env or videos)")
    parser.add_argument("--db-user", type=str, default=None, help="PostgreSQL username (defaults to DB_USER env or video_user)")
    parser.add_argument("--db-password", type=str, default=None, help="PostgreSQL password (defaults to DB_PASSWORD env or video_pass)")

    args = parser.parse_args()

    effective_host = args.db_host or os.environ.get("DB_HOST", DEFAULT_DB_HOST)
    effective_port = args.db_port or os.environ.get("DB_PORT", DEFAULT_DB_PORT)
    effective_dbname = args.db_name or os.environ.get("DB_NAME", DEFAULT_DB_NAME)

    try:
        rows = fetch_companies(
            company_filter=args.company,
            status_filter=args.status,
            host=args.db_host,
            port=args.db_port,
            dbname=args.db_name,
            user=args.db_user,
            password=args.db_password,
        )
    except Exception as exc:
        print(f"[ERROR] Could not connect to PostgreSQL at {effective_host}:{effective_port}/{effective_dbname}: {exc}")
        sys.exit(1)

    if args.json:
        # Convert datetime objects to string
        clean_rows = []
        for r in rows:
            r_copy = dict(r)
            for k, v in r_copy.items():
                if hasattr(v, "isoformat"):
                    r_copy[k] = v.isoformat()
            clean_rows.append(r_copy)
        print(json.dumps(clean_rows, indent=2, ensure_ascii=False))
        return

    if args.company or args.detail:
        for r in rows:
            print_detail_card(r)
    else:
        print_table(rows)
        print("Tip: Run 'python view_companies.py --detail' for full extraction cards,")
        print("     or 'python view_companies.py --company \"name\"' to inspect a single company.")


if __name__ == "__main__":
    main()
