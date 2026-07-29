# -*- coding: utf-8 -*-
"""Scan SEPA (Mark Minervini) — Trend Template + loc co ban + boi canh dai han.

Quy trinh SEPA goc (Trade Like a Stock Market Wizard, Ch.3): buoc 1 Trend Template,
buoc 2 loc co ban (93% ma dat buoc 1 bi loai o day), buoc 3 Ho So Co Phieu Dan Dat,
buoc 4 danh gia thu cong. Script nay lam buoc 1-2 va mot phan buoc 3.

Vong 1 — Trend Template (8 tieu chi, Ch.5):
  gia > SMA50 > SMA150 > SMA200, SMA200 doc len, tren day 52W >= 25%,
  cach dinh 52W <= 25%, Perf.Y > 0, gia > 10 USD, KLTB 30 ngay > 300K,
  RS Rating >= nguong (mac dinh 70; >= 85 duoc danh dau ⭐)
  Han che: API chi cho offset [1]-[2] nen chi kiem duoc "SMA200 doc len HOM NAY",
  khong kiem duoc "doc len >= 1 thang" nhu sach yeu cau.

Vong 2 — gan nhan tier theo fundamentals (uu tien tu cao xuong):
  🏆 SEPA  : Perf.3M>=20, Perf.6M>=30, Revenue QYoY>=20%, EPS QoQ>=40%, EPS QYoY>=40%
  🚀 EARLY : Perf.3M>=10, Perf.6M>=20, EPS QoQ>=20%, ROE>=15%
  🌱 IPO   : niem yet <=5 nam (Perf.5Y == Perf.All) + gross margin FY >= 20%
  📈 TREND : chi dat ky thuat — khong bi loai, chi xep sau

Vong 2b — nhan them (KHONG loc cung, chi de doc):
  🔥 Code33  : Mat Ma 33 (Ch.8) — doanh so tang toc + loi nhuan tang toc + bien no.
               Sach doi 3 quy lien tiep; API khong cho du lieu quy truoc nen xap xi
               bang fq so voi ttm (quy gan nhat nhanh hon trung binh 12 thang).
  ⚡ surprise: bat ngo loi nhuan quy gan nhat >= 5% (Ch.7 — chat xuc tac).

Vong 3 — boi canh DAI HAN (Ch.6, nhom "cuu dan dat / bi lang quen"):
  off_ath  : gia cach dinh moi thoi dai bao nhieu %.
  Ma cach ATH < -40% bi LOAI, tru khi vua dat SEPA/EARLY vua qua kiem tra
  turnaround (Ch.6: loi nhuan quy gan nhat duong + bien loi nhuan phuc hoi
  + EPS 12 thang tang) — khi do gan nhan 🔄. Ma IPO <=5 nam duoc mien tru
  vi ATH chua co y nghia.

Vong 4 — do can (extension) de uu tien nen 1-2 thay vi nen 3-4 (Ch.5):
  ext50 / ext200 : gia cao hon SMA50 / SMA200 bao nhieu %
  🎯 early2      : ext200<=30, tren day 52W<=100%, cach dinh<=10%, chua can
  ⚠️ extended    : ext50>15 (mua duoi) hoac ext200>50 (nen cao)
  Sap xep nhom nay theo "thu tu diem pha vo" (Ch.9): ma nao sat dinh 52 tuan
  nhat thi dung truoc — de thi truong chon co phieu thay cho y kien ca nhan.

Khong bao gio "trang tay": tier tren 0 ma thi van thay tier duoi.

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

RS_STAR = 85      # Ch.5: toi thieu 70, ly tuong >= 90; RS TB sieu co phieu tai breakout = 87
ATH_FLOOR = -40   # Ch.6: cach dinh moi thoi dai qua xa => nhom "cuu dan dat / bi lang quen"


def rs_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """RS Rating theo dung trong so IBD: 40% quy gan nhat, 20% cho 3 quy con lai.

    Cong thuc cu (2*Perf.3M + Perf.6M + Perf.Y) bi trung lap vi Perf.6M va Perf.Y
    DA chua Perf.3M — khai trien ra thanh 4·Q1 + 2·Q2 + Q3 + Q4, tuc trong so
    50/25/12.5/12.5 thay vi 40/20/20/20. Hau qua: mot cu hoi 3 thang du thoi RS
    cua co phieu giam dai han len 80.
    """
    p3, p6, py = (df[c].fillna(0) for c in ("Perf.3M", "Perf.6M", "Perf.Y"))
    q1, q2, q34 = p3, p6 - p3, py - p6          # Q3+Q4 gop: 0.2*Q3 + 0.2*Q4 = 0.2*(Q3+Q4)
    ibd = 0.4 * q1 + 0.2 * q2 + 0.2 * q34
    pct = lambda s: (s.rank(pct=True) * 98 + 1).round(0).astype(int)  # noqa: E731
    return pd.DataFrame({"RS": pct(ibd)}, index=df.index)


def fetch_universe() -> pd.DataFrame:
    """Toan bo co phieu My du thanh khoan — dung lam mau so tinh RS percentile."""
    _, df = (
        Query()
        .select("name", "Perf.3M", "Perf.6M", "Perf.Y")
        .where(*LIQUID_FILTERS)
        .set_markets("america")
        .limit(20000)
        .get_scanner_data()
    )
    return df


def fetch_trend_template() -> pd.DataFrame:
    _, df = (
        Query()
        .select(
            "name", "description", "close", "change", "volume",
            "average_volume_30d_calc", "market_cap_basic", "sector",
            "SMA50", "SMA150", "SMA200", "SMA200[1]",
            "price_52_week_high", "price_52_week_low", "High.All",
            "Perf.3M", "Perf.6M", "Perf.Y", "Perf.5Y", "Perf.All",
            "total_revenue_yoy_growth_fq", "total_revenue_yoy_growth_ttm",
            "earnings_per_share_diluted_yoy_growth_fq",
            "earnings_per_share_diluted_yoy_growth_ttm",
            "earnings_per_share_diluted_qoq_growth_fq",
            "net_income_yoy_growth_fq", "net_margin_ttm", "net_margin_fy",
            "eps_surprise_percent_fq",
            "gross_margin_fy", "return_on_equity",
        )
        .where(
            *LIQUID_FILTERS,
            col("close") > col("SMA50"),
            col("SMA50") > col("SMA150"),
            col("SMA150") > col("SMA200"),
            col("SMA200") > col("SMA200[1]"),          # MA200 dang doc len
            col("close").above_pct("price_52_week_low", 1.25),
            col("close").above_pct("price_52_week_high", 0.75),
            col("Perf.Y") > 0,
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
    df["off_ath"] = ((num("close") / num("High.All") - 1) * 100).round(0)
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
    return tier, young


def add_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Mat Ma 33 (Ch.8) + bat ngo loi nhuan (Ch.7) — nhan doc them, khong loc cung."""
    num = lambda c: pd.to_numeric(df[c], errors="coerce")  # noqa: E731
    # Sach doi 3 quy lien tiep cung tang toc; API khong tra du lieu quy truoc
    # (..._fq[1] va ..._fq_h deu None) nen xap xi: quy gan nhat > trung binh 12 thang.
    rev_accel = num("total_revenue_yoy_growth_fq") > num("total_revenue_yoy_growth_ttm")
    eps_accel = (num("earnings_per_share_diluted_yoy_growth_fq")
                 > num("earnings_per_share_diluted_yoy_growth_ttm"))
    margin_up = num("net_margin_ttm") > num("net_margin_fy")
    df["code33"] = (rev_accel & eps_accel & margin_up).fillna(False)
    df["eps_surp"] = num("eps_surprise_percent_fq").round(1)
    # Ch.7: chi tin su kien danh bai uoc tinh MOT MUC DANG KE
    df["surprise"] = (df["eps_surp"] >= 5).fillna(False)
    return df


