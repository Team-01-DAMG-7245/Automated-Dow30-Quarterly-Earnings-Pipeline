from __future__ import annotations
from datetime import datetime, timedelta
import json
import os
from typing import List, Dict, Any

from airflow import DAG
from airflow.decorators import task
from airflow.models import Variable
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.utils.trigger_rule import TriggerRule


# ============
# Config/Paths
# ============

# Airflow Variables (set these in UI → Admin → Variables) with sane defaults:
PROJECT_ROOT = Variable.get("lantern_project_root", default_var=os.environ.get("PROJECT_ROOT", "/opt/airflow"))
PYTHON_BIN   = Variable.get("lantern_python_bin",   default_var=os.environ.get("PYTHON_BIN",   "python"))  # relies on your venv PATH
DATA_ROOT    = Variable.get("lantern_data_root",    default_var=os.path.join(PROJECT_ROOT, "data"))

# Output artifacts we expect:
REF_COMPANIES = os.path.join(DATA_ROOT, "reference", "dow30_companies.csv")
IR_PAGES      = os.path.join(DATA_ROOT, "reference", "ir_pages.csv")
EARN_URLS     = os.path.join(DATA_ROOT, "urls", "earnings_urls.json")  # change to .csv if your script emits CSV


# ============
# Callbacks & Defaults
# ============

def notify_failure(context):
    """
    Minimal on-failure callback.
    Replace print() with Slack/Webhook/etc if desired.
    """
    dag_id     = context.get("dag_run").dag_id if context.get("dag_run") else "unknown_dag"
    task_id    = context.get("task_instance").task_id
    run_id     = context.get("dag_run").run_id if context.get("dag_run") else "manual__unknown"
    exception  = context.get("exception")
    print(f"[ALERT] Airflow failure :: DAG={dag_id} Task={task_id} Run={run_id} :: {exception}")

default_args = {
    "owner": "lantern",
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "on_failure_callback": notify_failure,
    # sla removed - not compatible with mapped tasks
}

# ===========================
# DAG: Quarterly (and manual)
# ===========================
# Cron runs at 03:15 on the 2nd day of Jan/Apr/Jul/Oct (adjust as you like).
with DAG(
    dag_id="lantern_quarterly_pipeline",
    description="LANTERN Quarterly Pipeline - Manual Tested Workflow",
    start_date=datetime(2025, 1, 1),
    schedule=None,  # Manual trigger only
    catchup=False,
    default_args=default_args,
    max_active_runs=1,
    tags=["lantern", "earnings", "dow30"],
    params={
        # Manual trigger parameters (Airflow UI → Trigger DAG → "Config"):
        "run_label": "auto",       # e.g., "2025Q3", "backfill-2024Q4"
        "download_assets": True,   # set False for a "dry run" that stops after URL discovery
    },
) as dag:

    # -----------
    # Task 0: Echo config (helps debugging params/paths)
    # -----------
    @task
    def show_config(params: Dict[str, Any] = None):
        cfg = {
            "PROJECT_ROOT": PROJECT_ROOT,
            "PYTHON_BIN": PYTHON_BIN,
            "DATA_ROOT": DATA_ROOT,
            "REF_COMPANIES": REF_COMPANIES,
            "IR_PAGES": IR_PAGES,
            "EARN_URLS": EARN_URLS,
            "params": params or {},
        }
        print(json.dumps(cfg, indent=2))
        return cfg

    # -----------
    # Task 1: Build company reference (Step 2 in your outline)
    # -----------
    build_company_reference = BashOperator(
        task_id="build_company_reference",
        bash_command=f"""
            set -euo pipefail
            cd "{PROJECT_ROOT}"
            {PYTHON_BIN} src/scrape_dow30_wikipedia.py
            test -s "{REF_COMPANIES}" || (echo "Missing {REF_COMPANIES}" && exit 2)
        """,
    )

    # -----------
    # Task 2: Find IR pages (Step 3) - using find_ir_pages.py
    # -----------
    discover_ir_pages = BashOperator(
        task_id="discover_ir_pages",
        bash_command=f"""
            set -euo pipefail
            cd "{PROJECT_ROOT}"
            {PYTHON_BIN} src/find_ir_pages.py
            test -s "data/processed/ir_pages/ir_pages.json" || (echo "Missing IR pages output" && exit 2)
        """,
        execution_timeout=timedelta(minutes=10),
    )

    # -----------
    # Task 3: Find earnings reports (Step 4) - using find_earnings_reports.py
    # -----------
    locate_earnings_reports = BashOperator(
        task_id="locate_earnings_reports",
        bash_command=f"""
            set -euo pipefail
            cd "{PROJECT_ROOT}"
            {PYTHON_BIN} src/find_earnings_reports.py
            test -s "data/processed/earnings_reports/earnings_reports_links.json" || (echo "Missing earnings reports output" && exit 2)
        """,
        execution_timeout=timedelta(minutes=10),
    )


    # -----------
    # Task 4: Download reports - using download_reports.py
    # -----------
    download_company_artifacts = BashOperator(
        task_id="download_company_artifacts",
        bash_command=f"""
            set -euo pipefail
            cd "{PROJECT_ROOT}"
            {PYTHON_BIN} src/download_reports.py
            test -d "data/raw/earnings_reports" || (echo "Missing download output directory" && exit 2)
        """,
        execution_timeout=timedelta(minutes=15),
    )


    # -----------
    # Task 5: Parse reports - using parse_reports.py
    # -----------
    parse_reports = BashOperator(
        task_id="parse_reports",
        bash_command=f"""
            set -euo pipefail
            cd "{PROJECT_ROOT}"
            {PYTHON_BIN} src/parse_reports.py
            echo "✅ Parsing complete"
        """,
        execution_timeout=timedelta(minutes=20),
    )

    # -----------
    # Summary task
    # -----------
    @task
    def summarize_results():
        print("🎯 LANTERN Quarterly Pipeline Complete!")
        print("📊 Results available in data/ directory")
        print("✅ Generated company reference data")
        print("✅ Found IR pages")  
        print("✅ Found earnings reports")
        print("✅ Downloaded reports")
        print("✅ Parsed reports")
        return {"status": "completed"}

    # ============
    # Dependencies - Linear flow matching manual commands
    # ============
    cfg = show_config()
    cfg >> build_company_reference >> discover_ir_pages >> locate_earnings_reports >> download_company_artifacts >> parse_reports >> summarize_results()
