# -*- coding: utf-8 -*-
"""Backtest tham so THOAT LENH cho chien luoc VCP Viet Nam (HOSE, 2018-2026).

MUC DICH HEP: bao cao "SEPA Viet hoa" de xuat siet stop tu 8-10% xuong 4-6% va chot
loi co hoc 1/2 vi the o +20-25%. Ca hai deu la thay doi LON va bao cao khong co so
kiem chung (nguon cua no la mot bao cao sinh vien tren Studocu). Script nay tra loi
bang chinh du lieu cua ban.

CUA VAO LENH GIU NGUYEN, khong dong vao — backtest goc da kiem dinh no:
    VCP 3 lan nen + breakout + GTGD >= 10 ty + regime ON
    -> CAGR +10,36% · MaxDD -15,9% · thang 38,6% · lai TB +25,9% · lo TB -6,9%
Script chi quet phan SAU KHI DA VAO LENH.

⚠️ DAY LA BAN DUNG LAI, KHONG PHAI SCRIPT GOC. Script goc khong con trong repo,
nen luat thoat lenh cua no phai suy ra tu ket qua da cong bo. Chay `--baseline`
de xem cau hinh nao khop nhat voi 5 con so tren; moi so sanh tham so deu doc
theo huong TUONG DOI so voi baseline do, dung doc so tuyet doi.

Ba dieu chinh mo phong dung thi truong VN, deu bat mac dinh:
  --t2       Mua T+0 thi som nhat T+2 moi ban duoc. Day la ly do chinh khien
             stop 4% co the KHONG THUC HIEN DUOC: gia da xuyen qua tu lau roi.
  --lock     Phien giam san khoa thanh khoan (trang ben mua) thi khong thoat duoc,
             phai doi phien sau. Bien do +-7% cua HOSE tao ra dung tinh huong nay.
  gap        Cham stop thi khop o min(gia mo cua, stop) — khong gia dinh khop dep.

Cach dung:
    python backtest_vn_params.py --baseline        # do lai voi ket qua da cong bo
    python backtest_vn_params.py --sweep stop      # quet stop 4/5/6/8/10/12%
    python backtest_vn_params.py --sweep tp        # quet chot loi mot phan
    python backtest_vn_params.py --sweep t2        # T+2 ton bao nhieu tien
    python backtest_vn_params.py --grid            # stop x chot loi
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from tv_common import BASE

CACHE = BASE / ".vncache"
OUT = BASE.parent / "scans" / "backtest_vn.json"
INDEX = "VNINDEX"

# ── Cua vao lenh: sao chep y nguyen scan_vn_vcp.py, KHONG chinh ──
W = 20
TIGHT3 = 0.10
BASE_N = 60
VOL_BO = 1.5
LIQ_MIN = 10.0

START = "2018-01-01"
# Von ban dau tinh bang NGHIN DONG, cung don vi voi gia trong cache (15,95 = 15.950d)
# -> gia tri vi the = so co phieu x gia, khong phai nhan them 1000 o cho nao ca.
CAP0 = 1_000_000         # = 1 ty VND. Chi de quy ra %, khong anh huong ket qua
SLOTS = 6                # so vi the toi da cung luc (bao cao de xuat 4-8)
FEE = 0.0035             # phi mua+ban+thue ~0,35% mot vong o VN
MARGIN_RATE = 0.13       # lai vay margin CTCK ~13%/nam — bo ra thi ket qua la ao

# Ket qua backtest goc, dung lam moc doi chieu cho ban dung lai
GOC = {"cagr": 10.36, "maxdd": -15.9, "win": 38.6, "avg_win": 25.9, "avg_loss": -6.9}


def load_meta():
    """Bang symbol -> san, do scan_vn_vcp.py ghi ra. Khong co thi coi het la HOSE."""
    f = CACHE / "_meta.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("exchange", {})


def load_panels(exch=None):
    """Doc toan bo cache parquet thanh cac bang date x symbol.

    exch  Danh sach san can giu, vd ["HOSE","HNX"]. None = lay tat ca dang co cache.
    """
    ex = load_meta()
    frames = []
    for f in sorted(CACHE.glob("*.parquet")):
        if f.stem == INDEX:
            continue
        if exch and ex.get(f.stem, "HOSE") not in exch:
            continue
        try:
            d = pd.read_parquet(f)
        except Exception:
            continue
        if d is None or not len(d):
            continue
        d = d.copy()
        d["symbol"] = f.stem
        frames.append(d)
    if not frames:
        raise SystemExit("[!] Cache rong — chay `python scan_vn_vcp.py` truoc de tai du lieu")
    px = pd.concat(frames, ignore_index=True)
    px["time"] = pd.to_datetime(px["time"])
    px = (px[px["time"] >= START]
          .drop_duplicates(subset=["symbol", "time"])
          .sort_values(["symbol", "time"]))
    p = {c: px.pivot(index="time", columns="symbol", values=c)
         for c in ("open", "high", "low", "close", "volume")}
    idx = None
    fi = CACHE / f"{INDEX}.parquet"
    if fi.exists():
        idx = pd.read_parquet(fi)
        idx["time"] = pd.to_datetime(idx["time"])
        idx = (idx.drop_duplicates(subset=["time"], keep="last")
                  .sort_values("time").set_index("time")["close"].astype(float))
        idx = idx.reindex(p["close"].index).ffill()
    # Phien dau tien co gia = ngay len san (chan cut o START voi ma niem yet truoc do)
    p["first"] = p["close"].notna().idxmax()
    return p, idx


def build_signals(p, liq=LIQ_MIN):
    """Tin hieu breakout VCP-3 — dinh nghia y het scan_vn_vcp.py."""
    close, vol = p["close"], p["volume"]
    adtv = ((close * 1000 * vol) / 1e9).rolling(20).mean()
    ma50, ma200 = close.rolling(50).mean(), close.rolling(200).mean()
    hi52 = close.rolling(252).max()
    rng = (close.rolling(W).max() - close.rolling(W).min()) / close.rolling(W).max()
    vm = vol.rolling(W).mean()
    pivot = close.rolling(BASE_N).max().shift(1)

    ma20, ma100 = close.rolling(20).mean(), close.rolling(100).mean()
    up = (close > ma50) & (close > ma200) & (close >= hi52 * 0.75)
    vcp3 = ((rng.shift(2 * W) > rng.shift(W)) & (rng.shift(W) > rng)
            & (rng < TIGHT3) & (vm < vm.shift(2 * W)) & up)
    entry = (vcp3.shift(1).astype("boolean").fillna(False).astype(bool)
             & (close > pivot) & (vol > VOL_BO * vm) & (adtv >= liq))
    return {"entry": entry.fillna(False), "ma50": ma50, "ma20": ma20, "ma100": ma100,
            "rng": rng, "adtv": adtv, "pivot": pivot}


def regime_on(idx):
    """Cong tac tong: VN-Index > MA50 VA MA50 > MA200."""
    if idx is None:
        return None
    ma50, ma200 = idx.rolling(50).mean(), idx.rolling(200).mean()
    return ((idx > ma50) & (ma50 > ma200)).fillna(False)


def to_numpy(p, sig, on, dates=None):
    """Doi sang mang numpy mot lan. Vong lap qua 700 ma x 2000 phien bang pandas
    mat hang chuc phut; bang numpy con vai giay."""
    cols = list(p["close"].columns)
    dates = p["close"].index if dates is None else dates
    a = {k: p[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close")}
    for m in ("ma20", "ma50", "ma100"):
        a[m] = sig[m].to_numpy(dtype=float)
    a["rng"] = np.nan_to_num(sig["rng"].to_numpy(dtype=float), nan=9.0)
    a["entry"] = sig["entry"].to_numpy(dtype=bool)
    a["on"] = (on.to_numpy(dtype=bool) if on is not None
               else np.ones(len(p["close"]), dtype=bool))
    # Vi tri phien dau tien co gia -> tuoi niem yet tai phien k = (k - first_k)/252.
    # ⚠️ Ma da niem yet TRUOC khi cache bat dau co first_k = 0, va luc do cong thuc
    # tren cho ra tuoi SAI (ma len san 2010 se thanh "1,5 tuoi" vao nam 2019).
    # Danh dau chung bang -1 de coi la "gia / khong ro tuoi", khong bao gio lot vao
    # nhom non tre. Chi ma len san sau START moi co tuoi that.
    # TUOI NIEM YET lay tu NGAY NIEM YET THAT (fetch_listing_dates.py), khong suy tu
    # du lieu gia: nguon KBS chi tra ve ~8 nam nen VNM/FPT/HPG deu co phien dau la
    # 2018-08 du chung len san tu rat lau — suy tu gia se cho ket qua vo nghia.
    # ⚠️ listing_date la ngay len SAN HIEN TAI, khong phai ngay IPO goc: ma chuyen san
    # se tre hon thuc te (AAA hien 25/11/2016 vi chuyen HNX -> HOSE nam do).
    ld = {}
    f = CACHE / "_listing.json"
    if f.exists():
        raw = json.loads(f.read_text(encoding="utf-8"))
        ld = {k: pd.Timestamp(pd.to_datetime(v, format="%d/%m/%Y", errors="coerce"))
              for k, v in raw.items() if v}
    a["list_day"] = np.array(
        [ld[s].value / 86_400e9 if ld.get(s) is not None and pd.notna(ld.get(s)) else np.nan
         for s in cols])
    a["date_day"] = dates.astype("int64").to_numpy() / 86_400e9
    a["n_known_age"] = int(np.sum(~np.isnan(a["list_day"])))
    return cols, a


def _age(a, j, k):
    """Tuoi niem yet (nam) tai phien k. 99 = chua lay duoc ngay niem yet cho ma nay
    -> coi nhu co phieu gia, khong bao gio lot vao nhom non tre."""
    d = a["list_day"][j]
    return 99.0 if np.isnan(d) else (a["date_day"][k] - d) / 365.25


def run(cols, a, dates, stop_pct, tp_pct=None, tp_frac=0.5, trail_ma50=True,
        slots=SLOTS, t2=True, lock=True, hold_max=None, lev=1.0, trail_ma="ma50",
        min_age=None, max_age=None):
    """Chay mot cau hinh thoat lenh. Tra ve dict chi so + danh sach lenh.

    Thu tu kiem tra trong mot phien la XAU NHAT truoc (stop truoc chot loi) — khong
    biet dien bien trong phien nen phai gia dinh bat loi, tranh backtest dep gia.

    lev       Don bay (margin). lev=2 nghia la mua toi 2 lan von. Tien vay TINH LAI
              theo MARGIN_RATE — bo lai vay ra thi ket qua la ao.
    trail_ma  Duong trung binh dung lam luat thoat: ma20 (chat) / ma50 / ma100 (rong).
              Rong hon = de cho lenh thang chay xa hon, doi lai tra lai nhieu hon.
    """
    C, O, H, L = a["close"], a["open"], a["high"], a["low"]
    MA = a[trail_ma] if trail_ma else None
    RNG, ENT, ON = a["rng"], a["entry"], a["on"]
    nd = len(dates)
    cash, pos, trades = float(CAP0), {}, []
    eq = np.empty(nd)
    daily_rate = MARGIN_RATE / 252

    for k in range(nd):
        if k < 260:
            eq[k] = cash
            continue
        if cash < 0:                       # lai vay margin, tinh theo ngay
            cash += cash * daily_rate
        Ck = C[k]

        # ── 1. Thoat lenh ──
        for j in list(pos):
            q = pos[j]
            if t2 and k - q["k"] < 2:          # chua ve tai khoan, khong ban duoc
                continue
            cl, o, h, l = Ck[j], O[k, j], H[k, j], L[k, j]
            if np.isnan(cl):
                continue
            pc = C[k - 1, j]
            # Phien giam san khoa thanh khoan: bien do gan bang 0 va giam sau
            if (lock and not np.isnan(pc) and not np.isnan(h) and not np.isnan(l)
                    and (h - l) / pc < 0.005 and (cl / pc - 1) <= -0.065):
                continue

            px_out, why = None, None
            if not np.isnan(l) and l <= q["stop"]:
                px_out = min(o, q["stop"]) if not np.isnan(o) else q["stop"]
                why = "stop"
            elif tp_pct and not q["tp"] and not np.isnan(h) and h >= q["px"] * (1 + tp_pct / 100):
                tgt = q["px"] * (1 + tp_pct / 100)
                n = int(q["n"] * tp_frac)
                if n > 0:
                    cash += n * tgt * (1 - FEE / 2)
                    q["n"] -= n
                    q["part"] = (tgt / q["px"] - 1) * 100
                q["tp"] = True
                q["stop"] = max(q["stop"], q["px"])       # phan con lai ve hoa von
                if q["n"] <= 0:
                    px_out, why = tgt, "tp"
            if px_out is None and trail_ma50 and MA is not None and not np.isnan(MA[k, j]) and cl < MA[k, j]:
                px_out, why = cl, trail_ma
            if px_out is None and hold_max and k - q["k"] >= hold_max:
                px_out, why = cl, "hold"

            if px_out is not None:
                cash += q["n"] * px_out * (1 - FEE / 2)
                ret = (px_out / q["px"] - 1) * 100
                if q["part"] is not None:                  # da chot mot phan truoc do
                    ret = q["part"] * tp_frac + ret * (1 - tp_frac)
                trades.append({"sym": cols[j], "in": str(dates[q["k"]].date()),
                               "out": str(dates[k].date()), "days": k - q["k"],
                               "age": q["age"], "ret": round(ret - FEE * 100, 2),
                               "why": why})
                del pos[j]

        mv = sum(pos[x]["n"] * (Ck[x] if not np.isnan(Ck[x]) else pos[x]["px"]) for x in pos)

        # ── 2. Vao lenh ──
        free = slots - len(pos)
        if free > 0 and ON[k]:
            cand = [j for j in np.nonzero(ENT[k])[0] if j not in pos]
            if min_age is not None or max_age is not None:
                lo = -np.inf if min_age is None else min_age
                hi = np.inf if max_age is None else max_age
                cand = [j for j in cand if lo <= _age(a, j, k) <= hi]
            cand.sort(key=lambda j: RNG[k, j])             # nen chat nhat truoc
            for j in cand[:free]:
                px_in = Ck[j]
                if np.isnan(px_in) or px_in <= 0:
                    continue
                equity = cash + mv
                if equity <= 0:                       # chay het von, khong mua nua
                    break
                # Suc mua con lai = von x don bay - gia tri dang nam giu.
                # Voi lev=1 thi rut gon dung ve `cash`, tuc khong duoc am tien.
                budget = min(equity * lev / slots, equity * lev - mv)
                n = int(budget / px_in)
                if n <= 0:
                    continue
                cash -= n * px_in * (1 + FEE / 2)
                pos[j] = {"n": n, "px": px_in, "k": k, "age": round(_age(a, j, k), 1),
                          "stop": px_in * (1 - stop_pct / 100), "tp": False, "part": None}
                mv += n * px_in

        eq[k] = cash + sum(pos[x]["n"] * (Ck[x] if not np.isnan(Ck[x]) else pos[x]["px"])
                           for x in pos)

    return metrics(pd.Series(eq, index=dates), trades, nd)


def metrics(eq, trades, n):
    """CAGR / sut giam toi da / thang thua — cung bo so voi backtest goc."""
    eq = eq.replace(0, np.nan).ffill().fillna(CAP0)
    yrs = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = ((eq.iloc[-1] / CAP0) ** (1 / yrs) - 1) * 100
    dd = (eq / eq.cummax() - 1) * 100
    r = pd.Series([t["ret"] for t in trades], dtype=float)
    win = r[r > 0]
    loss = r[r <= 0]
    dr = eq.pct_change().dropna()
    return {
        "trades": len(trades),
        "per_year": round(len(trades) / yrs, 1),
        "cagr": round(cagr, 2),
        "maxdd": round(dd.min(), 1),
        "win": round(len(win) / len(r) * 100, 1) if len(r) else 0.0,
        "avg_win": round(win.mean(), 1) if len(win) else 0.0,
        "avg_loss": round(loss.mean(), 1) if len(loss) else 0.0,
        "payoff": round(abs(win.mean() / loss.mean()), 2) if len(win) and len(loss) and loss.mean() else None,
        "expectancy": round(r.mean(), 2) if len(r) else 0.0,
        "sharpe": round(dr.mean() / dr.std() * np.sqrt(252), 2) if dr.std() else None,
        "avg_days": round(np.mean([t["days"] for t in trades]), 1) if trades else 0,
        "final": round(eq.iloc[-1] / CAP0, 2),
        "_trades": trades,
    }


def show(rows, title, note=""):
    print(f"\n{title}")
    if note:
        print(f"  {note}")
    hdr = f"{'cau hinh':<26}{'lenh':>5}{'/nam':>6}{'CAGR%':>8}{'MaxDD%':>8}{'thang%':>8}{'laiTB':>7}{'loTB':>7}{'l/l':>6}{'kyvong':>8}{'Sharpe':>8}"
    print("  " + hdr)
    print("  " + "-" * len(hdr))
    for name, m in rows:
        print(f"  {name:<26}{m['trades']:>5}{m['per_year']:>6}{m['cagr']:>8}{m['maxdd']:>8}"
              f"{m['win']:>8}{m['avg_win']:>7}{m['avg_loss']:>7}"
              f"{(m['payoff'] if m['payoff'] is not None else 0):>6}{m['expectancy']:>8}"
              f"{(m['sharpe'] if m['sharpe'] is not None else 0):>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", choices=["stop", "tp", "t2", "slots", "liq", "age", "exch", "lev"],
                    help="quet mot tham so")
    ap.add_argument("--exch", default=None,
                    help="san can dung, vd HOSE hoac HOSE,HNX,UPCOM (mac dinh: tat ca dang co cache)")
    ap.add_argument("--liq", type=float, default=LIQ_MIN, help="nguong GTGD TB20 (ty)")
    ap.add_argument("--lev", type=float, default=1.0, help="don bay (2 = vay bang von)")
    ap.add_argument("--trail", default="ma50", choices=["ma20", "ma50", "ma100"])
    ap.add_argument("--grid", action="store_true", help="quet stop x chot loi")
    ap.add_argument("--baseline", action="store_true", help="do ban dung lai voi ket qua goc")
    ap.add_argument("--stop", type=float, default=8.0)
    ap.add_argument("--tp", type=float, default=None, help="chot mot phan o +X%%")
    ap.add_argument("--tp-frac", type=float, default=0.5)
    ap.add_argument("--slots", type=int, default=SLOTS)
    ap.add_argument("--no-t2", action="store_true", help="bo rang buoc T+2 (de do xem no ton bao nhieu)")
    ap.add_argument("--no-lock", action="store_true", help="bo mo phong phien giam san khoa thanh khoan")
    ap.add_argument("--no-trail", action="store_true", help="bo luat thoat khi thung MA50")
    args = ap.parse_args()

    print("[i] Doc cache…")
    exch = [e.strip().upper() for e in args.exch.split(",")] if args.exch else None
    p, idx = load_panels(exch)
    print(f"[i] {p['close'].shape[1]} ma · {p['close'].shape[0]} phien "
          f"({p['close'].index[0].date()} → {p['close'].index[-1].date()})"
          + (f" · san: {', '.join(exch)}" if exch else " · tat ca san dang co cache"))
    on = regime_on(idx)
    dates = p["close"].index
    if on is None:
        print("[!] Khong co VNINDEX trong cache — chay khong co cong tac tong")

    def prep(liq):
        """Dung lai tin hieu voi mot nguong thanh khoan khac."""
        return to_numpy(p, build_signals(p, liq=liq), on)

    cols, arr = prep(args.liq)
    base = dict(slots=args.slots, t2=not args.no_t2, lock=not args.no_lock,
                trail_ma50=not args.no_trail, lev=args.lev, trail_ma=args.trail)
    rows, out = [], {}

    if args.baseline:
        # Luat thoat cua script goc khong con — thu vai bien the, xem cai nao khop
        # 5 con so da cong bo. Cai khop nhat se la moc de doc cac quet ben duoi.
        # Chi thu cac bien the CO luat thoat theo MA50: bo trail di thi lenh thang
        # khong bao gio dong, backtest thanh vo nghia (thang 0%, chi con lenh cham stop).
        for name, kw in [("stop 8% · 6 vi the", dict(stop_pct=8, slots=6)),
                         ("stop 10% · 6 vi the", dict(stop_pct=10, slots=6)),
                         ("stop 8% · 8 vi the", dict(stop_pct=8, slots=8)),
                         ("stop 10% · 8 vi the", dict(stop_pct=10, slots=8))]:
            kw.setdefault("trail_ma50", True)
            m = run(cols, arr, dates, **{**base, **kw})
            rows.append((name, m))
        show(rows, "── BAN DUNG LAI vs BACKTEST GOC ──",
             f"goc: CAGR {GOC['cagr']}% · MaxDD {GOC['maxdd']}% · thang {GOC['win']}% · "
             f"lai TB {GOC['avg_win']}% · lo TB {GOC['avg_loss']}%")
        print("\n  Doc: cau hinh nao gan 5 con so tren nhat thi coi la baseline. Neu khong cai nao\n"
              "  gan, ban dung lai LECH so voi script goc — luc do chi duoc doc CHENH LECH giua\n"
              "  cac cau hinh ben duoi, tuyet doi khong doc so tuyet doi.")

    elif args.sweep == "stop":
        for s in (4, 5, 6, 8, 10, 12):
            rows.append((f"stop {s}%", run(cols, arr, dates, stop_pct=s, tp_pct=args.tp,
                                           tp_frac=args.tp_frac, **base)))
        show(rows, "── QUET STOP LOSS ──",
             "Bao cao de xuat siet ve 4-6%. Cot MaxDD va ky vong quyet dinh, khong phai CAGR.")

    elif args.sweep == "tp":
        rows.append(("khong chot som", run(cols, arr, dates, stop_pct=args.stop, **base)))
        for t in (15, 20, 25, 30):
            rows.append((f"chot {args.tp_frac:.0%} o +{t}%",
                         run(cols, arr, dates, stop_pct=args.stop, tp_pct=t,
                             tp_frac=args.tp_frac, **base)))
        show(rows, "── QUET CHOT LOI MOT PHAN ──",
             f"stop giu {args.stop:g}%. Bao cao de xuat chot 1/2 o +20-25% (lai TB goc la +25,9%).")

    elif args.sweep == "t2":
        for nm, kw in [("co T+2 (that)", dict(t2=True, lock=True)),
                       ("co T+2, khong khoa san", dict(t2=True, lock=False)),
                       ("khong T+2 (nhu My)", dict(t2=False, lock=False))]:
            rows.append((nm, run(cols, arr, dates, stop_pct=args.stop,
                                 tp_pct=args.tp, tp_frac=args.tp_frac,
                                 **{**base, **kw})))
        show(rows, "── T+2,5 VA BIEN DO SAN TON BAO NHIEU TIEN ──",
             f"stop {args.stop:g}%. Chenh lech giua dong dau va dong cuoi la cai gia cua cau truc thi truong VN.")

    elif args.sweep == "liq":
        # Ha nguong = mo cua cho von hoa nho, noi cac cu chay lon thuong nam.
        # Doi lai: so lenh phinh ra ma chat luong co the loang, va truot gia that
        # (backtest khong do duoc truot gia) se an vao phan lai them.
        for q in (1, 2, 3, 5, 10, 20):
            c2, a2 = prep(q)
            rows.append((f"GTGD >= {q} ty", run(c2, a2, dates, stop_pct=args.stop,
                                                tp_pct=args.tp, tp_frac=args.tp_frac, **base)))
        show(rows, "── QUET NGUONG THANH KHOAN ──",
             "⚠️ Backtest KHONG mo phong truot gia. Ma 1-3 ty thuc te se te hon bang nay.")

    elif args.sweep == "age":
        # Minervini Ch.6: cong ty non tre la "thanh phan quan trong nhat".
        # Tuoi chi biet duoc voi ma len san SAU khi cache bat dau (2018).
        for nm, kw in [("tat ca", {}),
                       ("chi <= 2 nam tuoi", dict(max_age=2)),
                       ("chi <= 3 nam tuoi", dict(max_age=3)),
                       ("chi <= 5 nam tuoi", dict(max_age=5)),
                       ("chi ma cu (>= 8 nam)", dict(min_age=8))]:
            rows.append((nm, run(cols, arr, dates, stop_pct=args.stop, tp_pct=args.tp,
                                 tp_frac=args.tp_frac, **{**base, **kw})))
        show(rows, "── TUOI NIEM YET ──",
             "Ma len san truoc 2018 khong biet tuoi that -> luon roi vao nhom 'cu'.")
        m = run(cols, arr, dates, stop_pct=args.stop, **base)
        yg = [t for t in m["_trades"] if t["age"] < 90]
        if yg:
            print(f"\n  Trong {len(m['_trades'])} lenh co {len(yg)} lenh o ma len san sau 2018 "
                  f"(loi TB {np.mean([t['ret'] for t in yg]):+.1f}% so voi "
                  f"{np.mean([t['ret'] for t in m['_trades'] if t['age'] >= 90]):+.1f}% cua ma cu)")

    elif args.sweep == "exch":
        for e in (["HOSE"], ["HOSE", "HNX"], ["HOSE", "HNX", "UPCOM"], ["HNX"], ["UPCOM"]):
            try:
                p2, i2 = load_panels(e)
            except SystemExit:
                print(f"  (bo qua {'+'.join(e)} — chua co ma nao trong cache)")
                continue
            if p2["close"].shape[1] < 5:
                continue
            c2, a2 = to_numpy(p2, build_signals(p2, liq=args.liq), regime_on(i2))
            rows.append(("+".join(e), run(c2, a2, p2["close"].index, stop_pct=args.stop,
                                          tp_pct=args.tp, tp_frac=args.tp_frac, **base)))
        show(rows, "── MO RONG SAN ──", f"nguong thanh khoan {args.liq:g} ty")

    elif args.sweep == "lev":
        for L in (1, 1.5, 2, 3):
            rows.append((f"don bay {L:g}x", run(cols, arr, dates, stop_pct=args.stop,
                                                tp_pct=args.tp, tp_frac=args.tp_frac,
                                                **{**base, "lev": L})))
        show(rows, "── DON BAY ──", f"da tru lai vay margin {MARGIN_RATE:.0%}/nam")

    elif args.sweep == "slots":
        for n in (4, 6, 8, 12):
            rows.append((f"{n} vi the", run(cols, arr, dates, stop_pct=args.stop,
                                            tp_pct=args.tp, tp_frac=args.tp_frac,
                                            **{**base, "slots": n})))
        show(rows, "── SO VI THE CUNG LUC ──", "Bao cao de xuat 4-8 ma do tuong quan beta cao.")

    elif args.grid:
        for s in (5, 6, 8, 10):
            for t in (None, 20, 25):
                nm = f"stop {s}% · " + ("giu het" if t is None else f"chot 1/2 +{t}%")
                rows.append((nm, run(cols, arr, dates, stop_pct=s, tp_pct=t,
                                     tp_frac=args.tp_frac, **base)))
        show(rows, "── LUOI STOP x CHOT LOI ──")

    else:
        m = run(cols, arr, dates, stop_pct=args.stop, tp_pct=args.tp,
                tp_frac=args.tp_frac, **base)
        nm = f"stop {args.stop:g}%" + (f" · chot {args.tp_frac:.0%} o +{args.tp:g}%" if args.tp else "")
        rows.append((nm, m))
        show(rows, "── MOT CAU HINH ──")
        print("\n  10 lenh gan nhat:")
        for t in m["_trades"][-10:]:
            print(f"    {t['in']} → {t['out']}  {t['sym']:<5} {t['ret']:>7.2f}%  "
                  f"{t['days']:>3} phien  ({t['why']})")

    out = {name: {k: v for k, v in m.items() if k != "_trades"} for name, m in rows}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[ok] {OUT}")


if __name__ == "__main__":
    main()
