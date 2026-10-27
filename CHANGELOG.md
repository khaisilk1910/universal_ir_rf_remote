# Changelog

## Unreleased — Configured for khaisilk1910/universal_ir_rf_remote

- Updated GitHub manifest URLs, issue tracker and code owner for the live repository.
- Added GitHub CODEOWNERS and complete GitHub/HACS publishing instructions for this repository.
- Kept automatic manifest/version synchronization in the release workflow.

## Previous improvements — Automated GitHub/HACS version sync

- Added an Actions manual release workflow that updates `manifest.json` before committing, tagging and publishing.
- Preserved manual tag releases with strict version checks to prevent mismatched HACS installs.
- Added stable semantic-version validation and version-independent release regression tests.


## 4.1.1 — GitHub / HACS packaging

- Added the HACS repository manifest, release process, automated tests, HACS validation, and hassfest workflows.
- Added an owner-aware repository configuration tool for documentation, issue tracker, and code owners.
- Included maintainer and installation guides in English and Vietnamese.
- The runtime API and domain are unchanged from 4.1.0.

# Universal IR RF Remote Manager

## 4.1.0 — Đổi tên và nhận diện tích hợp

- Tên hiển thị chính thức: **Universal IR RF Remote Manager**.
- Domain kỹ thuật: `universal_ir_rf_remote`; package Python, các service, config flow và đường dẫn thư viện dùng cùng namespace.
- Bổ sung icon độ phân giải chuẩn, biểu tượng cho dark mode, logo ngang và các bản HiDPI trong `brand/`.
- Loại bỏ nhánh code đặc biệt chỉ dành cho một model remote; cài đặt mới mặc định **IR**, quạt **tắt**.
- Giữ chức năng đa remote, thư viện JSON theo config entry, ghi nguyên tử, tải dữ liệu sau khi khởi động, Fan/Sensor và Diagnostics.
- Bổ sung công cụ chép lại metadata từ file JSON do người dùng chỉ định (không thay đổi config registry).

**Lưu ý quan trọng:** Đổi domain đồng nghĩa cần thêm config entry mới và điều chỉnh automation sử dụng namespace cũ; không tự động đổi domain các entry đã cài.
