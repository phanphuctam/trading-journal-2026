# Bộ lọc cổ phiếu Mỹ — ĐANG NGỦ (từ 03/08/2026)

Không xoá gì cả. Toàn bộ code Mỹ còn nguyên trong repo, chỉ bị **ẩn khỏi giao diện**
bằng đúng một dòng: `SCAN_MARKETS = ['VN']` trong `app-src.html`.

## Vì sao gác lại

Tài khoản IBKR (U27575817, pháp nhân **Interactive Brokers LLC** — Mỹ) đã được duyệt,
quyền giao dịch cổ phiếu Mỹ và cổ phiếu lẻ đã bật, không có phí duy trì. Nhưng **không
nạp được tiền từ Việt Nam**:

| Phương thức | Kết quả |
|---|---|
| Stablecoin qua ZeroHash | Không đủ điều kiện — dịch vụ crypto của IBKR chỉ mở cho người cư trú tại Mỹ |
| Wise | Không gửi tiền đi từ Việt Nam được (chỉ nhận về) |
| ACH / liên kết ngân hàng | Cần tài khoản ngân hàng nội địa Mỹ |
| Chuyển khoản quốc tế (SWIFT) | Vướng Thông tư 20/2022/TT-NHNN — đầu tư chứng khoán không nằm trong danh mục mục đích được chuyển ngoại tệ |

Thêm hai ràng buộc khiến các đường vòng không dùng được:
- **Quy tắc bên thứ nhất của IBKR:** chỉ rút được về tài khoản mà trước đó đã nạp từ đó.
  Nạp bằng đường nào thì phải rút về đúng đường đó.
- **CRS/FATCA:** IBKR báo cáo tài sản về cơ quan thuế Việt Nam. Vốn vào bằng đường không
  chính thức thì chính dữ liệu đó thành bằng chứng bất lợi khi đối chiếu.

**Cửa duy nhất còn lại:** thu nhập phát sinh từ nước ngoài, trả thẳng vào tài khoản nước
ngoài đứng tên mình, chưa từng về Việt Nam. Khi nào có nguồn đó (hoặc luật đổi) thì mở lại.

## Còn gì trong repo

| Đường dẫn | Nội dung |
|---|---|
| `automation/scan_trend_template.py` | Bộ lọc SEPA/Trend Template + RS Rating. Chạy được, không sửa gì |
| `scans/latest.json` | Kết quả scan Mỹ gần nhất (01/08/2026, 136 mã) |
| `automation/scans/scan_*.csv/.json` | Lịch sử scan Mỹ |
| `app-src.html` → `_FA_US` | Bảng 11 bước đọc cơ bản Mỹ (TradingView / Zacks / Fintel) |
| `app-src.html` → nhánh `else` trong `_loadScanResults` | Giao diện bảng Mỹ (SEPA/EARLY/IPO/TREND) |
| `app-src.html` → `pickScan(sym, rs)` | Thêm mã Mỹ vào watchlist |
| `.github/workflows/trading.yml` | Phần Mỹ đang chú thích ở cuối file |

## Cách bật lại

1. `app-src.html`: `SCAN_MARKETS = ['VN']` → `['US', 'VN']` (giữ cả hai, có nút chuyển)
   hoặc `['US']`. Một dòng này tự kéo theo: nút chuyển thị trường, `_faList()` chọn
   `_FA_US`, watchlist đóng dấu `cc: 'USD'`.
2. `.github/workflows/trading.yml`: bỏ chú thích phần Mỹ ở cuối file —
   cron thứ Bảy chạy `scan_trend_template.py --no-push` với `CHART_LAYOUT_ID: zg2TshOU`,
   thêm cron phiên Mỹ `*/30 13-21 * * 1-5` gọi `alert_watcher.py --market us`,
   `git add` thêm `scans/latest.json`.
3. `python automation/rebuild_index.py` rồi push.

## Việc CHƯA làm — công tắc tổng cho thị trường Mỹ

Bản VN có công tắc tổng (`market_regime()` trong `scan_vn_vcp.py`), bản Mỹ **chưa có**.
Kế hoạch đã duyệt là dùng quy tắc **QQQ > MA50 VÀ MA50 > MA200**.

**Cạm bẫy đã tốn thời gian dò ra — đừng dò lại:**

`tradingview-screener` **KHÔNG** trả về ETF hay chỉ số. Đã thử và đều ra 0 dòng:

```python
Query().select("name","close","SMA50","SMA200").where(col("name").isin(["QQQ","SPY"]))
       .set_markets("america")           # -> n = 0
Query()...where(col("name") == "QQQ", col("type") == "fund")   # -> n = 0
Query()...set_markets("index")           # -> HTTP 404
```

Nguyên nhân: `LIQUID_FILTERS` dùng `col("type") == "stock"`, và bản thân screener
`america` cũng không phục vụ ETF/chỉ số.

**Cách chạy được** — Yahoo chart API, miễn phí, không cần key, 500 phiên đủ tính MA200:

```python
import pandas as pd, requests

def fetch_index_close(symbol="QQQ"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d"
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    return pd.Series(res["indicators"]["quote"][0]["close"]).dropna()
```

Đã kiểm chứng 03/08/2026: QQQ close 700,07 · MA50 714,83 · MA200 645,55
→ dưới MA50 nên trạng thái **OFF**. (Stooq trả về trang HTML chặn, không dùng được.)

Sau đó viết `market_regime()` theo đúng khuôn trong `scan_vn_vcp.py`, thêm `regime` và
`entries_allowed` vào payload của `write_site_json()` — **dùng đúng tên trường như bản VN**
để `_regimeBanner()` ở giao diện dùng chung được, khỏi phải viết hai nhánh.

Còn phải sửa thêm khi bật lại:
- `_regimeBanner()` đang ghi cứng "VN-Index" trong thuộc tính `title` → đổi sang `r.index`.
- Câu kết khi trạng thái ON ghi "chỉ vào lệnh ở nhóm BREAKOUT" (tier của VN) → ở Mỹ là SEPA/EARLY.
- `_planWarnings()` đang đọc cứng `this._scanCache.VN.regime` → đổi sang thị trường đang hoạt động.
- `_preloadScanVN()` → nạp `scans/latest.json` hay `latest_vn.json` theo `_scanMkt()`.

Kế hoạch đầy đủ đã duyệt: `~/.claude/plans/b-n-i-t-i-kho-n-happy-lobster.md`

## Ghi chú về IBKR nếu sau này mở lại

- Chọn bảng phí **Tiered** thay vì Fixed. Với vị thế nhỏ, mức tối thiểu mới là thứ quyết
  định: Fixed tối thiểu $1/chiều ≈ 1,08% vòng mua-bán trên vị thế $185; Tiered ≈ $0,35 → 0,38%.
- Dưới $2.000 là tài khoản tiền mặt (không margin, không short, chờ T+1). Đổi lại quy tắc
  PDT $25.000 không áp dụng.
- Rút tiền: 2 lần/tháng miễn phí, sau đó $10 (wire) hoặc $1 (ACH).
