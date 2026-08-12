# -*- coding: utf-8 -*-
"""HO SO doanh nghiep cho cac ma TRONG WATCHLIST -> scans/profile_vn.json

fund_vn.py doc BAO CAO TAI CHINH (con so). File nay doc phan con lai cua ho so —
nhung thu quyet dinh gia khong kem gi loi nhuan nhung khong nam trong BCTC:

  · ROOM NGOAI (buoc 6). Ma KIN ROOM thi quy ngoai muon mua BAT BUOC phai thoa
    thuan ngoai san, luc mua khong hien len khop lenh. Bang trong app canh bao
    dung dieu do: cham "khoi ngoai khong mua" cho mot ma kin room la cham SAI, va
    no cham sai dung nhung ma tot nhat san (FPT, MWG, PNJ). May khong doc duoc
    mua/ban rong (vnstock ban cong dong khong mo endpoint do), nhung no doc duoc
    ty le so huu con lai — tuc doc duoc CHINH XAC luc nao tieu chi kia mat hieu luc.

  · SU KIEN SAP TOI (buoc 10). Ngay GDKHQ o VN lam gia bi dieu chinh giam DUNG
    bang phan co tuc/thuong: chia thuong 100% thi gia con mot nua. Tren do thi gia
    THO no giong het mot phien sap thung nen -> cat lo oan. Day la thu phai biet
    TRUOC, khong phai giai thich sau.

  · PHAT HANH DA THONG QUA NHUNG CHUA THUC HIEN (buoc 5). fund_vn.py dem so co
    phieu tu VON GOP nen chi thay phan DA phat hanh xong. Ke hoach phat hanh rieng
    le / ESOP vua duoc DHCD thong qua la qua bom hen gio ma bang can doi khong he
    biet. No nam o bang su kien.

  · GIAO DICH NOI BO (buoc 11). Ban lanh dao dang ky ban khoi luong lon ngay sau
    khi gia chay la tin hieu xau bac nhat o VN.

  · CHAT LUONG CONG BO THONG TIN (buoc 0). May QUET tieu de tin de tim tu khoa
    "y kien ngoai tru", "hoi to", "dien canh bao/kiem soat", "cham nop". Tim thay
    thi bao dong; KHONG tim thay thi may van cham 0 chu khong cham DAT — khong
    thay dau hieu khong co nghia la sach, chi co nghia la 50 tin gan nhat khong
    nhac den. Buoc nay nguoi VAN phai tu doc.

GIOI HAN DA KIEM CHUNG (vnstock 4.0.5, 12/08/2026):
  · Trading.foreign_trade / insider_deal / prop_trade / order_stats va
    Company.insider_trading / ownership / capital_history deu nem NotImplementedError
    voi nguon VCI. Nen KHONG co mua/ban rong khoi ngoai va tu doanh theo phien.
    Giao dich noi bo lay gian tiep qua bang SU KIEN (ma su kien DD*), it chi tiet hon.
  · Bang tin chi tra ~50 tin gan nhat, va nhieu tin thieu ngay/nguon.

Cach dung:
    python profile_vn.py              # ma trong watchlist.json
    python profile_vn.py PET ACB      # chi mot vai ma
"""
import argparse
import re
import time
import unicodedata
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")

from tv_common import BASE, load_json, save_json

WATCHLIST = BASE / "watchlist.json"
OUT = BASE.parent / "scans" / "profile_vn.json"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")

ROOM_TIGHT = 1.0        # con duoi 1 diem % so voi tran = coi nhu KIN ROOM
CAL_SOON = 14           # "sap toi" = trong bao nhieu ngay
INSIDER_BACK = 180      # nhin lai bao nhieu ngay cho giao dich noi bo
DILUTE_BACK = 365       # nhin lai bao nhieu ngay cho su kien pha loang


def nod(s):
    """Bo dau tieng Viet + ha chu thuong. Doi chieu tu khoa thi khong duoc phu
    thuoc vao viec nguon ghi co dau hay khong, hoa hay thuong."""
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")


