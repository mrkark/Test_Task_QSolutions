#!/usr/bin/env python3
"""
Impressum / Imprint Extraction and Token Optimization Module for DeepSeek.

Provides:
- CompanyStatus IntEnum (§2)
- URL normalization (§4.1)
- Impressum/Imprint link discovery (§4.2)
- Visible text extraction and token budget optimization (§4.3, §5)
- DeepSeek structured JSON extraction with OpenAI-compatible endpoint (§6)
- Status evaluation and database field mapping (§4.6)
"""
import os
import re
import time
import json
import urllib.parse
from enum import IntEnum
from typing import Optional, Dict, Any, Tuple, List
import requests
from bs4 import BeautifulSoup


class CompanyStatus(IntEnum):
    """
    Status codes for companies table (status is an INTEGER):
    - NULL / None: imported, not yet processed
    - 0: OK — Impressum parsed AND address complete
    - 1: NO_IMPRESSUM_LINK_FOUND — home page has no Impressum/Imprint link
    - 2: PARSING_FAILED — Impressum parsed but no fields detected (empty JSON)
    - 3: ADDRESS_INCOMPLETE — fields parsed but postcode/city/street/house_no not all filled
    - 4: ERROR — transport failure: unreachable, HTTP 4xx/5xx, DeepSeek API error
    - 5: NO_WEBSITE — web column is empty
    """
    OK = 0
    NO_IMPRESSUM_LINK_FOUND = 1
    PARSING_FAILED = 2
    ADDRESS_INCOMPLETE = 3
    ERROR = 4
    NO_WEBSITE = 5


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

MAX_TEXT_CHARS = 8000  # ≈ 2000 tokens (heuristic: tokens ≈ len(text) // 4)

SYSTEM_PROMPT = """\
You extract legally required company information ("Impressum" / "Imprint") from
German-language website text.
Return ONLY a valid JSON object (no markdown fences, no commentary) that parses
with json.loads. The JSON must have exactly these keys:
{
 "company_name": "<string or null>",
 "postal_address": {
 "street": "<string or null>",
 "house_no": "<string or null>",
 "postcode": "<string or null>",
 "city": "<string or null>",
 "country": "<string or null>"
 },
 "handelsregister": "<string or null>",
 "vat_number": "<string or null>",
 "phone": "<string or null>",
 "email": "<string or null>",
 "responsible_person": "<string or null>"
}
Rules:
- Extract ONLY information actually present in the text; use null when absent.
- Do not invent or guess values.
- phone: keep the international format when possible (e.g. +49 ...).
- vat_number: German VAT ids look like DE followed by 9 digits.
- email: lowercase.
- responsible_person: the named person or role legally responsible for the
 content (e.g. Geschaeftsfuehrer, Vorstand, "inhaltlich verantwortlich").
- Output valid JSON only.
"""


def normalize_url(url: Optional[str]) -> Optional[str]:
    """
    Normalizes company home page URL:
    - If web is empty/blank -> returns None
    - If URL has no scheme, prepends https://
    """
    if not url:
        return None
    cleaned = str(url).strip()
    if not cleaned:
        return None
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", cleaned):
        cleaned = "https://" + cleaned.lstrip("/")
    return cleaned


