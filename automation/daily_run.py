# -*- coding: utf-8 -*-
"""Chay 1 lan moi sang (Task Scheduler 09:00 gio VN):
  1. Scan Trend Template Minervini + RS Rating -> gui Telegram
  2. Check watchlist voi gia dong cua phien gan nhat -> bao pivot/stop

Dung --force vi 9h sang VN thi truong My da dong cua.
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
py = sys.executable

subprocess.run([py, str(BASE / "scan_trend_template.py")], timeout=600)
subprocess.run([py, str(BASE / "alert_watcher.py"), "--force"], timeout=300)
