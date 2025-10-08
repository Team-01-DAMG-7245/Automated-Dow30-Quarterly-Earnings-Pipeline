import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

IR_TEXTS = ["investor relations", "investors", "investor", "shareholder"]
IR_PATHS = ["investors", "investor-relations", "ir"]

def discover_ir_url(homepage: str) -> str | None:
    """Finds the Investor Relations (IR) page automatically for a given homepage."""
    try:
        r = requests.get(homepage, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Failed to load {homepage}: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    base = r.url  # handles redirects

    # Scan header/nav/footer first
    for section in [soup.select_one("header"), soup.select_one("nav"), soup.select_one("footer"), soup]:
        if not section:
            continue
        for a in section.find_all("a", href=True):
            text = (a.get_text(" ", strip=True) or "").lower()
            href = a["href"].lower()
            if any(k in text for k in IR_TEXTS) or any(k in href for k in IR_PATHS):
                return urljoin(base, a["href"])

    # fallback guesses
    for guess in ("/investors", "/investor-relations", "/ir"):
        url = urljoin(base, guess)
        try:
            g = requests.head(url, timeout=10, allow_redirects=True)
            if g.status_code < 400:
                return g.url
        except Exception:
            pass

    return None


