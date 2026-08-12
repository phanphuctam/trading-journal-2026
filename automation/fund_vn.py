# -*- coding: utf-8 -*-
"""So lieu CO BAN cho cac ma TRONG WATCHLIST -> scans/fund_vn.json

Muc dich: bang 🔬 Co ban trong journal truoc day bat nguoi doc tu mo 9 tab, tu doc
so, tu tinh phan tram, roi chi luu lai mot cai tick ✓/✕. Ket qua la moi lan doc mat
~20 phut va TOAN BO con so bi vut di — ba thang sau khong tra duoc luc do minh
thay gi. Script nay lam phan may lam duoc, de nguoi chi con phan phan xet.

QUAN TRONG — GIOI HAN DA KIEM CHUNG (vnstock ban cong dong, 08/2026):
  · Bao cao tai chinh chi tra ve 4 KY GAN NHAT. Quy hien tai la Q2/2026 thi ky xa
    nhat lay duoc la Q3/2025 — tuc KHONG CO Q2/2025 de so cung ky. Dung buoc 1
    (chu C cua CAN SLIM), buoc quan trong nhat, la buoc may KHONG tu lam duoc.
    -> Cach vuot: moi lan chay ghi 4 ky do vao fund_hist.json va gop don. Sau ~4 quy
       chay deu la tu co du lieu cung ky nam truoc, luc do npat_yoy_q tu dien ra.
       Tu nay den do buoc 1 van doc tay tren CafeF (bang co o nhap so).
  · Bang `ratio` cua vnstock HONG: tra ve du lieu 2018 lap lai, nhan cot sai het.
    KHONG dung. ROE / so co phieu / bien loi nhuan deu tu tinh tu 3 bao cao goc.
  · So CP luu hanh suy ra tu von gop (menh gia 10.000d/CP) — cach chuan o VN.

Ngan hang khong co "doanh thu thuan", "phai thu", "hang ton kho" nen ten truong
khac han doanh nghiep san xuat. Script nhan dien va doi chi tieu, khong bia so.

Cach dung:
    python fund_vn.py                 # ma trong watchlist.json
    python fund_vn.py HPG MWG         # chi mot vai ma
    python fund_vn.py --sleep 4       # cham hon neu bi chan (gioi han 20 req/phut)
"""
import argparse
import json
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")

from tv_common import BASE, load_json, save_json

WATCHLIST = BASE / "watchlist.json"
OUT = BASE.parent / "scans" / "fund_vn.json"
HIST = BASE.parent / "scans" / "fund_hist.json"
PAR_VALUE = 10_000          # menh gia co phieu VN

# ── Nguong cham diem. Lay dung tu bang trong app (app-src.html, _FA_VN) ────────
# Doi mot con so o day thi PHAI doi ca trong bang, khong duoc lech nhau.
Y_GROWTH_MIN = 20.0         # LNST nam tang >= 20%/nam, 3 nam lien tiep
ROE_MIN = 15.0              # ROE >= 15%
Q_NPAT_MIN = 25.0           # LNST quy YoY >= 25%   (chi cham duoc khi co lich su)
Q_REV_MIN = 20.0            # doanh thu quy YoY >= 20%
DILUTE_OK = 5.0             # so CP tang <= 5%/nam thi coi la on dinh
DILUTE_BAD = 15.0           # tang > 15%/nam la pha loang nang
OCF_OK = 0.8                # tong OCF 4 quy >= 0,8 x tong LNST
NONCORE_WARN = 30.0         # > 30% LNTT den tu ngoai cot loi = dang nghi

