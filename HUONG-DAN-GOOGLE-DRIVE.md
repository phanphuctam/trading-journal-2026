# Sao lưu Trading Journal lên Google Drive

App đã có thêm 2 nút trên thanh công cụ:
- **☁⬆** : Sao lưu (upload) toàn bộ dữ liệu (trades, deposits, notes, setups) lên Google Drive.
- **☁⬇** : Khôi phục bản sao lưu mới nhất từ Google Drive.

Mỗi lần bấm ☁⬆ sẽ tạo 1 file mới có dấu thời gian, ví dụ `trading-journal-20260625-1543.json`
→ giữ được toàn bộ lịch sử, không ghi đè, an toàn năm này qua năm nọ.

---

## ⚙️ Cài đặt 1 lần (bắt buộc)

### 1. Tạo Google Client ID (miễn phí)
1. Vào https://console.cloud.google.com/ → tạo 1 Project mới (vd: "Trading Journal").
2. **APIs & Services → Library** → tìm **Google Drive API** → **Enable**.
3. **APIs & Services → OAuth consent screen**:
   - User Type: **External** → Create.
   - Điền tên app + email của bạn → Save.
   - Phần **Test users** → **Add users** → thêm chính email Gmail của bạn.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Web application**.
   - **Authorized JavaScript origins** → Add URI: thêm địa chỉ bạn sẽ mở app (xem mục 3 bên dưới), ví dụ:
     - `http://localhost:8000`
     - và/hoặc `https://TEN-CUA-BAN.github.io` (nếu host trên GitHub Pages)
   - Create → copy chuỗi **Client ID** (dạng `xxxx.apps.googleusercontent.com`).

### 2. Dán Client ID vào file
Mở `Trading Journal 2026.html` bằng Notepad/VS Code, tìm:
```
const GDRIVE_CLIENT_ID = '486383706311-bgllvvl3uh4lu5foppu9j6r51vo72ljg.apps.googleusercontent.com';
```
Dán Client ID vào giữa 2 dấu nháy:
```
const GDRIVE_CLIENT_ID = '1234567.apps.googleusercontent.com';
```
Lưu file.

### 3. ⚠️ QUAN TRỌNG: phải mở qua http(s), KHÔNG mở bằng file://
Google chặn đăng nhập từ file mở trực tiếp (file://). Phải chạy qua 1 địa chỉ web:

**Trên PC (test nhanh):** mở terminal tại thư mục chứa file, chạy:
```
python -m http.server 8000
```
Rồi mở trình duyệt: `http://localhost:8000/Trading%20Journal%202026.html`
(Authorized origin phải có `http://localhost:8000`.)

**Dùng lâu dài + trên mobile (khuyên dùng):** đưa file lên hosting tĩnh miễn phí
**GitHub Pages / Netlify / Cloudflare Pages** → bạn được 1 link `https://...`
→ mở trên PC và điện thoại đều được; trên mobile bấm "Thêm vào màn hình chính" để dùng như app.
(Nhớ thêm đúng link https đó vào Authorized JavaScript origins ở mục 1.)

---

## 🔁 Cách dùng PC ↔ Mobile
Dữ liệu vẫn lưu riêng trên mỗi thiết bị (localStorage), nhưng đồng bộ qua Drive:
- Xong việc trên PC → bấm **☁⬆**.
- Sang mobile mở app → bấm **☁⬇** → có dữ liệu mới nhất.
- Và ngược lại.

## 🔒 Quyền truy cập
App dùng scope `drive.file`: chỉ thấy & sửa được những file do chính app này tạo,
KHÔNG đọc được các file Drive khác của bạn.
