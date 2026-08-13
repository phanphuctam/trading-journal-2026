# -*- coding: utf-8 -*-
"""Ham dung chung: doc config, gui Telegram, lay gia tu TradingView scanner."""
import json
import os
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
    """Doc config.json (may local), bien moi truong ghi de (GitHub Actions)."""
    cfg = load_json(BASE / "config.json", {})
    for key, envk in (("telegram_bot_token", "TELEGRAM_BOT_TOKEN"),
                      ("telegram_chat_id", "TELEGRAM_CHAT_ID"),
                      ("chart_layout_id", "CHART_LAYOUT_ID")):
        if os.environ.get(envk, "").strip():
            cfg[key] = os.environ[envk].strip()
    cfg.setdefault("approach_pct", 1.5)
    if not cfg.get("telegram_bot_token"):
        print("[!] Chua co token Telegram (config.json hoac bien TELEGRAM_BOT_TOKEN) — chay dry-run")
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


def vnstock_sleep(margin: float = 0.85, fallback: float = 3.4) -> float:
    """Giay nghi giua hai request vnstock, tinh tu HAN MUC THAT cua tai khoan.

    vnstock chan toc do o PHIA CLIENT theo tier — bang nam cung trong thu vien da
    cai (vnai/beam/auth.py, `Authenticator.TIER_LIMITS`):

        guest  (khong co API key)      20 req/phut
        free   (co API key MIEN PHI)   60 req/phut
        bronze/silver/golden/diamond   180 den 600 req/phut (tra tien)

    Truoc 13/08/2026 cac script go cung 3,4 giay — dung cho muc guest. Go cung
    nghia la dang ky API key mien phi xong VAN chay cham gap ba lan ma khong ai
    biet vi sao. Ham nay hoi thang thu vien nen chi can dat API key la nhanh len.

    Cach dat key (chon MOT):
      · Bien moi truong VNSTOCK_API_KEY  (dung cho GitHub Actions — khong ghi file)
      · python -c "from vnstock import register_user; register_user('<KEY>')"
        (ghi vao ~/.vnstock/api_key.json — dung cho may ca nhan)

    `margin` chua 15% bien an toan: han muc dem theo cua so truot o may chu, chay
    sat vach thi chi mot lan trung nhip la dinh 429 va mat ca lan chay. Doi mot
    lan chay 4 phut lay rui ro hong ca lan chay la doi te.
    """
    import contextlib
    import io

    try:
        # Nap vnai in ra banner quang cao — nuot di, day la ham chay ngam.
        with contextlib.redirect_stdout(io.StringIO()):
            import vnai
            info = vnai.get_user_tier() or {}
        per_min = (info.get("limits") or {}).get("per_minute")
        if per_min and per_min > 0:
            return round(60.0 / (per_min * margin), 2)
    except Exception:
        pass
    return fallback


def vnstock_tier() -> str:
    """Ten tier hien tai ('guest' / 'free' / ...) de in ra cho nguoi doc biet."""
    import contextlib
    import io

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import vnai
            return str((vnai.get_user_tier() or {}).get("tier") or "?")
    except Exception:
        return "?"


def get_quotes(symbols: list[str], market: str = "vietnam") -> dict:
    """Lay gia hien tai cho danh sach ma (1 request duy nhat).

    market: "vietnam" (HOSE/HNX/UPCOM) hoac "america".
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
        .set_markets(market)
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
