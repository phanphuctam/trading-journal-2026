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

# ── Bo sung tu bao cao SEPA-Viet-hoa (2026-08-06) ──
# Tat ca deu la LOP PHONG THU: chung khong noi cua vao lenh (3 nen + r3<10% +
# vol kho can + GTGD>=10 ty + regime ON van nguyen), chi chan bot cach thua tien
# ma backtest goc khong nhin thay vi no chi do gia dong cua.
# Bien do dao dong theo san: HOSE +-7%, HNX +-10%, UPCOM +-15%.
# (Bao cao SEPA-Viet-hoa ghi HNX +-15% — SAI, do la bien do cua UPCOM.)
CEIL = {"HOSE": 6.8, "HNX": 9.5, "UPCOM": 14.5}   # % coi nhu dong cua GIA TRAN
CEIL_DEFAULT = 6.8
CEIL_BASE_N = 60       # dem phien tran trong bao nhieu phien gan nhat
CEIL_MANIP = 4         # >= bao nhieu phien tran trong nen thi nghi "doi lai"
VOL_MIN = 100_000      # KL toi thieu (cp/phien, TB20) — chan ma gia cao it co phieu
MAX_POS_PCT = 2.0      # tran vi the = % GTGD TB20 (bao cao de xuat 1-2%)
CHASE = 5.0            # Minervini: khong mua qua 5% tren pivot
DD_LOOKBACK = 25       # cua so dem NGAY PHAN PHOI
DD_DANGER = 5          # >= bao nhieu ngay phan phoi thi coi la thi truong dang xa
FTD_GAIN = 1.5         # % tang toi thieu cua mot NGAY BUNG NO THEO DA
FTD_MIN_DAY = 4        # FTD hop le tu ngay thu 4 cua nhip no luc hoi phuc

# Noi phieu quan sat nhung GIU NGUYEN cong vao lenh:
#   - BREAKOUT van doi: 3 nen + r3<10% + vol kho can + GTGD >= 10 ty + regime ON.
#     (backtest: noi con 2 nen -> CAGR -0.78%; do chat la loi the, khong dong vao)
#   - Quan sat mo rong: GTGD >= 5 ty (co 💧), TREND trong vong 30% dinh 52T
#     (thay vi 25%) de thay nen dang hinh thanh som hon.
#   - Co 💪 "dan dat": khi thi truong OFF ma van bam sat dinh 52T — Minervini:
#     leader cua song tang sau lo dien ngay trong pha dieu chinh.
#
# LOP PHONG THU BO SUNG (2026-08-06, tu bao cao SEPA-Viet-hoa):
#   Khong lam CUA VAO LENH rong ra — chi chan bot cach thua tien ma backtest goc
#   khong nhin thay, vi no chi kiem tra gia dong cua:
#   - Quy tac 5%: vuot pivot roi nhung gia da di qua 5% -> tier BO_FAR, khong phai
#     tin hieu mua (Minervini: qua 5% thi stop rong den muc hong ty le lai/lo).
#   - 🔒 dong cua GIA TRAN: bien do +-7% lam breakout "trang ben ban" — ban khong
#     khop duoc, hom sau gap-up. Gia dong cua khong noi len dieu do.
#   - ⚑ nhieu phien tran trong nen 60 phien = van tay doi lai (wash trading).
#   - KL TB20 >= 100k co phieu, ben canh GTGD >= 10 ty.
#   - Tran vi the 2% GTGD TB20: mua hon the la tu day gia len, va luc cat lo thi
#     tu dap gia xuong.
#   - Ngay phan phoi + FTD tren VN-Index: canh bao SOM hon MA50 (chi bao tre),
#     nhung CHI la thong tin — chua backtest nen khong duoc lat cong tac tong.


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


