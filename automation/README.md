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

## Bước 2 — Lịch chạy tự động (ĐÃ CÀI SẴN)

Task Scheduler **"TJ-DailyScan"** chạy `daily_run.py` **9h00 sáng mỗi ngày** (giờ VN, máy phải đang bật):
1. Scan Trend Template + RS Rating → gửi top 15 qua Telegram
2. Check watchlist với giá đóng cửa phiên gần nhất → báo pivot/stop

Lệnh quản lý:
```powershell
schtasks /Run /TN "TJ-DailyScan"       # chay thu ngay
schtasks /Query /TN "TJ-DailyScan"     # xem trang thai
schtasks /Delete /TN "TJ-DailyScan" /F # xoa lich
```

Nếu sau này muốn alert **realtime trong phiên** (20h30–3h sáng VN, máy phải bật):
```powershell
schtasks --% /Create /TN "TJ-AlertWatcher" /SC MINUTE /MO 5 /F /TR "\"C:\Users\tamph\AppData\Local\Programs\Python\Python313\pythonw.exe\" \"C:\Users\tamph\Desktop\CLAUDE CODE\Journal Trading\automation\alert_watcher.py\""
```
(script tự nghỉ khi thị trường Mỹ đóng cửa nên không tốn tài nguyên)

## Quy trình dùng hằng ngày

1. **9h sáng**: bot Telegram gửi kết quả scan — **bấm tên mã để mở thẳng chart TradingView** (layout riêng của bạn) + cảnh báo watchlist (🚀 vượt pivot / 👀 gần pivot / 🛑 chạm stop)
2. Scan xong script tự ghi `scans/latest.json` → **commit + push GitHub → Netlify tự deploy** → mở https://phantam.netlify.app tab **Watch** thấy bảng kết quả scan (kèm giờ scan), bấm mã mở chart, bấm **＋** để đưa vào watchlist
3. Điền pivot + stop cho mã vừa thêm → bấm **⬇ watchlist.json** → chép file từ Downloads vào thư mục `automation\` (ghi đè)
4. Vào lệnh xong thì ghi vào journal như bình thường, xóa mã khỏi Watch

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

`index.html` (bản deploy Netlify) được đóng gói từ `app-src.html`:

```powershell
# 1. Sua app-src.html
# 2. Nhung lai vao index.html:
python "automation\rebuild_index.py"
# 3. Mo index.html kiem tra, roi keo tha len Netlify
```