def turnaround_ok(df: pd.DataFrame) -> pd.Series:
    """Ch.6 — turnaround doi: 2-3 quy loi nhuan tich cuc gan nhat, EPS 12 thang
    gan/vuot dinh cu, bien loi nhuan phuc hoi, gia dang tang manh.
    Xap xi bang du lieu co san: loi nhuan quy tang, EPS 12 thang tang, bien no ra.
    """
    num = lambda c: pd.to_numeric(df[c], errors="coerce")  # noqa: E731
    return ((num("net_income_yoy_growth_fq") > 0)
            & (num("earnings_per_share_diluted_yoy_growth_ttm") > 0)
            & (num("net_margin_ttm") >= num("net_margin_fy"))).fillna(False)


def chart_url(cfg: dict, ticker: str) -> str:
    """Link mo chart TradingView; dung layout rieng cua user neu co cau hinh."""
    layout = (cfg.get("chart_layout_id") or "").strip()
    base = f"https://www.tradingview.com/chart/{layout}/" if layout else "https://www.tradingview.com/chart/"
    return f"{base}?symbol={quote(ticker, safe='')}"


def write_site_json(cfg: dict, df: pd.DataFrame, scanned_at: str, rs_min: int, dropped: int):
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
            "off_ath": None if pd.isna(r["off_ath"]) else float(r["off_ath"]),
            "star": bool(r["RS"] >= RS_STAR), "code33": bool(r["code33"]),
            "surprise": bool(r["surprise"]),
            "eps_surp": None if pd.isna(r["eps_surp"]) else float(r["eps_surp"]),
            "turn": bool(r["turn"]),
        }
        for _, r in df.iterrows()
    ]
    SITE_SCAN.parent.mkdir(exist_ok=True)
    with open(SITE_SCAN, "w", encoding="utf-8") as f:
        json.dump({"app": "tj-scan", "scanned_at": scanned_at, "rs_min": rs_min,
                   "total": len(df), "dropped_ath": dropped,
                   "chart_base": chart_base, "results": results},
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
    print(f"  {len(df)} ma qua 8 tieu chi Trend Template.")

    df["RS"] = df["name"].map(rs["RS"])
    df = df[df["RS"] >= args.rs].copy()
    print(f"  {len(df)} ma dat RS >= {args.rs}.")
    df["off_high_%"] = ((df["close"] / df["price_52_week_high"] - 1) * 100).round(1)
    df["above_low_%"] = ((df["close"] / df["price_52_week_low"] - 1) * 100).round(0)
    df = add_extension(df)
    df = add_quality(df)
    df["tier"], df["young"] = classify(df)
    df["turn"] = turnaround_ok(df)

    # Vong 3 — boi canh dai han. Ma cach ATH qua xa la nhom "cuu dan dat / bi lang
    # quen" (Ch.6: tranh hoan toan). Chi giu lai neu co CATALYST co ban that:
    # dat SEPA/EARLY va qua kiem tra turnaround. IPO <=5 nam mien tru.
    deep = (df["off_ath"] < ATH_FLOOR).fillna(False) & ~df["young"]
    rescued = deep & df["tier"].isin(["SEPA", "EARLY"]) & df["turn"]
    drop = deep & ~rescued
    n_drop, n_resc = int(drop.sum()), int(rescued.sum())
    if n_drop:
        print(f"  Loai {n_drop} ma cach dinh moi thoi dai < {ATH_FLOOR}% "
              f"(vd: {', '.join(df.loc[drop, 'name'].head(8))})")
    if n_resc:
        print(f"  Giu lai {n_resc} ma duoi ATH nhung dat turnaround: "
              f"{', '.join(df.loc[rescued, 'name'])}")
    df = df[~drop].copy()
    df["turn"] = df["turn"] & (df["off_ath"] < ATH_FLOOR).fillna(False)

    df["extended"] = (df["ext50"] > 15) | (df["ext200"] > 50)
    # Nen 1-2 sat diem pha vo: chua can so voi MA200, chua nhan doi tu day,
    # va dang o sat dinh 52 tuan (Ch.9 — mua theo thu tu diem pha vo).
    df["early2"] = (
        (df["ext200"] <= 30)
        & (df["above_low_%"] <= 100)
        & (df["off_high_%"] >= -10)
        & ~df["extended"]
    ).fillna(False)

    df["_tier_rank"] = df["tier"].map(TIER_ORDER)
    # Nhom 1 = 🎯 nen 1-2, sap theo THU TU DIEM PHA VO (Ch.9): ma sat dinh 52 tuan
    #          nhat dung truoc — de thi truong chon co phieu thay cho y kien ca nhan.
    # Nhom 2 = con lai, giu sort cu (tier -> RS giam dan).
    df = pd.concat([
        df[df["early2"]].sort_values(["off_high_%", "RS"], ascending=[False, False]),
        df[~df["early2"]].sort_values(["_tier_rank", "RS"], ascending=[True, False]),
    ]).reset_index(drop=True)
    counts = df["tier"].value_counts()
    print(f"  {len(df)} ma con lai: "
          + " | ".join(f"{t} {counts.get(t, 0)}" for t in TIER_ORDER)
          + f" || 🎯 nen 1-2 {int(df['early2'].sum())} | ⭐ RS≥{RS_STAR} {int((df['RS'] >= RS_STAR).sum())}"
          + f" | 🔥 Code33 {int(df['code33'].sum())} | ⚡ surprise {int(df['surprise'].sum())}"
          + f" | ⚠️ da can {int(df['extended'].sum())}")

    # Luu ket qua
    now_vn = datetime.now(VN)
    scanned_at = now_vn.strftime("%d/%m/%Y %H:%M") + " (VN)"
    SCAN_DIR.mkdir(exist_ok=True)
    today = now_vn.strftime("%Y-%m-%d")
    out_cols = ["name", "ticker", "tier", "young", "early2", "extended", "code33", "surprise",
                "turn", "description", "sector", "close", "change", "RS", "eps_surp",
                "ext50", "ext200", "off_ath", "off_high_%", "above_low_%",
                "volume", "market_cap_basic"]
    df[out_cols].to_csv(SCAN_DIR / f"scan_{today}.csv", index=False, encoding="utf-8-sig")
    df[out_cols].to_json(SCAN_DIR / f"scan_{today}.json", orient="records", force_ascii=False, indent=2)
    print(f"Da luu: automation/scans/scan_{today}.csv / .json")

    # JSON cho journal tren GitHub Pages (+ commit/push de site tu cap nhat)
    write_site_json(cfg, df, scanned_at, args.rs, n_drop)
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
        star = " ⭐" if r["RS"] >= RS_STAR else ""
        c33 = " 🔥" if r["code33"] else ""
        sur = " ⚡" if r["surprise"] else ""
        turn = " 🔄" if r["turn"] else ""
        hot = " ⚠️" if r["extended"] else ""
        tag = f" [{r['tier']}]" if show_tier else ""
        link = chart_url(cfg, r["ticker"])
        ath = "" if pd.isna(r["off_ath"]) else f" | ATH {r['off_ath']:.0f}%"
        return (f"<a href=\"{link}\"><b>{r['name']}</b></a>{star}{c33}{sur}{turn}{seed}{hot}{flag}{tag} "
                f"RS {r['RS']} | ${r['close']:,.2f} ({r['change']:+.1f}%) | "
                f"tren MA200 {r['ext200']:.0f}% | cach dinh {r['off_high_%']}%{ath}")

    sections = [
        ("SEPA", "🏆 <b>SEPA</b> — ky thuat + EPS ≥40%, doanh thu ≥20%", 10),
        ("EARLY", "🚀 <b>Early Stage</b> — EPS QoQ ≥20%, ROE ≥15%", 8),
        ("IPO", "🌱 <b>IPO ≤5 nam</b> — bien lai gop ≥20%", 8),
        ("TREND", "📈 <b>Trend khac</b>", 5),
    ]
    lines = [f"📊 <b>Trend Template Scan</b> — {scanned_at}",
             f"{len(df)} ma dat Trend Template + RS ≥ {args.rs}"
             + (f" (da loai {n_drop} ma duoi ATH {ATH_FLOOR}%)" if n_drop else "")]

    # Nen 1-2 len dau bang — day moi la vung mua cua Minervini
    base1 = df[df["early2"]]
    if len(base1):
        lines += ["", f"🎯 <b>NEN 1-2</b> — sat diem pha vo, chua can MA200: {len(base1)} ma"]
        lines += [fmt_row(r, show_tier=True) for _, r in base1.head(10).iterrows()]
        if len(base1) > 10:
            lines.append(f"…va {len(base1) - 10} ma nua (xem tab Watch)")
    else:
        lines += ["", "🎯 <b>NEN 1-2</b>: 0 ma — ca thi truong dang o nen cao, han che vao lenh moi"]

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
    lines += ["", f"⭐ RS≥{RS_STAR} · 🔥 Mat Ma 33 · ⚡ bat ngo EPS · 🔄 turnaround · ⚠️ da can",
              "👉 Xem day du: https://phanphuctam.github.io/trading-journal-2026 (tab Watch)"]
    text = "\n".join(lines)

    print()
    print(df.head(args.top)[["name", "tier", "early2", "RS", "code33", "surprise",
                             "ext50", "ext200", "off_ath", "off_high_%", "above_low_%"]].to_string(index=False))

    if not args.no_telegram:
        send_telegram(cfg, text)


if __name__ == "__main__":
    main()
