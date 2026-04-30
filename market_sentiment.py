import csv
import json
from io import StringIO

NAAIM_CSV_URL = "https://www.naaim.org/programs/naaim-exposure-index/naaim_exposure_index.csv"
NAAIM_HTML_URL = "https://www.naaim.org/programs/naaim-exposure-index/"  # with www
NAAIM_CACHE_FILE = "naaim_cache.json"

def _save_naaim_cache(data: dict):
    try:
        with open(NAAIM_CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Could not save NAAIM cache: {e}")

def _load_naaim_cache() -> dict:
    if os.path.exists(NAAIM_CACHE_FILE):
        with open(NAAIM_CACHE_FILE) as f:
            return json.load(f)
    return None

def _naaim_from_csv(url: str) -> dict:
    """Try to parse the latest value from a CSV file provided by NAAIM."""
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    # The CSV typically has columns like: Date, Exposure Index
    reader = csv.DictReader(StringIO(r.text))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV is empty")
    # Assume last row is the most recent
    last = rows[-1]
    # Try common column names
    for col in ("Exposure Index", "NAAIM Exposure Index", "Value", "Index"):
        if col in last:
            value = float(last[col])
            break
    else:
        # If no obvious column, take the second column value
        value_key = list(last.keys())[1]
        value = float(last[value_key])
    return {"value": value, "source": url}

def _naaim_from_html(url: str) -> dict:
    """Original HTML parsing logic, kept unchanged."""
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    patterns = [
        r"NAAIM Exposure Index number is\*?\s*:\s*([\-]?[0-9]+(?:\.[0-9]+)?)",
        r"This week[’']?s NAAIM Exposure Index number is\*?\s*([\-]?[0-9]+(?:\.[0-9]+)?)",
        r"Exposure Index is\s*:\s*([\-]?[0-9]+(?:\.[0-9]+)?)",
    ]
    for pat in patterns:
        m = re.search(pat, page_text, re.I)
        if m:
            value = float(m.group(1))
            return {"value": value, "source": url}
    raise ValueError("無法從 NAAIM 頁面解析數值")

def fetch_naaim():
    """Fetch NAAIM exposure index with fallback and cache."""
    # 1. Try CSV
    try:
        data = _naaim_from_csv(NAAIM_CSV_URL)
        logger.info("NAAIM data obtained from CSV")
        _save_naaim_cache(data)
        return data
    except Exception as e:
        logger.warning(f"CSV fetch failed: {e}. Trying HTML page...")

    # 2. Try HTML page (with www)
    try:
        data = _naaim_from_html(NAAIM_HTML_URL)
        logger.info("NAAIM data obtained from HTML")
        _save_naaim_cache(data)
        return data
    except Exception as e:
        logger.warning(f"HTML fetch failed: {e}. Attempting cache...")

    # 3. Fallback to local cache
    cached = _load_naaim_cache()
    if cached:
        logger.warning("Using cached NAAIM data")
        # Send a Telegram alert that we're using cached data
        try:
            send_telegram_message(
                "⚠️ <b>NAAIM 即時數據無法獲取，顯示為上次快取值</b>\n"
                f"來源：{cached.get('source', '-')}"
            )
        except:
            pass
        return cached

    # 4. Nothing works – raise error (will be caught by main's try/except)
    raise RuntimeError("All NAAIM fetch methods failed and no cache available")