def market_regime(idx, breadth50, breadth200):
    """Cong tac tong. ON = duoc phep vao lenh, OFF = dung ngoai.

    Quy tac: VN-Index > MA50 VA MA50 > MA200. VN khong co ban khong, nen khi
    thi truong giam thi lua chon duy nhat la khong lam gi. Do rong (breadth) chi
    de tham khao — no khong tham gia quyet dinh, tranh them bien so chua kiem dinh.

    Ngay phan phoi va FTD cung chi la THONG TIN kem theo: chung canh bao som hon
    MA50 nhung chua duoc backtest tren HOSE, nen khong duoc phep lat trang thai.
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
    ap.add_argument("--hnx", action="store_true", help="them san HNX")
    ap.add_argument("--upcom", action="store_true", help="them san UPCOM (821 ma, nhieu ma rac)")
    ap.add_argument("--all", action="store_true", help="ca ba san: HOSE + HNX + UPCOM")
    ap.add_argument("--offline", action="store_true", help="chi dung cache")
    ap.add_argument("--refresh", action="store_true", help="cap nhat 90 phien cuoi (toan bo)")
    ap.add_argument("--refresh-liquid", action="store_true",
                    help="chi cap nhat ma thanh khoan — du cho scan, nhanh hon nhieu (dung cho CI)")
    ap.add_argument("--liq", type=float, default=LIQ_MIN, help="GTGD TB20 toi thieu de vao lenh (ty)")
    ap.add_argument("--obs-liq", type=float, default=OBS_LIQ, help="GTGD TB20 toi thieu de quan sat (ty)")
    ap.add_argument("--vol-min", type=float, default=VOL_MIN,
                    help="KL TB20 toi thieu (cp/phien) de vao lenh — chan ma gia cao it co phieu")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    from vnstock import Listing
    lst = Listing().symbols_by_exchange()
    exch = ["HOSE"] + (["HNX"] if (args.hnx or args.all) else []) \
                    + (["UPCOM"] if (args.upcom or args.all) else [])
    meta = lst[(lst.exchange.isin(exch)) & (lst.type == "stock")]
    names = dict(zip(meta.symbol, meta.organ_name))
    exmap = dict(zip(meta.symbol, meta.exchange))
    syms = sorted(meta.symbol.unique())
    print(f"[i] Vu tru: {len(syms)} ma ({', '.join(exch)})")
    # Ghi lai bang san de backtest_vn_params.py dung duoc ma khong can goi API
    CACHE.mkdir(exist_ok=True)
    (CACHE / "_meta.json").write_text(
        json.dumps({"exchange": exmap, "name": names}, ensure_ascii=False), encoding="utf-8")

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
    vsh20 = vol.rolling(20).mean()          # KL TB20 tinh bang co phieu
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    hi52 = close.rolling(252).max()
    lo52 = close.rolling(252).min()
    hi_all = close.cummax()
    rng = (close.rolling(W).max() - close.rolling(W).min()) / close.rolling(W).max()
    vm = vol.rolling(W).mean()
    pivot = close.rolling(BASE_N).max().shift(1)

    # Phien dong cua GIA TRAN. Bien do +-7% (HOSE) la dac thu VN va no pha hai thu:
    #  1. Breakout dong tran = trang ben ban -> ban KHONG khop duoc, hom sau gap-up
    #     va diem vao lech xa pivot. Gia dong cua khong noi len dieu do.
    #  2. Nhieu phien tran trong nen la van tay quen thuoc cua doi lai: ho ve duoc
    #     do thi dep bang cach keo tran vai phien voi khoi luong tu doi ung.
    # TUOI NIEM YET. Minervini Ch.6: phan lon sieu co phieu tro thanh dai chung trong
    # 8-10 nam TRUOC khi bung no — cong ty non tre la "thanh phan quan trong nhat".
    # Tuoi lay tu NGAY NIEM YET THAT (fetch_listing_dates.py -> .vncache/_listing.json).
    # Khong suy tu du lieu gia duoc: nguon KBS chi tra ve ~8 nam nen VNM/FPT/HPG deu co
    # phien dau la 2018-08 du chung len san tu rat lau.
    # ⚠️ Do la ngay len SAN HIEN TAI, khong phai ngay IPO goc — ma chuyen san se tre hon
    # thuc te (AAA hien 25/11/2016 vi chuyen HNX -> HOSE nam do).
    today = pd.Timestamp(datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date())
    lf = CACHE / "_listing.json"
    listing = {}
    if lf.exists():
        listing = {k: pd.to_datetime(v, format="%d/%m/%Y", errors="coerce")
                   for k, v in json.loads(lf.read_text(encoding="utf-8")).items() if v}
    else:
        print("[!] Chua co .vncache/_listing.json — chay fetch_listing_dates.py de co tuoi niem yet")
    age_y = pd.Series({s: (today - d).days / 365.25
                       for s, d in listing.items() if pd.notna(d)})

    chg_all = close.pct_change(fill_method=None) * 100
    ceil_thr = pd.Series({s: CEIL.get(exmap.get(s, "HOSE"), CEIL_DEFAULT) for s in close.columns})
    ceil_mask = chg_all.ge(ceil_thr, axis=1)
    ceil_base = ceil_mask.rolling(CEIL_BASE_N).sum()

    # ── Chon PHIEN GAN NHAT CO DU LIEU DAY DU, khong mac dinh lay dong cuoi ──
    # Cache duoc tai lam nhieu dot nen cac ma khong cung mot ngay cuoi. Neu chi mot
    # nhom nho vua tai xong (vd 800 ma UPCOM moi) thi dong cuoi cua bang chi co nhom
    # do co gia, toan bo HOSE/HNX la NaN -> scan im lang tra ve vai ma va trong nhu
    # mot ngay khong co co hoi. Da xay ra that: scan --all lan dau chi ra 4 ma UPCOM.
    cover = close.notna().sum(axis=1)
    ok = cover >= cover.max() * 0.6
    i = int(np.nonzero(ok.to_numpy())[0][-1]) - len(close)   # chi so am tu cuoi
    d = close.index[i]
    if i != -1:
        print(f"[!] Bo qua {-i - 1} phien cuoi thieu du lieu — dung phien {d.date()} "
              f"({int(cover.iloc[i])}/{int(cover.max())} ma co gia). "
              f"Chay --refresh-liquid de cap nhat duoi cache.")
    prev = close.iloc[i - 1]
    c, v = close.iloc[i], vol.iloc[i]
    r3, r2, r1 = rng.iloc[i], rng.iloc[i - W], rng.iloc[i - 2 * W]
    v3, v1 = vm.iloc[i], vm.iloc[i - 2 * W]
    r3p, r2p = rng.iloc[i - 1], rng.iloc[i - 1 - W]
    v3p, v1p = vm.iloc[i - 1], vm.iloc[i - 1 - 2 * W]
    c_prev = close.iloc[i - 1]
    up_prev = ((c_prev > ma50.iloc[i - 1]) & (c_prev > ma200.iloc[i - 1])
               & (c_prev >= hi52.iloc[i - 1] * 0.75))

    # Chuan VAO LENH: GTGD >= --liq (nhu backtest) VA KL >= --vol-min co phieu.
    # Rang buoc KL bo sung bat truong hop GTGD dat nho gia cao nhung so co phieu
    # khop moi phien qua it — so lenh mong, cat lo la tu dap gia minh.
    liq_sig = (adtv.iloc[i] >= args.liq) & (vsh20.iloc[i] >= args.vol_min)
    liq_obs = adtv.iloc[i] >= args.obs_liq   # chuan QUAN SAT — noi phieu
    up = (c > ma50.iloc[i]) & (c > ma200.iloc[i]) & (c >= hi52.iloc[i] * 0.75)
    up_obs = (c > ma50.iloc[i]) & (c > ma200.iloc[i]) & (c >= hi52.iloc[i] * 0.70)
    vcp3 = (r1 > r2) & (r2 > r3) & (r3 < TIGHT3) & (v3 < v1) & up & liq_obs
    vcp2 = (r2 > r3) & (r3 < TIGHT2) & (v3 < v1) & up & liq_obs
    # breakout: hom qua dang o trang thai VCP, hom nay vuot pivot voi khoi luong.
    # Tin hieu vao lenh nen doi thanh khoan CHUAN (>= --liq), khong an theo nguong quan sat
    vcp3_prev = ((rng.iloc[i - 1 - 2 * W] > r2p) & (r2p > r3p) & (r3p < TIGHT3)
                 & (v3p < v1p) & up_prev)
    bo_all = vcp3_prev & (c > pivot.iloc[i]) & (v > VOL_BO * v3) & liq_sig
    # Quy tac 5% cua Minervini: vuot pivot roi nhung gia da di qua 5% thi khong con
    # la diem mua — stop bi keo qua rong, ty le lai/lo hong. Truoc day scan gop chung
    # vao BREAKOUT; gio tach rieng de khong bao "vao lenh" cho mot lenh mua duoi.
    chase_ok = c <= pivot.iloc[i] * (1 + CHASE / 100)
    bo = bo_all & chase_ok
    bo_far = bo_all & ~chase_ok

    # ── Cong tac tong (tinh truoc de gan co "dan dat" cho tung ma) ──
    nsig = int(liq_sig.sum())
    b50 = round(float(((c > ma50.iloc[i]) & liq_sig).sum()) / nsig * 100, 1) if nsig else None
    b200 = round(float(((c > ma200.iloc[i]) & liq_sig).sum()) / nsig * 100, 1) if nsig else None
    reg = market_regime(fetch_index(offline=args.offline), b50, b200)
    allow = reg["state"] == "ON"
    print(f"[i] Thi truong: {reg['state']} — {reg['reason']}"
          + (f" · do rong tren MA50 {b50}% / MA200 {b200}%" if b50 is not None else ""))
    if reg.get("dist_days") is not None:
        print(f"[i] Ngay phan phoi: {reg['dist_days']}/{DD_LOOKBACK} phien"
              + ("  ⚠️ TU {} TRO LEN LA DAU HIEU TO CHUC DANG XA".format(DD_DANGER)
                 if reg.get("dist_warn") else "")
              + (f" · FTD gan nhat {reg['ftd']['date']} (+{reg['ftd']['chg']}%, "
                 f"{reg['ftd']['ago']} phien truoc)" if reg.get("ftd") else " · chua co FTD"))

    rows = []
    for s in close.columns:
        if not bool(liq_obs.get(s, False)) or pd.isna(c.get(s)):
            continue
        if bool(bo.get(s, False)):
            tier = "BREAKOUT"
        elif bool(bo_far.get(s, False)):
            tier = "BO_FAR"
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
            "contractions": (3 if tier in ("BREAKOUT", "BO_FAR", "VCP3") else (2 if tier == "VCP2" else 0)),
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
            "lowliq": bool(adtv_s < args.liq or float(vsh20.iloc[i][s] or 0) < args.vol_min),
            "vol20": int(vsh20.iloc[i][s]) if pd.notna(vsh20.iloc[i].get(s)) else None,
            # 🔒 hom nay dong cua gia tran -> trang ben ban, gan nhu khong khop duoc
            "ceil": bool(ceil_mask.iloc[i].get(s, False)),
            # ⚑ so phien tran trong nen 60 phien — nhieu qua thi nghi ngo doi lai
            "ceil_base": int(ceil_base.iloc[i][s]) if pd.notna(ceil_base.iloc[i].get(s)) else None,
            "manip": bool(pd.notna(ceil_base.iloc[i].get(s))
                          and ceil_base.iloc[i][s] >= CEIL_MANIP),
            # Tran vi the: mua qua 2% GTGD TB20 thi chinh minh la nguoi day gia len,
            # va luc cat lo cung chinh minh dap gia xuong. Con so nay tinh bang VND.
            "max_pos": int(adtv_s * 1e9 * MAX_POS_PCT / 100),
            # % gia dang o tren pivot — > 5% la mua duoi theo Minervini
            "over_pivot": round(-to_pivot, 1) if (to_pivot is not None and to_pivot < 0) else None,
            # Tuoi niem yet (nam), None = chua lay duoc ngay niem yet cho ma nay.
            # Backtest HOSE+HNX 2018-2026: vung 2-8 nam thang 57,4% va sut giam toi da
            # -8,3%, so voi ma tren 8 nam chi thang 32,1% va sut giam -27,2%. Duoi 2 nam
            # thi te han ca hai (thang 16,7%, CAGR am) — non qua chua co nen gia tu te.
            "age": round(float(age_y[s]), 1) if s in age_y.index else None,
            "young": bool(s in age_y.index and 2 <= float(age_y[s]) <= 8),
            "tooyoung": bool(s in age_y.index and float(age_y[s]) < 2),
            # 💪 Index dang OFF ma ma nay van trong vong 5% dinh 52T. Nguong phai chat:
            # ca danh sach von da loc "tren MA50+MA200", noi ra -15% thi 19/21 ma dinh co.
            "lead": bool((not allow) and off_hi >= -5),
        })

    order = {"BREAKOUT": 0, "BO_FAR": 1, "VCP3": 2, "VCP2": 3, "TREND": 4}
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
        "vol_min": args.vol_min,
        "max_pos_pct": MAX_POS_PCT,
        "chase": CHASE,
        "ceil_manip": CEIL_MANIP,
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
        if reg.get("dist_warn"):
            lines.append(f"⚠️ <b>{reg['dist_days']} ngay phan phoi</b> trong {DD_LOOKBACK} phien — "
                         f"to chuc dang xa hang, siet chat quan tri rui ro")
        if b50 is not None:
            lines.append(f"Do rong: {b50}% tren MA50 · {b200}% tren MA200")
        lines.append(f"Vu tru {payload['universe']} ma quan sat (≥ {args.obs_liq:g} ty) · "
                     f"{nsig} ma du chuan vao lenh (≥ {args.liq:g} ty, ≥ {args.vol_min:,.0f} cp)")
        bo_title = ("🎯 <b>BREAKOUT hom nay</b> — vuot pivot + khoi luong" if allow
                    else "🚫 <b>Vuot pivot hom nay</b> — CHI GHI NHAN, thi truong dang OFF")
        for t, title in ((("BREAKOUT", bo_title)),
                         ("BO_FAR", f"⛔ <b>Vuot pivot nhung da xa &gt; {CHASE:g}%</b> — mua duoi, bo qua"),
                         ("VCP3", "🔵 <b>VCP 3 nen</b> — dang nen, cho pha vo"),
                         ("VCP2", "🟡 <b>VCP 2 nen</b> — chua dat kiem dinh, tham khao")):
            sub = [r for r in rows if r["tier"] == t]
            if not sub:
                lines += ["", f"{title}: 0 ma"]
                continue
            lines += ["", f"{title}: {len(sub)} ma"]
            for r in sub[:10]:
                fl = ("🔒" if r.get("ceil") else "") + ("⚑" if r.get("manip") else "")
                lines.append(f"  <code>{r['symbol']}</code>{fl} {r['close']/1000:.2f} · nen {r['tight']}% · "
                             f"pivot {r['pivot']/1000:.2f} ({r['to_pivot']:+.1f}%) · {r['adtv']:.0f} ty"
                             + (f" · tran vi the {r['max_pos']/1e6:.0f}tr" if t in ("BREAKOUT", "VCP3") else ""))
        if any(r.get("ceil") for r in rows):
            lines.append("")
            lines.append("🔒 = dong cua GIA TRAN: trang ben ban, gan nhu khong khop duoc — "
                         "hom sau gap-up thi diem vao da lech xa pivot, dung mua duoi.")
        lines += ["", "👉 Tab Watch tren journal de xem day du"]
        send_telegram(cfg, "\n".join(lines))


if __name__ == "__main__":
    main()