# ── Tu khoa. Viet KHONG DAU vi da chay qua nod() truoc khi so ─────────────────
# Buoc 0: dau hieu chat luong cong bo thong tin co van de. Chia hai muc do vi
# "y kien ngoai tru" va "thay ke toan truong" khong the cung mot mau do.
NEWS_RED = [
    ("y kien ngoai tru", "kiem toan neu y kien NGOAI TRU"),
    ("ngoai tru cua kiem toan", "kiem toan neu y kien NGOAI TRU"),
    ("tu choi dua ra y kien", "kiem toan TU CHOI dua ra y kien"),
    ("hoi to", "HOI TO / dieu chinh so lieu da cong bo"),
    ("dien kiem soat", "co phieu vao dien KIEM SOAT"),
    ("dien canh bao", "co phieu vao dien CANH BAO"),
    ("han che giao dich", "co phieu bi HAN CHE giao dich"),
    ("dinh chi giao dich", "co phieu bi DINH CHI giao dich"),
    ("huy niem yet", "nguy co HUY NIEM YET"),
]
NEWS_AMBER = [
    ("cham nop", "cham nop bao cao"),
    ("chua cong bo", "cham cong bo thong tin"),
    ("xu phat", "bi xu phat hanh chinh"),
    ("vi pham", "co ghi nhan vi pham"),
    # KHONG bat "giai trinh" chung chung: HOSE BAT BUOC giai trinh moi khi KQKD bien
    # dong > 10%, nen gan nhu ma nao cung co — bat no vao day thi ca watchlist deu
    # sang den vang va den vang mat het y nghia. Chi bat phan sau kiem toan.
    ("sau kiem toan", "so lieu truoc/sau kiem toan lech nhau"),
    ("tu nhiem", "bien dong nhan su cap cao"),
    ("mien nhiem", "bien dong nhan su cap cao"),
]
# Buoc 5: su kien lam TANG so co phieu luu hanh
EV_DILUTE = ["niem yet them", "niem yet bo sung", "phat hanh them", "chao ban",
             "co tuc bang co phieu", "thuong co phieu", "esop", "phat hanh rieng le",
             "phat hanh co phieu", "tang von"]
# Buoc 11: giao dich cua nguoi ben trong
EV_INSIDER = ["giao dich noi bo", "co dong lon", "nguoi lien quan", "co dong noi bo"]
# Phai la CUM TU, khong duoc de tran mot tieng "ban": "ban lanh dao", "ban hanh",
# "ban dieu hanh" deu chua no, va mot ma bi gan nham "noi bo dang ky BAN" thi canh
# bao do sai o dung cho nguoi ta tin no nhat.
EV_SELL = ["dang ky ban", "dang ki ban", "ban co phieu", "ban ra", "thoai von",
           "to sell", "sell shares"]
EV_BUY = ["dang ky mua", "dang ki mua", "mua co phieu", "mua vao", "mua lai",
          "to buy", "buy shares", "subscribe to buy"]
# Buoc 10: moc lich phai biet TRUOC
EV_MEETING = ["dai hoi", "hop dai hoi", "dhcd", "dhdcd"]
EV_CASH_DIV = ["co tuc bang tien", "tra co tuc"]


# Tin GO BO tinh trang xau dung nguyen tu khoa cua tin GAN tinh trang xau:
# "khong con thuoc dien canh bao" chua tron ven "dien canh bao". Khong loc thi may
# bao dong dung luc doanh nghiep vua thoat an — tuc bao SAI theo huong nguy hiem.
NEG_PREFIX = ["khong con", "ra khoi", "duoc go bo", "go bo", "thoat khoi", "huy bo",
              "cham dut", "dua ra khoi"]


def hit(text, table):
    """Tra list mo ta cua moi tu khoa xuat hien trong `text`, tru tin go bo."""
    t = nod(text)
    if any(n in t for n in NEG_PREFIX):
        return []
    return sorted({desc for kw, desc in table if kw in t})


def any_kw(text, kws):
    t = nod(text)
    return any(k in t for k in kws)


def d(v):
    """Chuoi ngay ISO cua vnstock -> date. Hong thi None, khong doan."""
    if v is None or v != v:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(v))
    if not m:
        return None
    try:
        return datetime(int(m[1]), int(m[2]), int(m[3])).date()
    except ValueError:
        return None


def num(v):
    if v is None or v != v:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def p1(v, scale=100.0):
    """Phan le -> phan tram, lam tron 2 chu so."""
    x = num(v)
    return None if x is None else round(x * scale, 2)


def fetch(sym, sleep):
    """4 loi goi cho mot ma. Hong mot bang thi bo bang do, khong bo ca ma —
    ho so thieu mot phan van dung duoc, con dung han thi khong."""
    from vnstock.api.company import Company
    c = Company(symbol=sym, source="VCI")
    out = {}
    for name, fn in (("ov", c.overview), ("sh", c.shareholders),
                     ("ev", c.events), ("nw", c.news)):
        try:
            time.sleep(sleep)
            out[name] = fn()
        except Exception as e:
            print(f"    {sym}: bang {name} hong ({type(e).__name__}) — bo qua")
            out[name] = None
    return out


