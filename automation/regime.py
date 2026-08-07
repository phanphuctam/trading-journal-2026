# -*- coding: utf-8 -*-
"""CONG TAC TONG thi truong Viet Nam -> scans/regime_vn.json

Tach ra tu scan_vn_vcp.py (da xoa 2026-08-07). Ly do tach: viec CHON CO PHIEU
chuyen sang loc bang mat tren TradingView, nhung viec CHON THOI DIEM thi khong
co cong cu nao thay the — TradingView khong co khai niem "duoc phep vao lenh".

Quy tac: VN-Index > MA50 VA MA50 > MA200. VN khong cho ban khong, nen khi thi
truong giam thi lua chon duy nhat la khong lam gi.

Chi ton DUNG 1 request (VN-Index). Khong quet ca san nua -> bo do rong (breadth),
von di no da duoc ghi ro la "chi de tham khao, khong tham gia quyet dinh".

Cach dung:
    python regime.py                # cap nhat scans/regime_vn.json
    python regime.py --offline      # chi dung cache
    python regime.py --telegram     # gui trang thai qua Telegram
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from tv_common import BASE, load_config, send_telegram

CACHE = BASE / ".vncache"
OUT = BASE.parent / "scans" / "regime_vn.json"
INDEX = "VNINDEX"
START = "2018-01-01"

DD_LOOKBACK = 25       # cua so dem NGAY PHAN PHOI
DD_DANGER = 5          # >= bao nhieu ngay phan phoi thi coi la thi truong dang xa
FTD_GAIN = 1.5         # % tang toi thieu cua mot NGAY BUNG NO THEO DA
FTD_MIN_DAY = 4        # FTD hop le tu ngay thu 4 cua nhip no luc hoi phuc


def fetch_index(offline=False):
    """Tai VN-Index (cache rieng, luon cap nhat duoi vi chi 1 request)."""
    f = CACHE / f"{INDEX}.parquet"
    old = pd.read_parquet(f) if f.exists() else None
    if offline:
        return old
    try:
        from vnstock import Quote
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        end = datetime.now(tz).strftime("%Y-%m-%d")
        start = START if old is None or not len(old) else (
            pd.to_datetime(old["time"]).max() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        new = Quote(symbol=INDEX, source="KBS").history(start=start, end=end, interval="1D")
        if new is not None and len(new):
            old = pd.concat([old, new], ignore_index=True) if old is not None else new
            old = (old.drop_duplicates(subset=["time"], keep="last")
                      .sort_values("time").reset_index(drop=True))
            CACHE.mkdir(exist_ok=True)
            old.to_parquet(f)
    except Exception as e:
        print(f"[!] Khong tai duoc {INDEX}: {str(e)[:70]} — dung cache")
    return old


def _dist_days(d, lookback=DD_LOOKBACK):
    """NGAY PHAN PHOI (O'Neil): chi so giam >= 0,2% ma khoi luong CAO HON phien truoc
    = to chuc dang xa hang trong khi gia con dep. Dem trong `lookback` phien gan nhat;
    >= 5 la canh bao thi truong sap quay dau.

    Vi sao can: cong tac tong MA50/MA200 la chi bao TRE — no bao 'dung ngoai' sau khi
    chi so da mat 8-10%. Ngay phan phoi la canh bao SOM, thay duoc truoc khi gay MA.
    """
    c = d["close"].astype(float).values
    v = d["volume"].astype(float).values if "volume" in d.columns else None
    t = pd.to_datetime(d["time"]).dt.date.values
    n, days = len(c), []
    for k in range(max(1, n - lookback), n):
        chg = (c[k] / c[k - 1] - 1) * 100
        if chg <= -0.2 and (v is None or v[k] > v[k - 1]):
            days.append({"date": str(t[k]), "chg": round(chg, 2)})
    return days


def _ftd(d, win=60):
    """NGAY BUNG NO THEO DA (Follow-Through Day).

    Dinh nghia O'Neil, tham so da Viet hoa theo bao cao (>= 1,5% thay vi 1,7%):
      - Nhip no luc hoi phuc bat dau o ngay dau tien dong cua TANG sau mot day.
      - Tu ngay thu 4 tro di, mot phien tang >= 1,5% kem khoi luong cao hon phien
        truoc = FTD, tuc dong tien to chuc da quay lai.
      - Thung day cu -> nhip hoi that bai, dem lai tu dau.

    CHI DE THAM KHAO — khong tham gia quyet dinh ON/OFF. Bao cao de xuat dung FTD
    de vao som hon MA50, nhung do la thay doi CUA VAO LENH nen phai backtest truoc.
    """
    c = d["close"].astype(float).values
    v = d["volume"].astype(float).values if "volume" in d.columns else None
    t = pd.to_datetime(d["time"]).dt.date.values
    n = len(c)
    if n < 10:
        return None
    s = max(1, n - win)
    low, day, res = c[s - 1], 0, None
    for k in range(s, n):
        if c[k] < low:                      # thung day -> nhip hoi gay, dem lai
            low, day = c[k], 0
            continue
        if day == 0:
            if c[k] > c[k - 1]:             # ngay 1 cua nhip no luc hoi phuc
                day = 1
            continue
        day += 1
        chg = (c[k] / c[k - 1] - 1) * 100
        if day >= FTD_MIN_DAY and chg >= FTD_GAIN and (v is None or v[k] > v[k - 1]):
            res = {"date": str(t[k]), "day": day, "chg": round(chg, 2),
                   "ago": n - 1 - k}
            day = 0                          # da xac nhan, cho nhip moi
    return res


def market_regime(idx):
    """Cong tac tong. ON = duoc phep vao lenh, OFF = dung ngoai.

    Ngay phan phoi va FTD chi la THONG TIN kem theo: chung canh bao som hon MA50
    nhung chua duoc backtest tren HOSE, nen khong duoc phep lat trang thai.
    """
    out = {"index": INDEX}
    if idx is None or not len(idx):
        out.update(state="UNKNOWN",
                   reason="Khong co du lieu VN-Index — coi nhu khong duoc vao lenh")
        return out
    d = idx.copy()
    d["time"] = pd.to_datetime(d["time"])
    d = d.drop_duplicates(subset=["time"], keep="last").sort_values("time")
    c = d["close"].astype(float)
    if len(c) < 200:
        out.update(state="UNKNOWN", reason=f"Chi co {len(c)} phien VN-Index, can >= 200")
        return out
    close = float(c.iloc[-1])
    ma50, ma200 = float(c.rolling(50).mean().iloc[-1]), float(c.rolling(200).mean().iloc[-1])
    above50, ma_stack = close > ma50, ma50 > ma200
    fails = []
    if not above50:
        fails.append(f"VN-Index {close:,.0f} duoi MA50 {ma50:,.0f}")
    if not ma_stack:
        fails.append(f"MA50 {ma50:,.0f} duoi MA200 {ma200:,.0f}")
    dd = _dist_days(d)
    ftd = _ftd(d)
    out.update(
        date=str(d["time"].iloc[-1].date()), close=round(close, 2),
        ma50=round(ma50, 2), ma200=round(ma200, 2),
        above_ma50=above50, ma50_above_ma200=ma_stack,
        state="ON" if (above50 and ma_stack) else "OFF",
        reason=(f"VN-Index {close:,.0f} tren MA50 {ma50:,.0f}, MA50 tren MA200 {ma200:,.0f}"
                if above50 and ma_stack else " · ".join(fails)),
        dist_days=len(dd), dist_lookback=DD_LOOKBACK, dist_danger=DD_DANGER,
        dist_warn=len(dd) >= DD_DANGER, dist_list=dd[-6:],
        ftd=ftd,
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="chi dung cache, khong goi API")
    ap.add_argument("--telegram", action="store_true", help="gui trang thai qua Telegram")
    args = ap.parse_args()

    idx = fetch_index(offline=args.offline)
    reg = market_regime(idx)
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M")

    doc = {
        "app": "trading-journal",
        "market": "VN",
        "checked_at": now,
        "regime": reg,
        "entries_allowed": reg.get("state") == "ON",
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    icon = {"ON": "🟢", "OFF": "🔴"}.get(reg.get("state"), "🟡")
    head = {"ON": "DUOC PHEP VAO LENH", "OFF": "DUNG NGOAI — KHONG VAO LENH NAO"}.get(
        reg.get("state"), "CHUA XAC DINH — coi nhu dung ngoai")
    print(f"{icon} {head}")
    print(f"   {reg.get('reason', '')}")
    if reg.get("dist_days") is not None:
        warn = " ⚠️" if reg.get("dist_warn") else ""
        print(f"   Ngay phan phoi: {reg['dist_days']}/{reg['dist_lookback']} phien{warn}")
    if reg.get("ftd"):
        f = reg["ftd"]
        print(f"   FTD: {f['date']} (+{f['chg']}%, {f['ago']} phien truoc)")
    print(f"-> {OUT}")

    if args.telegram:
        msg = [f"{icon} <b>{head}</b>", reg.get("reason", "")]
        if reg.get("dist_warn"):
            msg.append(f"⚠️ {reg['dist_days']}/{reg['dist_lookback']} ngay phan phoi "
                       f"— to chuc dang xa hang")
        if reg.get("ftd"):
            f = reg["ftd"]
            msg.append(f"FTD {f['date']} (+{f['chg']}%, {f['ago']} phien truoc)")
        send_telegram(load_config(), "\n".join(x for x in msg if x))


if __name__ == "__main__":
    main()
