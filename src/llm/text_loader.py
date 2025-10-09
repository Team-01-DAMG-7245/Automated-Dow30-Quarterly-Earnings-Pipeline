from pathlib import Path
from typing import Tuple
from pdfminer.high_level import extract_text

def load_text(path: Path) -> Tuple[str, str]:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        txt = extract_text(str(p)) or ""
    else:
        # fallback for .txt/.html pre-cleaned by your downloader
        txt = p.read_text(errors="ignore")
    return txt, str(p)
