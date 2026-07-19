# -*- coding: utf-8 -*-
"""Scan Trend Template (Mark Minervini) + RS Rating + phan bac theo 3 screen cua user.

Vong 1 — cong ky thuat (noi long theo screen rong nhat cua user):
  gia > SMA50 > SMA150 > SMA200, tren day 52W >= 20%, cach dinh 52W <= 30%,
  Perf.3M > 0, gia > 10 USD, KLTB 30 ngay > 300K, RS Rating >= nguong (mac dinh 70)

Vong 2 — gan nhan tier theo fundamentals (uu tien tu cao xuong):
  🏆 SEPA  : Perf.3M>=20, Perf.6M>=30, Revenue QYoY>=20%, EPS QoQ>=40%, EPS QYoY>=40%
             (= screen "Mark Minervini" cua user)
  🚀 EARLY : Perf.3M>=10, Perf.6M>=20, EPS QoQ>=20%, ROE>=15%
             (= screen "Early Stage 2")
  🌱 IPO   : niem yet <=5 nam (Perf.5Y == Perf.All) + gross margin FY >= 20%
             (= screen "IPO Base")
  📈 TREND : chi dat ky thuat — khong bi loai, chi xep sau

Vong 3 — do DO CAN (extension) de uu tien nen 1/nen 2 thay vi nen 3/nen 4:
  ext50 / ext200 : gia cao hon SMA50 / SMA200 bao nhieu % (nen cang cao = nen cang muon)
  rs_new         : RS 3 thang tru RS 12 thang — suc manh VUA MOI xuat hien
  🎯 early2      : ext200<=30, tren day 52W<=100%, rs_new>=15, cach dinh<=15%
                   => chan dung dien hinh cua co phieu dau Stage 2 (nen 1-2)
  ⚠️ extended    : ext50>15 (mua duoi) hoac ext200>50 (nen cao)
  score          : RS - 0.6*ext200 + 0.5*rs_new — chi dung de xep hang TRONG nhom
                   nen som. Phan con lai giu nguyen thu tu cu (tier -> RS).
                   Nen som la nhom THEM VAO dau bang, khong loai bo nen 3-4.

Khong bao gio "trang tay": tier tren 0 ma thi van thay tier duoi.
(Tieu chi "SMA200 doc len 1 thang" API khong ho tro — proxy bang Perf.3M > 0)

Cach dung:
    python scan_trend_template.py                 # scan + gui Telegram + push
    python scan_trend_template.py --rs 80         # nguong RS >= 80
    python scan_trend_template.py --no-telegram --no-push   # chay thu
"""
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
from tradingview_screener import Query, col

from tv_common import BASE, load_config, send_telegram

SCAN_DIR = BASE / "scans"
ROOT = BASE.parent
SITE_SCAN = ROOT / "scans" / "latest.json"
VN = ZoneInfo("Asia/Ho_Chi_Minh")

LIQUID_FILTERS = [
    col("type") == "stock",
    col("is_primary") == True,  # noqa: E712
    col("close") > 10,
    col("average_volume_30d_calc") > 300_000,
]

TIER_ORDER = {"SEPA": 0, "EARLY": 1, "IPO": 2, "TREND": 3}
TIER_BADGE = {"SEPA": "🏆", "EARLY": "🚀", "IPO": "🌱", "TREND": ""}


def rs_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """RS Rating kieu IBD + RS 3 thang / 12 thang rieng.

    RS   : quy gan nhat trong so gap doi, xep percentile 1-99 (nhu cu).
    RS3  : percentile rieng cua Perf.3M.
    RS12 : percentile rieng cua Perf.Y.
    RS3 - RS12 lon = suc manh moi xuat hien gan day (dau Stage 2), khac han
    co phieu manh deu ca nam (da o nen 3-4) co hieu ~ 0.
    """
    p3, p6, py = (df[c].fillna(0) for c in ("Perf.3M", "Perf.6M", "Perf.Y"))
    pct = lambda s: (s.rank(pct=True) * 98 + 1).round(0).astype(int)  # noqa: E731
    return pd.DataFrame({"RS": pct(2 * p3 + p6 + py), "RS3": pct(p3), "RS12": pct(py)},
                        index=df.index)


def fetch_universe() -> pd.DataFrame:
    """Toan bo co phieu My du thanh khoan — dung lam mau so tinh RS percentile."""
    _, df = (
        Query()
        .select("name", "Perf.3M", "Perf.6M", "Perf.Y")
        .where(*LIQUID_FILTERS)
        .set_markets("america")
        .limit(8000)
        .get_scanner_data()
    )
    return df


