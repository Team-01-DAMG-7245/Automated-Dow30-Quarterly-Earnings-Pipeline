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

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- 8GB+ RAM (for AI models)

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

4. **Run the pipeline**
   - Navigate to the `lantern_quarterly_pipeline` DAG
   - Click "Trigger DAG" to start processing

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

