#!/usr/bin/env python3
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

WIKI_URL = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LanternBot/1.0)"}

def find_constituents_table(soup: BeautifulSoup):
    # Find a wikitable that includes both 'Company' and 'Symbol' in headers
    for t in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
        if ("company" in " ".join(headers)) and any(h in headers for h in ["symbol", "ticker", "ticker symbol"]):
            return t
    raise RuntimeError("Could not find constituents table on Wikipedia.")

def header_index_map(table):
    # Build a name->index map for the row <td> order based on the header row
    header_cells = table.find("tr").find_all(["th", "td"])
    names = [h.get_text(strip=True).lower() for h in header_cells]
    idx = {}
    for i, name in enumerate(names):
        if name == "company":
            idx["company"] = i
        elif name in ("symbol", "ticker", "ticker symbol"):
            idx["symbol"] = i
    if "company" not in idx or "symbol" not in idx:
        raise RuntimeError(f"Could not map headers properly. Found: {names}")
    return idx

def fetch_dow30_rows():
    r = requests.get(WIKI_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    table = find_constituents_table(soup)
    col_idx = header_index_map(table)

    rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all(["td", "th"])
        if len(tds) <= max(col_idx.values()):
            continue
        company_cell = tds[col_idx["company"]]
        symbol_cell  = tds[col_idx["symbol"]]

        company = company_cell.get_text(" ", strip=True)
        ticker  = symbol_cell.get_text(" ", strip=True).split()[0]

        a = company_cell.find("a", href=True)
        company_page = urljoin(WIKI_URL, a["href"]) if a else None
        rows.append({"company": company, "ticker": ticker, "company_wikipedia": company_page})
    return rows

def extract_official_website(company_page):
    if not company_page:
        return None
    try:
        res = requests.get(company_page, headers=HEADERS, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")
        info = soup.find("table", class_="infobox")
        if not info:
            return None
        for tr in info.find_all("tr"):
            th = tr.find("th")
            if th and "website" in th.get_text(" ", strip=True).lower():
                a = tr.find("a", href=True)
                if a and a["href"].startswith("http"):
                    return a["href"]
    except Exception:
        return None
    return None

def main():
    print("Fetching Dow 30 constituents from Wikipedia…")
    rows = fetch_dow30_rows()
    print(f"Found {len(rows)} companies. Extracting official websites…")

    out = []
    for i, r_ in enumerate(rows, 1):
        site = extract_official_website(r_["company_wikipedia"])
        out.append({
            "ticker": r_["ticker"],
            "company": r_["company"],
            "website": site,
            "company_wikipedia": r_["company_wikipedia"],
            "source": "Wikipedia infobox",
        })
        print(f"{i:02d}. {r_['company']} ({r_['ticker']}) → {site}")
        time.sleep(0.4)

    df = pd.DataFrame(out).sort_values("ticker")
    out_dir = "data/reference"
    csv_path = f"{out_dir}/dow30_companies.csv"
    json_path = f"{out_dir}/dow30_companies.json"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2)
    print(f"\n✅ Saved {len(df)} companies to:")
    print(f"  - {csv_path}")
    print(f"  - {json_path}")

if __name__ == "__main__":
    main()