def fetch_trend_template() -> pd.DataFrame:
    _, df = (
        Query()
        .select(
            "name", "description", "close", "change", "volume",
            "average_volume_30d_calc", "market_cap_basic", "sector",
            "SMA50", "SMA150", "SMA200",
            "price_52_week_high", "price_52_week_low",
            "Perf.3M", "Perf.6M", "Perf.Y", "Perf.5Y", "Perf.All",
            "total_revenue_yoy_growth_fq",
            "earnings_per_share_diluted_yoy_growth_fq",
            "earnings_per_share_diluted_qoq_growth_fq",
            "gross_margin_fy", "return_on_equity",
        )
        .where(
            *LIQUID_FILTERS,
            col("close") > col("SMA50"),
            col("SMA50") > col("SMA150"),
            col("SMA150") > col("SMA200"),
            col("close").above_pct("price_52_week_low", 1.20),
            col("close").above_pct("price_52_week_high", 0.70),
            col("Perf.3M") > 0,
        )
        .set_markets("america")
        .limit(2000)
        .get_scanner_data()
    )
    return df


def add_extension(df: pd.DataFrame) -> pd.DataFrame:
    """Do do can cua gia so voi MA — de biet co phieu dang o nen may.

    ext200 <= 30%  ~ nen 1-2 (vua thoat vung tich luy)
    ext200 30-50%  ~ nen 2-3
    ext200 > 50%   ~ da can, rui ro mua dinh
    ext50  > 15%   ~ mua duoi, cho hoi ve MA50
    """
    num = lambda c: pd.to_numeric(df[c], errors="coerce")  # noqa: E731
    df["ext50"] = ((num("close") / num("SMA50") - 1) * 100).round(1)
    df["ext200"] = ((num("close") / num("SMA200") - 1) * 100).round(1)
    df["rs_new"] = (df["RS3"] - df["RS12"]).astype(int)
    return df


def classify(df: pd.DataFrame):
    """Gan tier theo 3 screen TradingView cua user. NaN tu dong khong dat."""
    num = lambda c: pd.to_numeric(df[c], errors="coerce")  # noqa: E731
    p3, p6 = num("Perf.3M"), num("Perf.6M")
    rev_yoy = num("total_revenue_yoy_growth_fq")
    eps_yoy = num("earnings_per_share_diluted_yoy_growth_fq")
    eps_qoq = num("earnings_per_share_diluted_qoq_growth_fq")
    roe = num("return_on_equity")
    gm = num("gross_margin_fy")
    # Niem yet <= 5 nam: TradingView dien Perf.5Y = Perf.All khi lich su ngan hon 5 nam
    young = (num("Perf.5Y") - num("Perf.All")).abs() < 1e-6

    sepa = (p3 >= 20) & (p6 >= 30) & (rev_yoy >= 20) & (eps_qoq >= 40) & (eps_yoy >= 40)
    early = (p3 >= 10) & (p6 >= 20) & (eps_qoq >= 20) & (roe >= 15)
    ipo = young & (gm >= 20)

    tier = pd.Series("TREND", index=df.index)
    tier[ipo] = "IPO"
    tier[early] = "EARLY"
    tier[sepa] = "SEPA"

    # Nen som (dau Stage 2): chua can so voi MA200, chua nhan doi tu day,
    # suc manh vua moi xuat hien, nhung van sat dinh 52W.
    early2 = (
        (df["ext200"] <= 30)
        & (df["above_low_%"] <= 100)
        & (df["rs_new"] >= 15)
        & (df["off_high_%"] >= -15)
        & (p3 > 0)
    ).fillna(False)
    return tier, young, early2


def chart_url(cfg: dict, ticker: str) -> str:
    """Link mo chart TradingView; dung layout rieng cua user neu co cau hinh."""
    layout = (cfg.get("chart_layout_id") or "").strip()
    base = f"https://www.tradingview.com/chart/{layout}/" if layout else "https://www.tradingview.com/chart/"
    return f"{base}?symbol={quote(ticker, safe='')}"