def build_overview(ov):
    """Thong tin nen + ROOM NGOAI. Room la thu quan trong nhat o day."""
    if ov is None or not len(ov):
        return None
    r = ov.iloc[0]
    fo, fomax = p1(r.get("foreigner_percentage")), p1(r.get("maximum_foreign_percentage"))
    # Tran room = 0 la DU LIEU THIEU chu khong phai "cam nguoi nuoc ngoai": PET tra
    # ve tran 0% trong khi ngoai dang giu 0,77% — vo ly, tuc o trong. Coi 0 la 0 thi
    # may se bao KIN ROOM cho moi ma thieu du lieu, tuc bao dong gia dung noi nguy
    # hiem nhat: cho ma la ly do BO QUA mot tieu chi.
    if fomax is not None and fomax <= 0:
        fomax = None
    left = None if fo is None or fomax is None else round(fomax - fo, 2)
    mc = num(r.get("market_cap"))
    return {
        "name": r.get("organ_short_name") or r.get("organ_name"),
        "sector": r.get("sector"),
        "icb2": r.get("icb_code_lv2"), "icb4": r.get("icb_code_lv4"),
        "listing_date": str(r.get("listing_date") or "")[:10] or None,
        "market_cap_ty": None if mc is None else round(mc / 1e9, 1),
        "shares_m": None if num(r.get("issue_share")) is None
        else round(num(r["issue_share"]) / 1e6, 1),
        "free_float_pct": p1(r.get("free_float_percentage")),
        "state_pct": p1(r.get("state_percentage")),
        "foreign_pct": fo, "foreign_max_pct": fomax, "room_left_pct": left,
        # KIN ROOM: day la co quan trong nhat cua khoi nay, xem docstring
        "room_full": bool(left is not None and left <= ROOM_TIGHT),
        "target_price": num(r.get("target_price")),
        "upside_pct": p1(r.get("upside_to_target_percent")),
        "analyst": r.get("analyst"),
    }


def build_holders(sh):
    """Muc do tap trung so huu. O VN mot co dong nam qua nua thi thanh khoan thuc
    te mong hon nhieu so voi von hoa — va gia do dang bi mot nguoi quyet dinh."""
    if sh is None or not len(sh):
        return None
    rows = []
    for _, r in sh.iterrows():
        p = p1(r.get("share_own_percent"))
        if p is None or p <= 0:
            continue
        rows.append({"name": str(r.get("share_holder") or "")[:80], "pct": p})
    rows.sort(key=lambda x: -x["pct"])
    return {"n": len(rows),
            "top1_pct": rows[0]["pct"] if rows else None,
            "top5_pct": round(sum(x["pct"] for x in rows[:5]), 2) if rows else None,
            "top": rows[:8]}


def build_events(ev, today):
    """Phan loai su kien thanh 4 ro: sap toi, pha loang, noi bo, con lai.

    Mot su kien co the roi vao nhieu ro (vd 'co tuc bang co phieu' vua la pha
    loang vua co ngay GDKHQ sap toi) — khong ep no chon mot ro, vi ca hai goc nhin
    deu can den no.
    """
    if ev is None or not len(ev):
        return None
    soon, dilute, insider, cash = [], [], [], []
    for _, r in ev.iterrows():
        name = str(r.get("event_name_vi") or "")
        title = str(r.get("event_title_vi") or "")
        txt = name + " " + title
        ex = d(r.get("exright_date"))
        rec = d(r.get("record_date"))
        pub = d(r.get("public_date")) or d(r.get("display_date1"))
        item = {"name": name, "title": title[:160],
                "exright": str(ex) if ex else None,
                "record": str(rec) if rec else None,
                "public": str(pub) if pub else None,
                "ratio": num(r.get("exercise_ratio")),
                "value_per_share": num(r.get("value_per_share"))}
        # ── Sap toi: chi tinh theo ngay GDKHQ / chot danh sach, la hai moc ANH
        #    HUONG THANG len gia va len quyen so huu.
        for dt, kind in ((ex, "GDKHQ"), (rec, "chot danh sach")):
            if dt and today <= dt <= today + timedelta(days=CAL_SOON):
                soon.append({**item, "kind": kind, "date": str(dt),
                             "in_days": (dt - today).days})
                break
        if any_kw(txt, EV_MEETING):
            dt = ex or rec or pub
            if dt and today <= dt <= today + timedelta(days=CAL_SOON):
                soon.append({**item, "kind": "DHCD", "date": str(dt),
                             "in_days": (dt - today).days})
        if any_kw(txt, EV_DILUTE):
            dt = pub or ex or rec
            if dt is None or dt >= today - timedelta(days=DILUTE_BACK):
                dilute.append(item)
        if any_kw(txt, EV_INSIDER):
            dt = pub or ex or rec
            if dt is None or dt >= today - timedelta(days=INSIDER_BACK):
                side = ("ban" if any_kw(txt, EV_SELL) else
                        "mua" if any_kw(txt, EV_BUY) else "?")
                insider.append({**item, "side": side})
        if any_kw(txt, EV_CASH_DIV):
            cash.append(item)
    soon.sort(key=lambda x: x["date"])
    return {"soon": soon[:8], "dilute": dilute[:10],
            "insider": insider[:12], "cash_div": cash[:4],
            "n_sell": sum(1 for x in insider if x["side"] == "ban"),
            "n_buy": sum(1 for x in insider if x["side"] == "mua")}


