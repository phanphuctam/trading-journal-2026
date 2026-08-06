# Tự động hóa Trading Journal — Scan Minervini + Alert Telegram

## Có gì trong thư mục này

| File | Công dụng |
|---|---|
| `alert_watcher.py` | Theo dõi watchlist, báo Telegram khi **vượt pivot / gần pivot / chạm stop** |
| `scan_trend_template.py` | Scan **Trend Template Minervini + RS Rating** toàn thị trường Mỹ, gửi top qua Telegram |
| `watchlist.json` | Danh sách mã theo dõi (xuất từ tab **Watch** trong journal) |
| `config.json` | Token Telegram + cài đặt (KHÔNG commit lên git) |
| `scan_vn_vcp.py` | Scan **VCP** cổ phiếu Việt (HOSE/HNX) + công tắc tổng VN-Index → `scans/latest_vn.json` |
| `backtest_vn_params.py` | Backtest **tham số thoát lệnh** cho chiến lược VCP Việt trên cache giá |
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

## Backtest tham số thoát lệnh (cổ phiếu Việt)

`backtest_vn_params.py` chạy trên cache giá `.vncache` (không cần mạng, ~10 giây/cấu hình).
**Cửa vào lệnh không đụng vào** — chỉ quét phần sau khi đã vào lệnh.

```powershell
python "automation\backtest_vn_params.py" --baseline          # do ban dung lai voi ket qua goc
python "automation\backtest_vn_params.py" --sweep stop --slots 8
python "automation\backtest_vn_params.py" --sweep tp --slots 8 --stop 6
python "automation\backtest_vn_params.py" --sweep t2 --slots 8 --stop 5
python "automation\backtest_vn_params.py" --grid --slots 8
```

⚠️ Đây là **bản dựng lại**, không phải script backtest gốc (script gốc không còn trong repo).
Cấu hình khớp nhất với 5 con số đã công bố là *stop 10% · 8 vị thế · thoát khi thủng MA50*
(13,5 lệnh/năm · CAGR 9,4% · thắng 40,5% · lãi TB 25,1% · lỗ TB −6,1%, so với gốc
14 lệnh/năm · 10,4% · 38,6% · 25,9% · −6,9%). Đọc **chênh lệch giữa các cấu hình**,
đừng đọc số tuyệt đối.

### Kết quả (HOSE 2018-2026, 702 mã, 8 vị thế, thoát khi thủng MA50)

| Câu hỏi từ báo cáo "SEPA Việt hoá" | Kết luận từ dữ liệu |
|---|---|
| Siết stop từ 8-10% xuống **4-6%**? | **Đúng một nửa.** Stop 6% tốt nhất: CAGR 10,1% / MaxDD −19,1%, hơn stop 8% (9,4% / −20,3%) và stop 10% (9,4% / −20,4%). Nhưng **4% thì hỏng** (CAGR 6,0%) — cắt đúng lúc nền còn rung. → đã đổi mặc định trong journal thành −6% |
| Chốt lời cơ học **1/2 vị thế ở +20-25%**? | **Không phải bữa trưa miễn phí.** Chốt 1/2 ở +20% kéo CAGR 10,1% → 7,7%, đổi lại MaxDD −19,1% → −13,3%. Đây là **đánh đổi lợi nhuận lấy êm ái**, không phải cải thiện. Nếu vẫn muốn: chốt ở **+30%** giữ được nhiều nhất (CAGR 9,1%, MaxDD −14,2%, Sharpe 0,99 — cao nhất bảng) |
| **T+2,5 phá huỷ chiến lược breakout**? | **Sai.** Chỉ **2/121 lệnh** bị chặn bởi T+2, và cả hai vẫn thoát ở đúng mức stop chỉ chậm 1-2 phiên → CAGR, MaxDD, tỉ lệ thắng **giống hệt** tới 2 chữ số thập phân. Cổ phiếu vừa phá vỡ nền VCP kèm khối lượng, trong lúc thị trường ON, rất hiếm khi sập ngay phiên sau. Lập luận trung tâm của báo cáo — bỏ breakout, chuyển sang mua sớm pocket pivot để "tạo đệm T+2,5" — **không có cơ sở trong dữ liệu này** |
| Chỉ giữ **4-8 mã** cùng lúc? | Là **núm vặn khẩu vị rủi ro, không phải lợi thế**. 4 vị thế: CAGR 13,2% nhưng MaxDD −25,5%. 12 vị thế: 8,7% và −14,2%. Sharpe gần như không đổi (0,88-0,92) ở mọi mức |

Mô phỏng đã bật sẵn ba ràng buộc thật của thị trường VN: **T+2** (mua T+0, sớm nhất T+2
mới bán được), **phiên giảm sàn khoá thanh khoản** (không thoát được, đợi phiên sau), và
**chạm stop thì khớp ở `min(giá mở cửa, stop)`** — không giả định khớp đẹp.

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