def write_site_json(cfg: dict, df: pd.DataFrame, scanned_at: str, rs_min: int):
    """Ghi scans/latest.json o goc repo de journal tren GitHub Pages doc duoc."""
    layout = (cfg.get("chart_layout_id") or "").strip()
    chart_base = f"https://www.tradingview.com/chart/{layout}/" if layout else "https://www.tradingview.com/chart/"
    # Ma nen som phan lon nam o tier TREND nen se bi head(60) cat sach neu chi
    # sort theo tier — phai giu lai TAT CA va dua len dau danh sach.
    df = pd.concat([df[df["early2"]], df[~df["early2"]].head(60)]).drop_duplicates("name")
    results = [
        {
            "symbol": r["name"], "ticker": r["ticker"], "desc": r["description"],
            "sector": r["sector"], "close": round(float(r["close"]), 2),
            "change": round(float(r["change"]), 2), "rs": int(r["RS"]),
            "off_high": float(r["off_high_%"]), "above_low": float(r["above_low_%"]),
            "tier": r["tier"], "young": bool(r["young"]),
            "early2": bool(r["early2"]), "extended": bool(r["extended"]),
            "ext50": float(r["ext50"]), "ext200": float(r["ext200"]),
            "rs_new": int(r["rs_new"]), "score": float(r["score"]),
        }
        for _, r in df.iterrows()
    ]
    SITE_SCAN.parent.mkdir(exist_ok=True)
    with open(SITE_SCAN, "w", encoding="utf-8") as f:
        json.dump({"app": "tj-scan", "scanned_at": scanned_at, "rs_min": rs_min,
                   "total": len(df), "chart_base": chart_base, "results": results},
                  f, ensure_ascii=False, indent=1)
    print(f"Da ghi {SITE_SCAN.relative_to(ROOT)}")


