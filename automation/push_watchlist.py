# -*- coding: utf-8 -*-
"""Cap nhat watchlist va day len GitHub cho bot 24/7.

Quy trinh: tren site bam "⬇ watchlist.json" (file roi vao Downloads), roi chay:
    python automation/push_watchlist.py

Script tu tim file watchlist*.json MOI NHAT trong Downloads, chep vao automation/,
commit + push. Neu ban da tu chep file vao automation/ roi thi cu chay lenh nay,
no se bo qua buoc chep va chi commit + push.
"""
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
DEST = BASE / "watchlist.json"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def validate(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return isinstance(data, list) and all(isinstance(w, dict) and w.get("symbol") for w in data)
    except Exception:
        return False


def main():
    downloads = Path.home() / "Downloads"
    candidates = sorted(downloads.glob("watchlist*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        newest = candidates[0]
        dest_mtime = DEST.stat().st_mtime if DEST.exists() else 0
        if newest.stat().st_mtime > dest_mtime:
            if not validate(newest):
                print(f"[!] {newest.name} khong phai watchlist hop le — bo qua")
            else:
                shutil.copy2(newest, DEST)
                print(f"Da chep {newest.name} (luc {datetime.fromtimestamp(newest.stat().st_mtime):%H:%M %d/%m}) vao automation/")

    if not DEST.exists() or not validate(DEST):
        print("[!] automation/watchlist.json khong ton tai hoac khong hop le")
        sys.exit(1)

    wl = json.loads(DEST.read_text(encoding="utf-8-sig"))
    print(f"Watchlist hien tai: {', '.join(w['symbol'] for w in wl) or '(trong)'}")

    rel = "automation/watchlist.json"
    subprocess.run(["git", "-C", str(ROOT), "add", rel], check=True)
    r = subprocess.run(["git", "-C", str(ROOT), "commit", "-m",
                        f"Cap nhat watchlist {datetime.now():%Y-%m-%d %H:%M}", "--", rel],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("Watchlist khong thay doi so voi ban tren GitHub — khong can push.")
        return
    p = subprocess.run(["git", "-C", str(ROOT), "push"], capture_output=True, text=True, timeout=120)
    if p.returncode == 0:
        print("✅ Da push — bot 24/7 tren GitHub se dung watchlist moi tu lan chay ke tiep.")
    else:
        print("[!] Push loi:", (p.stdout + p.stderr).strip()[:300])


if __name__ == "__main__":
    main()
