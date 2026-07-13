# -*- coding: utf-8 -*-
"""Ham dung chung: doc config, gui Telegram, lay gia tu TradingView scanner."""
import json
import sys
from pathlib import Path

import requests

# Console Windows mac dinh cp1252 khong in duoc emoji
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config() -> dict:
    cfg = load_json(BASE / "config.json", {})
    if not cfg:
        print("[!] Chua co automation/config.json — tao tu config.example.json")
        sys.exit(1)
    return cfg


def send_telegram(cfg: dict, text: str) -> bool:
    """Gui tin nhan Telegram. Neu chua co token thi in ra man hinh (dry-run)."""
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id = str(cfg.get("telegram_chat_id", "")).strip()
    if not token or not chat_id or "DIEN_" in token:
        print("=== DRY-RUN (chua co Telegram token) — noi dung tin nhan ===")
        print(text)
        print("===========================================================")
        return False
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"[!] Telegram loi {r.status_code}: {r.text[:300]}")
        return False
    return True


def get_quotes(symbols: list[str]) -> dict:
    """Lay gia hien tai cho danh sach ma (1 request duy nhat).

    Tra ve dict: symbol -> {close, high, low, volume, change, avg_vol}
    """
    from tradingview_screener import Query, col

    if not symbols:
        return {}
    _, df = (
        Query()
        .select("name", "close", "high", "low", "volume", "change",
                "average_volume_30d_calc")
        .where(col("name").isin(symbols))
        .set_markets("america")
        .limit(len(symbols) + 20)
        .get_scanner_data()
    )
    out = {}
    for _, row in df.iterrows():
        out[row["name"]] = {
            "close": row["close"],
            "high": row["high"],
            "low": row["low"],
            "volume": row["volume"],
            "change": row["change"],
            "avg_vol": row["average_volume_30d_calc"],
        }
    return out
