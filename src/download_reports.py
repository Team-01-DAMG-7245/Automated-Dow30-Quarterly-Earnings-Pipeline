# src/download_reports.py
# Project LANTERN - Report Downloader

import requests
import json
import yaml
from pathlib import Path
from datetime import datetime
import time
from urllib.parse import urlparse
import hashlib


def load_params():
    """Load parameters from params.yaml"""
    try:
        with open('params.yaml', 'r') as f:
            params = yaml.safe_load(f)
            return params.get('download_reports', {})
    except FileNotFoundError:
        print("⚠ params.yaml not found, using defaults")
        return {
            'input_file': 'data/processed/earnings_reports/earnings_reports_links.json',
            'output_dir': 'data/raw/earnings_reports',
            'max_reports_per_company': 3,
            'timeout': 30,
            'rate_limit': 2,
            'max_retries': 3
        }


def get_headers():
    """Return browser-like headers"""
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
    }


def sanitize_filename(filename):
    """Remove invalid characters from filename"""
    import re
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename


def download_file(url, output_path, timeout=30, max_retries=3):
    """
    Download a file with retry logic
    """
    for attempt in range(max_retries):
        try:
            print(f"      Downloading: {url}")
            response = requests.get(url, headers=get_headers(), timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Save file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = output_path.stat().st_size / (1024 * 1024)  # MB
            print(f"      ✓ Downloaded: {output_path.name} ({file_size:.2f} MB)")
            return True
            
        except Exception as e:
            print(f"      ❌ Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                print(f"      ❌ Failed after {max_retries} attempts")
                return False
    
    return False


def download_reports_for_company(ticker, company_data, params):
    """
    Download earnings reports for a single company
    """
    company_name = company_data.get('company_name', ticker)
    reports = company_data.get('reports', [])
    
    print(f"  📥 Processing {len(reports)} reports...")
    
    if not reports:
        print(f"  ⚠ No reports to download")
        return {
            'ticker': ticker,
            'company_name': company_name,
            'downloaded': 0,
            'failed': 0,
            'files': [],
            'success': False
        }
    
    # Create company directory
    company_dir = Path(params['output_dir']) / ticker
    company_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded_files = []
    failed_count = 0
    
    # Limit number of reports
    reports_to_download = reports[:params['max_reports_per_company']]
    
    for i, report in enumerate(reports_to_download, 1):
        url = report.get('url')
        
        if not url:
            print(f"    [{i}/{len(reports_to_download)}] ⚠ No URL provided")
            failed_count += 1
            continue
        
        print(f"    [{i}/{len(reports_to_download)}]")
        
        # Generate filename
        # Try to get a meaningful name from URL or report text
        parsed_url = urlparse(url)
        url_filename = Path(parsed_url.path).name
        
        if url_filename and url_filename.lower().endswith('.pdf'):
            filename = sanitize_filename(url_filename)
        else:
            # Generate filename from report text or hash
            report_text = report.get('text', '')[:50]
            if report_text:
                filename = sanitize_filename(report_text) + '.pdf'
            else:
                # Use hash of URL as filename
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                filename = f"report_{i}_{url_hash}.pdf"
        
        output_path = company_dir / filename
        
        # Skip if already downloaded
        if output_path.exists():
            print(f"      ✓ Already exists: {filename}")
            downloaded_files.append(str(output_path))
            continue
        
        # Download
        success = download_file(
            url=url,
            output_path=output_path,
            timeout=params['timeout'],
            max_retries=params['max_retries']
        )
        
        if success:
            downloaded_files.append(str(output_path))
        else:
            failed_count += 1
        
        # Rate limiting
        time.sleep(params['rate_limit'])
    
    return {
        'ticker': ticker,
        'company_name': company_name,
        'downloaded': len(downloaded_files),
        'failed': failed_count,
        'files': downloaded_files,
        'success': len(downloaded_files) > 0
    }


def process_all_companies(earnings_data, params):
    """
    Download reports for all companies
    """
    results = []
    
    # Filter for companies with reports
    companies_with_reports = [c for c in earnings_data if c.get('success', False) and c.get('reports')]
    
    print(f"\n📊 {len(companies_with_reports)} companies have reports to download")
    
    for idx, company in enumerate(companies_with_reports, 1):
        ticker = company['ticker']
        company_name = company.get('company_name', ticker)
        
        print(f"\n[{idx}/{len(companies_with_reports)}] {ticker} - {company_name}")
        
        result = download_reports_for_company(ticker, company, params)
        result['download_date'] = datetime.now().isoformat()
        
        results.append(result)
    
    return results


def save_results(results, output_dir):
    """Save download results"""
    output_path = Path(output_dir)
    
    # Save download log
    log_file = output_path / 'download_log.json'
    with open(log_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Saved download log to: {log_file}")
    
    # Save summary
    summary = {
        'download_date': datetime.now().isoformat(),
        'total_companies': len(results),
        'successful_companies': sum(1 for r in results if r['success']),
        'failed_companies': sum(1 for r in results if not r['success']),
        'total_files_downloaded': sum(r['downloaded'] for r in results),
        'total_files_failed': sum(r['failed'] for r in results)
    }
    
    summary_file = output_path / 'download_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"✓ Saved summary to: {summary_file}")
    
    return summary


def main():
    print("="*60)
    print("Project LANTERN - Earnings Report Downloader")
    print("="*60)
    
    # Load parameters
    params = load_params()
    print(f"\nParameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    
    # Load earnings report links
    input_file = params['input_file']
    print(f"\n📂 Loading earnings report links from: {input_file}")
    
    try:
        with open(input_file, 'r') as f:
            earnings_data = json.load(f)
        print(f"✓ Loaded {len(earnings_data)} companies")
    except FileNotFoundError:
        print(f"❌ File not found: {input_file}")
        print(f"💡 Run find_earnings_reports.py first!")
        return
    
    # Download reports
    print("\n" + "="*60)
    print("Downloading Earnings Reports")
    print("="*60)
    
    results = process_all_companies(earnings_data, params)
    
    # Save results
    summary = save_results(results, params['output_dir'])
    
    # Print summary
    print("\n" + "="*60)
    print("📊 Download Summary")
    print("="*60)
    print(f"Total companies processed: {summary['total_companies']}")
    print(f"✓ Successful: {summary['successful_companies']}")
    print(f"❌ Failed: {summary['failed_companies']}")
    print(f"📄 Files downloaded: {summary['total_files_downloaded']}")
    print(f"❌ Files failed: {summary['total_files_failed']}")
    print(f"\n📁 Reports saved to: {params['output_dir']}")
    print("="*60)


if __name__ == "__main__":
    main()