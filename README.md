# 🚀 Project LANTERN - Dow 30 Earnings Analysis Pipeline

**Automated extraction, processing, and analysis of quarterly earnings reports from Dow 30 companies using Airflow orchestration.**

## 📋 Overview

Project LANTERN is a comprehensive data pipeline that automatically discovers, downloads, and processes quarterly earnings reports from all Dow 30 companies. The system uses web scraping, AI-powered document parsing, and Apache Airflow orchestration to create a structured dataset of financial information.

## ✨ Features

- **🔍 Automated Discovery**: Finds IR pages and earnings reports for all 30 Dow companies
- **📥 Smart Downloading**: Downloads latest quarterly reports with retry logic
- **🤖 AI-Powered Parsing**: Extracts text, tables, and images using multiple ML models
- **📊 Multi-Format Output**: Converts documents to Markdown, JSON, and plain text
- **🔄 Airflow Orchestration**: Fully automated pipeline with monitoring and error handling
- **📈 Comprehensive Coverage**: Processes 30+ companies with 300+ reports
- **☁️ Cloud Storage**: Optional AWS S3 integration for scalable data storage

| **Team Member** | **Key Contributions**                                                       |
| --------------- | --------------------------------------------------------------------------- |
| **Kundana**     | Dow 30 reference list, IR page identification, AWS S3 setup & documentation |
| **Swara**       | Latest earnings report discovery, Airflow orchestration & S3 integration    |
| **Natnincha**   | Report download & parsing, data validation, IR refinement                   |


## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Wikipedia     │───▶│   IR Discovery  │───▶│ Earnings Search │
│   Scraping      │    │   (24/30 cos)   │    │  (301 reports)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Results &     │◀───│   AI Parsing    │◀───│   Downloads     │
│   Analytics     │    │ (43 files)      │    │  (43 files)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start
Documentation and project reflection Codelabs: https://codelabs-preview.appspot.com/?file_id=1IFZfiqRGc0BlpBJSmeF0G1SxeHYczArDDNNhFX68aD8#0


### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- 8GB+ RAM (for AI models)
- AWS Account (for S3 storage - optional)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd project-lantern-dow30
   ```

2. **Start the services**
   ```bash
   docker-compose up -d
   ```

3. **Access Airflow UI**
   - Open http://localhost:8080
   - Login: `airflow` / `airflow`

4. **Configure AWS S3 (Optional)**
   ```bash
   # Copy the AWS configuration template
   cp aws_config.example .env
   
   # Edit .env and add your AWS credentials
   # AWS_ACCESS_KEY_ID=your_access_key_here
   # AWS_SECRET_ACCESS_KEY=your_secret_key_here
   # S3_BUCKET_NAME=your-bucket-name
   ```

5. **Run the pipeline**
   - Navigate to the `lantern_quarterly_pipeline` DAG
   - Click "Trigger DAG" to start processing
   - To enable S3 upload, set `upload_to_s3: true` in the DAG parameters

### Manual Execution

You can also run the pipeline manually:

```bash
# Step 1: Generate company data
python src/scrape_dow30_wikipedia.py

# Step 2: Find IR pages  
python src/find_ir_pages.py

# Step 3: Find earnings reports
python src/find_earnings_reports.py

# Step 4: Download reports
python src/download_reports.py

# Step 5: Parse reports
python src/parse_reports.py
```

## 📊 Pipeline Results

### Coverage Statistics
- **Companies Processed**: 30 (100% of Dow 30)
- **IR Pages Found**: 24/30 companies (80% success rate)
- **Earnings Reports**: 301 total reports discovered
- **Downloads Successful**: 43 files downloaded
- **Parsing Complete**: Full text, table, and image extraction

### Output Structure
```
data/
├── raw/
│   ├── scraped/           # Company reference data
│   └── earnings_reports/  # Downloaded PDF files
├── processed/
│   ├── ir_pages/          # Discovered IR URLs
│   ├── earnings_reports/  # Earnings report links
│   └── parsed_earnings/   # Parsed content by company
└── parsed/
    └── converted/         # Multi-format outputs
        ├── markdown/      # Human-readable format
        ├── json/          # Structured data
        └── txt/           # Plain text
