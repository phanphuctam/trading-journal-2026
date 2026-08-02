# -*- coding: utf-8 -*-
"""Lay ty gia USD/VND, ghi scans/fx.json cho journal doc.

Vi sao can: nhat ky ghi lenh My bang USD, lenh VN bang VND. Journal luu ty gia
NGAY TAI THOI DIEM ghi lenh vao tung ban ghi (truong `fx`), nen duong von khong
bi ve lai moi khi ty gia doi. File nay chi cung cap ty gia MOI NHAT — dung lam
gia tri mac dinh cho lenh sap ghi, khong dung de tinh lai lenh cu.

Nguon (deu mien phi, khong can API key), lay cai nao thanh cong truoc:
  1. open.er-api.com          — ty gia trung binh thi truong
  2. currency-api (jsDelivr)  — CDN tinh, du phong khi (1) chet
Neu ca hai hong: giu nguyen gia tri cu trong fx.json (khong ghi de bang rac).

Luu y: day la ty gia lien ngan hang. Khi thuc su chuyen tien, ngan hang ban ra
cao hon khoang 0,5-1%. Journal cho phep sua tay neu muon dung ty gia thuc te.

Cach dung:
    python fetch_fx.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent.parent / "scans" / "fx.json"
TIMEOUT = 20
FLOOR, CEIL = 15000, 50000   # chan gia tri vo ly (API doi format / tra nham don vi)

SOURCES = [
    ("open.er-api.com", "https://open.er-api.com/v6/latest/USD",
     lambda j: j["rates"]["VND"]),
    ("currency-api", "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
     lambda j: j["usd"]["vnd"]),
]


def main():
    rate = src = None
    for name, url, pick in SOURCES:
        try:
            j = requests.get(url, timeout=TIMEOUT).json()
            v = float(pick(j))
            if not (FLOOR <= v <= CEIL):
                print(f"[!] {name} tra ve {v} — ngoai khoang hop ly, bo qua")
                continue
            rate, src = round(v, 2), name
            break
        except Exception as e:
            print(f"[!] {name}: {str(e)[:70]}")

    if rate is None:
        if OUT.exists():
            old = json.loads(OUT.read_text(encoding="utf-8"))
            print(f"[!] Khong lay duoc ty gia — giu nguyen {old.get('usdvnd')} tu {old.get('date')}")
            return
        print("[!] Khong lay duoc ty gia va chua co fx.json")
        raise SystemExit(1)

    now = datetime.now(timezone.utc)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "usdvnd": rate,
        "date": now.strftime("%Y-%m-%d"),
        "fetched_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "source": src,
        "note": "Ty gia lien ngan hang. Ngan hang ban ra thuong cao hon 0,5-1%.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ok] 1 USD = {rate:,.0f} VND ({src})")


if __name__ == "__main__":
    main()