# ── Ten truong. Doanh nghiep thuong va ngan hang khac nhau nen thu theo thu tu ──
K_REV = ["net_sales", "total_operating_income", "net_interest_income"]
# LOI NHUAN NAO MOI DUNG — sua 2026-08-08 sau khi doi chieu VIC.
# EPS = loi nhuan cua CO DONG CONG TY ME / so co phieu, va gia di theo EPS. Lay LNST
# TONG (gom co dong khong kiem soat) la sai o moi tap doan co cong ty con lo nang:
#   VIC 2024 — LNST tong 5.276 ty, nhung LNST cong ty me 11.903 ty (CDTS -6.627 ty).
#   Chenh 2,3 lan. Dung so tong thi cham diem tang truong sai hoan toan.
# Chi lui ve LNST tong khi bao cao khong co dong cong ty me (doanh nghiep khong hop nhat).
K_NPAT_PARENT = ["attributable_to_parent_company"]
K_NPAT_TOTAL = ["net_profit_loss_after_tax"]
K_PBT = ["net_accounting_profit_loss_before_tax"]
K_MINORITY_EQ = ["minority_interests"]     # trong BANG CAN DOI: loi ich CDTS, nam TRONG von chu
K_OCF = ["net_cash_inflows_outflows_from_operating_activities",
         "net_cash_from_operating_activities"]
K_EQUITY = ["owners_equity"]
K_CAPITAL = ["paid_in_capital", "charter_capital", "common_shares"]
K_RECV = ["accounts_receivable"]
K_INV = ["inventories_net", "inventories"]
# Rieng ngan hang: buoc 3 trong bang doi NPL/LLR/tang truong tin dung
K_LOANS = ["loans_and_advances_to_customers"]
K_LOANS_NET = ["loans_and_advances_to_customers_net"]
K_DEPOSITS = ["deposits_from_customers"]
# Loi nhuan NGOAI hoat dong cot loi — day la cho O'Neil goi la bay #3
K_NONCORE = ["financial_income", "net_other_income_expenses",
             "income_from_investments_in_other_entities",
             "gain_loss_from_joint_ventures_from_2015"]
# Chi co o ngan hang -> dung de nhan dien nhom
K_BANK_MARK = "loans_and_advances_to_customers"


def periods_of(df):
    """Cot ky, giu nguyen thu tu vnstock tra ve (moi nhat truoc)."""
    return [c for c in df.columns if c not in ("item", "item_en", "item_id")]


def row(df, keys, cols):
    """Lay mot dong theo item_id, thu lan luot cac ten trong `keys`.

    Bang co dong trung item_id (vd other_current_assets xuat hien 2 lan) nen chi
    lay lan xuat hien DAU TIEN — dong sau thuong la muc phu bang 0.
    Tra ve list cung do dai `cols`, phan tu None neu thieu.
    """
    for k in keys:
        m = df[df["item_id"] == k]
        if len(m):
            r = m.iloc[0]
            out = []
            for c in cols:
                v = r.get(c)
                out.append(None if v is None or v != v else float(v))
            if any(v is not None for v in out):
                return out
    return [None] * len(cols)


def npat_of(df, cols):
    """LNST cua co dong cong ty me; khong co thi lui ve LNST tong.

    Tra (list gia tri, 'parent'|'total') de ghi ro so nay lay tu dau — nguoi doc
    phai biet minh dang nhin cai gi, khong duoc doan.
    """
    p = row(df, K_NPAT_PARENT, cols)
    if any(v is not None and v != 0 for v in p):
        return p, "parent"
    return row(df, K_NPAT_TOTAL, cols), "total"


def bs_check(bq, by):
    """Tu kiem bang can doi: TONG TAI SAN = NO PHAI TRA + VON CHU SO HUU.

    Day la dang thuc ke toan, khong phai uoc luong — lech qua 0,5% nghia la du lieu
    tai ve bi thieu dong hoac ghep sai ky. Truong hop do thi KHONG cham diem, vi
    mot con so sai co ve chac chan con nguy hiem hon la khong co so nao.
    """
    worst = None
    for df in (bq, by):
        cols = periods_of(df)
        ta = row(df, ["total_assets"], cols)
        li = row(df, ["liabilities", "total_liabilities"], cols)
        eq = row(df, K_EQUITY, cols)
        for i in range(len(cols)):
            if None in (ta[i], li[i], eq[i]) or not ta[i]:
                continue
            d = abs((li[i] + eq[i] - ta[i]) / ta[i] * 100)
            if worst is None or d > worst:
                worst = d
    return {"bs_dev_pct": None if worst is None else round(worst, 4),
            "ok": worst is not None and worst <= 0.5}


