# -*- coding: utf-8 -*-
"""So lieu phong thu cho cac ma TRONG WATCHLIST -> scans/watch_stats.json

Tach ra tu scan_vn_vcp.py (da xoa 2026-08-07). Viec CHON MA da chuyen sang loc
bang mat tren TradingView, nen o day khong con quet ca san: chi tinh cho nhung
ma nguoi dung da tu tay dua vao watchlist (~10-20 ma thay vi 151).

Ba thu tinh o day deu la thu MAT KHONG LAM DUOC, khong phai thu thay the mat:

  · TRAN VI THE (max_pos) = 2% gia tri giao dich TB20 phien.
    Mua nhieu hon the thi chinh minh la nguoi day gia len luc vao, va la nguoi
    dap gia xuong luc cat lo. So lenh HOSE mong nen day la rui ro that.
    No chi len tieng voi ma mong — ma thanh khoan lon thi khong bao gio cham.

  · 🔒 DONG CUA GIA TRAN (ceil). Bien do HOSE +-7%, HNX +-10%, UPCOM +-15%.
    Breakout dong tran = trang ben ban, KHONG khop duoc, hom sau gap-up va diem
    vao lech xa pivot. Thu yeu — nhin cot Chg% cung thay — nhung du lieu san roi.

  · ⚑ NHIEU PHIEN TRAN TRONG NEN (manip) = van tay doi lai: keo tran vai phien
    voi khoi luong tu doi ung de VE RA mot cai nen dep. Day la thu dang gia nhat
    trong ba, vi no chong lai dung diem mu cua viec nhin bang mat — do thi bi lam
    gia TRONG RAT DEP, do la muc dich cua viec lam gia. Dem 4 phien tran rai trong
    60 phien thi mat khong lam noi.

Tuoi niem yet (age) chi di kem cho biet, khong con la tieu chi: no la thu tra
MOT LAN luc them ma vao watchlist, khong phai tin hieu hang ngay.

Cach dung:
    python watch_stats.py               # cap nhat cache roi tinh
    python watch_stats.py --offline     # chi dung cache co san
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from tv_common import BASE, load_json

CACHE = BASE / ".vncache"
WATCHLIST = BASE / "watchlist.json"
OUT = BASE.parent / "scans" / "watch_stats.json"
START = "2018-01-01"

CEIL = {"HOSE": 6.8, "HNX": 9.5, "UPCOM": 14.5}   # % coi nhu dong cua GIA TRAN
CEIL_DEFAULT = 6.8
CEIL_BASE_N = 60       # dem phien tran trong bao nhieu phien gan nhat
CEIL_MANIP = 4         # >= bao nhieu phien tran trong nen thi nghi "doi lai"
MAX_POS_PCT = 2.0      # tran vi the = % GTGD TB20


def refresh(symbols, days=120, sleep=3.2):
    """Tai moi / cap nhat duoi cache. vnstock community gioi han 20 request/phut."""
    from vnstock import Quote
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    end = datetime.now(tz).strftime("%Y-%m-%d")
    tail = (datetime.now(tz) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    CACHE.mkdir(exist_ok=True)
    print(f"[i] Cap nhat {len(symbols)} ma (~{len(symbols) * sleep / 60:.0f} phut)…")
    for s in symbols:
        f = CACHE / f"{s}.parquet"
        first = not f.exists()
        try:
            time.sleep(sleep)
            new = Quote(symbol=s, source="KBS").history(
                start=START if first else tail, end=end, interval="1D")
            if new is None or not len(new):
                continue
            new["symbol"] = s
            if first:
                new.to_parquet(f)
            else:
                (pd.concat([pd.read_parquet(f), new], ignore_index=True)
                   .drop_duplicates(subset=["time"], keep="last")
                   .sort_values("time")
                   .to_parquet(f))
        except Exception as e:
            print(f"    bo qua {s}: {str(e)[:50]}")


def stats_for(sym, exch, age_y):
    """Tinh so lieu cho mot ma tu cache. Tra None neu khong du du lieu."""
    f = CACHE / f"{sym}.parquet"
    if not f.exists():
        return None
    d = pd.read_parquet(f)
    if len(d) < CEIL_BASE_N:
        return None
    d = (d.assign(time=pd.to_datetime(d["time"]))
           .drop_duplicates(subset=["time"], keep="last")
           .sort_values("time"))
    c, v = d["close"].astype(float), d["volume"].astype(float)

    # Gia tu nguon KBS tinh bang NGHIN dong -> nhan 1000 de ra VND
    adtv = float((c * 1000 * v).tail(20).mean() / 1e9)          # ty VND
    vol20 = float(v.tail(20).mean())
    chg = c.pct_change(fill_method=None) * 100
    thr = CEIL.get(exch, CEIL_DEFAULT)
    ceil_mask = chg >= thr
    ceil_base = int(ceil_mask.tail(CEIL_BASE_N).sum())

    return {
        "symbol": sym,
        "exchange": exch,
        "bar_date": str(d["time"].iloc[-1].date()),
        "close": int(round(float(c.iloc[-1]) * 1000)),
        "adtv": round(adtv, 1),
        "vol20": int(vol20),
        "max_pos": int(adtv * 1e9 * MAX_POS_PCT / 100),
        "ceil": bool(ceil_mask.iloc[-1]),
        "ceil_base": ceil_base,
        "manip": ceil_base >= CEIL_MANIP,
        "age": round(float(age_y[sym]), 1) if sym in age_y else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="chi dung cache co san")
    args = ap.parse_args()

    wl = load_json(WATCHLIST, [])
    syms = sorted({str(w.get("symbol", "")).upper() for w in wl if w.get("symbol")})
    if not syms:
        print("watchlist.json trong — khong co ma nao de tinh.")
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps({"stats": {}}, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        return

    if not args.offline:
        refresh(syms)

    # San niem yet: _meta.json do scan cu de lai. Thieu ma nao thi coi la HOSE —
    # nguong tran HOSE chat nhat nen doan sai chi bo sot canh bao, khong bao nham.
    meta = load_json(CACHE / "_meta.json", {})
    exmap = meta.get("exchange", {})
    missing = [s for s in syms if s not in exmap]
    if missing and not args.offline:
        try:
            from vnstock import Listing
            lst = Listing().symbols_by_exchange()
            exmap.update(dict(zip(lst.symbol, lst.exchange)))
            meta["exchange"] = exmap
            CACHE.mkdir(exist_ok=True)
            (CACHE / "_meta.json").write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[!] Khong lay duoc bang san: {str(e)[:60]} — mac dinh HOSE")
    if [s for s in syms if s not in exmap]:
        print(f"[!] Chua ro san: {', '.join(s for s in syms if s not in exmap)} — coi la HOSE")

    # Tuoi niem yet that (fetch_listing_dates.py). Thieu thi bo trong, khong chan.
    today = pd.Timestamp(datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date())
    lf = CACHE / "_listing.json"
    age_y = {}
    if lf.exists():
        for k, val in json.loads(lf.read_text(encoding="utf-8")).items():
            dt = pd.to_datetime(val, format="%d/%m/%Y", errors="coerce")
            if pd.notna(dt):
                age_y[k] = (today - dt).days / 365.25

    out = {}
    for s in syms:
        st = stats_for(s, exmap.get(s, "HOSE"), age_y)
        if st:
            out[s] = st
        else:
            print(f"[!] {s}: khong du du lieu trong cache")

    doc = {
        "app": "trading-journal",
        "market": "VN",
        "checked_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M"),
        "max_pos_pct": MAX_POS_PCT,
        "ceil_manip": CEIL_MANIP,
        "ceil_base_n": CEIL_BASE_N,
        "stats": out,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    for s, r in out.items():
        cap = (f"{r['max_pos'] / 1e9:.1f} ty" if r["max_pos"] >= 1e9
               else f"{r['max_pos'] / 1e6:.0f}tr")
        flags = ("🔒" if r["ceil"] else "") + ("⚑" if r["manip"] else "")
        print(f"  {s:<5} GTGD {r['adtv']:>7.1f} ty · tran vi the {cap:>8}"
              f" · tran/{CEIL_BASE_N}p: {r['ceil_base']} {flags}")
    if any(r["manip"] for r in out.values()):
        print("⚑ = nhieu phien tran trong nen 60 phien — van tay doi lai, do thi dep la do ve")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
