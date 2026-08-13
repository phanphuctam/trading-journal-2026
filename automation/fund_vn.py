# -*- coding: utf-8 -*-
"""So lieu CO BAN cho cac ma TRONG WATCHLIST -> scans/fund_vn.json

Muc dich: bang 🔬 Co ban trong journal truoc day bat nguoi doc tu mo 9 tab, tu doc
so, tu tinh phan tram, roi chi luu lai mot cai tick ✓/✕. Ket qua la moi lan doc mat
~20 phut va TOAN BO con so bi vut di — ba thang sau khong tra duoc luc do minh
thay gi. Script nay lam phan may lam duoc, de nguoi chi con phan phan xet.

SO KY LAY DUOC PHU THUOC API KEY (do that 13/08/2026):
  · KHONG co key (tier 'guest'): 4 ky gan nhat.
  · CO key MIEN PHI (tier 'free'): 8 ky, ca quy lan nam.
  Khac biet nay khong phai "nhieu so hon cho vui":
    - 8 quy nghia la CO SAN quy cung ky nam truoc de so — buoc 1 (chu C cua CAN
      SLIM) doc thang tu bao cao, khong phai suy nguoc.
    - 8 nam moi nhin ra duoc bay "phuc hoi gia" (4-5-6-2-2,5). Voi 4 nam thi mot
      ma sap ba nam roi hoi mot nam van co the trong nhu dang tang truong deu.
  Lay key: vnstocks.com/account#api-key. Xem automation/README.md.

VAN GIU PHEP SUY NGUOC lam luoi do (`rs_money` + `backfill_yoy`): bang
`ratio_summary` co chuoi TTM tu 2018, ma TTM(t) - TTM(t-1) = Q(t) - Q(t-4), nen
biet Q(t) thi suy nguoc ra Q(t-4). Dung khi chay khong key, khi ky can so nam
ngoai 8 ky, hoac khi lich su tich luy con trong. So BAO CAO THAT luon thang.
Phep suy nguoc co CONG DOI CHIEU rieng, xem `ttm_dev` — bat buoc, khong bo qua.

GIOI HAN KHAC (dung o moi tier):
  · Bang `ratio` (Finance.ratio) HONG: tra ve du lieu 2018 lap lai, nhan cot sai het.
    KHONG dung. Nhung `Company.ratio_summary` — mot bang KHAC — thi CHAY TOT va co
    du PE/PB/ROE/bien loi nhuan/NPL/CAR/CIR/CASA/LDR/NIM tu 2018 den quy gan nhat.
  · So CP luu hanh suy ra tu von gop (menh gia 10.000d/CP) — cach chuan o VN.

Ngan hang khong co "doanh thu thuan", "phai thu", "hang ton kho" nen ten truong
khac han doanh nghiep san xuat. Script nhan dien va doi chi tieu, khong bia so.

Cach dung:
    python fund_vn.py                 # ma trong watchlist.json
    python fund_vn.py HPG MWG         # chi mot vai ma
    python fund_vn.py --sleep 4       # cham hon neu bi chan (mac dinh tu tinh theo tier)
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

from tv_common import BASE, load_json, save_json, vnstock_sleep, vnstock_tier

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
OCF_WINDOW = 4              # so quy gop lai — MOT vong mua vu tron ven, khong doi
PEAK_YEARS = 5              # soi nguoc bao nhieu nam de tim "dinh cu" (bay phuc hoi gia)
NONCORE_WARN = 30.0         # > 30% LNTT den tu ngoai cot loi = dang nghi
# Buoc 2b (vnmar): bien loi nhuan phai NO RA, khong can cao. Lay nguong tu chinh
# bang trong app — "bien MO RONG qua tung quy". Chi so sanh voi CUNG KY NAM TRUOC
# vi mua vu o VN rat manh (ban le quy 4, thep quy 2-3).
MARGIN_SHRINK = 1.0         # bien co lai > 1 diem % so cung ky = hong
# Buoc 3 (vnsec), phan ngan hang. Nguong lay dung tu bang trong app.
NPL_MAX = 2.0               # no xau < 2% va khong tang
LLR_MIN = 80.0              # ty le bao phu no xau > 80%
# Cong doi chieu chuoi TTM truoc khi cho phep suy nguoc quy cung ky. Xem `ttm_dev`.
# Dat 1,0% vi cac ma doi chieu duoc deu nam trong 0,00-0,60%, con hai ma hong thi
# vot len 4,02% va 6,57% — khoang trong o giua rong, khong phai nguong chon bua.
TTM_DEV_MAX = 1.0

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
K_GROSS = ["gross_profit"]                 # ngan hang khong co -> bien gop = None

# ── Bang ratio_summary. Ten cot lay dung nhu vnstock tra ve ────────────────────
# CANH BAO: day KHONG phai bang `Finance.ratio` (bang do hong, xem docstring).
# Moi dong la mot ky; ratio_type = RATIO_TTM (luy ke 4 quy) hoac RATIO_YEAR (ca nam,
# dong nay co quarter = 5). Cac ty le deu la PHAN LE (0,1245 = 12,45%).
RS_BANK = {"npl": ["npl"],                            # no xau / tong du no
           "llr": ["loans_loss_reserves_to_np_ls"],   # du phong / no xau = ty le bao phu
           "prov": ["loans_loss_reserve_to_loans"],   # du phong / tong du no
           "nim": ["net_interest_margin"],
           "cir": ["cir", "cost_to_income"],          # chi phi / thu nhap, vnstock ghi so am
           "car": ["car"],                            # chi co o dong RATIO_YEAR
           "casa": ["casa_ratio"],
           "ldr": ["ldr_loan_deposit_ratio"]}


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


# ══ BANG ratio_summary — thu go duoc gioi han "4 ky gan nhat" ══════════════════

def rs_rows(rs, kind):
    """Loc ratio_summary theo loai ky, sap CU -> MOI. Tra list dict."""
    if rs is None or not len(rs):
        return []
    d = rs[rs["ratio_type"] == kind].sort_values(["year", "quarter"])
    return [r._asdict() if hasattr(r, "_asdict") else dict(r) for _, r in d.iterrows()]


def rs_key(r):
    """Nhan ky cua mot dong ratio_summary: '2026-Q2', hoac '2025' voi dong ca nam."""
    y, q = int(r["year"]), int(r["quarter"])
    return str(y) if q == 5 else f"{y}-Q{q}"


def num(v):
    """float hoac None. NaN cua pandas tu no khac chinh no nen bat bang v != v."""
    if v is None or v != v:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def rs_money(rows, ratio_col):
    """Chuoi TIEN luy ke 4 quy (TTM), suy tu von hoa chia he so dinh gia.

        market_cap / pe = LNST TTM (cua co dong cong ty me — cung mau so voi EPS)
        market_cap / ps = doanh thu TTM

    Gia co ca o tu va mau nen no triet tieu: ket qua khong phu thuoc thi gia luc do,
    day la chinh con so bao cao duoc viet nguoc lai. Da doi chieu 12/08/2026 tren
    PET/FPT/HPG/MWG: tong 4 quy that so voi so nay lech 0,00% (FPT 0,6%).

    Tra dict {'2026-Q2': ty_dong, ...}. Bo ky co he so am hoac 0 (doanh nghiep lo:
    PE am thi phep chia ra so vo nghia, tha khong co con hon co so sai).
    """
    out = {}
    for r in rows:
        mc, k = num(r.get("market_cap")), num(r.get(ratio_col))
        if mc is None or not k or k <= 0:
            continue
        out[rs_key(r)] = mc / k / 1e9
    return out


def ttm_dev(rows, ratio_col, real, periods):
    """TU DOI CHIEU chuoi TTM voi bao cao — cong bat buoc truoc khi suy nguoc.

    Chuoi TTM la LNST luy ke 4 quy, nen o KY MOI NHAT no phai bang tong 4 quy that
    dang cam trong tay. Lech bao nhieu % thi tra ve chinh so do.

    Vi sao BAT BUOC: phep suy nguoc lay HIEU cua hai gia tri TTM, nen sai so tuyet
    doi cua ca hai don thang vao ket qua. Do tren 9 ma (12/08/2026): PET/HPG/MWG/
    ACB/GEX lech 0,00%, VIC 0,34%, FPT 0,60% — nhung MSN lech 4,02% va HVN 6,57%.
    Voi MSN, 4% cua 6.770 ty la ~270 ty nem vao mot quy goc chi ~1.125 ty: con so
    YoY in ra se sai hang chuc diem phan tram MA VAN TRONG NHU THAT. Ma nao khong
    doi chieu duoc thi KHONG suy nguoc, de nguoi doc tay — thieu so con hon sai so.

    Tra None neu khong du du lieu de doi chieu (cung la KHONG cho suy nguoc).
    """
    if not rows or not periods:
        return None
    newest = periods[0]
    vals = [real[i] for i in range(min(4, len(periods))) if i < len(real) and real[i] is not None]
    if len(vals) < 4:
        return None
    s = sum(vals) / 1e9
    ttm = rs_money(rows, ratio_col).get(newest)
    if ttm is None or not s:
        return None
    return round(abs(s - ttm) / abs(s) * 100, 2)


def prev_q(p):
    """Ky lien truoc: '2026-Q1' -> '2025-Q4'. Khong phai dang quy thi tra None."""
    try:
        y, q = p.split("-Q")
        y, q = int(y), int(q)
    except ValueError:
        return None
    return f"{y - 1}-Q4" if q == 1 else f"{y}-Q{q - 1}"


def last_year_q(p):
    """Cung quy nam truoc: '2026-Q2' -> '2025-Q2'."""
    try:
        y, q = p.split("-Q")
    except ValueError:
        return None
    return f"{int(y) - 1}-Q{q}"


def src_of(e, field):
    """Mot o trong lich su den tu dau: 'ttm' = suy nguoc, 'bc' = bao cao that.

    Nhan phai gan theo TUNG O chu khong theo ca ky: mot ma co the doi chieu duoc
    doanh thu (lech 0,00%) nhung khong doi chieu duoc loi nhuan (MSN lech 4,02%),
    luc do trong cung mot ky se co mot o suy nguoc va mot o khong co gi. Gan nhan
    chung thi bang se ghi "loi nhuan suy nguoc" cho mot con so KHONG HE TON TAI.

    `src` khong hau to la nhan doi cu, hieu la ap cho ca hai o.
    """
    v = e.get("src_" + field) or e.get("src")
    return "ttm" if v == "ttm" else "bc"


def backfill_yoy(h, periods, real, ttm, field):
    """Suy ky CUNG QUY NAM TRUOC tu chuoi TTM roi ghi vao lich su `h`.

    Dang thuc:  TTM(t) - TTM(t-1) = Q(t) - Q(t-4)   =>   Q(t-4) = Q(t) - dTTM
    Ve trai gom 4 quy ket thuc o t tru 4 quy ket thuc o t-1, moi thu giua triet tieu.

    So BAO CAO THAT luon thang: chi ghi de o cho con trong hoac cho truoc do cung
    do chinh phep suy nguoc nay dien ra (danh dau src='ttm'). Lam nguoc lai thi mot
    so uoc luong se de len so that va khong ai biet.
    """
    n = 0
    for i, p in enumerate(periods):
        q_now = real[i] if i < len(real) else None
        pv, ly = prev_q(p), last_year_q(p)
        if q_now is None or pv is None or ly is None:
            continue
        if ttm.get(p) is None or ttm.get(pv) is None:
            continue
        val = q_now / 1e9 - (ttm[p] - ttm[pv])       # ty dong
        old = h.get(ly, {})
        if old.get(field) is not None and src_of(old, field) != "ttm":
            continue                                 # da co so bao cao that
        e = h.setdefault(ly, {})
        e[field] = val * 1e9                         # lich su luu VND cho dong bo
        e["src_" + field] = "ttm"
        n += 1
    return n


def pct(new, old):
    """Tang truong %. Goc am hoac 0 thi vo nghia -> None, khong tra so bia."""
    if new is None or old is None or old <= 0:
        return None
    return round((new - old) / old * 100, 1)


def ty(v):
    """Doi VND -> ty dong, lam tron 1 chu so. Giu None."""
    return None if v is None else round(v / 1e9, 1)


def fetch(sym, sleep):
    """6 loi goi cho mot ma. vnstock cong dong gioi han ~20 request/phut.

    Loi goi thu 6 (`rs`) la bang ratio_summary — no dat nhung dat xung dang: mot
    request nay mo ra ca chuoi TTM tu 2018 (de suy nguoc quy cung ky), PE/PB/ROE,
    va toan bo chi tieu ngan hang (NPL/LLR/NIM/CIR/CAR/CASA/LDR) ma bang can doi
    khong co. Hong thi bo qua, phan con lai van chay nhu cu.
    """
    from vnstock.api.financial import Finance
    from vnstock.api.company import Company
    f = Finance(symbol=sym, source="VCI")
    out = {}
    for name, fn, per in (("iq", f.income_statement, "quarter"),
                          ("iy", f.income_statement, "year"),
                          ("bq", f.balance_sheet, "quarter"),
                          ("by", f.balance_sheet, "year"),
                          ("cq", f.cash_flow, "quarter")):
        time.sleep(sleep)
        out[name] = fn(period=per, lang="vi")
    try:
        time.sleep(sleep)
        out["rs"] = Company(symbol=sym, source="VCI").ratio_summary()
    except Exception as e:
        print(f"    {sym}: khong lay duoc ratio_summary ({type(e).__name__}) — "
              f"bo qua PE/ROE/NPL va phep suy nguoc quy")
        out["rs"] = None
    return out


def build(sym, d, hist):
    """Tinh moi chi tieu cho mot ma. `hist` la lich su da tich luy (co the rong)."""
    iq, iy, bq, by, cq, rs = d["iq"], d["iy"], d["bq"], d["by"], d["cq"], d.get("rs")
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

    # ── Ghi vao lich su tich luy ──
    # So BAO CAO THAT: ghi de vo dieu kien, nhung khong ghi de bang None (chay hut
    # mot lan khong duoc xoa mat ky da co).
    h = hist.setdefault(sym, {})
    # Di tru nhan doi CU ("src" ap chung cho ca ky) thanh nhan tung o. Bat buoc phai
    # lam, khong phai don dep cho gon: giu nhan chung thi khi mot o duoc thay bang so
    # bao cao that, nhan chung van con va o CON LAI se bi doc nham — hoac te hon, o
    # vua thanh so that lai bi tiep tuc gan mac "suy nguoc".
    for e in h.values():
        if "src" in e:
            for fld in ("rev", "npat"):
                if e.get(fld) is not None:
                    e.setdefault("src_" + fld, e["src"])
            del e["src"]

    for i, p in enumerate(pq):
        e = h.setdefault(p, {})
        # Go nhan "so suy nguoc" THEO TUNG O, va chi go o nao that su vua duoc thay
        # bang so bao cao. Go vo dieu kien la bien mot so uoc luong thanh so bao cao
        # chi vi lan chay nay hut du lieu — tu do khong con gi danh dau no nua.
        if rev_q[i] is not None:
            e["rev"] = rev_q[i]
            e.pop("src_rev", None)
        if npat_q[i] is not None:
            e["npat"] = npat_q[i]
            e.pop("src_npat", None)
        if rev_q[i] is not None and npat_q[i] is not None:
            e.pop("src", None)              # nhan doi cu, chi go khi ca hai o da that

    # ── Suy nguoc quy cung ky nam truoc tu chuoi TTM ──
    # Day la thu thay the viec ngoi doi 4 quy: xem `backfill_yoy`. Chuoi TTM co tu
    # 2018 nen dien duoc ca nhung quy con thieu o giua, khong chi 4 quy sat canh.
    # NHUNG chi lam khi chuoi TTM DOI CHIEU DUOC voi bao cao (xem `ttm_dev`): hai
    # ty le lech nay duoc tinh RIENG cho LNST va doanh thu, vi mot ma co the khop
    # o so nay ma lech o so kia.
    ttm_rows = rs_rows(rs, "RATIO_TTM")
    ttm_npat = rs_money(ttm_rows, "pe")
    ttm_rev = rs_money(ttm_rows, "ps")
    dev_npat = ttm_dev(ttm_rows, "pe", npat_q, pq)
    dev_rev = ttm_dev(ttm_rows, "ps", rev_q, pq)
    ok_npat = dev_npat is not None and dev_npat <= TTM_DEV_MAX
    ok_rev = dev_rev is not None and dev_rev <= TTM_DEV_MAX
    n_bf = ((backfill_yoy(h, pq, npat_q, ttm_npat, "npat") if ok_npat else 0)
            + (backfill_yoy(h, pq, rev_q, ttm_rev, "rev") if ok_rev else 0))

    def yoy_from_hist(p_now, field):
        """So voi CUNG QUY NAM TRUOC lay tu lich su. Chua co thi tra None."""
        prev = last_year_q(p_now)
        if prev is None:
            return None
        a, b = h.get(p_now, {}).get(field), h.get(prev, {}).get(field)
        return pct(a, b)

    def yoy_src(p_now):
        """So LNST cung ky den tu dau: 'bc' = bao cao that, 'ttm' = suy nguoc.

        Tra None khi khong co so nao — de goi y "suy nguoc" khong bao gio dinh vao
        mot o trong.
        """
        prev = last_year_q(p_now)
        if prev is None or h.get(prev, {}).get("npat") is None:
            return None
        return src_of(h[prev], "npat")

    # ── Buoc 2 (chu A): LNST nam. Can 3 lan tang lien tiep >= 20% ──
    y_growth = [pct(npat_y[i], npat_y[i + 1]) for i in range(len(npat_y) - 1)]
    y_ok = bool(y_growth) and all(g is not None and g >= Y_GROWTH_MIN for g in y_growth[:3]) \
        and len([g for g in y_growth[:3] if g is not None]) >= 3
    # Bay "phuc hoi gia": nam moi nhat van thap hon dinh cu (4-5-6-2-2,5)
    # Cua so soi nguoc PHAI chot bang con so, khong duoc de no chay theo so ky nguon
    # tra ve: co API key thi nguon nhay tu 4 nam len 8 nam, va phep so nay lang le
    # doi thanh "so voi dinh cua 8 nam". Dinh nam 2018-2019 truoc COVID thi rat nhieu
    # doanh nghiep VN chua lay lai duoc — de nguyen la ca watchlist bi danh below_peak,
    # tuc buoc 2 truot het, ma khong ai hieu vi sao. PEAK_YEARS = 5 phu tron mot chu
    # ky (gom ca COVID) va dung dang bieu do 5 diem trong vi du cua O'Neil.
    # Day la LUA CHON, khong phai chan ly — day so day du van nam trong fund_vn.json
    # de tu nhin lai bang mat.
    valid_np = [v for v in npat_y[:PEAK_YEARS] if v is not None]
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

    # ── Buoc dong tien: tong OCF 4 QUY so voi tong LNST 4 QUY ──
    # PHAI cat dung 4 quy. Truoc 13/08/2026 doan nay cong TOAN BO ocf_q, va no dung
    # vi nguon luc do chi tra ve dung 4 ky. Co API key thi nguon tra 8 ky, va cung
    # doan code do lang le doi thanh "8 quy" — PET nhay tu -7,10x sang -2,98x ma
    # khong dong nao bao. Nguong OCF_OK = 0,8 duoc dat cho cua so 4 quy (mot vong
    # mua vu tron ven); doi cua so ma giu nguyen nguong la so sanh hai thu khac nhau.
    ocf_w = ocf_q[:OCF_WINDOW]
    npat_w = npat_q[:OCF_WINDOW]
    ocf_sum = sum(v for v in ocf_w if v is not None) if any(v is not None for v in ocf_w) else None
    npat_sum = sum(v for v in npat_w if v is not None) if any(v is not None for v in npat_w) else None
    ocf_ratio = None
    if ocf_sum is not None and npat_sum and npat_sum > 0:
        ocf_ratio = round(ocf_sum / npat_sum, 2)

    # ── Khoan mot lan: bao nhieu % LNTT den tu ngoai cot loi ──
    noncore_pct = []
    for i in range(len(pq)):
        n, p = noncore_q[i], pbt_q[i]
        noncore_pct.append(None if n is None or not p or p <= 0 else round(n / p * 100, 1))

    # ── Buoc 3, phan ngan hang, phan doc tu BANG CAN DOI ──
    # Bang can doi khong co NPL (no nhom 3-5 nam trong thuyet minh BCTC). Ba so duoi
    # day la thu doc duoc tu bang can doi; NPL/LLR/NIM/CIR/CAR/CASA lay o khoi
    # ratio_summary phia duoi. `ldr_bs` giu rieng vi no tinh tu so du cuoi ky, co the
    # lech vai diem so voi LDR cong bo — giu ca hai de lech thi nhin ra ngay.
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
            "ldr_bs": round(loans[0] / deps[0] * 100, 1) if loans and deps and deps[0] else None,
            "provision_to_loans": llr,
        }

    # ── Buoc 2b: BIEN LOI NHUAN ──
    # Bien gop chi tinh duoc cho 4 quy co bao cao (khong co "loi nhuan gop" trong
    # chuoi TTM). Bien RONG thi so duoc voi CUNG KY NAM TRUOC nho phep suy nguoc o
    # tren — va cung ky moi la phep so dung: bien loi nhuan o VN theo mua rat manh,
    # so Q2 voi Q1 lien truoc la so tao lao.
    gross_q = row(iq, K_GROSS, pq)
    gm_q = [None if gross_q[i] is None or not rev_q[i] else round(gross_q[i] / rev_q[i] * 100, 2)
            for i in range(len(pq))]
    nm_q = [None if npat_q[i] is None or not rev_q[i] else round(npat_q[i] / rev_q[i] * 100, 2)
            for i in range(len(pq))]
    nm_ly = nm_delta = None
    nm_ly_derived = False
    if pq:
        ly = h.get(last_year_q(pq[0]), {})
        if ly.get("npat") is not None and ly.get("rev"):
            nm_ly = round(ly["npat"] / ly["rev"] * 100, 2)
            # Bien la mot PHEP CHIA: chi can MOT trong hai o la so suy nguoc thi ket
            # qua da mang sai so cua phep suy nguoc, du o kia doc thang tu bao cao.
            nm_ly_derived = (src_of(ly, "npat") == "ttm" or src_of(ly, "rev") == "ttm")
            if nm_q and nm_q[0] is not None:
                nm_delta = round(nm_q[0] - nm_ly, 2)

    # ── Dinh gia + ty suat, lay tu ky TTM moi nhat cua ratio_summary ──
    # KHONG tu tinh PE tu gia: gia o day la gia CUOI KY cua chinh bang do, con gia
    # hom nay nam o watch_stats.json. Tron hai moc thoi gian lai la tu bia so.
    last_ttm = ttm_rows[-1] if ttm_rows else {}
    year_rows = rs_rows(rs, "RATIO_YEAR")
    last_year = year_rows[-1] if year_rows else {}
    p100 = lambda v: None if num(v) is None else round(num(v) * 100, 2)
    val = {
        "as_of": rs_key(last_ttm) if last_ttm else None,
        "pe": None if num(last_ttm.get("pe")) is None else round(num(last_ttm["pe"]), 1),
        "pb": None if num(last_ttm.get("pb")) is None else round(num(last_ttm["pb"]), 2),
        "roe_ttm": p100(last_ttm.get("roe")),
        "roa_ttm": p100(last_ttm.get("roa")),
        "div_yield": p100(last_ttm.get("dividend_yield")),
        "debt_to_equity": None if num(last_ttm.get("debt_to_equity")) is None
        else round(num(last_ttm["debt_to_equity"]), 2),
        "market_cap_ty": ty(num(last_ttm.get("market_cap"))),
    }

    # ── Buoc 3, ngan hang: bay gio doc duoc NPL that ──
    # Truoc 12/08/2026 file nay ghi "KHONG co NPL, nam trong thuyet minh BCTC". Dung
    # voi bang can doi, nhung ratio_summary co san dong `npl` va `loans_loss_reserves_
    # to_np_ls` (ty le bao phu) — chinh hai so ma bang trong app bat doc tay.
    if is_bank:
        bank = bank or {}
        for k, names in RS_BANK.items():
            src = last_year if k == "car" else last_ttm      # CAR chi co o dong ca nam
            v = next((num(src.get(n)) for n in names if num(src.get(n)) is not None), None)
            bank[k] = None if v is None else round(abs(v) * 100, 2)
        # Xu huong NPL: so voi cung ky nam truoc (4 dong TTM truoc do)
        if len(ttm_rows) > 4:
            old_npl = num(ttm_rows[-5].get("npl"))
            bank["npl_ly"] = None if old_npl is None else round(old_npl * 100, 2)

    calc = {
        "npat_yoy_q": yoy_from_hist(pq[0], "npat") if pq else None,
        "rev_yoy_q": yoy_from_hist(pq[0], "rev") if pq else None,
        "yoy_src": yoy_src(pq[0]) if pq else None,
        "gm_q": gm_q, "nm_q": nm_q, "nm_ly": nm_ly, "nm_delta": nm_delta,
        "val": val,
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

    # ── Buoc 2b: bien loi nhuan & ROE ──
    # So bien RONG voi CUNG KY NAM TRUOC (khong so quy lien truoc — mua vu). ROE lay
    # so TTM cua ratio_summary neu co, khong thi lui ve ROE nam tu tinh.
    roe_use = val["roe_ttm"] if val["roe_ttm"] is not None else roe
    if nm_delta is not None:
        if nm_delta < -MARGIN_SHRINK:
            auto["vnmar"] = -1                # bien co lai ro -> hong, bat ke ROE
        elif roe_use is not None:
            auto["vnmar"] = 1 if (nm_delta >= 0 and roe_use >= ROE_MIN) else 0
        else:
            auto["vnmar"] = 0

    # ── Buoc 3: ngan hang ──
    # Doanh nghiep san xuat/ban le thi buoc nay khong ap dung -> khong cham (de trong,
    # nguoi bam bo qua). Chi cham cho ngan hang, va chi khi co du CA HAI so NPL+LLR:
    # NPL thap ma khong biet LLR thi khong ket luan duoc — giau no xau chinh la dang
    # bao NPL dep trong khi bao phu mong di.
    if is_bank and bank:
        npl, llr_cov = bank.get("npl"), bank.get("llr")
        if npl is not None and llr_cov is not None:
            rising = (bank.get("npl_ly") is not None and npl > bank["npl_ly"])
            good = npl < NPL_MAX and llr_cov > LLR_MIN and not rising
            worse = npl >= NPL_MAX and rising and llr_cov <= LLR_MIN
            auto["vnsec"] = 1 if good else (-1 if worse else 0)

    # Bang can doi khong khop dang thuc ke toan -> KHONG cham gi het. Mot con so sai
    # ma trong chac chan con nguy hiem hon la khong co so nao: no dat ten cho su nham lan.
    if not chk["ok"]:
        auto = {}

    # ── CHO NAO MAY KHONG CHAC — ghi ra de nguoi kiem tay ──────────────────────
    # Muc dich: mot goi y "DAT" khong noi ro no dua tren gia dinh gi thi nguy hiem
    # hon la khong goi y. Danh sach nay di thang len giao dien, canh dung buoc do.
    # Chuoi trong `man` di THANG len giao dien nen viet CO DAU, khong nhu ghi chu
    # trong code va dong in ra console.
    man = []

    def note(k, why, where):
        man.append({"k": k, "why": why, "where": where})

    if not chk["ok"]:
        note("vndisc", "bảng cân đối không khớp đẳng thức TS = Nợ + VCSH "
                       f"(lệch {chk['bs_dev_pct']}%) — máy đã bỏ chấm TOÀN BỘ các bước",
             "CafeF · Bảng cân đối kế toán")
    if calc["yoy_src"] == "ttm" and calc["npat_yoy_q"] is not None:
        note("vnq", "số CÙNG KỲ NĂM TRƯỚC là suy ngược từ chuỗi luỹ kế 4 quý chứ không đọc "
                    "thẳng từ BCTC — dùng để vào lệnh thì nên đối chiếu một lần",
             "CafeF · KQKD quý, đổi năm trên URL về năm trước")
    if basis_q == "total":
        note("vnq", "báo cáo không tách dòng “cổ đông công ty mẹ” — máy đang dùng LNST "
                    "TỔNG, tập đoàn có công ty con lỗ sẽ bị chấm sai", "FireAnt · BCTC quý")
    if calc["npat_yoy_q"] is None:
        ly_np = h.get(last_year_q(pq[0]), {}).get("npat") if pq else None
        if ly_np is not None and ly_np <= 0:
            # Gốc âm hoặc bằng 0 thì % tăng trưởng KHÔNG có nghĩa (lỗ 10 tỷ lên lãi 1 tỷ
            # ra "+110%" là con số vô nghĩa). Nói rõ là gốc lỗ, đừng nói là "thiếu số".
            note("vnq", f"cùng kỳ năm trước lỗ ({ty(ly_np)} tỷ) nên phần trăm tăng trưởng "
                        "không có nghĩa — máy không tính. Đây có thể là nền so sánh dễ, "
                        "phải tự nhìn con số tuyệt đối",
                 "CafeF · KQKD quý cùng kỳ năm trước")
        else:
            note("vnq", "chưa có số cùng kỳ năm trước (cả báo cáo lẫn suy ngược đều thiếu)",
                 "CafeF · KQKD quý cùng kỳ năm trước")
    # Cổng đối chiếu chặn — đây là cảnh báo QUAN TRỌNG NHẤT của bước 1, vì nó nói
    # rằng chính nguồn dữ liệu đang tự mâu thuẫn chứ không phải chỉ thiếu số.
    for lbl, dev, okk in (("lợi nhuận", dev_npat, ok_npat), ("doanh thu", dev_rev, ok_rev)):
        if dev is None:
            note("vnq", f"không đối chiếu được chuỗi luỹ kế {lbl} với báo cáo (thiếu kỳ "
                        "hoặc doanh nghiệp đang lỗ) — máy không suy ngược cùng kỳ",
                 "CafeF · KQKD quý cùng kỳ năm trước")
        elif not okk:
            note("vnq", f"chuỗi luỹ kế {lbl} LỆCH {dev}% so với tổng 4 quý báo cáo "
                        f"(ngưỡng {TTM_DEV_MAX}%) — nguồn tự mâu thuẫn nên máy TỪ CHỐI suy "
                        "ngược cùng kỳ. Bước này phải đọc tay hoàn toàn",
                 "CafeF · KQKD quý, mở thêm tab cùng kỳ năm trước")
    if calc["noncore_pct"] is not None and 20 <= calc["noncore_pct"] <= NONCORE_WARN:
        note("vnone", f"lãi ngoài cốt lõi {calc['noncore_pct']}% — chưa quá ngưỡng "
                      f"{NONCORE_WARN:.0f}% nhưng đã đáng kể, và máy không biết khoản đó có "
                      "tái diễn được năm sau không",
             "CafeF · Thu nhập khác & hoàn nhập dự phòng")
    # Biên ròng cùng kỳ chia hai số mà CẢ HAI đều là số suy ngược → sai số của phép
    # suy ngược vào đây hai lần. Nói ra, đừng để người đọc tưởng đang nhìn số báo cáo.
    if nm_ly_derived and nm_delta is not None:
        note("vnmar", "biên ròng cùng kỳ năm trước tính từ số suy ngược (đối chiếu lệch "
                      f"{dev_npat}% ở lợi nhuận, {dev_rev}% ở doanh thu) — đủ chắc để thấy "
                      "xu hướng, chưa đủ chắc để cãi nhau về vài phần mười điểm",
             "CafeF · KQKD quý cùng kỳ năm trước")
    if is_bank:
        if bank and bank.get("npl") is None:
            note("vnsec", "bảng tỉ số không trả NPL cho mã này",
                 "CafeF · Thuyết minh BCTC, phần nhóm nợ 3-5")
        if bank and bank.get("car") is not None:
            note("vnsec", f"CAR {bank['car']}% là số của CẢ NĂM gần nhất, không phải quý — "
                          "nguồn chỉ công bố CAR theo năm", "báo cáo thường niên của ngân hàng")
        note("vnmar", "ngân hàng không có “biên lợi nhuận gộp” — máy chỉ so được biên ròng "
                      "trên tổng thu nhập hoạt động, và NIM", "CafeF · KQKD")
    else:
        note("vnbs", "máy chỉ so TỔNG tồn kho với doanh thu. Nguyên vật liệu tăng có thể là "
                     "tin TỐT (gom hàng giá rẻ trước chu kỳ), chỉ thành phẩm tăng mới là hàng "
                     "ế — máy không tách được hai cái đó", "CafeF · Thuyết minh hàng tồn kho")
    note("vndil", "số cổ phiếu suy từ VỐN GÓP nên chỉ thấy phần ĐÃ phát hành xong. Kế hoạch "
                  "phát hành riêng lẻ / ESOP đã thông qua nhưng CHƯA thực hiện không hiện ở đây",
         "danh sách sự kiện ngay bên dưới + Vietstock · Hồ sơ doanh nghiệp")

    return {
        "sector": "bank" if is_bank else "corp",
        "manual": man,
        # Ghi ro so lay tu dau va da tu kiem chua — de nguoi doc biet minh dang nhin cai gi
        "check": {**chk, "npat_basis": basis_y, "npat_basis_q": basis_q,
                  "backfilled": n_bf,
                  # Hai so nay la BANG CHUNG cho phep suy nguoc, khong phai thong tin
                  # phu: 0,00% nghia la chuoi TTM va bao cao khop tuyet doi.
                  "ttm_dev_npat": dev_npat, "ttm_dev_rev": dev_rev,
                  "ttm_dev_max": TTM_DEV_MAX},
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
    ap.add_argument("--sleep", type=float, default=None,
                    help="giay nghi giua 2 request; de trong = tu tinh theo tier tai khoan")
    args = ap.parse_args()
    if args.sleep is None:
        args.sleep = vnstock_sleep()

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
    tier = vnstock_tier()
    print(f"[i] Lay bao cao tai chinh {len(syms)} ma "
          f"(~{len(syms) * 6 * args.sleep / 60:.1f} phut, tier '{tier}', "
          f"nghi {args.sleep}s/request)…")
    if tier == "guest":
        print("[i] Dang chay KHONG API key: 20 req/phut va BCTC chi 4 ky. Key MIEN PHI "
              "(vnstocks.com/account#api-key) cho 60 req/phut va 8 ky — 8 quy nghia la "
              "co san quy cung ky nam truoc, khong phai suy nguoc.")
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
        c, v = f["calc"], f["calc"]["val"]
        yoy = (f"LNST quy YoY {c['npat_yoy_q']:+.1f}%"
               + ("(suy nguoc)" if c["yoy_src"] == "ttm" else "")
               if c["npat_yoy_q"] is not None else "quy YoY: chua du lich su")
        roe_v = v["roe_ttm"] if v["roe_ttm"] is not None else c["roe"]
        roe = f"ROE {roe_v}%" if roe_v is not None else "ROE n/a"
        pe = f"PE {v['pe']}" if v["pe"] is not None else "PE n/a"
        mar = f"bien rong {c['nm_delta']:+.2f}d" if c["nm_delta"] is not None else "bien n/a"
        ocf = ("OCF: khong ap dung (ngan hang)" if f["sector"] == "bank"
               else f"OCF/LNST {c['ocf_ratio']}x" if c["ocf_ratio"] is not None else "OCF n/a")
        dil = f"CP {c['share_yoy']:+.1f}%" if c["share_yoy"] is not None else "CP n/a"
        bad = [k for k, x in f["auto"].items() if x == -1]
        ck = f["check"]
        note = "" if ck["ok"] else "  ⛔ BANG CAN DOI KHONG KHOP — khong cham diem"
        print(f"  {s:<5} [{f['sector']}/{ck['npat_basis']}] {yoy} · {roe} · {pe} · {mar}"
              f" · {ocf} · {dil}"
              + (f"  ⚠ hong: {','.join(bad)}" if bad else "  ✓") + note)
        if f["sector"] == "bank" and c["bank"]:
            b = c["bank"]
            print(f"        NH: NPL {b.get('npl')}% (nam truoc {b.get('npl_ly')}%) · "
                  f"bao phu {b.get('llr')}% · NIM {b.get('nim')}% · CIR {b.get('cir')}% · "
                  f"CASA {b.get('casa')}% · CAR {b.get('car')}%")
        if f["manual"]:
            print(f"        ✎ tu kiem tay {len(f['manual'])} cho: "
                  + ", ".join(sorted({m['k'] for m in f['manual']})))
    if funds:
        print(f"[i] Nguon tra ve {max(len(f['q_periods']) for f in funds.values())} quy / "
              f"{max(len(f['y_periods']) for f in funds.values())} nam.")
    nq = sum(1 for f in funds.values() if f["calc"]["npat_yoy_q"] is None)
    if nq:
        print(f"[i] {nq} ma van chua co quy cung ky nam truoc (ca suy nguoc lan lich su deu "
              f"thieu) — buoc 1 doc tay tren CafeF.")
    if fails:
        print(f"[!] That bai: {', '.join(fails)}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
