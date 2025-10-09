from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from typing import Dict, Any, Optional

import guidance as gd
from pydantic import BaseModel, Field

class EarningsSchema(BaseModel):
    company: str
    ticker: Optional[str] = None
    fiscal_period: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    revenue: Optional[str] = None
    eps_basic: Optional[str] = None
    eps_diluted: Optional[str] = None
    guidance_summary: Optional[str] = None
    call_datetime_utc: Optional[str] = None
    source_path: str

def _cache_path(out_dir: Path, text_sample: str, template_id: str) -> Path:
    h = hashlib.sha256((template_id + text_sample).encode("utf-8")).hexdigest()[:16]
    return out_dir / f"parsed_{template_id}_{h}.json"

def build_program(model: Optional[str] = None):
    llm = gd.llms.OpenAI(model=model or os.getenv("OPENAI_MODEL", "gpt-4.1"))
    prog = gd("""\
{{#system}}
Extract earnings facts from the provided text. Output exactly one JSON object and nothing else.
If a field is unknown, set it to null. Preserve original units (e.g., "$24.3B").
{{/system}}

{{#user}}
Text:
{{text_sample}}
              
Emit JSON with keys:
["company","ticker","fiscal_period","period_start","period_end","revenue",
 "eps_basic","eps_diluted","guidance_summary","call_datetime_utc","source_path"]
{{/user}}
""", llm=llm)
    return prog

def extract_earnings(text: str, source_path: str, model: Optional[str] = None) -> EarningsSchema:
    prog = build_program(model)
    out = prog(text=text).text().strip()
    # Harden: keep only the JSON object
    s, e = out.find("{"), out.rfind("}")
    if s == -1 or e == -1:
        raise ValueError("Model did not return JSON.")
    data = json.loads(out[s:e+1])
    data["source_path"] = source_path
    return EarningsSchema(**data)

def extract_with_cache(text: str, source_path: str, out_dir: Path, model: Optional[str] = None) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cp = _cache_path(out_dir, text[:2000], "earnings_v1")
    if cp.exists():
        return json.loads(cp.read_text())
    rec = extract_earnings(text, source_path, model=model)
    cp.write_text(rec.model_dump_json())
    return rec.model_dump()

              