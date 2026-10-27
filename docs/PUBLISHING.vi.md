# Đưa Universal IR RF Remote Manager lên GitHub và HACS

Hướng dẫn áp dụng trực tiếp cho repository **[khaisilk1910/universal_ir_rf_remote](https://github.com/khaisilk1910/universal_ir_rf_remote)**. Mã đã được cấu hình URL và tài khoản GitHub, không phải chỉnh sửa placeholder nào trước khi push.

## 1. Chuẩn bị

- Git, Python 3.13 (cho bộ kiểm thử); quyền push vào tài khoản GitHub `khaisilk1910`.
- Repository GitHub: **Public**, bật **Issues** và **Actions**.
- Tệp ZIP tải về phải được **giải nén**, và chạy lệnh Git tại thư mục gốc `universal_ir_rf_remote/` — nơi chứa `.github/`, `custom_components/` và `hacs.json`. **Không** upload nguyên file ZIP lên GitHub rồi mong HACS đọc được.
- Nếu GitHub yêu cầu đăng nhập khi `git push`, dùng Git Credential Manager, `gh auth login` (GitHub CLI), hoặc personal access token; **không** dùng mật khẩu tài khoản thay token.

Dữ liệu đã được thiết lập:

```json
{
  "domain": "universal_ir_rf_remote",
  "name": "Universal IR RF Remote Manager",
  "version": "4.1.1",
  "documentation": "https://github.com/khaisilk1910/universal_ir_rf_remote#readme",
  "issue_tracker": "https://github.com/khaisilk1910/universal_ir_rf_remote/issues",
  "codeowners": ["@khaisilk1910"]
}
```

Bản JSON trên chỉ hiển thị các trường chính; tệp `manifest.json` thật có thêm thuộc tính của Home Assistant.

## 2. Đưa mã lên repository trống (lần đầu)

Giải nén `Universal_IR_RF_Remote_Manager_khaisilk1910_GitHub_HACS.zip` rồi **mở terminal ngay trong thư mục `universal_ir_rf_remote`**:

```bash
git init -b main
git add .
git commit -m "Initial release: Universal IR RF Remote Manager"
git remote add origin https://github.com/khaisilk1910/universal_ir_rf_remote.git
git push -u origin main
```

Nếu Git báo thiếu tên/email tác giả, đặt thông tin của chính bạn rồi chạy lại `git commit`:

```bash
git config user.name "YOUR_NAME"
git config user.email "YOUR_EMAIL"
```

Không cần `git clone` trước nếu repository vẫn trống. Nếu đã có file hoặc commit trên GitHub, hãy kiểm tra lịch sử trước khi push; **không dùng `--force` để ghi đè**.

## 3. Kiểm tra trên GitHub

Mở [Actions](https://github.com/khaisilk1910/universal_ir_rf_remote/actions), chờ workflow **Validate integration** hoàn tất:

- `tests`: kiểm tra Python, metadata và pytest.
- `hacs`: chạy HACS validation.
- `hassfest`: kiểm tra manifest/integration theo Home Assistant.

Bạn có thể kiểm tra cục bộ trước khi push:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python tools/verify_repository.py --strict
```

**Lưu ý:** Chưa kiểm tra Home Assistant thực hoặc thiết bị IR/RF. Nếu HACS/hassfest báo lỗi trên GitHub, xử lý lỗi trước khi phát hành; kiểm thử offline không thay thế các bước này.

## 4. Phát hành lần đầu v4.1.1

Không cần sửa thủ công `manifest.json`. Mở [Actions](https://github.com/khaisilk1910/universal_ir_rf_remote/actions) → **Publish GitHub release** → **Run workflow** → chọn nhánh `main` → nhập **`4.1.1`** → Run workflow.

Workflow sẽ kiểm tra tag, xác nhận `manifest.json` có phiên bản tương ứng, chạy pytest, tạo tag `v4.1.1` và xuất bản [GitHub Release](https://github.com/khaisilk1910/universal_ir_rf_remote/releases). HACS cài mã từ chính tag phát hành đó.

**Để workflow có thể commit/tag/release:** vào **Settings → Actions → General → Workflow permissions**, kiểm tra quyền `Read and write permissions` khi repository áp dụng chính sách hạn chế. File workflow cũng yêu cầu `contents: write`. Nếu `main` được branch protection chặn bot push, quy trình có thể thất bại; cần cấu hình đúng quyền hoặc dùng quy trình PR + tag thủ công, không vô hiệu hóa bảo vệ nhánh tùy tiện.

## 5. Các release sau (tự đồng bộ phiên bản)

Khi cập nhật code và push nhánh `main`, chạy lại **Actions → Publish GitHub release** và nhập `4.1.2`, `4.2.0`, `5.0.0`... GitHub Actions tự động:

1. Kiểm tra phiên bản semantic và tag chưa tồn tại.
2. Cập nhật `custom_components/universal_ir_rf_remote/manifest.json` thành phiên bản vừa nhập.
3. Chạy kiểm tra metadata, compile và pytest.
4. Commit thay đổi lên `main`, tạo tag `vX.Y.Z` từ commit đó.
5. Tạo GitHub Release để HACS cung cấp bản cập nhật.

**Quan trọng:** Đừng tạo tag trước bằng giao diện GitHub rồi mới sửa `manifest.json` — HACS sẽ lấy nội dung tại tag cũ. Workflow có cơ chế từ chối tag/manifest không khớp. GitHub Release có thể cần vài phút mới hiển thị trong HACS; người dùng phải tải bản cập nhật và khởi động lại Home Assistant.

## 6. Cài qua HACS (Custom repository)

1. Mở **HACS → menu ⋮ → Custom repositories**.
2. Dán `https://github.com/khaisilk1910/universal_ir_rf_remote` và chọn loại **Integration**.
3. Tìm **Universal IR RF Remote Manager** rồi cài.
4. Khởi động lại Home Assistant.
5. Vào **Settings → Devices & services → Add integration**, thêm **Universal IR RF Remote Manager** và chọn entity `remote.*` có sẵn.

Cài bằng **Custom repositories** khác với việc xuất hiện trong danh sách tích hợp mặc định của HACS. Muốn được đưa vào danh sách mặc định phải đáp ứng yêu cầu và gửi PR xét duyệt riêng vào [hacs/default](https://github.com/hacs/default).

## 7. Thông tin và giấy phép

- Repository: https://github.com/khaisilk1910/universal_ir_rf_remote
- Vấn đề/báo lỗi: https://github.com/khaisilk1910/universal_ir_rf_remote/issues
- Releases: https://github.com/khaisilk1910/universal_ir_rf_remote/releases
- Code owner: `@khaisilk1910`
- Tên domain trong Home Assistant vẫn là `universal_ir_rf_remote`.

**Về giấy phép:** gói hiện có `LICENSE.template` để chủ sở hữu tự xem xét. Trước khi chuyển thành `LICENSE`, hãy xác nhận quyền phân phối/cấp phép với toàn bộ thành phần của mã nguồn gốc; không tự xem mẫu giấy phép là giấy phép có hiệu lực.

**Giới hạn:** chưa thể xác nhận GitHub Actions/HACS chạy thành công trong chính repository hoặc chức năng với Hub thật trước khi bạn push và thử nghiệm.
