<div align="center">
  <img src="custom_components/universal_ir_rf_remote/brand/icon@2x.png" width="112" alt="Universal IR RF Remote Manager" />

  # Universal IR RF Remote Manager

  **Quản lý và điều khiển thiết bị IR/RF trong Home Assistant qua các remote có sẵn.**

  [![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=khaisilk1910&repository=universal_ir_rf_remote&category=integration)

  [Releases](https://github.com/khaisilk1910/universal_ir_rf_remote/releases) · [Báo lỗi](https://github.com/khaisilk1910/universal_ir_rf_remote/issues)
</div>

## ✨ Tính năng

- Kết nối với **Broadlink, Tuya Local** và các nhà cung cấp có entity `remote.*` tương thích trong Home Assistant.
- **Học, phát, thử và quản lý lệnh IR/RF**; hỗ trợ nhập mã Base64 Broadlink đã có.
- Tạo **thiết bị ảo có tên riêng**, nhóm nhiều lệnh, đổi tên, chỉnh sửa và xóa thiết bị/lệnh.
- Tạo **nút Press** cho từng lệnh và **Fan entity** có bật/tắt, chọn tốc độ, ánh xạ các lệnh RF.
- Đồng bộ trạng thái Fan khi gửi các lệnh tốc độ/tắt bằng **Press, Select hoặc action của tích hợp**. Trạng thái là suy ra từ lệnh đã gửi, không phải phản hồi từ thiết bị vật lý.
- Quản lý nhiều remote độc lập; không tạo thêm kết nối tới hub nguồn.

## 📦 Cài đặt qua HACS

1. Cài [HACS](https://www.hacs.xyz/) trên Home Assistant nếu chưa có.
2. Nhấn nút **Add to HACS** phía trên, chọn máy chủ Home Assistant của bạn và mở repository.
3. Chọn **Download**. Nếu cần, vào **HACS → Custom repositories**, thêm `https://github.com/khaisilk1910/universal_ir_rf_remote` với loại **Integration**.
4. Khởi động lại Home Assistant, rồi vào **Settings → Devices & services → Add integration** và tìm **Universal IR RF Remote Manager**.
5. Chọn entity remote có sẵn (ví dụ `remote.broad`), sau đó vào **Configure** để tạo thiết bị và các lệnh.

> **Yêu cầu:** Remote nguồn phải được cài trong Home Assistant và hỗ trợ các action học/phát lệnh tương ứng. Khả năng RF phụ thuộc model và firmware của thiết bị.

## 📡 Học lệnh IR/RF

Trong **Settings → Devices & services → Universal IR RF Remote Manager → Configure → Learn a new command**, chọn **thiết bị**, **tên lệnh**, **IR hoặc RF**, sau đó nhấn **Start learning**.

### Học IR

Khi màn hình hiển thị đang chờ, hướng điều khiển gốc về hub và **nhấn nút cần học một lần**.

### Học RF với Broadlink

1. Chọn **RF** rồi nhấn **Start learning**. Broadlink bắt đầu **dò tần số**.
2. **Nhấn giữ nút** trên remote RF gốc khi đèn báo cam trên Broadlink đang ở pha dò.
3. Khi **đèn cam ngừng nhấp nháy/tắt rồi báo sáng hoặc nhấp nháy trở lại** (tùy model), **thả nút** và **nhấn lại một lần ngắn** để thu mã RF.
4. Đợi màn hình học lệnh hoàn tất. Nếu cần, mở **Notifications** trong Home Assistant để xem hướng dẫn từ Broadlink.
5. Ở màn hình tiếp theo, chọn **Test** (phát thử), **Save** (lưu), **Save and next** (lưu và học tiếp), **Relearn** (học lại) hoặc **Delete/Cancel** (xóa lệnh vừa học và hủy).

> **Lưu ý:** Broadlink RF cần **hai giai đoạn: dò tần số → thu mã**. Nếu giữ nút không phát tín hiệu liên tục, hãy thử nhấn lặp lại trong pha dò. Với **nhà cung cấp khác**, thực hiện theo tín hiệu đèn và hướng dẫn học của nhà cung cấp; không phải thiết bị nào cũng có đèn cam hoặc quy trình RF giống Broadlink. Chỉ lưu sau khi **Test** điều khiển được thiết bị thật.

## 🛠️ Hỗ trợ

Nếu không học được, hãy thử action `remote.learn_command` trực tiếp trong **Developer Tools → Actions** để xác định lỗi xuất phát từ hub hay tích hợp quản lý. Xem thêm [tài liệu Broadlink của Home Assistant](https://www.home-assistant.io/integrations/broadlink/) hoặc [tạo issue](https://github.com/khaisilk1910/universal_ir_rf_remote/issues).
