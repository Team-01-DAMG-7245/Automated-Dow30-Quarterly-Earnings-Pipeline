#!/usr/bin/env python3
"""
Part 2 — Automatically discover Investor Relations (IR) pages from official websites.

Improvements:
- IR_TEXTS: configurable anchor text keywords (multi-lingual), extendable via --extra_ir_texts
- Graceful 401/403 handling: accept investor-looking pages even if blocked by bot-walls
- Cleans tracking query params from final URLs
- Writes BOTH CSV and JSON outputs
- Retries with backoff on transient errors

Usage:
  python src/ir_finder.py \
    --in_csv data/reference/dow30_companies.csv \
    --out_csv data/reference/dow30_ir_pages.csv \
    --out_json data/reference/dow30_ir_pages.json \
    [--extra_ir_texts config/extra_ir_texts.txt]
"""

import argparse, json, re, time, sys
from typing import List, Optional
from urllib.parse import urlparse, urljoin, urlunparse, ParseResult

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import tldextract

# -------------------- Config --------------------

# Baseline anchor-text phrases that typically indicate investor relations, in multiple languages.
# You can extend this list at runtime via --extra_ir_texts <file>, one phrase per line.
IR_TEXTS: List[str] = [
    "investor", "investors", "investor relations", "ir",
    # Common variants
    "relations with investors", "relations investor",
    # French
    "relations investisseurs", "relations investisseurs et actionnaires",
    # Spanish/Portuguese/Italian
    "relaciones con inversores", "relación con inversores", "relacoes com investidores",
    "relazioni con gli investitori",
    # German
    "investor relations de", "investor relations deutschland", "investoren",
    # Chinese / Japanese / Korean (frequent on multi-lang sites)
    "投资者关系", "投資家情報", "투자자 관계",
]

# Common IR paths you can probe when no anchor is found
CANDIDATE_PATHS = [
    "/investors", "/investor", "/investor-relations", "/investor_relations",
    "/ir", "/investors/overview", "/investors/default.aspx",
    "/company/investors", "/about/investors", "/about-us/investors",
    "/our-company/investors", "/en-us/investors", "/en/investors",
    "/investor-relations/overview/default.aspx", "/investor-relations/default.aspx",
    "/investors/home/default.aspx", "/investor-relations/home/default.aspx",
    "/corporate/investors", "/corp/investors", "/company/investor-relations",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LanternBot/1.0)"}

# -------------------- Helpers --------------------

def build_investor_pattern(extra_terms: Optional[List[str]] = None) -> re.Pattern:
    # Merge base + extra terms and escape safely. Keep 'IR' as standalone as well.
    terms = set(IR_TEXTS)
    if extra_terms:
        terms.update([t.strip() for t in extra_terms if t.strip()])
    # Sort longer first to avoid partial greedy matches
    escaped = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    # Word boundary on Latin terms; allow non-Latin without word boundary
    pattern = r"(?i)(\b(" + "|".join(escaped) + r")\b|投资者关系|投資家情報|투자자\s*관계)"
    return re.compile(pattern, re.I)

def make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD", "OPTIONS"],
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

def normalize_root(url: str) -> Optional[str]:
    if not isinstance(url, str) or not url.strip():
        return None
    u = url.strip()
    if not u.startswith("http"):
        u = "https://" + u
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None

