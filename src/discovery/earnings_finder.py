import argparse
import re
import sys
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from urllib.parse import urlparse

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LanternBot/1.0)"}

# Keywords indicating earnings / quarterly results
EARNINGS_KEYWORDS = [
    r"quarterly results",
    r"earnings release",
    r"earnings results",
    r"quarterly earnings",
    r"q[1-4]\s*\d{4}",           # Q1 2025
    r"\bq[1-4]\b",               # standalone Q1/Q2 etc.
    r"results for the quarter",
    r"financial results",
    r"earnings call",
    r"supplemental (data|tables|information)",
    r"quarterly (update|highlights)",
    r"press release",
    r"quarter results",
    r"fiscal q[1-4]",
    r"\b10-q\b",
]
EARNINGS_RE = re.compile("|".join(EARNINGS_KEYWORDS), re.I)

# Exclusion terms to filter out non-earnings items
EXCLUDE_KEYWORDS = [
    r"dividend",
    r"stock split",
    r"acquisition",
    r"merger",
    r"buyback",
    r"annual report",
    r"proxy",
    r"esg",
    r"sustainability",
    r"preliminary",
]
EXCLUDE_RE = re.compile("|".join(EXCLUDE_KEYWORDS), re.I)

# Simple date patterns to capture YYYY-MM-DD, Month DD, YYYY
DATE_PATTERNS = [
    r"\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b",  # 2025-10-08
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),\s+(20\d{2})\b",
]
DATE_RES = [re.compile(p, re.I) for p in DATE_PATTERNS]

MONTHS = {
    'jan': 1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,
    'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,'sep':9,'sept':9,
    'september':9,'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12
}

# Generic subpaths commonly used by IR providers (Q4/Investis/Wire/Drupal/etc.)
SUBPATH_HINTS = [
    "financials/quarterly-results/default.aspx",
    "financials/quarterly-results",
    "financial-information/financial-results/default.aspx",
    "financial-information/financial-results",
    "financial-information/quarterly-results/default.aspx",
    "financial-information/quarterly-results",
    "financials",
    "financial-results",
    "financial-results/default.aspx",
    "news",
    "press",
    "press-releases",
    "news-and-events",
    "news-events",
    "investors/press-releases",
    "investor-relations/press-releases",
]

HOP_HINTS = (
    "financial", "quarter", "results", "earnings", "press", "news", "events"
)

# Map doc types to priorities (lower is better)
DOC_TYPE_PRIORITY = {
    "press_release": 0,
    "presentation": 1,
    "supplement": 2,
    "10-q": 3,
    "transcript": 4,
    "other": 9,
}

@dataclass
class Candidate:
    title: str
    url: str
    date: Optional[datetime]
    score: float
    quarter: Optional[Tuple[int, int]]  # (year, q)
    doc_type: str


def parse_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    t = text.strip()
    # Try ISO-like first
    m = DATE_RES[0].search(t)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d)
        except Exception:
            pass
    # Try Month DD, YYYY
    m = DATE_RES[1].search(t)
    if m:
        try:
            mo = MONTHS[m.group(1).lower()]
            d = int(m.group(2))
            y = int(m.group(3))
            return datetime(y, mo, d)
        except Exception:
            pass
    return None


QUARTER_WORDS = {
    "first": 1, "1st": 1,
    "second": 2, "2nd": 2,
    "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4,
}

QUARTER_PATTERNS = [
    re.compile(r"\b(q([1-4]))\s*(\d{4})\b", re.I),                # Q4 2025
    re.compile(r"\b(fiscal\s+q([1-4]))\b.*?(\d{4})?", re.I),      # fiscal Q1 (optional year)
    re.compile(r"\b(first|second|third|fourth)\s+quarter\b.*?(\d{4})?", re.I),
]

def parse_quarter(text: str, fallback_date: Optional[datetime]) -> Optional[Tuple[int, int]]:
    if not text:
        return None
    s = text.lower()
    # Pattern 1: Q{n} YYYY
    m = QUARTER_PATTERNS[0].search(s)
    if m:
        q = int(m.group(2))
        y = int(m.group(3))
        return (y, q)
    # Pattern 2: fiscal Q{n} [YYYY]
    m = QUARTER_PATTERNS[1].search(s)
    if m:
        q = int(m.group(2))
        if m.group(3):
            return (int(m.group(3)), q)
        if fallback_date:
            return (fallback_date.year, q)
    # Pattern 3: words
    m = QUARTER_PATTERNS[2].search(s)
    if m:
        q = QUARTER_WORDS.get(m.group(1), None)
        if q:
            if m.group(2):
                return (int(m.group(2)), q)
            if fallback_date:
                return (fallback_date.year, q)
    return None


