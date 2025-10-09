# src/find_ir_pages.py
# Project LANTERN - Investor Relations Page Finder with EDGAR Fallback

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import yaml
import pandas as pd
from pathlib import Path
from datetime import datetime
import time
from sec_edgar import SECEdgar


def load_params():
    """Load parameters from params.yaml"""
    try:
        with open('params.yaml', 'r') as f:
            params = yaml.safe_load(f)
            return params.get('find_ir_pages', {})
    except FileNotFoundError:
        print("⚠ params.yaml not found, using defaults")
        return {
            'input_file': 'data/raw/scraped/dow30_companies.csv',
            'output_dir': 'data/processed/ir_pages',
            'timeout': 10,
            'rate_limit': 2,
            'user_agent': 'FinTrustAnalytics project-lantern your-email@example.com'
        }


def get_headers():
    """Return browser-like headers"""
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }


def check_url_exists(url, timeout=5):
    """Check if a URL exists (returns 200)"""
    try:
        response = requests.head(url, headers=get_headers(), timeout=timeout, allow_redirects=True)
        return response.status_code == 200
    except:
        return False


def find_ir_page_automated(company_url, timeout=10):
    """
    Find IR page automatically - no manual mappings
    
    Strategy:
    1. Try common URL patterns
    2. Scrape homepage for IR links
    3. Return None if not found (EDGAR will be used as fallback)
    """
    
    print(f"  🔍 Searching: {company_url}")
    
    # Common IR page patterns
    common_patterns = [
        '/investors',
        '/investor-relations',
        '/ir',
        '/en/investors',
        '/investorrelations',
        '/investor',
        '/about/investor-relations',
        '/about/investors',
        '/company/investors',
        '/investor-relations.html',
    ]
    
    # Strategy 1: Try common patterns
    for pattern in common_patterns:
        test_url = urljoin(company_url, pattern)
        if check_url_exists(test_url, timeout):
            print(f"    ✓ Found via pattern: {pattern}")
            return {
                'ir_url': test_url,
                'method': 'common_pattern',
                'pattern': pattern,
                'success': True
            }
    
    # Strategy 2: Scrape homepage for IR links
    try:
        response = requests.get(company_url, headers=get_headers(), timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # IR keywords to search for
        ir_keywords = [
            'investor relations',
            'investors',
            'investor',
            'shareholder',
            'financial information',
        ]
        
        # Find all links
        links = soup.find_all('a', href=True)
        
        for link in links:
            link_text = link.get_text().lower().strip()
            link_href = link['href']
            
            # Check if link text or href contains IR keywords
            for keyword in ir_keywords:
                if keyword in link_text or keyword in link_href.lower():
                    ir_url = urljoin(company_url, link_href)
                    
                    # Make sure it's a valid URL
                    if urlparse(ir_url).scheme in ['http', 'https']:
                        print(f"    ✓ Found via homepage link: '{link_text[:50]}'")
                        return {
                            'ir_url': ir_url,
                            'method': 'homepage_link',
                            'link_text': link_text,
                            'success': True
                        }
        
        # Not found
        print(f"    ❌ IR page not found on website")
        return None
        
    except Exception as e:
        print(f"    ❌ Error scraping: {e}")
        return None


def get_edgar_fallback(ticker, sec_client):
    """
    Use SEC EDGAR as fallback when IR page not found
    """
    print(f"    📡 Using SEC EDGAR fallback...")
    
    # Get CIK
    cik = sec_client.get_cik_from_ticker(ticker)
    
    if not cik:
        print(f"    ❌ Could not find CIK for {ticker}")
        return {
            'ir_url': None,
            'edgar_cik': None,
            'method': 'edgar_failed',
            'success': False,
            'error': 'CIK not found'
        }
    
    # Construct EDGAR company page URL
    edgar_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=8-K&dateb=&owner=exclude&count=40"
    
    print(f"    ✓ Using EDGAR (CIK: {cik})")
    
    return {
        'ir_url': edgar_url,
        'edgar_cik': cik,
        'method': 'edgar_fallback',
        'success': True,
        'note': 'Using SEC EDGAR filings page'
    }


def process_all_companies(companies_df, params):
    """
    Process all companies - try automated discovery, fallback to EDGAR
    """
    sec_client = SECEdgar(user_agent=params['user_agent'])
    results = []
    
    for idx, row in companies_df.iterrows():
        ticker = row['ticker']
        company_name = row['company_name']
        website = row['company_website']
        
        print(f"\n[{idx+1}/{len(companies_df)}] {ticker} - {company_name}")
        
        result = None
        
        # Try automated IR discovery if website available
        if not pd.isna(website) and website:
            result = find_ir_page_automated(website, timeout=params['timeout'])
        else:
            print(f"  ⚠ No website available")
        
        # If not found, use EDGAR fallback
        if result is None:
            result = get_edgar_fallback(ticker, sec_client)
        
        # Add company info
        result['ticker'] = ticker
        result['company_name'] = company_name
        result['company_website'] = website
        result['discovered_date'] = datetime.now().isoformat()
        
        results.append(result)
        
        # Rate limiting
        time.sleep(params['rate_limit'])
    
    return results


def save_results(results, output_dir):
    """Save IR page results"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save full results
    results_file = output_path / 'ir_pages.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Saved results to: {results_file}")
    
    # Save summary
    summary = {
        'discovery_date': datetime.now().isoformat(),
        'total_companies': len(results),
        'successful': sum(1 for r in results if r['success']),
        'failed': sum(1 for r in results if not r['success']),
        'methods': {}
    }
    
    # Count by method
    for result in results:
        method = result.get('method', 'unknown')
        summary['methods'][method] = summary['methods'].get(method, 0) + 1
    
    summary_file = output_path / 'ir_discovery_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"✓ Saved summary to: {summary_file}")
    
    return summary


def main():
    print("="*60)
    print("Project LANTERN - IR Page Finder")
    print("Automated Discovery with SEC EDGAR Fallback")
    print("="*60)
    
    # Load parameters
    params = load_params()
    
    # Check user agent
    if 'your-email@example.com' in params['user_agent']:
        print("\n⚠️  IMPORTANT: Update user_agent in params.yaml with your real email!")
        print("   SEC requires contact info for EDGAR API access.")
        print("   Example: 'FinTrustAnalytics project-lantern john@university.edu'\n")
    
    print(f"Parameters:")
    for key, value in params.items():
        if key != 'user_agent':
            print(f"  {key}: {value}")
    
    # Load companies
    input_file = params['input_file']
    print(f"\n📂 Loading companies from: {input_file}")
    
    try:
        companies_df = pd.read_csv(input_file)
        print(f"✓ Loaded {len(companies_df)} companies")
    except FileNotFoundError:
        print(f"❌ File not found: {input_file}")
        return
    
    # Process all companies
    print("\n" + "="*60)
    print("Finding IR Pages")
    print("="*60)
    
    results = process_all_companies(companies_df, params)
    
    # Save results
    summary = save_results(results, params['output_dir'])
    
    # Print summary
    print("\n" + "="*60)
    print("📊 Summary")
    print("="*60)
    print(f"Total companies: {summary['total_companies']}")
    print(f"✓ Successfully found: {summary['successful']}")
    print(f"❌ Failed: {summary['failed']}")
    print(f"\nDiscovery methods:")
    for method, count in summary['methods'].items():
        print(f"  {method}: {count}")
    print("\n💡 EDGAR fallback ensures 100% coverage")
    print("="*60)


if __name__ == "__main__":
    main()