def strip_query(u: str) -> str:
    try:
        p = urlparse(u)
        return urlunparse(ParseResult(p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return u

def fetch(session: requests.Session, url: str):
    try:
        r = session.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        return r.status_code, r.text, r.url
    except requests.RequestException:
        return None, None, None

def looks_investorish(s: Optional[str], pat: re.Pattern) -> bool:
    return bool(s and pat.search(s))

def find_ir_anchor(base_url: str, html: Optional[str], final_url: Optional[str], pat: re.Pattern):
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        txt = (a.get_text(" ", strip=True) or "").lower()
        href = a["href"]
        # Check text OR href against investor pattern
        if pat.search(txt) or pat.search(href):
            return urljoin(final_url or base_url, href)
    return None

def subdomain_candidates(root: str) -> List[str]:
    ext = tldextract.extract(root)
    rd = getattr(ext, "top_domain_under_public_suffix", None) or ext.registered_domain
    if not rd:
        return []
    return [
        f"https://investors.{rd}",
        f"https://ir.{rd}",
        f"https://investor.{rd}",
        f"https://corporate.{rd}",
        f"https://{rd}",
    ]

def acceptable(status: Optional[int], ctx: Optional[str], pat: re.Pattern) -> bool:
    if not status:
        return False
    if 200 <= status < 400:
        return True
    # Treat 401/403 as acceptable if the URL/body look like investor relations
    return status in (401, 403) and looks_investorish(ctx, pat)

# -------------------- Core probe --------------------

def probe_ir(root: str, session: requests.Session, pat: re.Pattern):
    # 1) Homepage → anchor to IR
    status, html, final = fetch(session, root)
    if acceptable(status, html or root, pat):
        ir = find_ir_anchor(root, html, final, pat)
        if ir:
            return strip_query(ir), "anchor_match", status

    # 2) Subdomains
    for sub in subdomain_candidates(root):
        status, html, final = fetch(session, sub)
        if acceptable(status, html or sub, pat):
            ir = find_ir_anchor(sub, html, final, pat)
            if ir:
                return strip_query(ir), f"subdomain_anchor({strip_query(sub)})", status
            if looks_investorish(sub, pat) or looks_investorish(html, pat):
                return strip_query(final or sub), "subdomain_keyword", status

    # 2b) Investor-looking subdomain as last resort (blocked portals)
    for sub in subdomain_candidates(root):
        if looks_investorish(sub, pat):
            # Even if we can't fetch it (or get 401/403), keep a clean URL
            return strip_query(sub), "subdomain_guess", 403

    # 3) Candidate paths
    for path in CANDIDATE_PATHS:
        candidate = urljoin(root, path)
        status, html, final = fetch(session, candidate)
        if acceptable(status, html or candidate, pat):
            target = strip_query(final or candidate)
            if looks_investorish(candidate, pat) or looks_investorish(html, pat):
                return target, "path_probe", status

    return None, "not_found", status or None

def locate_ir(row: dict, session: requests.Session, pat: re.Pattern) -> dict:
    ticker = row.get("ticker")
    company = row.get("company")
    website = normalize_root(row.get("website"))
    if not website:
        return {"ticker": ticker, "company": company, "website": None,
                "ir_url": None, "method": "no_website", "http_status": None}
    ir_url, method, status = probe_ir(website, session, pat)
    return {"ticker": ticker, "company": company, "website": website,
            "ir_url": ir_url, "method": method, "http_status": status}

# -------------------- CLI --------------------

def main():
    ap = argparse.ArgumentParser(description="Discover IR pages automatically from company websites.")
    ap.add_argument("--in_csv", required=True, help="CSV with columns: ticker,company,website")
    ap.add_argument("--out_csv", default="data/reference/dow30_ir_pages.csv", help="Output CSV path")
    ap.add_argument("--out_json", default=None, help="Optional JSON output path")
    ap.add_argument("--extra_ir_texts", default=None, help="Path to a file with extra IR text phrases (one per line)")
    ap.add_argument("--sleep", type=float, default=0.4, help="Delay between companies (sec)")
    args = ap.parse_args()

    extra_terms = None
    if args.extra_ir_texts:
        try:
            with open(args.extra_ir_texts, "r", encoding="utf-8") as f:
                extra_terms = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
        except Exception as e:
            print(f"WARNING: could not read --extra_ir_texts: {e}", file=sys.stderr)

    pat = build_investor_pattern(extra_terms)
    session = make_session()

    df = pd.read_csv(args.in_csv)
    results = []
    for _, row in df.iterrows():
        res = locate_ir(row.to_dict(), session, pat)
        results.append(res)
        print(f"[{res['ticker']}] {res['company']} → {res['ir_url']} ({res['method']})")
        time.sleep(args.sleep)

    out_df = pd.DataFrame(results)
    out_df.to_csv(args.out_csv, index=False)
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n✅ Saved results to:")
    print(f"  - CSV : {args.out_csv}")
    if args.out_json:
        print(f"  - JSON: {args.out_json}")

if __name__ == "__main__":
    main()
