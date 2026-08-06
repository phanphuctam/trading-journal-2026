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
| `fetch_listing_dates.py` | Lấy **ngày niêm yết thật** → `.vncache/_listing.json` (cần cho bộ lọc tuổi) |
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

### Kết quả (HOSE+HNX 2018-2026, 702 mã, 8 vị thế, thoát khi thủng MA50)

| Câu hỏi từ báo cáo "SEPA Việt hoá" | Kết luận từ dữ liệu |
|---|---|
| Siết stop từ 8-10% xuống **4-6%**? | **Đúng một nửa.** Stop 6% tốt nhất: CAGR 10,1% / MaxDD −19,1%, hơn stop 8% (9,4% / −20,3%) và stop 10% (9,4% / −20,4%). Nhưng **4% thì hỏng** (CAGR 6,0%) — cắt đúng lúc nền còn rung. → đã đổi mặc định trong journal thành −6% |
| Chốt lời cơ học **1/2 vị thế ở +20-25%**? | **Không phải bữa trưa miễn phí.** Chốt 1/2 ở +20% kéo CAGR 10,1% → 7,7%, đổi lại MaxDD −19,1% → −13,3%. Đây là **đánh đổi lợi nhuận lấy êm ái**, không phải cải thiện. Nếu vẫn muốn: chốt ở **+30%** giữ được nhiều nhất (CAGR 9,1%, MaxDD −14,2%, Sharpe 0,99 — cao nhất bảng) |
| **T+2,5 phá huỷ chiến lược breakout**? | **Sai.** Chỉ **2/121 lệnh** bị chặn bởi T+2, và cả hai vẫn thoát ở đúng mức stop chỉ chậm 1-2 phiên → CAGR, MaxDD, tỉ lệ thắng **giống hệt** tới 2 chữ số thập phân. Cổ phiếu vừa phá vỡ nền VCP kèm khối lượng, trong lúc thị trường ON, rất hiếm khi sập ngay phiên sau. Lập luận trung tâm của báo cáo — bỏ breakout, chuyển sang mua sớm pocket pivot để "tạo đệm T+2,5" — **không có cơ sở trong dữ liệu này** |
| Chỉ giữ **4-8 mã** cùng lúc? | Là **núm vặn khẩu vị rủi ro, không phải lợi thế**. 4 vị thế: CAGR 13,2% nhưng MaxDD −25,5%. 12 vị thế: 8,7% và −14,2%. Sharpe gần như không đổi (0,88-0,92) ở mọi mức |

Mô phỏng đã bật sẵn ba ràng buộc thật của thị trường VN: **T+2** (mua T+0, sớm nhất T+2
mới bán được), **phiên giảm sàn khoá thanh khoản** (không thoát được, đợi phiên sau), và
**chạm stop thì khớp ở `min(giá mở cửa, stop)`** — không giả định khớp đẹp.

### Mở rộng vũ trụ: HNX có, UPCOM không

8 vị thế · stop 6% · GTGD ≥ 3 tỷ:

| Vũ trụ | CAGR | MaxDD | Lệnh/năm | Lãi TB | Sharpe |
|---|---|---|---|---|---|
| HOSE riêng | 8,04% | −14,6% | 15,9 | +24,9% | 0,80 |
| **HOSE+HNX** (bot đang chạy) | **10,08%** | −18,4% | 16,3 | +31,6% | **0,87** |
| HOSE+HNX+UPCOM | 7,89% | −20,6% | 17,5 | +27,0% | 0,71 |
| HNX riêng | 7,33% | −19,7% | 3,5 | **+60,7%** | 0,78 |
| UPCOM riêng | 0,77% | −12,7% | 3,6 | +20,8% | 0,18 |

Thêm UPCOM **kéo CAGR xuống** 10,08% → 7,89%: slot có hạn, mã UPCOM nén chặt (vì thanh
khoản mỏng nên giá ít nhúc nhích) chiếm chỗ của setup tốt hơn. Giữ `--hnx`, đừng `--upcom`.

Hạ ngưỡng thanh khoản **không giúp**. HOSE+HNX: 3 tỷ → 10,08%, 10 tỷ → 10,09%, 30 tỷ →
9,88%. CAGR phẳng nhưng tỉ lệ thắng tăng đều 32,1% → 43,7% khi nâng ngưỡng, và backtest
chưa tính trượt giá. Giữ 10 tỷ.

### ⚠️ Giá trong cache đã ĐIỀU CHỈNH cổ tức