```

## 🛠️ Technical Stack

### Core Technologies
- **Apache Airflow**: Workflow orchestration
- **Python 3.11**: Primary language
- **Docker**: Containerization
- **PostgreSQL**: Airflow metadata

### AI/ML Libraries
- **PyMuPDF**: PDF processing
- **pdfplumber**: Text extraction
- **camelot-py**: Table extraction
- **pytesseract**: OCR processing
- **layoutparser**: Document layout analysis
- **torch**: Deep learning models

### Data Processing
- **pandas**: Data manipulation
- **requests**: Web scraping
- **BeautifulSoup**: HTML parsing
- **tldextract**: Domain processing

## 📁 Project Structure

```
project-lantern-dow30/
├── dags/                          # Airflow DAG definitions
│   └── lantern_quarterly_pipeline.py
├── src/                          # Core scripts
│   ├── scrape_dow30_wikipedia.py # Company data scraping
│   ├── find_ir_pages.py          # IR page discovery
│   ├── find_earnings_reports.py  # Earnings report search
│   ├── download_reports.py       # Report downloading
│   ├── parse_reports.py          # AI-powered parsing
│   └── [processing modules]
├── data/                         # Data storage
│   ├── raw/                      # Raw downloads
│   ├── processed/                # Processed data
│   └── parsed/                   # Final outputs
├── reports/                      # Analysis reports
├── docker-compose.yml            # Service orchestration
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## 🔧 Configuration

### Airflow Variables
Set these in Airflow UI → Admin → Variables:

- `lantern_project_root`: `/opt/airflow` (Docker) or your local path
- `lantern_python_bin`: `python`
- `lantern_data_root`: `${PROJECT_ROOT}/data`

### Environment Variables
```bash
AIRFLOW_UID=50000
AIRFLOW_GID=0
```

### AWS S3 Configuration

The pipeline supports optional cloud storage using AWS S3. Data is organized by company and reporting period:

```
s3://your-bucket/
├── company/
│   ├── AAPL/
│   │   ├── 2024Q3/
│   │   │   ├── raw_reports/          # Original PDF files
│   │   │   ├── parsed_content/       # Extracted text, tables, images
│   │   │   └── converted_formats/    # JSON, Markdown, TXT
│   │   └── 2024Q4/...
│   └── MSFT/...
├── reference/                        # Company metadata and URLs
│   └── run_20250109_143022/
│       ├── dow30_companies.json
│       └── earnings_urls.json
└── summary/                          # Upload summaries
    └── run_20250109_143022/
        └── upload_summary.json
```

#### Setup Steps:

1. **Create AWS Account** (if you don't have one)
2. **Create IAM User** with S3 permissions:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:CreateBucket",
           "s3:PutObject",
           "s3:GetObject",
           "s3:ListBucket"
         ],
         "Resource": "*"
       }
     ]
   }
   ```
3. **Configure Credentials**:
   ```bash
   # Copy template and edit
   cp aws_config.example .env
   
   # Add your credentials
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=...
   S3_BUCKET_NAME=your-unique-bucket-name
   ```
4. **Enable S3 Upload** in Airflow:
   - Trigger DAG with config: `{"upload_to_s3": true}`
   - Or set in DAG parameters when triggering

## 📈 Pipeline Stages

### Stage 1: Company Discovery
- Scrapes Dow 30 components from Wikipedia
- Extracts company names, tickers, and websites
- **Output**: 30 companies with 27 having websites

### Stage 2: IR Page Discovery  
- Searches company websites for investor relations pages
- Uses pattern matching and homepage link analysis
- Falls back to SEC EDGAR when needed
- **Output**: 24/30 companies with IR pages found

### Stage 3: Earnings Report Search
- Crawls IR pages for quarterly earnings reports
- Identifies latest reports using scoring algorithms
- **Output**: 301 potential reports from 17 companies

### Stage 4: Report Download
- Downloads PDF files with retry logic
- Handles various URL formats and redirects
- **Output**: 43 successfully downloaded files

### Stage 5: AI-Powered Parsing
- **Text Extraction**: pdfplumber + OCR fallback
- **Table Extraction**: Hybrid lattice/stream detection
- **Image Extraction**: PyMuPDF + layout analysis
- **Format Conversion**: Markdown, JSON, plain text
- **Output**: Multi-format structured data

### Logs and Monitoring

- **Airflow UI**: http://localhost:8080
- **Task Logs**: Available in Airflow UI under each task
- **Container Logs**: `docker-compose logs <service>`

## 👥 Team Contributions

| Team Member | Tasks Completed |
|-------------|-----------------|
| **Natnicha** | • Dow 30 company discovery and website identification<br>• Company reference database creation<br>• IR page detection algorithms<br>• Document parsing and content extraction |
| **Swara** | • Earnings report discovery and scoring<br>• Automated download pipeline development<br>• Airflow workflow orchestration<br>• AWS S3 cloud storage integration |
| **Kundana** | • IR page identification systems<br>• Documentation and project reflection |

