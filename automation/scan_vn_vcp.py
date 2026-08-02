# -*- coding: utf-8 -*-
"""Scan VCP (Mark Minervini) cho co phieu Viet Nam — HOSE (+ tuy chon HNX).

Vi sao KHONG dung nguyen bo loc My:
  Backtest HOSE 2018-2026 (403 ma, 713k dong) cho thay:
    - Trend Template dung lam bo loc xep hang: alpha ~0 (t=0.13). Ty le pass
      dao dong 0%-85% theo pha thi truong -> khong co tinh chon loc.
    - RS Rating: cang siet cang te (RS>=90 cho alpha AM -0.47%).
      Momentum 6-12 thang KHONG ton tai o HOSE (decile D9-D0 = -0.77%).
    - VCP 3 lan nen + breakout: CAGR +10.36%, MaxDD -15.9% (VN-Index: +8.67%,
      -40.3%). Thang 38.6%, lai TB +25.9%, lo TB -6.9% (ty le 3.75:1).
    - Noi long con 2 lan nen -> chet han (CAGR -0.78%). Do chat la loi the.
  => Bo RS lam bo loc. Giu: thanh khoan, boi canh xu huong, VCP.

Dinh nghia VCP (giong het backtest da kiem dinh):
  cua so w = 20 phien; bien do r = (max-min)/max tren moi cua so
  r1 (phien -40..-21) > r2 (-20..-1) > r3 (20 phien gan nhat), r3 < 10%
  khoi luong TB 20 phien gan nhat < khoi luong TB cua so dau (can hang)
  boi canh: gia > MA50, > MA200, trong vong 25% dinh 52 tuan
  diem mua (pivot): dinh dong cua 60 phien gan nhat
  BREAKOUT: dong cua vuot pivot + khoi luong >= 1.5x TB20

CONG TAC TONG (regime): VN khong cho ban khong, va gan nhu ca san chay theo mot
nhip -> chon dung thoi diem an dut chon dung co phieu. Chi cho phep vao lenh khi
VN-Index > MA50 VA MA50 > MA200. Ngoai ra: DUNG NGOAI, scan chi de theo doi.

Cach dung:
    python scan_vn_vcp.py                  # scan HOSE, ghi scans/latest_vn.json
    python scan_vn_vcp.py --hnx            # them san HNX
    python scan_vn_vcp.py --offline        # chi dung cache, khong goi API
    python scan_vn_vcp.py --telegram       # gui ket qua qua Telegram
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from tv_common import BASE, load_config, send_telegram

CACHE = BASE / ".vncache"
OUT = BASE.parent / "scans" / "latest_vn.json"
CHART = "https://www.tradingview.com/chart/"
START = "2018-01-01"

W = 20                 # do dai mot cua so nen
TIGHT3 = 0.10          # bien do toi da cua lan nen cuoi (VCP 3 nen)
TIGHT2 = 0.12          # bien do toi da (VCP 2 nen — chi tham khao)
BASE_N = 60            # so phien tinh pivot
VOL_BO = 1.5           # boi so khoi luong khi breakout
LIQ_MIN = 10.0         # GTGD TB 20 phien toi thieu de VAO LENH (chuan backtest)
OBS_LIQ = 5.0          # nguong QUAN SAT — noi phieu, khong noi tin hieu
NEAR_PIVOT = 8.0       # coi la "sap toi diem mua" neu cach pivot <= %
INDEX = "VNINDEX"      # chi so dung lam cong tac tong

# Noi phieu quan sat nhung GIU NGUYEN cong vao lenh:
#   - BREAKOUT van doi: 3 nen + r3<10% + vol kho can + GTGD >= 10 ty + regime ON.
#     (backtest: noi con 2 nen -> CAGR -0.78%; do chat la loi the, khong dong vao)
#   - Quan sat mo rong: GTGD >= 5 ty (co 💧), TREND trong vong 30% dinh 52T
#     (thay vi 25%) de thay nen dang hinh thanh som hon.
#   - Co 💪 "dan dat": khi thi truong OFF ma van bam sat dinh 52T — Minervini:
#     leader cua song tang sau lo dien ngay trong pha dieu chinh.


def fetch_all(symbols, offline=False, sleep=3.2):
    """Tai/doc cache OHLCV. vnstock community gioi han 20 request/phut."""
    CACHE.mkdir(exist_ok=True)
    frames, miss = [], []
    for s in symbols:
        f = CACHE / f"{s}.parquet"
        if f.exists():
            d = pd.read_parquet(f)
            if len(d):
                frames.append(d)
        else:
            miss.append(s)
    if miss and not offline:
        from vnstock import Quote
        end = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d")
        print(f"[i] Tai moi {len(miss)} ma (~{len(miss)*sleep/60:.0f} phut)…")
        for i, s in enumerate(miss, 1):
            try:
                time.sleep(sleep)
                d = Quote(symbol=s, source="KBS").history(
                    start=START, end=end, interval="1D")
                if d is not None and len(d):
                    d["symbol"] = s
                    d.to_parquet(CACHE / f"{s}.parquet")
                    frames.append(d)
            except Exception as e:
                print(f"    bo qua {s}: {str(e)[:50]}")
            if i % 20 == 0:
                print(f"    {i}/{len(miss)}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def refresh_tail(symbols, days=90, sleep=3.2):
    """Cap nhat phan duoi cua cache (chay hang tuan cho nhanh hon tai lai het)."""
    from vnstock import Quote
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    end = datetime.now(tz).strftime("%Y-%m-%d")
    start = (datetime.now(tz) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    print(f"[i] Cap nhat {len(symbols)} ma tu {start} (~{len(symbols)*sleep/60:.0f} phut)…")
    for i, s in enumerate(symbols, 1):
        f = CACHE / f"{s}.parquet"
        if not f.exists():
            continue
        try:
            time.sleep(sleep)
            new = Quote(symbol=s, source="KBS").history(
                start=start, end=end, interval="1D")
            if new is None or not len(new):
                continue
            new["symbol"] = s
            old = pd.read_parquet(f)
            merged = (pd.concat([old, new], ignore_index=True)
                        .drop_duplicates(subset=["time"], keep="last")
                        .sort_values("time"))
            merged.to_parquet(f)
        except Exception as e:
            print(f"    bo qua {s}: {str(e)[:50]}")
        if i % 20 == 0:
            print(f"    {i}/{len(symbols)}")


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


def market_regime(idx, breadth50, breadth200):
    """Cong tac tong. ON = duoc phep vao lenh, OFF = dung ngoai.

    Quy tac: VN-Index > MA50 VA MA50 > MA200. VN khong co ban khong, nen khi
    thi truong giam thi lua chon duy nhat la khong lam gi. Do rong (breadth) chi
    de tham khao — no khong tham gia quyet dinh, tranh them bien so chua kiem dinh.
    """
    out = {"index": INDEX, "breadth50": breadth50, "breadth200": breadth200}
    if idx is None or not len(idx):
        out.update(state="UNKNOWN", reason="Khong co du lieu VN-Index — coi nhu khong duoc vao lenh")
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
    out.update(
        date=str(d["time"].iloc[-1].date()), close=round(close, 2),
        ma50=round(ma50, 2), ma200=round(ma200, 2),
        above_ma50=above50, ma50_above_ma200=ma_stack,
        state="ON" if (above50 and ma_stack) else "OFF",
        reason=(f"VN-Index {close:,.0f} tren MA50 {ma50:,.0f}, MA50 tren MA200 {ma200:,.0f}"
                if above50 and ma_stack else " · ".join(fails)),
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hnx", action="store_true", help="them san HNX")
    ap.add_argument("--offline", action="store_true", help="chi dung cache")
    ap.add_argument("--refresh", action="store_true", help="cap nhat 90 phien cuoi (toan bo)")
    ap.add_argument("--refresh-liquid", action="store_true",
                    help="chi cap nhat ma thanh khoan — du cho scan, nhanh hon nhieu (dung cho CI)")
    ap.add_argument("--liq", type=float, default=LIQ_MIN, help="GTGD TB20 toi thieu de vao lenh (ty)")
    ap.add_argument("--obs-liq", type=float, default=OBS_LIQ, help="GTGD TB20 toi thieu de quan sat (ty)")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    from vnstock import Listing
    lst = Listing().symbols_by_exchange()
    exch = ["HOSE"] + (["HNX"] if args.hnx else [])
    meta = lst[(lst.exchange.isin(exch)) & (lst.type == "stock")]
    names = dict(zip(meta.symbol, meta.organ_name))
    exmap = dict(zip(meta.symbol, meta.exchange))
    syms = sorted(meta.symbol.unique())
    print(f"[i] Vu tru: {len(syms)} ma ({', '.join(exch)})")

    if args.refresh_liquid and not args.offline:
        # Chi tai lai nhung ma con co cua vao vu tru (GTGD >= mot nua nguong).
        # Thanh khoan doi rat cham theo tuan nen bo qua ma "chet" khong lam sai ket qua,
        # va cat so request tu ~400 xuong ~150 — vua khung 20 request/phut cua vnstock.
        liq_syms = []
        for s in syms:
            f = CACHE / f"{s}.parquet"
            if not f.exists():
                liq_syms.append(s); continue
            try:
                d = pd.read_parquet(f).tail(20)
                if len(d) and (d["close"] * 1000 * d["volume"] / 1e9).mean() >= args.obs_liq / 2:
                    liq_syms.append(s)
            except Exception:
                liq_syms.append(s)
        print(f"[i] Refresh nhanh: {len(liq_syms)}/{len(syms)} ma thanh khoan")
        refresh_tail(liq_syms)
    elif args.refresh and not args.offline:
        refresh_tail(syms)
    px = fetch_all(syms, offline=args.offline)
    if px.empty:
        print("[!] Khong co du lieu"); return

    px["time"] = pd.to_datetime(px["time"])
    px = px.drop_duplicates(subset=["symbol", "time"]).sort_values(["symbol", "time"])
    close = px.pivot(index="time", columns="symbol", values="close")
    vol = px.pivot(index="time", columns="symbol", values="volume")
    if len(close) < 260:
        print(f"[!] Chi co {len(close)} phien, can >= 260"); return

    adtv = ((close * 1000 * vol) / 1e9).rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    hi52 = close.rolling(252).max()
    lo52 = close.rolling(252).min()
    hi_all = close.cummax()
    rng = (close.rolling(W).max() - close.rolling(W).min()) / close.rolling(W).max()
    vm = vol.rolling(W).mean()
    pivot = close.rolling(BASE_N).max().shift(1)

    i = -1
    d = close.index[i]
    prev = close.iloc[i - 1]
    c, v = close.iloc[i], vol.iloc[i]
    r3, r2, r1 = rng.iloc[i], rng.iloc[i - W], rng.iloc[i - 2 * W]
    v3, v1 = vm.iloc[i], vm.iloc[i - 2 * W]
    r3p, r2p = rng.iloc[i - 1], rng.iloc[i - 1 - W]
    v3p, v1p = vm.iloc[i - 1], vm.iloc[i - 1 - 2 * W]
    c_prev = close.iloc[i - 1]
    up_prev = ((c_prev > ma50.iloc[i - 1]) & (c_prev > ma200.iloc[i - 1])
               & (c_prev >= hi52.iloc[i - 1] * 0.75))

    liq_sig = adtv.iloc[i] >= args.liq       # chuan VAO LENH — dung nhu backtest
    liq_obs = adtv.iloc[i] >= args.obs_liq   # chuan QUAN SAT — noi phieu
    up = (c > ma50.iloc[i]) & (c > ma200.iloc[i]) & (c >= hi52.iloc[i] * 0.75)
    up_obs = (c > ma50.iloc[i]) & (c > ma200.iloc[i]) & (c >= hi52.iloc[i] * 0.70)
    vcp3 = (r1 > r2) & (r2 > r3) & (r3 < TIGHT3) & (v3 < v1) & up & liq_obs
    vcp2 = (r2 > r3) & (r3 < TIGHT2) & (v3 < v1) & up & liq_obs
    # breakout: hom qua dang o trang thai VCP, hom nay vuot pivot voi khoi luong.
    # Tin hieu vao lenh nen doi thanh khoan CHUAN (>= --liq), khong an theo nguong quan sat
    vcp3_prev = ((rng.iloc[i - 1 - 2 * W] > r2p) & (r2p > r3p) & (r3p < TIGHT3)
                 & (v3p < v1p) & up_prev)
    bo = vcp3_prev & (c > pivot.iloc[i]) & (v > VOL_BO * v3) & liq_sig

    # ── Cong tac tong (tinh truoc de gan co "dan dat" cho tung ma) ──
    nsig = int(liq_sig.sum())
    b50 = round(float(((c > ma50.iloc[i]) & liq_sig).sum()) / nsig * 100, 1) if nsig else None
    b200 = round(float(((c > ma200.iloc[i]) & liq_sig).sum()) / nsig * 100, 1) if nsig else None
    reg = market_regime(fetch_index(offline=args.offline), b50, b200)
    allow = reg["state"] == "ON"
    print(f"[i] Thi truong: {reg['state']} — {reg['reason']}"
          + (f" · do rong tren MA50 {b50}% / MA200 {b200}%" if b50 is not None else ""))

    rows = []
    for s in close.columns:
        if not bool(liq_obs.get(s, False)) or pd.isna(c.get(s)):
            continue
        if bool(bo.get(s, False)):
            tier = "BREAKOUT"
        elif bool(vcp3.get(s, False)):
            tier = "VCP3"
        elif bool(vcp2.get(s, False)):
            tier = "VCP2"
        elif bool(up_obs.get(s, False)):
            tier = "TREND"
        else:
            continue
        # Gia luu bang VND (khong phai nghin dong) de khop voi TradingView —
        # alert_watcher so pivot voi gia song, lech don vi la bao breakout gia.
        px_now, pv = float(c[s]) * 1000, float(pivot.iloc[i][s]) * 1000
        pxp = float(prev[s]) * 1000 if pd.notna(prev.get(s)) else px_now
        h52, l52, hall = (float(hi52.iloc[i][s]) * 1000, float(lo52.iloc[i][s]) * 1000,
                          float(hi_all.iloc[i][s]) * 1000)
        m50, m200 = float(ma50.iloc[i][s]) * 1000, float(ma200.iloc[i][s]) * 1000
        to_pivot = (pv / px_now - 1) * 100 if px_now > 0 else None
        off_hi = (px_now / h52 - 1) * 100
        adtv_s = float(adtv.iloc[i][s])
        rows.append({
            "symbol": s,
            "ticker": f"{exmap.get(s,'HOSE')}:{s}",
            "desc": names.get(s, s),
            "sector": exmap.get(s, ""),
            "close": round(px_now),
            "change": round((px_now / pxp - 1) * 100, 2) if pxp else 0.0,
            "tier": tier,
            "tight": round(float(r3[s]) * 100, 1) if pd.notna(r3.get(s)) else None,
            "contractions": (3 if tier in ("BREAKOUT", "VCP3") else (2 if tier == "VCP2" else 0)),
            "pivot": round(pv) if pd.notna(pv) else None,
            "to_pivot": round(to_pivot, 1) if to_pivot is not None else None,
            "adtv": round(adtv_s, 1),
            "vol_x": round(float(v[s] / v3[s]), 1) if v3.get(s) else None,
            "dry": round(float(v3[s] / v1[s]), 2) if v1.get(s) else None,
            "off_high": round(off_hi, 1),
            "above_low": round((px_now / l52 - 1) * 100, 1),
            "off_ath": round((px_now / hall - 1) * 100, 1),
            "ext50": round((px_now / m50 - 1) * 100, 1),
            "ext200": round((px_now / m200 - 1) * 100, 1),
            "extended": bool((px_now / m50 - 1) * 100 > 15 or (px_now / m200 - 1) * 100 > 50),
            "near": bool(to_pivot is not None and 0 < to_pivot <= NEAR_PIVOT),
            # 💧 du de quan sat nhung chua du chuan vao lenh 10 ty
            "lowliq": bool(adtv_s < args.liq),
            # 💪 Index dang OFF ma ma nay van trong vong 5% dinh 52T. Nguong phai chat:
            # ca danh sach von da loc "tren MA50+MA200", noi ra -15% thi 19/21 ma dinh co.
            "lead": bool((not allow) and off_hi >= -5),
        })

    order = {"BREAKOUT": 0, "VCP3": 1, "VCP2": 2, "TREND": 3}
    # trong cung tier: ma "dan dat" truoc, roi nen chat nhat (Minervini — cang chat
    # cang tot), rieng TREND thi xep theo khoang cach toi diem mua
    rows.sort(key=lambda r: (order[r["tier"]],
                             0 if r.get("lead") else 1,
                             r["tight"] if r["tier"] != "TREND" else 99,
                             abs(r["to_pivot"]) if r["to_pivot"] is not None else 99))

    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    payload = {
        "app": "trading-journal-2026",
        "market": "VN",
        "scanned_at": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        "bar_date": str(d.date()),
        "liq_min": args.liq,
        "obs_liq": args.obs_liq,
        "universe": int(liq_obs.sum()),
        "universe_sig": nsig,
        "total": len(rows),
        "counts": {k: sum(1 for r in rows if r["tier"] == k) for k in order},
        "regime": reg,
        "entries_allowed": allow,
        "chart_base": CHART,
        "results": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ok] {OUT}  —  {len(rows)} ma  {payload['counts']}")

    if rows:
        df = pd.DataFrame(rows)
        df["close_k"] = (df["close"] / 1000).round(2)
        df["pivot_k"] = (df["pivot"] / 1000).round(2)
        print(df.head(args.top)[["symbol", "tier", "close_k", "tight", "pivot_k",
                                 "to_pivot", "adtv", "off_high", "ext200"]].to_string(index=False))

    if args.telegram:
        cfg = load_config()
        lines = [f"🇻🇳 <b>Scan VCP Viet Nam</b> — {payload['scanned_at']}"]
        if allow:
            lines.append(f"🟢 <b>Duoc phep vao lenh</b> — {reg['reason']}")
        else:
            lines.append(f"🔴 <b>DUNG NGOAI — khong vao lenh nao</b>\n{reg['reason']}\n"
                         f"VN khong cho ban khong: thi truong giam thi giu tien mat.")
        if b50 is not None:
            lines.append(f"Do rong: {b50}% tren MA50 · {b200}% tren MA200")
        lines.append(f"Vu tru {payload['universe']} ma quan sat (≥ {args.obs_liq:g} ty) · "
                     f"{nsig} ma du chuan vao lenh (≥ {args.liq:g} ty)")
        bo_title = ("🎯 <b>BREAKOUT hom nay</b> — vuot pivot + khoi luong" if allow
                    else "🚫 <b>Vuot pivot hom nay</b> — CHI GHI NHAN, thi truong dang OFF")
        for t, title in ((("BREAKOUT", bo_title)),
                         ("VCP3", "🔵 <b>VCP 3 nen</b> — dang nen, cho pha vo"),
                         ("VCP2", "🟡 <b>VCP 2 nen</b> — chua dat kiem dinh, tham khao")):
            sub = [r for r in rows if r["tier"] == t]
            if not sub:
                lines += ["", f"{title}: 0 ma"]
                continue
            lines += ["", f"{title}: {len(sub)} ma"]
            for r in sub[:10]:
                lines.append(f"  <code>{r['symbol']}</code> {r['close']/1000:.2f} · nen {r['tight']}% · "
                             f"pivot {r['pivot']/1000:.2f} ({r['to_pivot']:+.1f}%) · {r['adtv']:.0f} ty")
        lines += ["", "👉 Tab Watch tren journal de xem day du"]
        send_telegram(cfg, "\n".join(lines))


if __name__ == "__main__":
    main()