Mọi nguồn vnstock (KBS, VCI) đều trả giá **đã điều chỉnh cổ tức** — VNM 02/01/2019 về
68,7 nghìn trong cache trong khi biểu đồ TradingView vùng đó nằm khoảng 100-120 nghìn.
Không tắt được.

Hệ quả cần nhớ: **đường trung bình động trong scan sẽ lệch so với đồ thị TradingView** ở
mã trả cổ tức lớn. Scan có thể báo "giá trên MA200" trong khi đồ thị cho thấy ngược lại.
Và các con số backtest ở trên đều tính trên giá đã điều chỉnh, nên có phần **ưu ái** chiến
lược bám xu hướng với nhóm cổ tức cao. Luôn mở đồ thị xác nhận trước khi vào lệnh.

### Trend Template: dùng để PHÂN LOẠI, không dùng để vào lệnh

Bộ lọc bối cảnh trong scan chỉ kiểm 3 điều kiện (giá > MA50, > MA200, trong 25% đỉnh 52T).
Siết lên đủ 8 điều kiện Trend Template **không cải thiện cửa vào lệnh** (CAGR 9,67% →
9,55%, Sharpe 0,82 → 0,84) nên cửa vào lệnh giữ nguyên.

Nhưng 3 điều kiện đó **không đủ để gọi là "xu hướng tăng"**: VNM ngày 31/07/2026 vượt cả
ba trong khi MA50 < MA150 < MA200 (xếp ngược hoàn toàn) và MA200 vẫn dốc xuống — đúng là
cổ phiếu cắm đầu đi xuống nhiều năm. Nay scan tính đủ 8 tiêu chí và **chỉ mã đạt 8/8 mới
vào nhóm `TREND`**; còn lại xuống nhóm `POOL` kèm điểm N/8 và danh sách tiêu chí còn thiếu.

### TUỔI NIÊM YẾT — phát hiện mạnh nhất

Cần chạy `fetch_listing_dates.py` trước (tuổi **không** suy được từ dữ liệu giá: nguồn KBS
chỉ trả ~8 năm nên VNM/FPT/HPG đều hiện "phiên đầu 2018-08"). HOSE+HNX · 10 tỷ · 8 vị thế:

| Lọc tuổi | CAGR | MaxDD | Lệnh/năm | Thắng | Kỳ vọng | Sharpe |
|---|---|---|---|---|---|---|
| tất cả | 10,09% | −19,1% | 13,9 | 37,0% | 6,54 | 0,88 |
| 0-2 năm | −0,52% | −7,6% | 2,1 | **16,7%** | −1,94 | −0,23 |
| **2-8 năm** | 8,44% | **−8,3%** | 5,5 | **57,4%** | **12,95** | **1,13** |
| > 8 năm | 4,97% | −27,2% | 9,8 | 32,1% | 4,61 | 0,52 |

Đây là tiêu chí "công ty non trẻ" của Minervini (Ch.6) được xác nhận trên dữ liệu VN, kèm
một tinh chỉnh quan trọng: **dưới 2 năm thì tệ hơn tất cả** (thắng 16,7%, CAGR âm) — chưa
đủ lịch sử giá để tạo nền tử tế.

Đã kiểm định độ bền: kết quả **ổn định qua mọi mức stop** (5/6/8/10% đều cho Sharpe
1,11-1,15) và **vẫn đúng khi bỏ HNX ra** (HOSE riêng: thắng 58,7%, MaxDD −8,3%, Sharpe
1,16). Không phải hiện tượng vắt tham số.

Vì sụt giảm chỉ −8,3%, bộ lọc tuổi chịu được đòn bẩy tốt hơn hẳn:

| Cấu hình | CAGR | MaxDD | Sharpe |
|---|---|---|---|
| 3 vị thế · 3x · **không** lọc tuổi | 28,64% | −46,1% | 0,82 |
| **6 vị thế · 3x · lọc 2-8 năm** | **29,33%** | **−24,2%** | **1,27** |

Cùng lợi nhuận, **một nửa sụt giảm**.

⚠️ Cảnh báo mẫu: chỉ 47 lệnh trong 8,5 năm (5,5 lệnh/năm), riêng 2021 chiếm 15 lệnh. Tỉ lệ
thắng 57,4% có sai số khoảng ±14 điểm. Và `listing_date` là ngày lên **sàn hiện tại**,
không phải ngày IPO gốc — mã chuyển sàn sẽ hiện trẻ hơn thực tế.

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
