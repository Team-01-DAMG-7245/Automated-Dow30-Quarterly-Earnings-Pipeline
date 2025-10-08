# src/scrape_dow30_wikipedia.py

import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import os
import yaml
from datetime import datetime


def load_params():
    """
    Load parameters from params.yaml
    """
    try:
        with open('params.yaml', 'r') as f:
            params = yaml.safe_load(f)
            return params['generate_company_reference']
    except FileNotFoundError:
        # Fallback to defaults if params.yaml doesn't exist
        print("⚠ params.yaml not found, using defaults")
        return {
            'source_url': 'https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average',
            'output_dir': 'data/raw/scraped',
            'backup_enabled': True,
            'date_format': '%Y%m%d',
            'request_timeout': 15,
            'source_name': 'Wikipedia'
        }


def scrape_dow30_from_wikipedia(params):
    """
    Scrape Dow 30 from Wikipedia - most reliable source
    """
    url = params['source_url']
    timeout = params['request_timeout']
    
    print(f"Fetching from {url}...")
    
    try:
        # Add headers to avoid 403 Forbidden
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # First, get the HTML content with proper headers
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        # Then parse with pandas
        tables = pd.read_html(response.content)
        
        # Find the components table
        for i, table in enumerate(tables):
            # Look for table with Symbol and Company columns
            if 'Symbol' in table.columns or 'Ticker' in table.columns:
                print(f"✓ Found components table (table #{i})")
                
                # Clean up the dataframe
                df = table.copy()
                
                # Standardize column names
                column_mapping = {}
                for col in df.columns:
                    col_lower = str(col).lower()
                    if 'symbol' in col_lower or 'ticker' in col_lower:
                        column_mapping[col] = 'ticker'
                    elif 'company' in col_lower:
                        column_mapping[col] = 'company_name'
                    elif 'exchange' in col_lower:
                        column_mapping[col] = 'exchange'
                    elif 'industry' in col_lower or 'sector' in col_lower:
                        column_mapping[col] = 'industry'
                    elif 'date' in col_lower and 'added' in col_lower:
                        column_mapping[col] = 'date_added'
                
                df = df.rename(columns=column_mapping)
                
                # Must have ticker and company name
                if 'ticker' in df.columns and 'company_name' in df.columns:
                    # Clean ticker symbols (remove footnotes)
                    df['ticker'] = df['ticker'].astype(str).str.replace(r'\[.*?\]', '', regex=True).str.strip()
                    df['company_name'] = df['company_name'].astype(str).str.replace(r'\[.*?\]', '', regex=True).str.strip()
                    
                    # Filter out any invalid rows
                    df = df[df['ticker'].str.len() > 0]
                    df = df[df['ticker'] != 'nan']
                    
                    print(f"✓ Successfully extracted {len(df)} companies")
                    return df
        
        print("❌ Could not find components table")
        return None
        
    except Exception as e:
        print(f"❌ Error scraping Wikipedia: {e}")
        return None


def add_company_websites(df, params):
    """
    Add official company websites from known mapping
    """
    # Comprehensive mapping of Dow 30 company websites
    website_mapping = {
        # Technology
        'AAPL': 'https://www.apple.com',
        'MSFT': 'https://www.microsoft.com',
        'IBM': 'https://www.ibm.com',
        'CSCO': 'https://www.cisco.com',
        'INTC': 'https://www.intel.com',
        'CRM': 'https://www.salesforce.com',
        
        # Financial Services
        'JPM': 'https://www.jpmorganchase.com',
        'GS': 'https://www.goldmansachs.com',
        'AXP': 'https://www.americanexpress.com',
        'V': 'https://www.visa.com',
        
        # Healthcare
        'JNJ': 'https://www.jnj.com',
        'UNH': 'https://www.unitedhealthgroup.com',
        'MRK': 'https://www.merck.com',
        'AMGN': 'https://www.amgen.com',
        
        # Consumer
        'WMT': 'https://www.walmart.com',
        'HD': 'https://www.homedepot.com',
        'MCD': 'https://www.mcdonalds.com',
        'DIS': 'https://www.thewaltdisneycompany.com',
        'NKE': 'https://www.nike.com',
        'KO': 'https://www.coca-colacompany.com',
        'PG': 'https://www.pg.com',
        
        # Industrial
        'CAT': 'https://www.caterpillar.com',
        'BA': 'https://www.boeing.com',
        'MMM': 'https://www.3m.com',
        'HON': 'https://www.honeywell.com',
        'DOW': 'https://www.dow.com',
        
        # Energy
        'CVX': 'https://www.chevron.com',
        
        # Telecom
        'VZ': 'https://www.verizon.com',
        
        # Insurance
        'TRV': 'https://www.travelers.com',
        
        # Pharmacy
        'WBA': 'https://www.walgreensbootsalliance.com',
    }
    
    df['company_website'] = df['ticker'].map(website_mapping)
    
    # Add metadata
    df['scraped_date'] = datetime.now().strftime(params['date_format'])
    df['source'] = params['source_name']
    
    # Log missing websites
    missing = df[df['company_website'].isna()]['ticker'].tolist()
    if missing:
        print(f"⚠ Missing websites for: {', '.join(missing)}")
    
    return df


