"""
AWS S3 Storage Integration for Project LANTERN

This module provides functionality to upload processed results to AWS S3,
organized by company and reporting period.
"""

import os
import json
import boto3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class S3StorageManager:
    """
    Manages AWS S3 operations for Project LANTERN data storage.
    
    Organizes data by company ticker and reporting period:
    s3://bucket/company/AAPL/2024Q3/...
    """
    
    def __init__(self, bucket_name: Optional[str] = None, region: str = 'us-east-1'):
        """
        Initialize S3 storage manager.
        
        Args:
            bucket_name: S3 bucket name (defaults to env var or auto-generated)
            region: AWS region (default: us-east-1)
        """
        self.bucket_name = bucket_name or os.getenv('S3_BUCKET_NAME')
        self.region = region
        
        # Initialize S3 client
        try:
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
            logger.info(f"✅ S3 client initialized for region: {self.region}")
        except NoCredentialsError:
            logger.error("❌ AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize S3 client: {e}")
            raise
    
    def create_bucket_if_not_exists(self) -> str:
        """
        Create S3 bucket if it doesn't exist.
        
        Returns:
            str: Bucket name
        """
        if not self.bucket_name:
            # Generate bucket name if not provided
            timestamp = datetime.now().strftime("%Y%m%d")
            self.bucket_name = f"lantern-dow30-results-{timestamp}"
            logger.info(f"Generated bucket name: {self.bucket_name}")
        
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"✅ Bucket '{self.bucket_name}' already exists")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket doesn't exist, create it
                try:
                    if self.region == 'us-east-1':
                        # us-east-1 doesn't need LocationConstraint
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    logger.info(f"✅ Created bucket: {self.bucket_name}")
                except ClientError as create_error:
                    logger.error(f"❌ Failed to create bucket: {create_error}")
                    raise
            else:
                logger.error(f"❌ Error accessing bucket: {e}")
                raise
        
        return self.bucket_name
    
    def upload_file(self, local_file_path: str, s3_key: str, 
                   content_type: Optional[str] = None, metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Upload a single file to S3.
        
        Args:
            local_file_path: Path to local file
            s3_key: S3 object key (path within bucket)
            content_type: MIME type of the file
            metadata: Additional metadata for the object
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Determine content type if not provided
            if not content_type:
                content_type = self._get_content_type(local_file_path)
            
            # Prepare ExtraArgs for upload_file
            extra_args = {
                'ContentType': content_type
            }
            
            # Add metadata if provided
            if metadata:
                extra_args['Metadata'] = metadata
            
            # Upload file
            self.s3_client.upload_file(local_file_path, self.bucket_name, s3_key, ExtraArgs=extra_args)
            logger.info(f"✅ Uploaded: {local_file_path} → s3://{self.bucket_name}/{s3_key}")
            return True
            
        except FileNotFoundError:
            logger.error(f"❌ File not found: {local_file_path}")
            return False
        except ClientError as e:
            logger.error(f"❌ Failed to upload {local_file_path}: {e}")
            return False
    
    def upload_directory(self, local_dir: str, s3_prefix: str, 
                        recursive: bool = True, file_extensions: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Upload entire directory to S3.
        
        Args:
            local_dir: Local directory path
            s3_prefix: S3 key prefix (e.g., 'company/AAPL/2024Q3/')
            recursive: Whether to upload subdirectories
            file_extensions: List of file extensions to include (None = all)
            
        Returns:
            Dict with upload statistics
        """
        local_path = Path(local_dir)
        if not local_path.exists():
            logger.error(f"❌ Directory not found: {local_dir}")
            return {"success": False, "error": "Directory not found"}
        
        uploaded_files = []
        failed_files = []
        
        # Find all files to upload
        pattern = "**/*" if recursive else "*"
        files_to_upload = list(local_path.glob(pattern))
        files_to_upload = [f for f in files_to_upload if f.is_file()]
        
        # Filter by file extensions if specified
        if file_extensions:
            files_to_upload = [
                f for f in files_to_upload 
                if f.suffix.lower() in [ext.lower() for ext in file_extensions]
            ]
        
        logger.info(f"📤 Uploading {len(files_to_upload)} files from {local_dir}")
        
        for file_path in files_to_upload:
            # Calculate relative path and S3 key
            relative_path = file_path.relative_to(local_path)
            s3_key = f"{s3_prefix.rstrip('/')}/{relative_path}".replace("\\", "/")
            
            # Upload file
            if self.upload_file(str(file_path), s3_key):
                uploaded_files.append(str(relative_path))
            else:
                failed_files.append(str(relative_path))
        
        result = {
            "success": len(failed_files) == 0,
            "uploaded_count": len(uploaded_files),
            "failed_count": len(failed_files),
            "uploaded_files": uploaded_files,
            "failed_files": failed_files
        }
        
        logger.info(f"📊 Upload complete: {len(uploaded_files)} successful, {len(failed_files)} failed")
        return result
    
    def upload_company_results(self, company_ticker: str, reporting_period: str, 
                             data_root: str) -> Dict[str, Any]:
        """
        Upload all results for a specific company and reporting period.
        
        Args:
            company_ticker: Company ticker symbol (e.g., 'AAPL')
            reporting_period: Reporting period (e.g., '2024Q3')
            data_root: Root directory containing processed data
            
        Returns:
            Dict with upload results for each data type
        """
        s3_prefix = f"company/{company_ticker}/{reporting_period}"
        results = {}
        
        # Define data types and their local paths
        data_types = {
            "raw_reports": f"{data_root}/raw/earnings_reports/{company_ticker}",
            "parsed_content": f"{data_root}/processed/parsed_earnings/{company_ticker}",
            "converted_formats": f"{data_root}/parsed/converted"
        }
        
        for data_type, local_path in data_types.items():
            if os.path.exists(local_path):
                logger.info(f"📤 Uploading {data_type} for {company_ticker} {reporting_period}")
                result = self.upload_directory(local_path, f"{s3_prefix}/{data_type}")
                results[data_type] = result
            else:
                logger.warning(f"⚠️ Path not found: {local_path}")
                results[data_type] = {"success": False, "error": "Path not found"}
        
        return results
    
    def upload_pipeline_results(self, data_root: str, run_label: str = None) -> Dict[str, Any]:
        """
        Upload all pipeline results organized by company and period.
        
        Args:
            data_root: Root directory containing all processed data
            run_label: Optional run label for this pipeline execution
            
        Returns:
            Dict with comprehensive upload results
        """
        if not run_label:
            run_label = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        logger.info(f"🚀 Starting S3 upload for run: {run_label}")
        
        # Load company reference data
        companies_file = os.path.join(data_root, "reference", "dow30_companies.json")
        if not os.path.exists(companies_file):
            logger.error(f"❌ Company reference not found: {companies_file}")
            return {"success": False, "error": "Company reference not found"}
        
        with open(companies_file, 'r') as f:
            companies = json.load(f)
        
        # Upload summary and reference data
        summary_results = {}
        reference_files = [
            "reference/dow30_companies.json",
            "reference/dow30_companies.csv",
            "reference/ir_pages.json",
            "urls/earnings_urls.json"
        ]
        
        for ref_file in reference_files:
            local_path = os.path.join(data_root, ref_file)
            if os.path.exists(local_path):
                s3_key = f"reference/{run_label}/{os.path.basename(local_path)}"
                if self.upload_file(local_path, s3_key):
                    summary_results[ref_file] = {"success": True, "s3_key": s3_key}
                else:
                    summary_results[ref_file] = {"success": False}
        
        # Upload company-specific results
        company_results = {}
        parsed_earnings_dir = os.path.join(data_root, "processed", "parsed_earnings")
        
        if os.path.exists(parsed_earnings_dir):
            for company_dir in os.listdir(parsed_earnings_dir):
                if os.path.isdir(os.path.join(parsed_earnings_dir, company_dir)):
                    # Extract reporting period from file timestamps or use current quarter
                    reporting_period = self._extract_reporting_period(
                        os.path.join(parsed_earnings_dir, company_dir)
                    )
                    
                    result = self.upload_company_results(
                        company_dir, reporting_period, data_root
                    )
                    company_results[company_dir] = result
        
        # Create and upload upload summary
        upload_summary = {
            "run_label": run_label,
            "upload_timestamp": datetime.now().isoformat(),
            "bucket_name": self.bucket_name,
            "summary_results": summary_results,
            "company_results": company_results,
            "total_companies": len(company_results)
        }
        
        # Upload summary to S3
        summary_key = f"summary/{run_label}/upload_summary.json"
        self._upload_json_to_s3(upload_summary, summary_key)
        
        logger.info(f"✅ Pipeline upload complete for run: {run_label}")
        return upload_summary
    
    def _get_content_type(self, file_path: str) -> str:
        """Get MIME content type for file."""
        ext = Path(file_path).suffix.lower()
        content_types = {
            '.json': 'application/json',
            '.csv': 'text/csv',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg'
        }
        return content_types.get(ext, 'application/octet-stream')
    
    def _extract_reporting_period(self, company_dir: str) -> str:
        """
        Extract reporting period from company directory.
        This is a simplified implementation - you may want to enhance this.
        """
        # Try to extract from directory structure or file names
        # For now, use current quarter as fallback
        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        return f"{now.year}Q{quarter}"
    
    def _upload_json_to_s3(self, data: Dict[str, Any], s3_key: str) -> bool:
        """Upload JSON data directly to S3."""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(data, indent=2),
                ContentType='application/json'
            )
            logger.info(f"✅ Uploaded JSON: s3://{self.bucket_name}/{s3_key}")
            return True
        except ClientError as e:
            logger.error(f"❌ Failed to upload JSON: {e}")
            return False


def main():
    """Example usage of S3StorageManager."""
    try:
        # Initialize S3 manager
        s3_manager = S3StorageManager()
        
        # Create bucket if needed
        bucket_name = s3_manager.create_bucket_if_not_exists()
        print(f"Using bucket: {bucket_name}")
        
        # Example: Upload pipeline results
        data_root = "data"  # Adjust path as needed
        if os.path.exists(data_root):
            results = s3_manager.upload_pipeline_results(data_root, "test_run")
            print(f"Upload results: {json.dumps(results, indent=2)}")
        else:
            print(f"Data directory not found: {data_root}")
            
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