def build_news(nw):
    """Quet TIEU DE tin tim dau hieu cong bo thong tin co van de."""
    if nw is None or not len(nw):
        return None
    red, amber, recent = [], [], []
    for _, r in nw.iterrows():
        t = str(r.get("news_title") or r.get("friendly_title") or "")
        if not t:
            continue
        pub = str(r.get("public_date") or "")[:10]
        recent.append({"t": t[:150], "d": pub})
        for x in hit(t, NEWS_RED):
            red.append({"flag": x, "t": t[:150], "d": pub})
        for x in hit(t, NEWS_AMBER):
            amber.append({"flag": x, "t": t[:150], "d": pub})
    return {"n": len(recent), "red": red[:8], "amber": amber[:8], "recent": recent[:12]}


def build(sym, raw, today):
    ov = build_overview(raw.get("ov"))
    sh = build_holders(raw.get("sh"))
    ev = build_events(raw.get("ev"), today)
    nw = build_news(raw.get("nw"))

    # Chuoi trong `man` di THANG len giao dien nen viet CO DAU.
    auto, man = {}, []

    def note(k, why, where):
        man.append({"k": k, "why": why, "where": where})

    # ── Buoc 0: chat luong cong bo thong tin ──
    # KHONG BAO GIO cham DAT o day. Quet 50 tieu de tin ma khong thay gi thi chi
    # co nghia la 50 tieu de do khong nhac den, khong co nghia la doanh nghiep sach.
    if nw:
        auto["vndisc"] = -1 if nw["red"] else 0
        if not nw["red"]:
            note("vndisc", f"máy chỉ quét TIÊU ĐỀ của {nw['n']} tin gần nhất và không thấy "
                           "từ khoá báo động — đây KHÔNG phải kết luận “sạch”. Ý kiến kiểm "
                           "toán nằm trong file BCTC chứ không nằm ở tiêu đề tin",
                 "CafeF · tin doanh nghiệp + BCTC kiểm toán năm gần nhất")

    # ── Buoc 6: bao tro cua dong tien lon ──
    # vnstock ban cong dong khong mo mua/ban rong khoi ngoai -> KHONG cham. Nhung
    # doc duoc room con lai, tuc doc duoc chinh xac luc nao tieu chi nay mat hieu luc.
    if ov:
        auto["vnfo"] = 0
        if ov["foreign_max_pct"] is None:
            note("vnfo", f"nguồn không có TRẦN ROOM của mã này (ngoại đang giữ "
                         f"{ov['foreign_pct']}%) — máy không biết mã có kín room hay không",
                 "HOSE · danh sách tỷ lệ sở hữu nước ngoài tối đa")
        elif ov["room_full"]:
            note("vnfo", f"KÍN ROOM (ngoại giữ {ov['foreign_pct']}% / trần "
                         f"{ov['foreign_max_pct']}%) — quỹ ngoại muốn mua bắt buộc phải thoả "
                         "thuận ngoài sàn, lực mua đó KHÔNG hiện lên khớp lệnh. Đừng chấm "
                         "trượt bước này chỉ vì không thấy khối ngoại mua",
                 "không cần kiểm — đây là lý do BỎ QUA tiêu chí")
        else:
            note("vnfo", "máy không đọc được mua/bán ròng của khối ngoại (vnstock bản cộng "
                         "đồng khoá endpoint này) — phải tự xem",
                 "Vietstock · Thống kê giao dịch, tab GD nước ngoài")

    # ── Buoc 5: pha loang chua thuc hien ──
    if ev is not None:
        if ev["dilute"]:
            auto["vndil"] = -1
            note("vndil", f"có {len(ev['dilute'])} sự kiện làm tăng số cổ phiếu trong 12 tháng "
                          "(niêm yết thêm / phát hành / cổ tức bằng cổ phiếu). Máy không biết "
                          "cái nào ĐÃ xong và cái nào còn là kế hoạch treo trên đầu",
                 "Vietstock · Hồ sơ doanh nghiệp + nghị quyết ĐHCĐ")

        # ── Buoc 11: giao dich noi bo ──
        if ev["insider"]:
            auto["vnins"] = -1 if ev["n_sell"] else (1 if ev["n_buy"] else 0)
            if ev["n_sell"]:
                note("vnins", f"{ev['n_sell']} lượt đăng ký BÁN của nội bộ/cổ đông lớn trong "
                              "6 tháng. Máy đọc từ bảng sự kiện nên không biết khối lượng, và "
                              "không biết đã bán hết hay chưa",
                     "Vietstock · Giao dịch cổ đông nội bộ")
        else:
            auto["vnins"] = 0

        # ── Buoc 10: lich su kien ──
        # DAT khi 2 tuan toi trong lich. Khong bao gio dam bao duoc ngay ra BCTC:
        # o VN no khong duoc an dinh truoc, chi co han chot 20-30 ngay sau khi chot quy.
        auto["vncald"] = -1 if ev["soon"] else 0
        if ev["soon"]:
            for s in ev["soon"][:3]:
                note("vncald", f"{s['kind']} ngày {s['date']} (còn {s['in_days']} ngày): "
                               f"{s['name']}", "Vietstock · Lịch sự kiện")
        note("vncald", "ngày công bố BCTC quý KHÔNG có trong bảng sự kiện — ở VN nó không được "
                       "ấn định trước, chỉ có hạn chót 20-30 ngày sau khi chốt quý",
             "canh cuối tháng 1/4/7/10")

    if sh and sh["top1_pct"] and sh["top1_pct"] >= 50:
        note("vnfo", f"một cổ đông nắm {sh['top1_pct']}% — lượng trôi nổi thực tế mỏng hơn "
                     "nhiều so với vốn hoá, và giá đang do một người quyết định",
             "Vietstock · Cơ cấu cổ đông")

    return {"overview": ov, "holders": sh, "events": ev, "news": nw,
            "auto": auto, "manual": man}


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
    OUT.parent.mkdir(exist_ok=True)
    if not syms:
        print("watchlist.json trong — khong co ma nao de lay.")
        save_json(OUT, {"profiles": {}})
        return

    today = datetime.now(TZ).date()
    profiles, fails = {}, []
    print(f"[i] Lay ho so {len(syms)} ma (~{len(syms) * 4 * args.sleep / 60:.1f} phut)…")
    for s in syms:
        try:
            profiles[s] = build(s, fetch(s, args.sleep), today)
        except Exception as e:
            fails.append(s)
            print(f"    bo qua {s}: {type(e).__name__} {str(e)[:70]}")

    save_json(OUT, {
        "app": "trading-journal", "market": "VN",
        "checked_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "source": "vnstock/VCI · overview + co dong + su kien + tin",
        "room_tight": ROOM_TIGHT, "cal_soon_days": CAL_SOON,
        "profiles": profiles,
    })

    for s, p in profiles.items():
        ov, ev, nw = p["overview"], p["events"], p["news"]
        room = ("room: n/a" if not ov or ov["room_left_pct"] is None else
                (f"KIN ROOM ({ov['foreign_pct']}/{ov['foreign_max_pct']}%)" if ov["room_full"]
                 else f"room con {ov['room_left_pct']}d"))
        bits = [room]
        if ev:
            if ev["soon"]:
                bits.append(f"⏰ {len(ev['soon'])} su kien trong {CAL_SOON} ngay "
                            f"({ev['soon'][0]['kind']} {ev['soon'][0]['date']})")
            if ev["dilute"]:
                bits.append(f"⚠ {len(ev['dilute'])} su kien pha loang/12 thang")
            if ev["n_sell"]:
                bits.append(f"⚠ noi bo dang ky BAN x{ev['n_sell']}")
        if nw and nw["red"]:
            bits.append("⛔ tin: " + nw["red"][0]["flag"])
        print(f"  {s:<5} " + " · ".join(bits))
    if fails:
        print(f"[!] That bai: {', '.join(fails)}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
