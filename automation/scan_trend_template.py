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


def rs_rating(df: pd.DataFrame) -> pd.Series:
    """RS Rating kieu IBD: quy gan nhat trong so gap doi, xep percentile 1-99."""
    p3, p6, py = (df[c].fillna(0) for c in ("Perf.3M", "Perf.6M", "Perf.Y"))
    raw = 2 * p3 + p6 + py
    return (raw.rank(pct=True) * 98 + 1).round(0).astype(int)


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


def classify(df: pd.DataFrame):
    """Gan tier theo 3 screen TradingView cua user. NaN tu dong khong dat."""
    num = lambda c: pd.to_numeric(df[c], errors="coerce")
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
    return tier, young


def chart_url(cfg: dict, ticker: str) -> str:
    """Link mo chart TradingView; dung layout rieng cua user neu co cau hinh."""
    layout = (cfg.get("chart_layout_id") or "").strip()
    base = f"https://www.tradingview.com/chart/{layout}/" if layout else "https://www.tradingview.com/chart/"
    return f"{base}?symbol={quote(ticker, safe='')}"


def write_site_json(cfg: dict, df: pd.DataFrame, scanned_at: str, rs_min: int):
    """Ghi scans/latest.json o goc repo de journal tren Netlify doc duoc."""
    layout = (cfg.get("chart_layout_id") or "").strip()
    chart_base = f"https://www.tradingview.com/chart/{layout}/" if layout else "https://www.tradingview.com/chart/"
    results = [
        {
            "symbol": r["name"], "ticker": r["ticker"], "desc": r["description"],
            "sector": r["sector"], "close": round(float(r["close"]), 2),
            "change": round(float(r["change"]), 2), "rs": int(r["RS"]),
            "off_high": float(r["off_high_%"]), "above_low": float(r["above_low_%"]),
            "tier": r["tier"], "young": bool(r["young"]),
        }
        for _, r in df.head(60).iterrows()
    ]
    SITE_SCAN.parent.mkdir(exist_ok=True)
    with open(SITE_SCAN, "w", encoding="utf-8") as f:
        json.dump({"app": "tj-scan", "scanned_at": scanned_at, "rs_min": rs_min,
                   "total": len(df), "chart_base": chart_base, "results": results},
                  f, ensure_ascii=False, indent=1)
    print(f"Da ghi {SITE_SCAN.relative_to(ROOT)}")


def push_site_json():
    """Commit + push scans/latest.json de Netlify tu deploy."""
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
            print("Da push len GitHub — Netlify se tu deploy sau ~1 phut.")
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
    uni["RS"] = rs_rating(uni)
    rs_map = uni.set_index("name")["RS"]
    print(f"  {len(uni)} ma trong universe.")

    print("Dang scan Trend Template...")
    df = fetch_trend_template()
    print(f"  {len(df)} ma qua 6 tieu chi gia/MA.")

    df["RS"] = df["name"].map(rs_map)
    df = df[df["RS"] >= args.rs].copy()
    df["off_high_%"] = ((df["close"] / df["price_52_week_high"] - 1) * 100).round(1)
    df["above_low_%"] = ((df["close"] / df["price_52_week_low"] - 1) * 100).round(0)
    df["tier"], df["young"] = classify(df)
    df["_tier_rank"] = df["tier"].map(TIER_ORDER)
    df = df.sort_values(["_tier_rank", "RS"], ascending=[True, False]).reset_index(drop=True)
    counts = df["tier"].value_counts()
    print(f"  {len(df)} ma dat RS >= {args.rs}: "
          + " | ".join(f"{t} {counts.get(t, 0)}" for t in TIER_ORDER))

    # Luu ket qua
    now_vn = datetime.now(VN)
    scanned_at = now_vn.strftime("%d/%m/%Y %H:%M") + " (VN)"
    SCAN_DIR.mkdir(exist_ok=True)
    today = now_vn.strftime("%Y-%m-%d")
    out_cols = ["name", "ticker", "tier", "young", "description", "sector", "close", "change", "RS",
                "off_high_%", "above_low_%", "volume", "market_cap_basic"]
    df[out_cols].to_csv(SCAN_DIR / f"scan_{today}.csv", index=False, encoding="utf-8-sig")
    df[out_cols].to_json(SCAN_DIR / f"scan_{today}.json", orient="records", force_ascii=False, indent=2)
    print(f"Da luu: automation/scans/scan_{today}.csv / .json")

    # JSON cho journal tren Netlify (+ commit/push de site tu cap nhat)
    write_site_json(cfg, df, scanned_at, args.rs)
    if not args.no_push:
        push_site_json()

    # Bao cao "moi lot vao hom nay" so voi lan scan truoc
    prev_files = sorted(SCAN_DIR.glob("scan_*.json"))
    new_names = set()
    if len(prev_files) >= 2:
        prev = pd.read_json(prev_files[-2])
        new_names = set(df["name"]) - set(prev["name"])

    def fmt_row(r):
        flag = " 🆕" if r["name"] in new_names else ""
        seed = " 🌱" if r["young"] and r["tier"] != "IPO" else ""
        link = chart_url(cfg, r["ticker"])
        return (f"<a href=\"{link}\"><b>{r['name']}</b></a>{seed}{flag} RS {r['RS']} | "
                f"${r['close']:,.2f} ({r['change']:+.1f}%) | cach dinh {r['off_high_%']}%")

    sections = [
        ("SEPA", "🏆 <b>SEPA</b> — ky thuat + EPS ≥40%, doanh thu ≥20%", 10),
        ("EARLY", "🚀 <b>Early Stage</b> — EPS QoQ ≥20%, ROE ≥15%", 8),
        ("IPO", "🌱 <b>IPO ≤5 nam</b> — bien lai gop ≥20%", 8),
        ("TREND", "📈 <b>Trend khac</b> (top RS)", 5),
    ]
    lines = [f"📊 <b>Trend Template Scan</b> — {scanned_at}",
             f"{len(df)} ma dat ky thuat + RS ≥ {args.rs}"]
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
    lines += ["", "👉 Xem day du: https://phantam.netlify.app (tab Watch)"]
    text = "\n".join(lines)

    print()
    print(df.head(args.top)[["name", "tier", "RS", "close", "change", "off_high_%", "sector"]].to_string(index=False))

    if not args.no_telegram:
        send_telegram(cfg, text)


if __name__ == "__main__":
    main()
