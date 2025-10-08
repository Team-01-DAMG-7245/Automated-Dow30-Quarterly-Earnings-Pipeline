# src/sec_edgar.py
# SEC EDGAR API utilities for earnings data

import requests
import json
import time
from datetime import datetime, timedelta
from pathlib import Path


class SECEdgar:
    """
    Interface to SEC EDGAR database
    """
    
    BASE_URL = "https://data.sec.gov"
    
    def __init__(self, user_agent="FinTrustAnalytics project-lantern contact@example.com"):
        """
        Initialize SEC EDGAR client
        
        Note: SEC requires a user agent with contact info
        """
        self.headers = {
            'User-Agent': user_agent,
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'data.sec.gov'
        }
        self.rate_limit = 0.1  # SEC allows 10 requests per second
    
    def get_cik_from_ticker(self, ticker):
        """
        Get CIK (Central Index Key) from ticker symbol
        """
        # SEC maintains a ticker -> CIK mapping
        url = f"{self.BASE_URL}/files/company_tickers.json"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            companies = response.json()
            
            # Search for ticker
            for key, company in companies.items():
                if company['ticker'] == ticker:
                    cik = str(company['cik_str']).zfill(10)  # Pad to 10 digits
                    return cik
            
            return None
            
        except Exception as e:
            print(f"Error getting CIK for {ticker}: {e}")
            return None
    
    def get_company_filings(self, cik, form_type='8-K', count=100):
        """
        Get recent filings for a company
        
        Args:
            cik: Company CIK number
            form_type: Type of filing (8-K for earnings, 10-Q for quarterly, 10-K for annual)
            count: Number of filings to retrieve
        """
        url = f"{self.BASE_URL}/submissions/CIK{cik}.json"
        
        try:
            time.sleep(self.rate_limit)
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Get recent filings
            filings = data.get('filings', {}).get('recent', {})
            
            # Filter by form type
            filtered_filings = []
            for i in range(len(filings.get('form', []))):
                if filings['form'][i] == form_type:
                    filing = {
                        'accessionNumber': filings['accessionNumber'][i],
                        'filingDate': filings['filingDate'][i],
                        'reportDate': filings['reportDate'][i],
                        'form': filings['form'][i],
                        'primaryDocument': filings['primaryDocument'][i],
                        'primaryDocDescription': filings.get('primaryDocDescription', [''])[i]
                    }
                    filtered_filings.append(filing)
                    
                    if len(filtered_filings) >= count:
                        break
            
            return filtered_filings
            
        except Exception as e:
            print(f"Error getting filings for CIK {cik}: {e}")
            return []
    
    def get_filing_url(self, cik, accession_number, document):
        """
        Construct URL to filing document
        """
        # Remove dashes from accession number
        accession_clean = accession_number.replace('-', '')
        
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{document}"
        return url
    
    def is_earnings_filing(self, filing):
        """
        Check if an 8-K filing is likely an earnings announcement
        
        8-K Item 2.02 is "Results of Operations and Financial Condition"
        """
        desc = filing.get('primaryDocDescription', '').lower()
        
        earnings_keywords = [
            'results of operations',
            'financial condition',
            'earnings',
            'quarterly results',
            'item 2.02',
        ]
        
        return any(keyword in desc for keyword in earnings_keywords)
    
    def download_filing(self, url, output_path):
        """
        Download a filing document
        """
        try:
            time.sleep(self.rate_limit)
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Save to file
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            return True
            
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return False