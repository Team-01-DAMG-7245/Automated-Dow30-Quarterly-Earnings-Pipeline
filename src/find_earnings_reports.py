# src/find_earnings_reports.py
# Project LANTERN - Earnings Report Finder

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import yaml
from pathlib import Path
from datetime import datetime
import time
import re


def load_params():
    """Load parameters from params.yaml"""
    try:
        with open('params.yaml', 'r') as f:
            params = yaml.safe_load(f)
            return params.get('find_earnings_reports', {})
    except FileNotFoundError:
        print("⚠ params.yaml not found, using defaults")
        return {
            'input_file': 'data/processed/ir_pages/ir_pages.json',
            'output_dir': 'data/processed/earnings_reports',
            'timeout': 10,
            'rate_limit': 2
        }


def get_headers():
    """Return browser-like headers"""
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }


def find_earnings_reports(ir_url, timeout=10):
    """
    Find latest earnings reports from IR page
    """
    
    print(f"  🔍 Searching: {ir_url}")
    
    try:
        response = requests.get(ir_url, headers=get_headers(), timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Keywords for earnings content
        earnings_keywords = [
            'quarterly results',
            'earnings release',
            'earnings report',
            'q1 2025', 'q2 2025', 'q3 2025', 'q4 2024',
            'q1 2024', 'q2 2024', 'q3 2024', 'q4 2023',
            'financial results',
            'earnings announcement',
            'press release',
        ]
        
        # Find all links
        links = soup.find_all('a', href=True)
        
        candidates = []
        
        for link in links:
            link_text = link.get_text().lower().strip()
            link_href = link['href']
            full_url = urljoin(ir_url, link_href)
            
            # Check if link is relevant to earnings
            relevance_score = 0
            matched_keywords = []
            
            for keyword in earnings_keywords:
                if keyword in link_text or keyword in link_href.lower():
                    relevance_score += 1
                    matched_keywords.append(keyword)
            
            # Prioritize PDFs
            if link_href.lower().endswith('.pdf'):
                relevance_score += 2
            
            if relevance_score > 0:
                candidates.append({
                    'url': full_url,
                    'text': link_text,
                    'relevance_score': relevance_score,
                    'matched_keywords': matched_keywords,
                    'is_pdf': link_href.lower().endswith('.pdf')
                })
        
        # Sort by relevance
        candidates.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        if candidates:
            # Return top 5 most relevant
            top_candidates = candidates[:5]
            print(f"    ✓ Found {len(candidates)} potential reports (showing top 5)")
            for i, c in enumerate(top_candidates, 1):
                print(f"      {i}. {c['text'][:60]}... (score: {c['relevance_score']})")
            
            return {
                'reports': top_candidates,
                'count': len(candidates),
                'success': True
            }
        else:
            print(f"    ❌ No earnings reports found")
            return {
                'reports': [],
                'count': 0,
                'success': False,
                'message': 'No earnings reports found'
            }
        
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return {
            'reports': [],
            'count': 0,
            'success': False,
            'error': str(e)
        }


def process_all_companies(ir_data, params):
    """
    Process all companies and find their earnings reports
    """
    results = []
    
    for idx, company in enumerate(ir_data):
        ticker = company['ticker']
        company_name = company.get('company_name', ticker)
        ir_url = company.get('ir_url')
        
        print(f"\n[{idx+1}/{len(ir_data)}] {ticker} - {company_name}")
        
        # Skip if no IR URL or company discovery failed
        if not ir_url or not company.get('success', False):
            print(f"  ⚠ No valid IR URL available, skipping")
            results.append({
                'ticker': ticker,
                'company_name': company_name,
                'ir_url': None,
                'reports': [],
                'success': False,
                'error': 'No IR URL available'
            })
            continue
        
        # Find earnings reports
        report_result = find_earnings_reports(ir_url, timeout=params['timeout'])
        
        # Add company info
        report_result['ticker'] = ticker
        report_result['company_name'] = company_name
        report_result['ir_url'] = ir_url
        report_result['discovered_date'] = datetime.now().isoformat()
        
        results.append(report_result)
        
        # Rate limiting
        time.sleep(params['rate_limit'])
    
    return results


def save_results(results, output_dir):
    """Save earnings report results"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save full results
    results_file = output_path / 'earnings_reports_links.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Saved results to: {results_file}")
    
    # Save summary
    summary = {
        'discovery_date': datetime.now().isoformat(),
        'total_companies': len(results),
        'successful': sum(1 for r in results if r['success']),
        'failed': sum(1 for r in results if not r['success']),
        'total_reports_found': sum(r.get('count', 0) for r in results)
    }
    
    summary_file = output_path / 'earnings_discovery_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"✓ Saved summary to: {summary_file}")
    
    return summary


def main():
    print("="*60)
    print("Project LANTERN - Earnings Report Finder")
    print("="*60)
    
    # Load parameters
    params = load_params()
    print(f"\nParameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    
    # Load IR pages
    input_file = params['input_file']
    print(f"\n📂 Loading IR pages from: {input_file}")
    
    try:
        with open(input_file, 'r') as f:
            ir_data = json.load(f)
        print(f"✓ Loaded {len(ir_data)} companies")
    except FileNotFoundError:
        print(f"❌ File not found: {input_file}")
        print(f"💡 Run find_ir_pages.py first!")
        return
    
    # Process all companies
    print("\n" + "="*60)
    print("Finding Earnings Reports")
    print("="*60)
    
    results = process_all_companies(ir_data, params)
    
    # Save results
    summary = save_results(results, params['output_dir'])
    
    # Print summary
    print("\n" + "="*60)
    print("📊 Summary")
    print("="*60)
    print(f"Total companies: {summary['total_companies']}")
    print(f"✓ Successfully found: {summary['successful']}")
    print(f"❌ Not found: {summary['failed']}")
    print(f"📄 Total reports found: {summary['total_reports_found']}")
    print("="*60)


if __name__ == "__main__":
    main()