def classify_doc_type(hay: str) -> str:
    if re.search(r"press\s*release", hay):
        return "press_release"
    if re.search(r"presentation|slides|deck", hay):
        return "presentation"
    if re.search(r"supplement|tables|data\s*supplement|financial\s*supplement", hay):
        return "supplement"
    if re.search(r"\b10-?q\b", hay):
        return "10-q"
    if re.search(r"transcript", hay):
        return "transcript"
    return "other"


def fetch(url: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
        return r.status_code, r.text, r.url
    except requests.RequestException:
        return None, None, None


def extract_candidates(base_url: str, html: str) -> List[Candidate]:
    soup = BeautifulSoup(html, "lxml")

    candidates: List[Candidate] = []
    for a in soup.find_all("a", href=True):
        title = (a.get_text(" ", strip=True) or "").strip()
        href = a["href"].strip()
        full_url = urljoin(base_url, href)

        hay = f"{title} {href}".lower()
        if not EARNINGS_RE.search(hay):
            continue
        if EXCLUDE_RE.search(hay):
            continue

        # Try to find nearby date: sibling text or within parent
        context_text = " ".join(
            [title] + [p.get_text(" ", strip=True) for p in a.parents if hasattr(p, 'get_text')][:2]
        )
        dt = parse_date(title) or parse_date(href) or parse_date(context_text)

        # Quarter inference
        quarter = parse_quarter(f"{title} {context_text}", dt)

        # Doc type
        doc_type = classify_doc_type(hay)

        # Scoring: keywords + recency + doc type priority
        score = 1.0
        if re.search(r"\b(q[1-4]|quarter|earnings)\b", hay):
            score += 1.0
        if doc_type in ("press_release", "presentation", "supplement"):
            score += 0.5
        if dt:
            # More recent gets higher
            days = (datetime.utcnow() - dt).days if dt else 3650
            score += max(0.0, 365.0 - min(days, 365)) / 365.0  # up to +1 within a year

        candidates.append(Candidate(title=title, url=full_url, date=dt, score=score, quarter=quarter, doc_type=doc_type))

    return candidates


def select_best(candidates: List[Candidate]) -> Optional[Candidate]:
    if not candidates:
        return None

    # Rank by: quarter recency (year, q), then date recency, then doc type priority, then score
    def recency_key(c: Candidate):
        quarter_key = c.quarter if c.quarter else (c.date.year, 0) if c.date else (0, 0)
        date_key = c.date or datetime(1970, 1, 1)
        type_priority = DOC_TYPE_PRIORITY.get(c.doc_type, 9)
        return (quarter_key[0], quarter_key[1], date_key, -c.score, -type_priority)

    # Choose the max by the tuple above (most recent and best)
    best = max(candidates, key=recency_key)

    # If multiple in same quarter, prefer doc type priority explicitly
    same_quarter = [c for c in candidates if c.quarter and best.quarter and c.quarter == best.quarter]
    if same_quarter:
        same_quarter.sort(key=lambda c: (DOC_TYPE_PRIORITY.get(c.doc_type, 9), -(c.date.timestamp() if c.date else 0)))
        return same_quarter[0]

    return best


def process_company(row: dict) -> dict:
    ticker = row.get("ticker")
    company = row.get("company")
    ir_url = row.get("ir_url")

    if not isinstance(ir_url, str) or not ir_url.strip():
        return {
            "ticker": ticker,
            "company": company,
            "ir_url": ir_url,
            "latest_title": None,
            "latest_url": None,
            "latest_date": None,
            "latest_doc_type": None,
            "latest_quarter": None,
            "source": "no_ir_url",
        }

    status, html, final = fetch(ir_url)
    if not html:
        return {
            "ticker": ticker,
            "company": company,
            "ir_url": ir_url,
            "latest_title": None,
            "latest_url": None,
            "latest_date": None,
            "latest_doc_type": None,
            "latest_quarter": None,
            "source": f"fetch_failed:{status}",
        }

    base = final or ir_url
    base_host = urlparse(base).netloc
    cands = extract_candidates(base, html)

    # Early exit if we found a good press release
    if cands:
        best = select_best(cands)
        if best and best.doc_type == "press_release" and best.date and best.quarter:
            quarter_str = f"Q{best.quarter[1]} {best.quarter[0]}" if best.quarter else None
            return {
                "ticker": ticker,
                "company": company,
                "ir_url": ir_url,
                "latest_title": best.title,
                "latest_url": best.url,
                "latest_date": best.date.strftime("%Y-%m-%d") if best.date else None,
                "latest_doc_type": best.doc_type,
                "latest_quarter": quarter_str,
                "source": "ir_page_early_exit",
            }

    # Probe common provider subpaths from base (limit to 5 most common)
    for sp in SUBPATH_HINTS[:5]:
        candidate_url = urljoin(base.rstrip('/') + '/', sp)
        s2, h2, f2 = fetch(candidate_url)
        if h2:
            cands.extend(extract_candidates(f2 or candidate_url, h2))
            # Early exit if we found something good
            if cands:
                best = select_best(cands)
                if best and best.doc_type in ("press_release", "presentation") and best.date:
                    quarter_str = f"Q{best.quarter[1]} {best.quarter[0]}" if best.quarter else None
                    return {
                        "ticker": ticker,
                        "company": company,
                        "ir_url": ir_url,
                        "latest_title": best.title,
                        "latest_url": best.url,
                        "latest_date": best.date.strftime("%Y-%m-%d") if best.date else None,
                        "latest_doc_type": best.doc_type,
                        "latest_quarter": quarter_str,
                        "source": "subpath_early_exit",
                    }

    # If still no candidates, try limited hop crawl
    if not cands:
        soup = BeautifulSoup(html, "lxml")
        hops = 0
        for a in soup.find_all("a", href=True):
            href_raw = a["href"]
            href = href_raw.lower()
            if not any(k in href for k in HOP_HINTS):
                continue
            next_url = urljoin(base, href_raw)
            # Stay on same domain
            if urlparse(next_url).netloc != base_host:
                continue
            s2, h2, f2 = fetch(next_url)
            if not h2:
                continue
            cands2 = extract_candidates(f2 or next_url, h2)
            cands.extend(cands2)
            hops += 1
            if hops >= 8:  # Reduced from 20
                break

    best = select_best(cands)
    if best:
        quarter_str = f"Q{best.quarter[1]} {best.quarter[0]}" if best.quarter else None
        return {
            "ticker": ticker,
            "company": company,
            "ir_url": ir_url,
            "latest_title": best.title,
            "latest_url": best.url,
            "latest_date": best.date.strftime("%Y-%m-%d") if best.date else None,
            "latest_doc_type": best.doc_type,
            "latest_quarter": quarter_str,
            "source": "ir_page_or_child",
        }

    return {
        "ticker": ticker,
        "company": company,
        "ir_url": ir_url,
        "latest_title": None,
        "latest_url": None,
        "latest_date": None,
        "latest_doc_type": None,
        "latest_quarter": None,
        "source": "no_match",
    }


def confidence_label(doc_type: Optional[str], date_present: bool, quarter_present: bool) -> str:
    if doc_type == "press_release" and date_present and (quarter_present or True):
        return "high"
    if doc_type in ("presentation", "supplement", "10-q") and (date_present or quarter_present):
        return "medium"
    return "low"


def main():
    ap = argparse.ArgumentParser(description="Locate the latest quarterly earnings report from IR pages.")
    ap.add_argument("--in_csv", default="data/reference/dow30_ir_pages.csv")
    ap.add_argument("--out_csv", default="data/reference/dow30_latest_reports.csv")
    ap.add_argument("--out_json", default="data/reference/dow30_latest_reports.json")
    ap.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    args = ap.parse_args()

    try:
        df = pd.read_csv(args.in_csv)
    except Exception as e:
        print(f"Failed to read input CSV {args.in_csv}: {e}")
        sys.exit(1)

    print(f"🚀 Processing {len(df)} companies with {args.workers} parallel workers...")
    start_time = time.time()
    
    results = []
    json_records = []
    
    # Process companies in parallel
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        future_to_row = {executor.submit(process_company, row.to_dict()): row for _, row in df.iterrows()}
        
        # Collect results as they complete
        for future in as_completed(future_to_row):
            res = future.result()
            results.append(res)
            print(f"[{res['ticker']}] {res['company']} → {res.get('latest_url')} ({res.get('latest_date')}) [{res.get('latest_doc_type')}] {res.get('latest_quarter')}")

            # Build JSON record per requested structure
            q = res.get("latest_quarter")
            fiscal_period = q if q else None
            pub_date = res.get("latest_date")
            doc_type = res.get("latest_doc_type")
            conf = confidence_label(doc_type, bool(pub_date), bool(fiscal_period))

            json_records.append({
                "ticker": res.get("ticker"),
                "company": res.get("company"),
                "earnings_report": {
                    "url": res.get("latest_url"),
                    "title": res.get("latest_title"),
                    "fiscal_period": fiscal_period,
                    "fiscal_year_end": None,
                    "publication_date": pub_date,
                    "report_type": doc_type,
                    "confidence": conf,
                }
            })

    # Sort results by ticker to maintain consistent order
    results.sort(key=lambda x: x['ticker'])
    json_records.sort(key=lambda x: x['ticker'])

    out_df = pd.DataFrame(results)
    out_df.to_csv(args.out_csv, index=False)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(json_records, f, indent=2, ensure_ascii=False)
    
    elapsed = time.time() - start_time
    print(f"\n✅ Saved latest earnings links to: {args.out_csv}")
    print(f"✅ Saved latest earnings JSON to: {args.out_json}")
    print(f"⏱️  Completed in {elapsed:.1f} seconds ({elapsed/len(df):.1f}s per company)")


if __name__ == "__main__":
    main()
