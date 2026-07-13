# -*- coding: utf-8 -*-
"""Theo doi watchlist va gui Telegram khi gia cham pivot / gan pivot / cham stop.

Chay moi 5 phut qua Task Scheduler. Tu bo qua khi thi truong My dong cua.

Cach dung:
    python alert_watcher.py            # chay binh thuong
    python alert_watcher.py --force    # chay ke ca khi thi truong dong cua
    python alert_watcher.py --test     # gui tin nhan test Telegram
"""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from tv_common import BASE, load_config, load_json, save_json, send_telegram, get_quotes

ET = ZoneInfo("America/New_York")


def market_is_open(now=None) -> bool:
    now = now or datetime.now(ET)
    if now.weekday() >= 5:  # T7, CN
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def fmt_num(x):
    return f"{x:,.2f}" if isinstance(x, (int, float)) else "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="chay ke ca khi market dong")
    ap.add_argument("--test", action="store_true", help="gui tin nhan test roi thoat")
    args = ap.parse_args()

    cfg = load_config()

    if args.test:
        send_telegram(cfg, "✅ Trading Journal bot hoat dong! (tin nhan test)")
        return

    if not args.force and not market_is_open():
        print("Thi truong My dang dong cua — bo qua. (dung --force de chay thu)")
        return

    watchlist = load_json(BASE / "watchlist.json", [])
    if not watchlist:
        print("watchlist.json trong — khong co gi de theo doi.")
        return

    state_path = BASE / "state.json"
    state = load_json(state_path, {})
    today = datetime.now(ET).strftime("%Y-%m-%d")
    approach_pct = float(cfg.get("approach_pct", 1.5))

    symbols = sorted({w["symbol"].upper() for w in watchlist})
    quotes = get_quotes(symbols)

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
                    f"Gia: <b>${fmt_num(price)}</b> ≥ pivot ${fmt_num(pivot)} "
                    f"(+{(price / pivot - 1) * 100:.1f}%){vol_txt}\n"
                    f"📝 {note}"
                )
            elif pivot * (1 - approach_pct / 100) <= price < pivot and key_near not in state:
                state[key_near] = price
                messages.append(
                    f"👀 <b>{sym} GAN PIVOT</b> (con {(pivot / price - 1) * 100:.1f}%)\n"
                    f"Gia: ${fmt_num(price)} / pivot ${fmt_num(pivot)}{vol_txt}\n"
                    f"📝 {note}"
                )

        stop = w.get("stop")
        if stop:
            key_stop = f"{sym}:stop:{today}"
            if price <= stop and key_stop not in state:
                state[key_stop] = price
                messages.append(
                    f"🛑 <b>{sym} CHAM STOP</b>\n"
                    f"Gia: <b>${fmt_num(price)}</b> ≤ stop ${fmt_num(stop)}\n"
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
