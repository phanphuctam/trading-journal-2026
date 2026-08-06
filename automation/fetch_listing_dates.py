# -*- coding: utf-8 -*-
"""Lay NGAY NIEM YET that cua tung ma -> .vncache/_listing.json

Vi sao can: cache gia chi lui toi ~2018-08 (gioi han cua nguon KBS), nen khong the
suy ra tuoi niem yet tu du lieu gia — VNM/FPT/HPG deu hien "phien dau 2018-08-02"
du chung len san tu rat lau. Ma tieu chi cua Minervini (Ch.6) la cong ty phai NON
TRE: phan lon sieu co phieu bung no trong 8-10 nam dau sau khi dai chung. Muon kiem
dinh tieu chi do thi bat buoc phai co ngay niem yet that.

Ghi tung ma mot nen dung giua chung van dung duoc phan da lay; chay lai se bo qua
nhung ma da co.

    python fetch_listing_dates.py                 # lay cho danh sach ma thanh khoan
    python fetch_listing_dates.py --all           # lay cho moi ma co trong cache
"""
import argparse
import json
import time
from pathlib import Path

from tv_common import BASE

CACHE = BASE / ".vncache"
OUT = CACHE / "_listing.json"
LIQUID = CACHE / "_liquid.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="moi ma trong cache, khong chi ma thanh khoan")
    ap.add_argument("--sleep", type=float, default=3.2, help="giay giua hai request (gioi han 20/phut)")
    args = ap.parse_args()

    if args.all or not LIQUID.exists():
        syms = sorted(f.stem for f in CACHE.glob("*.parquet") if not f.stem.startswith("_")
                      and f.stem != "VNINDEX")
    else:
        syms = [s.strip() for s in LIQUID.read_text(encoding="utf-8").splitlines() if s.strip()]

    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = [s for s in syms if s not in done]
    print(f"[i] {len(syms)} ma · da co {len(done)} · can lay {len(todo)} "
          f"(~{len(todo)*args.sleep/60:.0f} phut)")

    from vnstock import Company
    for i, s in enumerate(todo, 1):
        try:
            time.sleep(args.sleep)
            o = Company(symbol=s).overview()
            ld = None
            if o is not None and len(o) and "listing_date" in o.columns:
                v = o["listing_date"].iloc[0]
                ld = None if v is None or str(v) == "nan" else str(v)[:10]
            done[s] = ld
        except Exception as e:
            done[s] = None
            print(f"    bo qua {s}: {str(e)[:60]}")
        if i % 20 == 0:
            OUT.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding="utf-8")
            print(f"    {i}/{len(todo)}")
    OUT.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding="utf-8")
    ok = sum(1 for v in done.values() if v)
    print(f"[ok] {OUT} — {ok}/{len(done)} ma co ngay niem yet")


if __name__ == "__main__":
    main()
