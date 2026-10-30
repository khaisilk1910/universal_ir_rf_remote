<div align="center">
  <img src="custom_components/universal_ir_rf_remote/brand/icon@2x.png" alt="Universal IR RF Remote Manager" width="110" />

  # Universal IR RF Remote Manager

  **Học, quản lý và điều khiển IR/RF trong Home Assistant — nhiều remote, nhiều thiết bị, tên lệnh tùy ý.**

  [![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=khaisilk1910&repository=universal_ir_rf_remote&category=integration)

  [Releases](https://github.com/khaisilk1910/universal_ir_rf_remote/releases) · [Báo lỗi](https://github.com/khaisilk1910/universal_ir_rf_remote/issues) · [Tài liệu chi tiết](docs/README.vi.md)
</div>

## ✨ Tính năng

- **Remote đa hãng:** Broadlink, Tuya Local và các nhà cung cấp có entity `remote.*` hỗ trợ học/phát lệnh chuẩn Home Assistant.
- **Thiết bị ảo:** tạo, đặt tên, đổi tên, sửa loại, xóa; nhóm nhiều lệnh IR/RF vào TV, quạt, đèn, rèm, cổng hoặc thiết bị **Generic**.
- **Tên lệnh tự do (v4.2.6):** nhập tên tiếng Việt hoặc tên bất kỳ như `Mở cổng`, `Netflix`, `Đảo chiều`, `Gió tự nhiên`; không phải dùng `speed_1`/`power`/`turn_off`. Tối đa **128 ký tự**, không trùng tên trong cùng thiết bị.
- **Thư viện lệnh:** học, phát thử, lưu, học tiếp, học lại, đổi tên và xóa lệnh; có nút **Press** riêng cho mỗi lệnh.
- **Nhập Broadlink Base64:** thêm mã IR/RF đã học sẵn mà không cần học lại.
- **Fan nhiều cấp:** chọn đúng thiết bị ảo, gán từng tốc độ và mã OFF bằng lệnh đã lưu; có ON/OFF, tốc độ % trên Dashboard, sửa/đổi tên/xóa cấu hình Fan.
- **Đồng bộ trong tích hợp:** Press, Select và Fan cập nhật trạng thái lẫn nhau khi gửi lệnh đã ánh xạ thành công; quản lý nhiều remote độc lập và không tạo kết nối hub thứ hai.

> **Lưu ý:** Đây là trình quản lý, **không phải driver IR/RF**. Cần cài Broadlink/Tuya Local hoặc tích hợp cung cấp `remote.*` trước. RF phụ thuộc phần cứng. Trạng thái Fan là trạng thái **ước đoán từ lệnh đã gửi**, không đọc phản hồi từ quạt thật.

## 📦 Cài đặt với HACS

1. Cài [HACS](https://www.hacs.xyz/) nếu chưa có, rồi nhấn **Add to HACS** ở đầu README.
2. Chọn máy chủ Home Assistant và **Download** tích hợp. Nếu nút không mở được, vào **HACS → ⋮ → Custom repositories**, thêm `https://github.com/khaisilk1910/universal_ir_rf_remote` với loại **Integration**.
3. Khởi động lại Home Assistant → **Settings → Devices & services → Add integration** → **Universal IR RF Remote Manager**.
4. Chọn entity remote có sẵn (ví dụ `remote.broad`), sau đó vào **Configure** để tạo thiết bị và các lệnh.

**Cài thủ công:** chép `custom_components/universal_ir_rf_remote/` vào `/config/custom_components/universal_ir_rf_remote/`, rồi khởi động lại Home Assistant.

## 🏷️ Tạo thiết bị và đặt tên lệnh bất kỳ (v4.2.6)

1. Vào **Settings → Devices & services → Universal IR RF Remote Manager → Configure → Manage appliances**.
2. **Create appliance**: đặt tên, chọn loại (ví dụ **Generic** cho thiết bị không thuộc TV/Fan/Light).
3. Chọn thiết bị vừa tạo → **Learn** → điền **Command / Tên lệnh** bằng tên bạn muốn, ví dụ `Bật đèn ngủ`, `Mở rèm 50%`, `Tốc độ gió tự nhiên`.
4. Chọn **IR** hoặc **RF** → **Start learning**; khi học xong chọn **Test** để phát thử, sau đó **Save** hoặc **Save and next** để nhập một tên lệnh mới và học tiếp.
5. Trong **Manage appliances → Commands** có thể **Test / Rename / Delete / Learn**; nếu đã có mã Broadlink, dùng **Import code** để nhập Base64 với tên tự chọn.

> Đổi tên lệnh không đổi ID nội bộ hoặc mã gốc của nhà cung cấp, nên ánh xạ Fan vẫn giữ nguyên. Các tên lệnh chỉ cần duy nhất **trong cùng một thiết bị**, không phải trên toàn hệ thống. [Xem hướng dẫn chi tiết](docs/CUSTOM_COMMAND_NAMES.vi.md).

## 📡 Cách học IR / RF

**IR:** Chọn IR → Start learning → hướng remote gốc về hub → **nhấn nút một lần** khi màn hình/đèn báo đang chờ.

**RF Broadlink (hai giai đoạn):**

1. Chọn **RF** → **Start learning**. Khi Broadlink bắt đầu dò tần số và đèn báo nhấp nháy, **nhấn giữ nút** trên remote RF gốc.
2. Khi đèn cam **ngừng nhấp nháy/tắt rồi bắt đầu nhấp nháy lại** (tùy model), **thả nút**, sau đó **nhấn lại một lần ngắn** để thu mã.
3. Theo dõi **Notifications** trong Home Assistant nếu có hướng dẫn từ Broadlink. Khi tiến trình kết thúc, chọn **Test**, **Save**, **Save and next**, **Relearn** hoặc **Delete/Cancel** theo nhu cầu.

> RF 315/433 MHz không cần nhập tần số vào trình học của Broadlink; khả năng thu/phát phụ thuộc model. Các hãng khác có thể dùng quy trình khác, hãy làm theo hướng dẫn của nhà cung cấp. **Tiến trình học kết thúc không bảo đảm thu thành công** — luôn thử trên thiết bị thật trước khi lưu.

## 🌀 Điều khiển quạt và đồng bộ Dashboard

Trong **Configure → Remote and fan settings → Add fan**, chọn thiết bị ảo đã lưu, số cấp tốc độ và ánh xạ từng cấp đến **bất kỳ tên lệnh nào** (không cần tên cố định). Gán lệnh OFF nếu có; có thể **Edit / Rename / Delete fan** mà không xóa thư viện mã.

- Ví dụ quạt sáu cấp: 17% → cấp 1, 33% → cấp 2, 50% → cấp 3, 67% → cấp 4, 83% → cấp 5, 100% → cấp 6.
- Khi nhấn nút **Press** của cấp tốc độ hoặc OFF, Fan và Select cập nhật trạng thái tương ứng nếu lệnh đó đã được ánh xạ và gửi thành công.
- Điều khiển trên Dashboard bằng Tile card với feature `fan-speed` hoặc action `fan.set_percentage`. Không thể tự nhận biết nút bấm trên remote RF vật lý.

[Xem hướng dẫn ánh xạ quạt](docs/FAN_MAPPING.vi.md) · [Đồng bộ trạng thái](docs/FAN_STATE_SYNC.vi.md) · [Dashboard](docs/DASHBOARD_FAN_SPEED.vi.md)

## 🛠️ Khi học lệnh không thành công

Kiểm tra entity `remote.*` và thử action `remote.learn_command` trong **Developer Tools → Actions**. Nếu action chuẩn cũng không học được, hãy kiểm tra phần cứng, hỗ trợ IR/RF, firmware và **Notifications / Logs** của nhà cung cấp. [Tài liệu Broadlink](https://www.home-assistant.io/integrations/broadlink/).

**Mã nguồn & cập nhật:** [GitHub repository](https://github.com/khaisilk1910/universal_ir_rf_remote) · [Releases](https://github.com/khaisilk1910/universal_ir_rf_remote/releases) · [License](LICENSE.md).