def find_impressum_link(
    home_url: str,
    html_content: Optional[str] = None,
    timeout: int = 15,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Optional[str]:
    """
    Locates the Impressum/Imprint link from a home page:
    1. Look for an <a> whose visible text, stripped and lower-cased, is 'impressum' or 'imprint'.
    2. Fall back to an <a> whose href contains 'impressum' or 'imprint'.
    3. Resolves relative URLs with urllib.parse.urljoin.
    """
    if not home_url:
        return None

    if html_content is None:
        try:
            resp = requests.get(
                home_url,
                headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
                timeout=timeout,
                allow_redirects=True,
            )
            if resp.status_code >= 400:
                return None
            html_content = resp.text
            base_url = resp.url
        except Exception:
            return None
    else:
        base_url = home_url

    soup = BeautifulSoup(html_content, "html.parser")
    anchors = soup.find_all("a")

    # Pass 1: exact text match (case-insensitive stripped)
    for a in anchors:
        text = a.get_text(strip=True).lower()
        href = a.get("href")
        if text in ("impressum", "imprint") and href:
            return urllib.parse.urljoin(base_url, href.strip())

    # Pass 2: href contains 'impressum' or 'imprint'
    for a in anchors:
        href = a.get("href")
        if href:
            clean_href = href.strip().lower()
            if "impressum" in clean_href or "imprint" in clean_href:
                return urllib.parse.urljoin(base_url, href.strip())

    # Pass 3: text contains 'impressum' or 'imprint' as substring (e.g. 'zum impressum')
    for a in anchors:
        text = a.get_text(strip=True).lower()
        href = a.get("href")
        if href and ("impressum" in text or "imprint" in text):
            return urllib.parse.urljoin(base_url, href.strip())

    return None


def extract_visible_text(html_content: str) -> str:
    """
    Parses Impressum page HTML:
    - Removes script, style, noscript, svg, nav, header, footer, form, iframe
    - Extracts visible text and normalizes whitespace
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # Decompose non-content / boilerplate container tags
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


# Head anchor pattern: matches opening headings of German legal disclosure
HEAD_ANCHOR_REGEX = re.compile(
    r"(?i)\b(angaben\s+gem[äa]ß\s+§\s*5\s+(?:tmg|ddg)|impressum|anbieter(?:kennzeichnung)?|diensteanbieter)\b"
)

# Tail anchor patterns: indicators of legal data points where disclosure ends
TAIL_PATTERNS = [
    re.compile(r"(?:\+49|0049|\b0\d{2,5}[-\s/]?\d{3,8}\b)"),  # Phone
    re.compile(r"(?:DE\s?\d{9})", re.IGNORECASE),             # VAT number
    re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),  # Email
    re.compile(r"(?:HRB|HRA)\s?\d+|Registergericht|Amtsgericht", re.IGNORECASE),  # Handelsregister
    re.compile(r"(?:Verantwortlich|Vertreten durch|Gesch[äa]ftsf[üu]hrer|Inhaltlich verantwortlich|Gesellschafter|Vorstand)", re.IGNORECASE),  # Responsibility
]

# Obvious boilerplate lines to discard in long documents
BOILERPLATE_LINE_REGEX = re.compile(
    r"(?i)^(?:zum (?:hauptinhalt|inhalt|menü|suchformular)|"
    r"wir verwenden cookies|diese website verwendet cookies|alle cookies akzeptieren|"
    r"konfigurieren|nur technisch notwendige|datenschutzerklärung|agb /|widerrufsrecht|"
    r"versand \+ versandkosten|zahlungsbedingungen|werkzeugleiste anzeigen|bilder ausblenden|"
    r"zur kategorie|rote rebsorten|weiße rebsorten|ausgewählte cru|raritäten|jahrgang \d{4})$"
)

LEGAL_PROXIMITY_REGEX = re.compile(
    r"(?i)\b(gmbh|gbr|ag|ug|e\.k\.|vertreten|gesch[äa]ftsf[üu]hrer|gesellschafter|inhaber|vorstand|"
    r"stra[ßs]e|str\.|hausnummer|postleitzahl|ust|steuer|hrb|hra|amtsgericht|telefon|tel|e-mail|mail)\b"
)


def optimize_impressum_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> Tuple[str, Dict[str, Any]]:
    """
    Token budget optimizer (§5):
    - If text <= max_chars, keeps it unchanged.
    - If text > max_chars:
      1. Drops boilerplate navigation and cookie banner lines.
      2. Locates the head anchor (opening heading with legal proximity scoring).
      3. Locates tail anchors (phone, VAT, email, Handelsregister, responsibility).
      4. Applies sandwich cut: [head_anchor - small_margin : last_tail_anchor + 400].
      5. Verification check: ensures head and at least one strong signal remain.
    Returns (optimized_text, stats_dict).
    """
    before_chars = len(text)
    before_tokens = before_chars // 4

    stats = {
        "before_chars": before_chars,
        "after_chars": before_chars,
        "before_tokens": before_tokens,
        "after_tokens": before_tokens,
        "optimized": False,
        "reduction_pct": 0.0,
    }

    if before_chars <= max_chars:
        return text, stats

    # 1. Strip boilerplate noise lines
    lines = text.splitlines()
    filtered_lines = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # If line is obvious noise and does not contain legal entity indicators
        if BOILERPLATE_LINE_REGEX.match(s) and not re.search(r"(?i)(gmbh|gbr|ag|e\.k\.|ug|haftung|vertreten|steuer|ust|hrb|hra|amtsgericht)", s):
            continue
        filtered_lines.append(s)

    working_text = "\n".join(filtered_lines)

    # 2. Find Best Head Anchor via proximity scoring
    head_start = 0
    best_score = -1
    candidates = list(HEAD_ANCHOR_REGEX.finditer(working_text))

    if candidates:
        for m in candidates:
            window = working_text[m.start():m.start() + 450]
            score = len(LEGAL_PROXIMITY_REGEX.findall(window))
            # Bonus if preceded or followed by newline / standalone line
            if "\n" in working_text[max(0, m.start()-2):m.start()]:
                score += 1
            if score > best_score:
                best_score = score
                head_start = max(0, m.start() - 50)
    else:
        # Fallback to first line
        head_start = 0

    # 3. Find Tail Anchors after head_start
    search_sub = working_text[head_start:]
    last_tail_rel_end = 0
    for pat in TAIL_PATTERNS:
        for m in pat.finditer(search_sub):
            if m.end() > last_tail_rel_end:
                last_tail_rel_end = m.end()

    tail_end = len(working_text)
    if last_tail_rel_end > 0:
        # Keep M = 400 chars margin after the last legal signal
        tail_end = min(len(working_text), head_start + last_tail_rel_end + 400)

    # 4. Sandwich Cut
    candidate = working_text[head_start:tail_end].strip()

    # 5. Verification & Fallback
    has_head = bool(HEAD_ANCHOR_REGEX.search(candidate))
    has_signal = any(bool(pat.search(candidate)) for pat in TAIL_PATTERNS)

    if not (has_head and has_signal) or len(candidate) < 100:
        # Fallback: head+tail window of original text
        half = max_chars // 2
        candidate = (text[:half] + "\n\n... [cut] ...\n\n" + text[-half:]).strip()

    after_chars = len(candidate)
    after_tokens = after_chars // 4
    reduction = round(100.0 * (1.0 - (after_chars / max(1, before_chars))), 1)

    stats.update({
        "after_chars": after_chars,
        "after_tokens": after_tokens,
        "optimized": True,
        "reduction_pct": reduction,
    })

    return candidate, stats


def extract_with_deepseek(
    optimized_text: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_retries: int = 3,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Calls DeepSeek API (OpenAI-compatible) with JSON mode (§6):
    - Endpoint: https://api.deepseek.com/chat/completions
    - response_format: {"type": "json_object"}
    - max_tokens: 1024, temperature: 0
    - Returns parsed JSON dict
    """
    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY is not set in environment or arguments.")

    model_name = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    url = "https://api.deepseek.com/chat/completions"

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Extract the Impressum data from the text below and return JSON:\n\n{optimized_text}",
            },
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 1024,
        "temperature": 0,
    }

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200:
                raise RuntimeError(f"DeepSeek HTTP {resp.status_code}: {resp.text}")

            res_json = resp.json()
            choices = res_json.get("choices") or []
            if not choices:
                raise ValueError(f"DeepSeek returned no choices: {res_json}")

            content = choices[0].get("message", {}).get("content", "").strip()
            if not content:
                # Per DeepSeek docs: blank content on JSON parse failure; retry with backoff
                time.sleep(attempt * 1.5)
                continue

            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
            raise ValueError(f"DeepSeek output parsed as {type(parsed)}, expected dict.")

        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                time.sleep(attempt * 1.5)

    raise RuntimeError(f"DeepSeek structured extraction failed after {max_retries} attempts: {last_err}")


