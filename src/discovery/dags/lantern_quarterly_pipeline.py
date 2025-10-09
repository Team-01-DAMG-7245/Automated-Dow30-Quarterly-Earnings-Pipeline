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
PROJECT_ROOT = Variable.get("lantern_project_root", default_var=os.environ.get("PROJECT_ROOT", "/Users/nithishsankar/project-lantern-dow30"))
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
    "sla": timedelta(hours=2),   # basic monitoring via SLAs
}

# ===========================
# DAG: Quarterly (and manual)
# ===========================
# Cron runs at 03:15 on the 2nd day of Jan/Apr/Jul/Oct (adjust as you like).
with DAG(
    dag_id="lantern_quarterly_pipeline",
    description="Project LANTERN: Orchestrate IR discovery → earnings URLs → downloads",
    start_date=datetime(2025, 1, 1),
    schedule="15 3 2 1,4,7,10 *",    # quarterly
    catchup=False,
    default_args=default_args,
    max_active_runs=1,
    tags=["lantern", "earnings", "dow30"],
    params={
        # Manual trigger parameters (Airflow UI → Trigger DAG → "Config"):
        # Overwrite default quarter/run_label if you want to re-run specific quarter
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
            {PYTHON_BIN} src/scrape_dow30_wikipedia.py \
              --out-csv "{REF_COMPANIES}" \
              --out-json "{DATA_ROOT}/reference/dow30_companies.json"
            test -s "{REF_COMPANIES}" || (echo "Missing {REF_COMPANIES}" && exit 2)
        """,
    )

    # -----------
    # Task 2: Discover IR pages (Step 3)
    # -----------
    discover_ir_pages = BashOperator(
        task_id="discover_ir_pages",
        bash_command=f"""
            set -euo pipefail
            cd "{PROJECT_ROOT}"
            {PYTHON_BIN} src/ir/discover_ir_pages.py \
              --companies "{REF_COMPANIES}" \
              --out "{IR_PAGES}"
            test -s "{IR_PAGES}" || (echo "Missing {IR_PAGES}" && exit 2)
        """,
    )

    # -----------
    # Task 3: Locate earnings report URLs (Step 4)
    # -----------
    locate_earnings_reports = BashOperator(
        task_id="locate_earnings_reports",
        bash_command=f"""
            set -euo pipefail
            cd "{PROJECT_ROOT}"
            {PYTHON_BIN} src/earnings/earnings_locator.py \
              --ir-pages "{IR_PAGES}" \
              --out "{EARN_URLS}"
            test -s "{EARN_URLS}" || (echo "Missing {EARN_URLS}" && exit 2)
        """,
    )

    # -----------
    # Task 3.5: Parse URLs file → list for mapping
    #           (Supports JSON or CSV; adjust loader as needed.)
    # -----------
    @task
    def load_earnings_targets() -> List[Dict[str, Any]]:
        """
        Returns a list like:
        [{"ticker":"AAPL","urls": ["...pdf","...html"], "quarter":"2025Q4"}, ...]
        """
        import csv, json, os
        targets: List[Dict[str, Any]] = []

        if EARN_URLS.endswith(".json"):
            with open(EARN_URLS, "r") as f:
                data = json.load(f)
            # Expect either list[dict] or dict[ticker]=...
            if isinstance(data, dict):
                for ticker, payload in data.items():
                    urls = payload.get("urls", []) if isinstance(payload, dict) else []
                    quarter = payload.get("quarter", "auto") if isinstance(payload, dict) else "auto"
                    targets.append({"ticker": ticker, "urls": urls, "quarter": quarter})
            elif isinstance(data, list):
                for row in data:
                    ticker = row.get("ticker")
                    urls = row.get("urls", [])
                    quarter = row.get("quarter", "auto")
                    if ticker and urls:
                        targets.append({"ticker": ticker, "urls": urls, "quarter": quarter})
        else:
            # CSV fallback: columns = ticker, url, quarter
            with open(EARN_URLS, newline="") as f:
                reader = csv.DictReader(f)
                by_ticker = {}
                for r in reader:
                    t = r.get("ticker")
                    u = r.get("url")
                    q = r.get("quarter", "auto")
                    if t and u:
                        by_ticker.setdefault(t, {"ticker": t, "urls": [], "quarter": q})
                        by_ticker[t]["urls"].append(u)
                targets = list(by_ticker.values())

        print(f"Prepared {len(targets)} company targets for downloads")
        return targets

    # -----------
    # Conditional branch: if no targets or params.download_assets == False → skip downloads
    # -----------
    def branch_on_targets(**context):
        params = context["params"]
        do_downloads = bool(params.get("download_assets", True))
        ti = context["ti"]
        targets: List[Dict[str, Any]] = ti.xcom_pull(task_ids="load_earnings_targets", default=[])
        if not do_downloads or not targets:
            return "skip_downloads"
        return "download_each_company.expand"  # fan-out

    branch = BranchPythonOperator(
        task_id="branch_on_targets",
        python_callable=branch_on_targets,
        provide_context=True,
    )

    # -----------
    # Parallel downloads (dynamic task mapping)
    # -----------
    @task(max_active_tis_per_dag=20, retries=2, retry_delay=timedelta(minutes=3))
    def download_company_artifacts(target: Dict[str, Any], run_label: str = "auto") -> Dict[str, Any]:
        """
        Download PDFs/HTML for a single company.
        Swap the inner logic to call your repo script if preferred.
        """
        import os, pathlib, requests, time

        ticker = target["ticker"]
        urls   = target.get("urls", [])
        quarter = target.get("quarter", run_label) or run_label

        out_dir = os.path.join(DATA_ROOT, "raw", "earnings", ticker, quarter)
        pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)

        downloaded = []
        for i, url in enumerate(urls):
            try:
                r = requests.get(url, timeout=45)
                r.raise_for_status()
                # Heuristic file extension
                ext = ".pdf" if "pdf" in url.lower() else ".html"
                fname = f"{ticker}_{quarter}_{i}{ext}"
                fpath = os.path.join(out_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(r.content)
                downloaded.append(fpath)
            except Exception as e:
                print(f"[{ticker}] Failed {url}: {e}")
                # let retry handle transient failures
                raise

            # basic pacing to be polite
            time.sleep(0.5)

        print(f"[{ticker}] downloaded {len(downloaded)} files → {out_dir}")
        return {"ticker": ticker, "quarter": quarter, "count": len(downloaded), "out_dir": out_dir}

    # This creates the *mapped* task group at runtime
    download_each_company = download_company_artifacts.expand(target=load_earnings_targets(), run_label="{{ params.run_label }}")

    skip_downloads = BashOperator(
        task_id="skip_downloads",
        bash_command='echo "No targets or download disabled. Skipping downloads."',
    )

    # -----------
    # Post-validate (runs whether we downloaded or skipped)
    # -----------
    @task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
    def summarize_results(results: List[Dict[str, Any]] | None = None):
        total = 0
        if results:
            for r in results:
                total += int(r.get("count", 0))
        print(f"[SUMMARY] Total downloaded files: {total}")
        # You could push metrics to a store, or raise if total == 0, etc.
        return {"downloaded_total": total}

    # -----------
    # Error notification if anything failed in the mapped downloads
    # -----------
    notify_if_failed = PythonOperator(
        task_id="notify_if_failed",
        python_callable=lambda: print("[POST] One or more tasks failed (handled by trigger rule)."),
        trigger_rule=TriggerRule.ONE_FAILED,   # runs only if something failed upstream
    )

    # ============
    # Dependencies
    # ============
    cfg = show_config()
    cfg >> build_company_reference >> discover_ir_pages >> locate_earnings_reports

    # Branching
    next_step = load_earnings_targets()
    locate_earnings_reports >> next_step >> branch
    branch >> download_each_company >> summarize_results(download_each_company)  # map results to summarize
    branch >> skip_downloads >> summarize_results(None)

    # Failure notifier watches the whole download fan-out
    download_each_company >> notify_if_failed