def push_site_json():
    """Commit + push scans/latest.json de GitHub Pages tu deploy."""
    rel = str(SITE_SCAN.relative_to(ROOT)).replace("\\", "/")
    try:
        # git pull bi treo tren may nay — dung fetch + rebase tach buoc
        subprocess.run(["git", "-C", str(ROOT), "fetch", "origin"],
                       capture_output=True, timeout=120)
        subprocess.run(["git", "-C", str(ROOT), "rebase", "--autostash", "origin/main"],
                       capture_output=True, timeout=60)
        subprocess.run(["git", "-C", str(ROOT), "add", rel], check=True, capture_output=True)
        r = subprocess.run(
            ["git", "-C", str(ROOT), "commit", "-m",
             f"Daily scan {datetime.now(VN):%Y-%m-%d}", "--", rel],
            capture_output=True, text=True)
        if r.returncode != 0:
            print("Khong co thay doi de commit (hoac loi):", (r.stdout + r.stderr).strip()[:200])
            return
        p = subprocess.run(["git", "-C", str(ROOT), "push"], capture_output=True, text=True, timeout=120)
        if p.returncode == 0:
            print("Da push len GitHub — GitHub Pages se tu deploy sau ~1 phut.")
        else:
            print("[!] Push loi:", (p.stdout + p.stderr).strip()[:300])
    except Exception as e:
        print("[!] Git loi:", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15, help="so ma gui qua Telegram")
    ap.add_argument("--rs", type=int, default=70, help="nguong RS Rating toi thieu")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--no-push", action="store_true", help="khong commit/push scans/latest.json")
    args = ap.parse_args()

    cfg = load_config()

    print("Dang tai universe de tinh RS Rating...")
    uni = fetch_universe()
    rs = rs_ratings(uni)
    rs.index = uni["name"]
    print(f"  {len(uni)} ma trong universe.")

    print("Dang scan Trend Template...")
    df = fetch_trend_template()
    print(f"  {len(df)} ma qua 6 tieu chi gia/MA.")

    for c in ("RS", "RS3", "RS12"):
        df[c] = df["name"].map(rs[c])
    df = df[df["RS"] >= args.rs].copy()
    df["off_high_%"] = ((df["close"] / df["price_52_week_high"] - 1) * 100).round(1)
    df["above_low_%"] = ((df["close"] / df["price_52_week_low"] - 1) * 100).round(0)
    df = add_extension(df)
    df["tier"], df["young"], df["early2"] = classify(df)
    df["extended"] = (df["ext50"] > 15) | (df["ext200"] > 50)
    df["score"] = (df["RS"]
                   - 0.6 * df["ext200"].clip(lower=0, upper=100).fillna(0)
                   + 0.5 * df["rs_new"]).round(1)
    df["_tier_rank"] = df["tier"].map(TIER_ORDER)
    # THEM nhom nen som len dau, KHONG dong vao thu tu cu cua phan con lai:
    #   nhom 1 = 🎯 nen som, sort theo score (uu tien suc manh moi noi, it can)
    #   nhom 2 = tat ca ma con lai, giu nguyen sort cu (tier -> RS giam dan)
    # Nho vay co phieu nen 3-4 manh (DELL, LQDA...) van o dung vi tri cu cua no.
    df = pd.concat([
        df[df["early2"]].sort_values("score", ascending=False),
        df[~df["early2"]].sort_values(["_tier_rank", "RS"], ascending=[True, False]),
    ]).reset_index(drop=True)
    counts = df["tier"].value_counts()
    print(f"  {len(df)} ma dat RS >= {args.rs}: "
          + " | ".join(f"{t} {counts.get(t, 0)}" for t in TIER_ORDER)
          + f" || 🎯 nen som {int(df['early2'].sum())} | ⚠️ da can {int(df['extended'].sum())}")

    # Luu ket qua
    now_vn = datetime.now(VN)
    scanned_at = now_vn.strftime("%d/%m/%Y %H:%M") + " (VN)"
    SCAN_DIR.mkdir(exist_ok=True)
    today = now_vn.strftime("%Y-%m-%d")
    out_cols = ["name", "ticker", "tier", "young", "early2", "extended", "description", "sector",
                "close", "change", "RS", "rs_new", "score", "ext50", "ext200",
                "off_high_%", "above_low_%", "volume", "market_cap_basic"]
    df[out_cols].to_csv(SCAN_DIR / f"scan_{today}.csv", index=False, encoding="utf-8-sig")
    df[out_cols].to_json(SCAN_DIR / f"scan_{today}.json", orient="records", force_ascii=False, indent=2)
    print(f"Da luu: automation/scans/scan_{today}.csv / .json")

    # JSON cho journal tren GitHub Pages (+ commit/push de site tu cap nhat)
    write_site_json(cfg, df, scanned_at, args.rs)
    if not args.no_push:
        push_site_json()

    # Bao cao "moi lot vao hom nay" so voi lan scan truoc
    prev_files = sorted(SCAN_DIR.glob("scan_*.json"))
    new_names = set()
    if len(prev_files) >= 2:
        prev = pd.read_json(prev_files[-2])
        new_names = set(df["name"]) - set(prev["name"])

    def fmt_row(r, show_tier=False):
        flag = " 🆕" if r["name"] in new_names else ""
        seed = " 🌱" if r["young"] and r["tier"] != "IPO" else ""
        base = " 🎯" if r["early2"] else ""
        hot = " ⚠️" if r["extended"] else ""
        tag = f" [{r['tier']}]" if show_tier else ""
        link = chart_url(cfg, r["ticker"])
        return (f"<a href=\"{link}\"><b>{r['name']}</b></a>{base}{seed}{hot}{flag}{tag} "
                f"RS {r['RS']} ({r['rs_new']:+d}) | ${r['close']:,.2f} ({r['change']:+.1f}%) | "
                f"tren MA200 {r['ext200']:.0f}% | cach dinh {r['off_high_%']}%")

    sections = [
        ("SEPA", "🏆 <b>SEPA</b> — ky thuat + EPS ≥40%, doanh thu ≥20%", 10),
        ("EARLY", "🚀 <b>Early Stage</b> — EPS QoQ ≥20%, ROE ≥15%", 8),
        ("IPO", "🌱 <b>IPO ≤5 nam</b> — bien lai gop ≥20%", 8),
        ("TREND", "📈 <b>Trend khac</b> (top score)", 5),
    ]
    lines = [f"📊 <b>Trend Template Scan</b> — {scanned_at}",
             f"{len(df)} ma dat ky thuat + RS ≥ {args.rs}"]

    # Nen som len dau bang — day moi la vung mua cua Minervini (nen 1-2)
    base1 = df[df["early2"]]
    if len(base1):
        lines += ["", f"🎯 <b>NEN SOM</b> — dau Stage 2, chua can MA200: {len(base1)} ma"]
        lines += [fmt_row(r, show_tier=True) for _, r in base1.head(10).iterrows()]
        if len(base1) > 10:
            lines.append(f"…va {len(base1) - 10} ma nua (xem tab Watch)")
    else:
        lines += ["", "🎯 <b>NEN SOM</b>: 0 ma — ca thi truong dang o nen cao, han che vao lenh moi"]

    for tname, title, cap in sections:
        sub = df[df["tier"] == tname]
        if not len(sub):
            if tname in ("SEPA", "EARLY"):
                lines += ["", f"{title}: 0 ma (thi truong chua co setup chuan)"]
            continue
        lines += ["", f"{title}: {len(sub)} ma"]
        lines += [fmt_row(r) for _, r in sub.head(cap).iterrows()]
        if len(sub) > cap:
            lines.append(f"…va {len(sub) - cap} ma nua (xem tab Watch)")
    new_shown = set(df.head(60)["name"])
    extra_new = new_names - new_shown
    if extra_new:
        lines += ["", "🆕 Moi lot vao hom nay: " + ", ".join(sorted(extra_new))]
    lines += ["", "👉 Xem day du: https://phanphuctam.github.io/trading-journal-2026 (tab Watch)"]
    text = "\n".join(lines)

    print()
    print(df.head(args.top)[["name", "tier", "early2", "RS", "rs_new", "score",
                             "ext50", "ext200", "off_high_%", "above_low_%"]].to_string(index=False))

    if not args.no_telegram:
        send_telegram(cfg, text)


if __name__ == "__main__":
    main()
