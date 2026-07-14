@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "automation\push_watchlist.py"
echo.
pause
