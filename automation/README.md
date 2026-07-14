# Tự động hóa Trading Journal — Scan Minervini + Alert Telegram

## Có gì trong thư mục này

| File | Công dụng |
|---|---|
| `alert_watcher.py` | Theo dõi watchlist, báo Telegram khi **vượt pivot / gần pivot / chạm stop** |
| `scan_trend_template.py` | Scan **Trend Template Minervini + RS Rating** toàn thị trường Mỹ, gửi top qua Telegram |
| `watchlist.json` | Danh sách mã theo dõi (xuất từ tab **Watch** trong journal) |
| `config.json` | Token Telegram + cài đặt (KHÔNG commit lên git) |
| `rebuild_index.py` | Nhúng lại `app-src.html` vào `index.html` sau khi sửa giao diện journal |
| `scans/` | Kết quả scan hằng ngày (CSV + JSON, tự tạo) |

## Bước 1 — Tạo bot Telegram (5 phút, miễn phí)

1. Mở Telegram, tìm **@BotFather** → gửi `/newbot` → đặt tên → nhận **token** (dạng `123456:ABC-xyz...`)
2. Mở `automation/config.json`, dán token vào `telegram_bot_token`
3. Nhắn 1 tin bất kỳ ("hi") cho bot vừa tạo
4. Mở trình duyệt: `https://api.telegram.org/bot<TOKEN>/getUpdates` (thay `<TOKEN>`) → tìm `"chat":{"id":123456789` → dán số đó vào `telegram_chat_id`
5. Test:
   ```
   python "automation\alert_watcher.py" --test
   ```
   → điện thoại nhận được tin nhắn là xong.

## Bước 2 — Bot 24/7 trên GitHub Actions (không cần máy bật)

Workflow `.github/workflows/trading.yml` chạy trên máy chủ GitHub:
- **9h00 sáng VN mỗi ngày**: scan Trend Template + check watchlist EOD → Telegram, tự commit `scans/latest.json` → GitHub Pages tự cập nhật
- **30 phút/lần trong phiên Mỹ** (20h30–3h sáng VN): check watchlist realtime → báo ngay khi vượt pivot / chạm stop

Cài 1 lần trên web GitHub (repo → **Settings**):
1. **General → Danger Zone → Change visibility → Private** (bảo vệ watchlist)
2. **Secrets and variables → Actions → New repository secret**, tạo 2 cái:
   - `TELEGRAM_BOT_TOKEN` = token từ BotFather
   - `TELEGRAM_CHAT_ID` = chat id của bạn
3. Tab **Actions** → workflow "Trading bot" → **Run workflow** để chạy thử

Backup trên máy (nếu không dùng Actions): task "TJ-DailyScan" 9h sáng — `schtasks /Delete /TN "TJ-DailyScan" /F` để xóa khi Actions đã chạy ổn.

## Quy trình dùng hằng ngày

1. **9h sáng**: bot Telegram gửi kết quả scan — **bấm tên mã để mở thẳng chart TradingView** (layout riêng của bạn) + cảnh báo watchlist (🚀 vượt pivot / 👀 gần pivot / 🛑 chạm stop)
2. Scan xong script tự ghi `scans/latest.json` → **commit + push GitHub → GitHub Pages tự deploy** → mở https://phanphuctam.github.io/trading-journal-2026 tab **Watch** thấy bảng kết quả scan (kèm giờ scan), bấm mã mở chart, bấm **＋** để đưa vào watchlist
3. Điền pivot + stop cho mã vừa thêm → bấm **⤴ Push GitHub** ngay trong tab Watch — xong, bot 24/7 dùng ngay.
   - Lần đầu bấm sẽ hỏi GitHub token: tạo **fine-grained PAT** tại github.com → Settings → Developer settings → Fine-grained tokens → chỉ chọn repo `trading-journal-2026`, quyền **Contents: Read and write**. Token chỉ lưu trong trình duyệt.
   - Đường dự phòng (không cần token): bấm **⬇ watchlist.json** rồi chạy `python "automation\push_watchlist.py"` (hoặc double-click `Cap nhat watchlist.bat`).
4. Vào lệnh xong thì ghi vào journal như bình thường, xóa mã khỏi Watch → bấm ⤴ Push GitHub lại

Cấu hình thêm trong `config.json`:
- `chart_layout_id`: ID layout chart TradingView của bạn (lấy từ URL, vd `zg2TshOU`) — link mở chart sẽ kèm indicator Minervini của bạn
- Scan không muốn tự push git: chạy với `--no-push`

## Lệnh thủ công

```powershell
python "automation\scan_trend_template.py" --no-telegram        # scan, chi in man hinh
python "automation\scan_trend_template.py" --rs 80 --top 30     # nguong RS 80, top 30
python "automation\alert_watcher.py" --force                    # check gia ngay ca khi market dong
```

## MCP TradingView trong Claude Code

Đã cấu hình trong `.mcp.json` (server `tradingview`). **Khởi động lại Claude Code** để kích hoạt, sau đó có thể hỏi trực tiếp:
- "Phân tích kỹ thuật NVDA đa khung thời gian"
- "Scan cổ phiếu breakout volume trên NASDAQ"
- "Top gainers hôm nay"

## Sửa giao diện journal

`index.html` (bản deploy GitHub Pages) được đóng gói từ `app-src.html`:

```powershell
# 1. Sua app-src.html
# 2. Nhung lai vao index.html:
python "automation\rebuild_index.py"
# 3. Mo index.html kiem tra, roi push GitHub (Pages tu deploy)
```
