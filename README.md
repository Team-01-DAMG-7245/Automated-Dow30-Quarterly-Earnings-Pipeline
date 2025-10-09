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

- Docker Desktop installed and running
- Python 3.11+
- 8GB+ RAM (for AI models)
- 5GB+ free disk space (for Docker images)

### Installation

1. **Clone and navigate**
   ```bash
   git clone <repository-url>
   cd project-lantern-dow30
   ```

2. **Start Docker Desktop** - Wait for whale icon in menu bar

3. **Start services** (first time: 5-15 minutes)
   ```bash
   docker compose up -d
   ```

4. **Monitor initialization**
   ```bash
   docker compose logs -f airflow-init
   docker compose ps
   ```

5. **Access Airflow UI**
   - Open http://localhost:8080
   - Login: `airflow` / `airflow`

6. **Configure Variables** (Admin → Variables)
   - `lantern_project_root` → `/opt/airflow`
   - `lantern_python_bin` → `python`
   - `lantern_data_root` → `/opt/airflow/data`

7. **Run Pipeline**
   - Find `lantern_quarterly_pipeline` DAG
   - Toggle ON
   - Click "Trigger DAG"

## 🐳 Docker Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# Check status
docker compose ps

# Restart
docker compose restart

# Complete reset
docker compose down -v
```

## 📊 Pipeline Results

### Coverage
- **Companies**: 30/30 (100%)
- **IR Pages**: 24/30 (80%)
- **Reports Found**: 301
- **Downloads**: 43 files
- **Parsing**: Complete

### Output Structure
```
data/
├── raw/
│   ├── scraped/           # Company reference
│   └── earnings_reports/  # PDFs
├── processed/
│   ├── ir_pages/          # IR URLs
│   ├── earnings_reports/  # Report links
│   └── parsed_earnings/   # Parsed content
└── parsed/
    └── converted/
        ├── markdown/      # Human-readable
        ├── json/          # Structured
        └── txt/           # Plain text
```

## 🛠️ Technical Stack

### Core
- Apache Airflow 2.7.3
- Python 3.11
- Docker & PostgreSQL 13

### AI/ML
- PyMuPDF, pdfplumber, camelot-py
- pytesseract, layoutparser
- torch

### Data
- pandas, numpy
- requests, BeautifulSoup
- tldextract

## 📁 Project Structure

```
project-lantern-dow30/
├── dags/                          # Airflow DAGs
├── src/                           # Core scripts
├── data/                          # Data storage
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 📈 Pipeline Stages

1. **Company Discovery** - Scrape Dow 30 from Wikipedia (30 companies)
2. **IR Page Discovery** - Find investor relations pages (24/30 found)
3. **Earnings Search** - Locate quarterly reports (301 reports)
4. **Download** - Retrieve PDF files (43 downloaded)
5. **AI Parsing** - Extract text, tables, images (multi-format output)

## 🔍 Monitoring

### Airflow UI
- Dashboard: http://localhost:8080
- DAG/Graph views for task monitoring
- Detailed task logs

### Container Logs
```bash
docker compose logs -f airflow-scheduler
docker compose logs -f airflow-webserver
```

## 🔄 Development

### Making Changes
- Edit locally in `src/` and `dags/`
- Changes auto-sync to containers
- Restart if needed: `docker compose restart`

### Adding Dependencies
```bash
# Add to requirements.txt
echo "package-name>=1.0.0" >> requirements.txt
docker compose down
docker compose up -d --build
```

### Manual Execution
```bash
python src/scrape_dow30_wikipedia.py
python src/find_ir_pages.py
python src/find_earnings_reports.py
python src/download_reports.py
python src/parse_reports.py
```