def save_dow30_data(df, params):
    """
    Save data to the configured output directory
    """
    # Create directory structure
    raw_dir = params['output_dir']
    os.makedirs(raw_dir, exist_ok=True)
    
    # Add timestamp to filename for versioning
    timestamp = datetime.now().strftime(params['date_format'])
    
    # Save CSV (main format)
    csv_path = f'{raw_dir}/dow30_companies.csv'
    df.to_csv(csv_path, index=False)
    print(f"✓ Saved CSV: {csv_path}")
    
    # Save versioned backup if enabled
    if params['backup_enabled']:
        csv_versioned = f'{raw_dir}/dow30_companies_{timestamp}.csv'
        df.to_csv(csv_versioned, index=False)
        print(f"✓ Saved versioned CSV: {csv_versioned}")
    
    # Save JSON (full data)
    json_path = f'{raw_dir}/dow30_companies.json'
    df.to_json(json_path, orient='records', indent=2)
    print(f"✓ Saved JSON: {json_path}")
    
    # Save versioned JSON if enabled
    if params['backup_enabled']:
        json_versioned = f'{raw_dir}/dow30_companies_{timestamp}.json'
        df.to_json(json_versioned, orient='records', indent=2)
        print(f"✓ Saved versioned JSON: {json_versioned}")
    
    # Save website mapping (ticker -> website dict)
    dict_path = f'{raw_dir}/dow30_websites.json'
    website_dict = df.set_index('ticker')['company_website'].dropna().to_dict()
    with open(dict_path, 'w') as f:
        json.dump(website_dict, f, indent=2, sort_keys=True)
    print(f"✓ Saved website mapping: {dict_path}")
    
    # Save metadata
    metadata = {
        'total_companies': len(df),
        'companies_with_websites': int(df['company_website'].notna().sum()),
        'companies_without_websites': int(df['company_website'].isna().sum()),
        'scraped_date': datetime.now().isoformat(),
        'source': params['source_name'],
        'source_url': params['source_url'],
        'tickers': sorted(df['ticker'].tolist())
    }
    
    metadata_path = f'{raw_dir}/dow30_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Saved metadata: {metadata_path}")
    
    # Summary
    print(f"\n📊 Summary:")
    print(f"   Total companies: {len(df)}")
    print(f"   With websites: {df['company_website'].notna().sum()}")
    print(f"   Missing websites: {df['company_website'].isna().sum()}")
    print(f"\n📁 Files saved to: {raw_dir}/")
    
    return df


def main():
    print("="*60)
    print("Scraping Dow 30 Components from Wikipedia")
    print("="*60)
    
    # Load parameters
    params = load_params()
    print(f"\nUsing parameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    print()
    
    # Scrape
    df = scrape_dow30_from_wikipedia(params)
    
    if df is not None and len(df) > 0:
        print(f"\n✓ Successfully scraped {len(df)} companies")
        
        # Add websites
        df = add_company_websites(df, params)
        
        # Display sample
        print("\nFirst 5 companies:")
        print(df[['ticker', 'company_name', 'company_website']].head())
        
        # Save data
        save_dow30_data(df, params)
        
        print("\n✅ Complete!")
        
    else:
        print("\n❌ Failed to scrape data")


if __name__ == "__main__":
    main()