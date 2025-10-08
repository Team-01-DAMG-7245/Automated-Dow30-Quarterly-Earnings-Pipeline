#!/usr/bin/env python3
"""
Part 2 — Automatically discover Investor Relations (IR) pages from official websites.

Usage:
  python src/ir_finder.py --in_csv data/reference/dow30_companies.csv \
                          --out_csv data/reference/dow30_ir_pages.csv

Input CSV must include: ticker, company, website
Output CSV columns:      ticker, company, website, ir_url, method, http_status
"""

import argparse
import re
import time
from urllib.parse import urlparse, urljoin, urlunparse, ParseResult

import pandas as pd
import requests
from bs4 import BeautifulSoup
import tldextract

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LanternBot/1.0)"}

# Common IR URL patterns seen across large-cap sites
CANDIDATE_PATHS = [
    "/investors", "/investor", "/investor-relations", "/investor_relations",
    "/ir", "/investors/overview", "/investors/default.aspx",
    "/company/investors", "/about/investors", "/about-us/investors",
    "/our-company/investors", "/en-us/investors", "/en/investors",
    "/investor-relations/overview/default.aspx", "/investor-relations/default.aspx",
    "/investors/home/default.aspx", "/investor-relations/home/default.aspx",
]

# Match anchor text or href that signals investor relations
INVESTOR_PATTERN = re.compile(r"\binvestor(s)?(\s*relations|\s*rel\.?)?\b", re.I)


def normalize_root(url: str) -> str | None:
    """Ensure URL has scheme and return scheme+netloc root."""
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc}"


def fetch(url: str):
    """GET with redirects; return (status_code, html, final_url)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        return r.status_code, r.text, r.url
    except requests.RequestException:
        return None, None, None


def strip_query(u: str) -> str:
    """Remove query/fragment noise for cleaner, stable links."""
    try:
        p = urlparse(u)
        cleaned = ParseResult(p.scheme, p.netloc, p.path, "", "", "")
        return urlunparse(cleaned)
    except Exception:
        return u


def looks_investorish(s: str | None) -> bool:
    return bool(s and INVESTOR_PATTERN.search(s))


def find_ir_anchor(base_url: str, html: str | None, final_url: str | None):
    """Look for <a> that mentions 'Investor' on a page (text or href)."""
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        txt = a.get_text(" ", strip=True) or ""
        href = a["href"]
        if INVESTOR_PATTERN.search(txt) or INVESTOR_PATTERN.search(href):
            return urljoin(final_url or base_url, href)
    return None


def subdomain_candidates(root: str) -> list[str]:
    """Try common IR subdomains; also probe corporate.* and naked domain."""
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


def probe_ir(root: str):
    """
    Search order:
      1) Homepage anchors
      2) Common subdomains (investors., ir., investor., corporate.)
      3) Common paths on root
    Accept 2xx/3xx normally; also accept 401/403 if URL/body clearly looks like IR.
    """
    def acceptable(status: int | None, ctx: str | None) -> bool:
        if not status:
            return False
        if 200 <= status < 400:
            return True
        # some IR portals block bots; consider found if page/URL clearly indicates investor relations
        return status in (401, 403) and looks_investorish(ctx)

    # 1) Homepage → anchor to IR
    status, html, final = fetch(root)
    if acceptable(status, html or root):
        ir = find_ir_anchor(root, html, final)
        if ir:
            return strip_query(ir), "anchor_match", status

    # 2) Subdomains
    for sub in subdomain_candidates(root):
        status, html, final = fetch(sub)
        if acceptable(status, html or sub):
            ir = find_ir_anchor(sub, html, final)
            if ir:
                return strip_query(ir), f"subdomain_anchor({strip_query(sub)})", status
            if looks_investorish(sub) or looks_investorish(html):
                return strip_query(final or sub), "subdomain_keyword", status

    # 3) Candidate paths
    for path in CANDIDATE_PATHS:
        candidate = urljoin(root, path)
        status, html, final = fetch(candidate)
        if acceptable(status, html or candidate):
            target = strip_query(final or candidate)
            if looks_investorish(candidate) or looks_investorish(html):
                return target, "path_probe", status

    return None, "not_found", status or None


def locate_ir(row: dict) -> dict:
    ticker = row.get("ticker")
    company = row.get("company")
    website = normalize_root(row.get("website"))
    if not website:
        return {
            "ticker": ticker, "company": company, "website": None,
            "ir_url": None, "method": "no_website", "http_status": None
        }

    ir_url, method, status = probe_ir(website)
    return {
        "ticker": ticker,
        "company": company,
        "website": website,
        "ir_url": ir_url,
        "method": method,
        "http_status": status
    }


def main():
    ap = argparse.ArgumentParser(description="Discover IR pages automatically from company websites.")
    ap.add_argument("--in_csv", required=True, help="CSV with columns: ticker,company,website")
    ap.add_argument("--out_csv", default="data/reference/dow30_ir_pages.csv", help="Output CSV path")
    ap.add_argument("--sleep", type=float, default=0.4, help="Delay between companies (sec)")
    args = ap.parse_args()

    df = pd.read_csv(args.in_csv)
    results = []
    for _, row in df.iterrows():
        res = locate_ir(row.to_dict())
        results.append(res)
        print(f"[{res['ticker']}] {res['company']} → {res['ir_url']} ({res['method']})")
        time.sleep(args.sleep)

    pd.DataFrame(results).to_csv(args.out_csv, index=False)
    print(f"\n✅ Saved IR results to: {args.out_csv}")


if __name__ == "__main__":
    main()
