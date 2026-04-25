# -*- coding: utf-8 -*-
"""
Market Sentiment Monitor (AAII & NAAIM)
Designed for GitHub Actions scheduled runs.
Sends AAII every Friday ~08:30 HKT, NAAIM every Thursday ~08:35 HKT.
Credentials are read from environment variables.
"""

import os
import re
import sys
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# ========================= CONFIG =========================
# Telegram settings (now from env vars!)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Extreme thresholds
AAII_EXTREME_BULL = 30
AAII_EXTREME_BEAR = -30
NAAIM_EXTREME_BULL = 90
NAAIM_EXTREME_BEAR = 10

# URLs
AAII_URL = "https://www.aaii.com/sentimentsurvey"
NAAIM_URL = "https://naaim.org/programs/naaim-exposure-index/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ========================= TELEGRAM =========================
def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set, skipping send.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

# ========================= FETCHERS =========================
def fetch_aaii():
    r = requests.get(AAII_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    # Attempt multiple regex patterns
    patterns = [
        r"Bullish[^0-9\-]*([0-9]+(?:\.[0-9]+)?)\s*%",
        r"Bullish\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        r"bullish[^0-9\-]*([0-9]+(?:\.[0-9]+)?)\s*%",
    ]
    bullish = None
    for pat in patterns:
        m = re.search(pat, page_text, re.I)
        if m:
            bullish = float(m.group(1))
            break

    neutral = None
    m_n = re.search(r"Neutral[^0-9\-]*([0-9]+(?:\.[0-9]+)?)\s*%", page_text, re.I)
    if m_n:
        neutral = float(m_n.group(1))

    bearish = None
    for pat in [r"Bearish[^0-9\-]*([0-9]+(?:\.[0-9]+)?)\s*%", r"Bearish\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*%"]:
        m = re.search(pat, page_text, re.I)
        if m:
            bearish = float(m.group(1))
            break

    if bullish is None or bearish is None:
        raise ValueError("無法從 AAII 頁面解析 Bullish/Bearish 數值")

    spread = bullish - bearish
    return {"bullish": bullish, "neutral": neutral, "bearish": bearish, "spread": spread, "source": AAII_URL}

def fetch_naaim():
    r = requests.get(NAAIM_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    # Several possible patterns
    patterns = [
        r"NAAIM Exposure Index number is\*?\s*:\s*([\-]?[0-9]+(?:\.[0-9]+)?)",
        r"This week[’']?s NAAIM Exposure Index number is\*?\s*([\-]?[0-9]+(?:\.[0-9]+)?)",
        r"Exposure Index is\s*:\s*([\-]?[0-9]+(?:\.[0-9]+)?)",
    ]
    value = None
    for pat in patterns:
        m = re.search(pat, page_text, re.I)
        if m:
            value = float(m.group(1))
            break
    if value is None:
        raise ValueError("無法從 NAAIM 頁面解析數值")
    return {"value": value, "source": NAAIM_URL}

# ========================= MESSAGE BUILDERS =========================
def build_aaii_message(data):
    spread = data["spread"]
    if spread > AAII_EXTREME_BULL:
        signal = "散戶極端樂觀"
        note = f"多頭減空頭 > {AAII_EXTREME_BULL}，屬散戶極端樂觀。"
    elif spread < AAII_EXTREME_BEAR:
        signal = "散戶極端悲觀"
        note = f"多頭減空頭 < {AAII_EXTREME_BEAR}，屬散戶極端悲觀。"
    else:
        signal = "中性區間"
        note = "目前未達極端門檻。"

    lines = []
    lines.append("📊 <b>AAII 散戶情緒調查</b>")
    lines.append(f"香港時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"最新 Bullish：<b>{data['bullish']:.1f}%</b>")
    if data["neutral"] is not None:
        lines.append(f"最新 Neutral：<b>{data['neutral']:.1f}%</b>")
    lines.append(f"最新 Bearish：<b>{data['bearish']:.1f}%</b>")
    lines.append(f"多頭減空頭：<b>{spread:+.1f}</b>")
    lines.append(f"判讀：<b>{signal}</b>")
    lines.append(note)
    lines.append("⚠️ 反向指標：散戶越極端樂觀，越要防範市場回落；散戶越極端悲觀，越要留意反彈機會。")
    lines.append(f"來源：{data['source']}")
    return "\n".join(lines)

def build_naaim_message(data):
    value = data["value"]
    if value < NAAIM_EXTREME_BEAR:
        signal = "主動投資經理敞口極端悲觀"
        note = f"低於 {NAAIM_EXTREME_BEAR}，屬極端悲觀。"
    elif value < 30:
        signal = "很悲觀"
        note = "低於 30，屬很悲觀。"
    elif value > NAAIM_EXTREME_BULL:
        signal = "主動投資經理敞口極端樂觀"
        note = f"高於 {NAAIM_EXTREME_BULL}，屬極端樂觀。"
    elif value > 70:
        signal = "很樂觀"
        note = "高於 70，屬很樂觀。"
    else:
        signal = "中性區間"
        note = "目前未達極端門檻。"

    lines = []
    lines.append("📈 <b>NAAIM 主動投資經理敞口指數</b>")
    lines.append(f"香港時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"最新敞口值：<b>{value:.2f}</b>")
    lines.append(f"判讀：<b>{signal}</b>")
    lines.append(note)
    lines.append(f"來源：{data['source']}")
    return "\n".join(lines)

# ========================= MAIN =========================
def main():
    today = datetime.now()
    weekday = today.weekday()  # Monday=0, Sunday=6

    if weekday == 3:  # Thursday
        logger.info("Running NAAIM task (Thursday)")
        try:
            data = fetch_naaim()
            msg = build_naaim_message(data)
            send_telegram_message(msg)
            logger.info("NAAIM message sent.")
        except Exception as e:
            err_msg = f"❌ <b>NAAIM 任務失敗</b>\n香港時間：{today.strftime('%Y-%m-%d %H:%M:%S')}\n錯誤：<code>{str(e)}</code>"
            logger.exception("NAAIM job failed")
            try:
                send_telegram_message(err_msg)
            except:
                pass
            return 1

    elif weekday == 4:  # Friday
        logger.info("Running AAII task (Friday)")
        try:
            data = fetch_aaii()
            msg = build_aaii_message(data)
            send_telegram_message(msg)
            logger.info("AAII message sent.")
        except Exception as e:
            err_msg = f"❌ <b>AAII 任務失敗</b>\n香港時間：{today.strftime('%Y-%m-%d %H:%M:%S')}\n錯誤：<code>{str(e)}</code>"
            logger.exception("AAII job failed")
            try:
                send_telegram_message(err_msg)
            except:
                pass
            return 1
    else:
        logger.info("Not a task day (AAII on Fri, NAAIM on Thu). Exiting.")
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
