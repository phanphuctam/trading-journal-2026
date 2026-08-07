# -*- coding: utf-8 -*-
"""Chay 1 lan moi sang (Task Scheduler 09:00 gio VN):
  1. Cong tac tong VN-Index -> scans/regime_vn.json (duoc phep vao lenh hay khong)
  2. So lieu phong thu cho ma trong watchlist -> scans/watch_stats.json
  3. Check watchlist voi gia dong cua phien gan nhat -> bao pivot/stop

Viec CHON CO PHIEU khong con o day: da chuyen sang loc bang mat tren TradingView
(xem AGENTS.md). Ba buoc tren la nhung thu TradingView khong lam duoc.

Dung --force vi 9h sang co the ngoai gio giao dich.
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
py = sys.executable

subprocess.run([py, str(BASE / "regime.py"), "--telegram"], timeout=300)
subprocess.run([py, str(BASE / "watch_stats.py")], timeout=900)
subprocess.run([py, str(BASE / "alert_watcher.py"), "--force"], timeout=300)
