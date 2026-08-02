# -*- coding: utf-8 -*-
"""Theo doi watchlist va gui Telegram khi gia cham pivot / gan pivot / cham stop.

Mac dinh theo thi truong Viet Nam (HOSE/HNX/UPCOM). Tu bo qua khi san dong cua.

Cach dung:
    python alert_watcher.py                 # thi truong VN
    python alert_watcher.py --market us     # thi truong My
    python alert_watcher.py --force         # chay ke ca khi san dong cua
    python alert_watcher.py --test          # gui tin nhan test Telegram
"""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from tv_common import BASE, load_config, load_json, save_json, send_telegram, get_quotes

ET = ZoneInfo("America/New_York")
VN = ZoneInfo("Asia/Ho_Chi_Minh")
TZ = {"us": ET, "vn": VN}


def market_is_open(market="vn", now=None) -> bool:
    """VN: 09:00-11:30 va 13:00-14:45 (co ATC). My: 09:30-16:00 gio ET."""
    tz = TZ.get(market, VN)
    now = now or datetime.now(tz)
    if now.weekday() >= 5:  # T7, CN
        return False
    m = now.hour * 60 + now.minute
    if market == "us":
        return 9 * 60 + 30 <= m <= 16 * 60
    return (9 * 60 <= m <= 11 * 60 + 30) or (13 * 60 <= m <= 14 * 60 + 45)


def fmt_num(x):
    return f"{x:,.2f}" if isinstance(x, (int, float)) else "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="chay ke ca khi market dong")
    ap.add_argument("--test", action="store_true", help="gui tin nhan test roi thoat")
    ap.add_argument("--market", choices=["vn", "us"], default="vn", help="thi truong theo doi")
    args = ap.parse_args()

    cfg = load_config()

    if args.test:
        send_telegram(cfg, "✅ Trading Journal bot hoat dong! (tin nhan test)")
        return

    if not args.force and not market_is_open(args.market):
        print(f"Thi truong {args.market.upper()} dang dong cua — bo qua. (dung --force de chay thu)")
        return

    watchlist = load_json(BASE / "watchlist.json", [])
    if not watchlist:
        print("watchlist.json trong — khong co gi de theo doi.")
        return

    state_path = BASE / "state.json"
    state = load_json(state_path, {})
    today = datetime.now(TZ.get(args.market, VN)).strftime("%Y-%m-%d")
    approach_pct = float(cfg.get("approach_pct", 1.5))

    symbols = sorted({w["symbol"].upper() for w in watchlist})
    quotes = get_quotes(symbols, market="america" if args.market == "us" else "vietnam")

    # Gia co phieu VN la VND, khong phai USD — dat ky hieu dung cho tung thi truong
    money = ((lambda v: f"${fmt_num(v)}") if args.market == "us"
             else (lambda v: f"{fmt_num(v)}đ"))

    messages = []
    for w in watchlist:
        sym = w["symbol"].upper()
        q = quotes.get(sym)
        if not q:
            print(f"[!] Khong lay duoc gia cho {sym} (kiem tra ma co dung san My khong)")
            continue
        price = q["close"]
        note = w.get("note", "")
        vol_ratio = (q["volume"] / q["avg_vol"]) if q.get("avg_vol") else None
        vol_txt = f" | Vol {vol_ratio:.1f}x TB30" if vol_ratio else ""

        pivot = w.get("pivot")
        if pivot:
            key_break = f"{sym}:breakout:{today}"
            key_near = f"{sym}:near:{today}"
            if price >= pivot and key_break not in state:
                state[key_break] = price
                messages.append(
                    f"🚀 <b>{sym} VUOT PIVOT</b>\n"
                    f"Gia: <b>{money(price)}</b> ≥ pivot {money(pivot)} "
                    f"(+{(price / pivot - 1) * 100:.1f}%){vol_txt}\n"
                    f"📝 {note}"
                )
            elif pivot * (1 - approach_pct / 100) <= price < pivot and key_near not in state:
                state[key_near] = price
                messages.append(
                    f"👀 <b>{sym} GAN PIVOT</b> (con {(pivot / price - 1) * 100:.1f}%)\n"
                    f"Gia: {money(price)} / pivot {money(pivot)}{vol_txt}\n"
                    f"📝 {note}"
                )

        stop = w.get("stop")
        if stop:
            key_stop = f"{sym}:stop:{today}"
            if price <= stop and key_stop not in state:
                state[key_stop] = price
                messages.append(
                    f"🛑 <b>{sym} CHAM STOP</b>\n"
                    f"Gia: <b>{money(price)}</b> ≤ stop {money(stop)}\n"
                    f"📝 {note}"
                )

    # Don dep: chi giu cac canh bao cua hom nay
    state = {k: v for k, v in state.items() if k.endswith(today)}

    if messages:
        send_telegram(cfg, "\n\n".join(messages))
        print(f"Da gui {len(messages)} canh bao.")
    else:
        print(f"OK — {len(symbols)} ma, khong co canh bao moi.")

    save_json(state_path, state)


if __name__ == "__main__":
    main()