def pct(new, old):
    """Tang truong %. Goc am hoac 0 thi vo nghia -> None, khong tra so bia."""
    if new is None or old is None or old <= 0:
        return None
    return round((new - old) / old * 100, 1)


def ty(v):
    """Doi VND -> ty dong, lam tron 1 chu so. Giu None."""
    return None if v is None else round(v / 1e9, 1)


def fetch(sym, sleep):
    """5 loi goi cho mot ma. vnstock cong dong gioi han ~20 request/phut."""
    from vnstock.api.financial import Finance
    f = Finance(symbol=sym, source="VCI")
    out = {}
    for name, fn, per in (("iq", f.income_statement, "quarter"),
                          ("iy", f.income_statement, "year"),
                          ("bq", f.balance_sheet, "quarter"),
                          ("by", f.balance_sheet, "year"),
                          ("cq", f.cash_flow, "quarter")):
        time.sleep(sleep)
        out[name] = fn(period=per, lang="vi")
    return out


def build(sym, d, hist):
    """Tinh moi chi tieu cho mot ma. `hist` la lich su da tich luy (co the rong)."""
    iq, iy, bq, by, cq = d["iq"], d["iy"], d["bq"], d["by"], d["cq"]
    pq, py = periods_of(iq), periods_of(iy)
    is_bank = bool(len(bq[bq["item_id"] == K_BANK_MARK]))
    chk = bs_check(bq, by)

    rev_q = row(iq, K_REV, pq)
    npat_q, basis_q = npat_of(iq, pq)
    # LNST TONG di kem de nguoi doi chieu tay khong bi lac. CafeF danh nhan hai dong
    # "cong ty me" / "co dong khong kiem soat" CO LUC NGUOC NHAU: PET Q3/2025 CafeF ghi
    # me 40,0 va CDTS 105,2, trong khi ca VCI lan KBS deu ghi me 105,2 va CDTS 40,0.
    # Tong thi ba nguon giong het (145,2) — nen hien ca tong la co diem tua de doi chieu,
    # thay vi bat nguoi tin mot con so le loi.
    npat_tot_q = row(iq, K_NPAT_TOTAL, pq)
    pbt_q = row(iq, K_PBT, pq)
    ocf_q = row(cq, K_OCF, periods_of(cq))
    recv_q = row(bq, K_RECV, periods_of(bq))
    inv_q = row(bq, K_INV, periods_of(bq))

    # Loi nhuan ngoai cot loi: cong cac dong khong den tu ban hang
    noncore_q = []
    parts = [row(iq, [k], pq) for k in K_NONCORE]
    for i in range(len(pq)):
        vals = [p[i] for p in parts if p[i] is not None]
        noncore_q.append(sum(vals) if vals else None)

    rev_y = row(iy, K_REV, py)
    npat_y, basis_y = npat_of(iy, py)
    pby = periods_of(by)
    # VCSH cua RIENG co dong cong ty me = von chu (ma 400) TRU loi ich CDTS (ma 429).
    # Da kiem bang dang thuc ke toan tren VIC: TS = No + VCSH khop tuyet doi, va dong
    # CDTS nam trong VCSH. Khong tru ra thi ROE cua tap doan co cong ty con bi thoi len.
    eq_tot = row(by, K_EQUITY, pby)
    eq_mi = row(by, K_MINORITY_EQ, pby)
    eq_y = [None if eq_tot[i] is None else eq_tot[i] - (eq_mi[i] or 0) for i in range(len(pby))]
    cap_y = row(by, K_CAPITAL, pby)

    # ── Ghi vao lich su tich luy. Day la thu duy nhat vuot duoc gioi han 4 ky ──
    h = hist.setdefault(sym, {})
    for i, p in enumerate(pq):
        h[p] = {"rev": rev_q[i], "npat": npat_q[i]}

    def yoy_from_hist(p_now, field):
        """So voi CUNG QUY NAM TRUOC lay tu lich su. Chua co thi tra None."""
        try:
            y, q = p_now.split("-Q")
            prev = f"{int(y) - 1}-Q{q}"
        except ValueError:
            return None
        a, b = h.get(p_now, {}).get(field), h.get(prev, {}).get(field)
        return pct(a, b)

    # ── Buoc 2 (chu A): LNST nam. Can 3 lan tang lien tiep >= 20% ──
    y_growth = [pct(npat_y[i], npat_y[i + 1]) for i in range(len(npat_y) - 1)]
    y_ok = bool(y_growth) and all(g is not None and g >= Y_GROWTH_MIN for g in y_growth[:3]) \
        and len([g for g in y_growth[:3] if g is not None]) >= 3
    # Bay "phuc hoi gia": nam moi nhat van thap hon dinh cu (4-5-6-2-2,5)
    valid_np = [v for v in npat_y if v is not None]
    below_peak = bool(valid_np) and npat_y[0] is not None and npat_y[0] < max(valid_np[1:], default=0)

    # ROE = LNST nam moi nhat / VCSH binh quan dau-cuoi ky
    roe = None
    if npat_y[0] is not None and eq_y and eq_y[0]:
        base = eq_y[0] if len(eq_y) < 2 or eq_y[1] is None else (eq_y[0] + eq_y[1]) / 2
        if base and base > 0:
            roe = round(npat_y[0] / base * 100, 1)

    # ── Buoc 5: pha loang. So CP = von gop / menh gia ──
    shares_y = [None if c is None else c / PAR_VALUE for c in cap_y]
    share_yoy = pct(shares_y[0], shares_y[1]) if len(shares_y) > 1 else None

    # ── Buoc 4: phai thu & ton kho so voi doanh thu ──
    # Tinh tren du lieu NAM, khong tinh tren quy. Ly do: chi lay duoc 4 quy lien tiep
    # nen "so quy" bat buoc phai so Q2 voi Q3 nam truoc — lech mua vu, ma mua vu o VN
    # rat manh (ban le quy 4, thep quy 2-3). Nam so nam la so sach, khong bi mua vu.
    recv_y = row(by, K_RECV, periods_of(by))
    inv_y = row(by, K_INV, periods_of(by))
    rev_growth = pct(rev_y[0], rev_y[1]) if len(rev_y) > 1 else None
    recv_vs = pct(recv_y[0], recv_y[1]) if len(recv_y) > 1 else None
    inv_vs = pct(inv_y[0], inv_y[1]) if len(inv_y) > 1 else None
    if is_bank:
        rev_growth = recv_vs = inv_vs = None      # ngan hang khong co phai thu/ton kho

    # ── Buoc dong tien: tong OCF 4 quy so voi tong LNST 4 quy ──
    ocf_sum = sum(v for v in ocf_q if v is not None) if any(v is not None for v in ocf_q) else None
    npat_sum = sum(v for v in npat_q if v is not None) if any(v is not None for v in npat_q) else None
    ocf_ratio = None
    if ocf_sum is not None and npat_sum and npat_sum > 0:
        ocf_ratio = round(ocf_sum / npat_sum, 2)

    # ── Khoan mot lan: bao nhieu % LNTT den tu ngoai cot loi ──
    noncore_pct = []
    for i in range(len(pq)):
        n, p = noncore_q[i], pbt_q[i]
        noncore_pct.append(None if n is None or not p or p <= 0 else round(n / p * 100, 1))

    # ── Buoc 3, phan ngan hang. Chi tinh nhung gi bao cao co that ──
    # KHONG co NPL o day: no nam trong thuyet minh BCTC (phan nhom no 3-5), khong co
    # trong bang can doi. Dung ty le du phong/cho vay lam thay se la bia so, nen bang
    # trong app van bat doc tay NPL. Hai so duoi day la thu that su doc duoc.
    bank = None
    if is_bank:
        loans = row(by, K_LOANS, periods_of(by))
        loans_net = row(by, K_LOANS_NET, periods_of(by))
        deps = row(by, K_DEPOSITS, periods_of(by))
        llr = None
        if loans and loans[0] and loans_net and loans_net[0] is not None:
            llr = round((loans[0] - loans_net[0]) / loans[0] * 100, 2)
        bank = {
            "loans_growth": pct(loans[0], loans[1]) if len(loans) > 1 else None,
            "deposit_growth": pct(deps[0], deps[1]) if len(deps) > 1 else None,
            "ldr": round(loans[0] / deps[0] * 100, 1) if loans and deps and deps[0] else None,
            "provision_to_loans": llr,
        }

    calc = {
        "npat_yoy_q": yoy_from_hist(pq[0], "npat") if pq else None,
        "rev_yoy_q": yoy_from_hist(pq[0], "rev") if pq else None,
        "y_growth": y_growth[:3],
        "y_ok3": y_ok,
        "below_peak": below_peak,
        "roe": roe,
        "share_yoy": share_yoy,
        "rev_growth_y": rev_growth, "recv_vs_rev": recv_vs, "inv_vs_rev": inv_vs,
        "ocf_ratio": ocf_ratio,
        "noncore_pct": noncore_pct[0] if noncore_pct else None,
        "bank": bank,
    }

    # ── Goi y cham diem. 1 = dat, -1 = hong, 0 = may khong ket luan duoc ──
    # May chi GOI Y. Nguoi van phai bam ✓/✕ — Minervini doc bao cao bang mat la
    # co ly do: con so dat nguong khong dong nghia voi cau chuyen dung.
    auto = {}
    if calc["npat_yoy_q"] is not None and calc["rev_yoy_q"] is not None:
        auto["vnq"] = 1 if (calc["npat_yoy_q"] >= Q_NPAT_MIN and calc["rev_yoy_q"] >= Q_REV_MIN) else -1
    if npat_q and npat_q[0] is not None and npat_q[0] < 0:
        auto["vnq"] = -1                      # lo quy gan nhat -> loai, khong can YoY
    if calc["noncore_pct"] is not None:
        auto["vnone"] = -1 if calc["noncore_pct"] > NONCORE_WARN else 1
    if y_growth and any(g is not None for g in y_growth):
        auto["vnnam"] = 1 if (y_ok and not below_peak and roe is not None and roe >= ROE_MIN) else -1
    if recv_vs is not None and inv_vs is not None and rev_growth is not None:
        both_fast = (rev_growth > 0 and recv_vs > 2 * rev_growth and inv_vs > 2 * rev_growth)
        auto["vnbs"] = -1 if both_fast else (1 if (recv_vs <= rev_growth and inv_vs <= rev_growth) else 0)
    # Dong tien: KHONG cham cho ngan hang. OCF cua ngan hang bi chi phoi boi dong
    # tien gui va giai ngan cho vay, khong phan anh chat luong loi nhuan — STB co
    # quy -58.545 ty roi quy sau +17.065 ty, ty le OCF/LNST ra 9x, vo nghia.
    if ocf_ratio is not None and not is_bank:
        auto["vncf"] = 1 if ocf_ratio >= OCF_OK else -1
    if share_yoy is not None:
        auto["vndil"] = 1 if share_yoy <= DILUTE_OK else (-1 if share_yoy > DILUTE_BAD else 0)
    # Bang can doi khong khop dang thuc ke toan -> KHONG cham gi het. Mot con so sai
    # ma trong chac chan con nguy hiem hon la khong co so nao: no dat ten cho su nham lan.
    if not chk["ok"]:
        auto = {}

    return {
        "sector": "bank" if is_bank else "corp",
        # Ghi ro so lay tu dau va da tu kiem chua — de nguoi doc biet minh dang nhin cai gi
        "check": {**chk, "npat_basis": basis_y, "npat_basis_q": basis_q},
        "q_periods": pq,
        "y_periods": py,
        "q": {"rev": [ty(v) for v in rev_q], "npat": [ty(v) for v in npat_q],
              "npat_tot": [ty(v) for v in npat_tot_q],
              "ocf": [ty(v) for v in ocf_q[:len(pq)]],
              "recv": [ty(v) for v in recv_q[:len(pq)]],
              "inv": [ty(v) for v in inv_q[:len(pq)]],
              "noncore_pct": noncore_pct},
        "y": {"rev": [ty(v) for v in rev_y], "npat": [ty(v) for v in npat_y],
              "equity": [ty(v) for v in eq_y[:len(py)]],
              "shares_m": [None if s is None else round(s / 1e6, 1) for s in shares_y[:len(py)]]},
        "calc": calc,
        "auto": auto,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", help="ma can lay; de trong = watchlist")
    ap.add_argument("--sleep", type=float, default=3.4,
                    help="giay nghi giua 2 request (gioi han ~20 req/phut)")
    args = ap.parse_args()

    syms = [s.upper() for s in args.symbols]
    if not syms:
        wl = load_json(WATCHLIST, [])
        syms = sorted({str(w.get("symbol", "")).upper() for w in wl if w.get("symbol")})
    if not syms:
        print("watchlist.json trong — khong co ma nao de lay.")
        OUT.parent.mkdir(exist_ok=True)
        save_json(OUT, {"funds": {}})
        return

    hist = load_json(HIST, {})
    funds, fails = {}, []
    print(f"[i] Lay bao cao tai chinh {len(syms)} ma "
          f"(~{len(syms) * 5 * args.sleep / 60:.1f} phut)…")
    for s in syms:
        try:
            funds[s] = build(s, fetch(s, args.sleep), hist)
        except Exception as e:
            fails.append(s)
            print(f"    bo qua {s}: {type(e).__name__} {str(e)[:70]}")

    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    doc = {
        "app": "trading-journal",
        "market": "VN",
        "checked_at": datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
        "source": "vnstock/VCI · ban cong dong chi tra 4 ky gan nhat",
        "thresholds": {"y_growth": Y_GROWTH_MIN, "roe": ROE_MIN,
                       "q_npat": Q_NPAT_MIN, "q_rev": Q_REV_MIN,
                       "dilute_ok": DILUTE_OK, "ocf": OCF_OK},
        "funds": funds,
    }
    OUT.parent.mkdir(exist_ok=True)
    save_json(OUT, doc)
    save_json(HIST, hist)

    for s, f in funds.items():
        c = f["calc"]
        yoy = (f"LNST quy YoY {c['npat_yoy_q']:+.1f}%" if c["npat_yoy_q"] is not None
               else "quy YoY: chua du lich su")
        roe = f"ROE {c['roe']}%" if c["roe"] is not None else "ROE n/a"
        ocf = ("OCF: khong ap dung (ngan hang)" if f["sector"] == "bank"
               else f"OCF/LNST {c['ocf_ratio']}x" if c["ocf_ratio"] is not None else "OCF n/a")
        dil = f"CP {c['share_yoy']:+.1f}%" if c["share_yoy"] is not None else "CP n/a"
        bad = [k for k, v in f["auto"].items() if v == -1]
        ck = f["check"]
        note = "" if ck["ok"] else "  ⛔ BANG CAN DOI KHONG KHOP — khong cham diem"
        print(f"  {s:<5} [{f['sector']}/{ck['npat_basis']}] {yoy} · {roe} · {ocf} · {dil}"
              + (f"  ⚠ hong: {','.join(bad)}" if bad else "  ✓") + note)
    nq = sum(1 for f in funds.values() if f["calc"]["npat_yoy_q"] is None)
    if nq:
        print(f"[i] {nq} ma chua co quy cung ky nam truoc — buoc 1 doc tay tren CafeF."
              f" Chay deu moi ngay thi ~4 quy nua se tu co.")
    if fails:
        print(f"[!] That bai: {', '.join(fails)}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