def evaluate_extraction_status(
    parsed_json: Dict[str, Any],
    fallback_company_name: Optional[str] = None,
) -> Tuple[CompanyStatus, Dict[str, Any]]:
    """
    Decides status per §4.6 and formats fields for PostgreSQL:
    1. status = 2 (PARSING_FAILED): no fields detected / empty JSON.
    2. status = 3 (ADDRESS_INCOMPLETE): fields detected, but postal_address incomplete.
       (Requires all 4: postcode, city, street, house_no).
    3. status = 0 (OK): fields detected AND address complete.
    """
    if not isinstance(parsed_json, dict) or not parsed_json:
        return CompanyStatus.PARSING_FAILED, {
            "legal_name": fallback_company_name,
            "postal_address": None,
            "handelsregister": None,
            "vat_number": None,
            "phone": None,
            "email": None,
            "responsible_person": None,
            "raw_json": parsed_json or {},
        }

    raw_comp = parsed_json.get("company_name")
    legal_name = str(raw_comp).strip() if raw_comp else (fallback_company_name or None)

    addr_obj = parsed_json.get("postal_address")
    if not isinstance(addr_obj, dict):
        addr_obj = {}

    street = str(addr_obj.get("street") or "").strip() or None
    house_no = str(addr_obj.get("house_no") or "").strip() or None
    postcode = str(addr_obj.get("postcode") or "").strip() or None
    city = str(addr_obj.get("city") or "").strip() or None
    country = str(addr_obj.get("country") or "").strip() or None

    handelsregister = str(parsed_json.get("handelsregister") or "").strip() or None
    vat_number = str(parsed_json.get("vat_number") or "").strip() or None
    phone = str(parsed_json.get("phone") or "").strip() or None
    raw_email = str(parsed_json.get("email") or "").strip()
    email = raw_email.lower() if raw_email else None
    responsible_person = str(parsed_json.get("responsible_person") or "").strip() or None

    # Construct human-readable postal_address string
    parts = []
    street_part = " ".join(filter(None, [street, house_no]))
    if street_part:
        parts.append(street_part)
    city_part = " ".join(filter(None, [postcode, city]))
    if city_part:
        parts.append(city_part)
    if country:
        parts.append(country)
    postal_address = ", ".join(parts) if parts else None

    # Check if any field was detected
    has_any_field = any([
        raw_comp,
        street,
        house_no,
        postcode,
        city,
        country,
        handelsregister,
        vat_number,
        phone,
        email,
        responsible_person,
    ])

    if not has_any_field:
        status = CompanyStatus.PARSING_FAILED
    else:
        # "Complete" means all four of postal_address.postcode, city, street, and house_no are non-empty
        is_address_complete = bool(street and house_no and postcode and city)
        if is_address_complete:
            status = CompanyStatus.OK
        else:
            status = CompanyStatus.ADDRESS_INCOMPLETE

    mapped = {
        "legal_name": legal_name,
        "postal_address": postal_address,
        "handelsregister": handelsregister,
        "vat_number": vat_number,
        "phone": phone,
        "email": email,
        "responsible_person": responsible_person,
        "raw_json": parsed_json,
    }
    return status, mapped
