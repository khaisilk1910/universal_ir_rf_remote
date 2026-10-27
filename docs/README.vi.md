# Universal IR RF Remote Manager

**Repository:** https://github.com/khaisilk1910/universal_ir_rf_remote  
**Phiên bản:** xem `custom_components/universal_ir_rf_remote/manifest.json` hoặc GitHub Releases · Giao diện tiếng Việt và tiếng Anh.

Quản lý và học/phát các lệnh **hồng ngoại (IR)** và **sóng vô tuyến (RF)** từ nhiều entity `remote.*` của Home Assistant. Đây là lớp quản lý lệnh; giao tiếp với phần cứng vẫn do tích hợp điều khiển remote gốc thực hiện. Không cần quét mạng, không mở socket riêng, không tải thư viện JSON trong giai đoạn setup.

## Tính năng

- **Đa remote**: mỗi entity `remote.*` có một config entry, thư viện metadata và cảm biến số lệnh riêng.
- **Học / phát / xóa lệnh** qua các action chuẩn `remote.learn_command`, `remote.send_command`, `remote.delete_command` khi nguồn hỗ trợ.
- **Quản lý thư viện**: đặt tên thiết bị và lệnh, thử phát lại, học lại, xóa chỉ metadata hoặc yêu cầu xóa mã tại nguồn.
- **Fan tùy chọn**: điều khiển bằng lệnh `speed_1...speed_N` và `turn_off`, trạng thái giả định (*optimistic*).
- **RF tùy chọn**: chọn IR, RF hoặc dải RF 315/433.92 MHz. Việc chỉnh dải tần chỉ xảy ra khi khai báo một entity `number.*` điều khiển tần số tương thích.
- **Startup nhẹ**: trì hoãn việc đọc thư viện đến sau khi HA đã khởi động; ghi JSON nguyên tử, cô lập theo config entry, unload/reload đúng vòng đời.
- **Icon thương hiệu** tích hợp trong `brand/` (256px và 512px), hỗ trợ theme sáng/tối.

## Nguồn điều khiển tương thích

Dùng với Broadlink, Tuya Local và các integration khác **khi chúng cung cấp `remote.*` với các action cần thiết**. Việc một entity có tồn tại không bảo đảm nó hỗ trợ học RF, chọn tần số, hay xóa mã. Hub IR-only không thể phát RF qua phần mềm này. Các entity chỉ có `infrared.*` hay `radio_frequency.*` mà không có `remote.*` chưa được hỗ trợ.

## Cài mới

1. Giải nén gói ZIP.
2. Sao chép toàn bộ `custom_components/universal_ir_rf_remote` vào `/config/custom_components/universal_ir_rf_remote`.
3. Khởi động lại Home Assistant.
4. Vào **Settings → Devices & services → Add integration**, tìm **Universal IR RF Remote Manager**.
5. Chọn một entity `remote.*`, thêm từng remote cần quản lý. Trong **Configure**, bạn có thể học, thử, phát, xóa lệnh và bật fan tùy chọn.

### Chuyển từ một bản dùng namespace kỹ thuật khác

**Quan trọng:** `domain` mới là `universal_ir_rf_remote`. Home Assistant xem đây là **một tích hợp mới**: không tự chuyển config entries, các service cũ hay entity IDs. Không đổi thủ công domain trong `.storage/core.config_entries`.

1. **Sao lưu toàn bộ cấu hình** Home Assistant, bao gồm `.storage`, trước khi cài đặt.
2. **Giữ bản cũ chạy** cho đến khi bạn xác nhận các mã đã học ở Broadlink/Tuya Local vẫn dùng được bằng action `remote.send_command` gốc.
3. Cài tích hợp mới, khởi động lại và thêm lại từng remote vào manager mới. Không cần học lại waveform nếu provider vẫn lưu chúng.
4. Để chuyển **metadata tên lệnh** của manager (nếu cần), mở *Diagnostics* của config entry mới và lấy giá trị `library_filename`. Dừng Home Assistant rồi sao chép file JSON metadata đã sao lưu thành đường dẫn `.storage/<library_filename>` mới. Có thể sử dụng `tools/import_metadata.py` (xem bên dưới). Sau đó khởi động Home Assistant lại.
5. Sửa automation/scripts để gọi `universal_ir_rf_remote.*` thay cho namespace trước, và cập nhật entity ID fan/sensor được tạo lại.
6. Khi đã xác minh hoạt động và dữ liệu, gỡ bỏ bản tích hợp cũ qua giao diện HA và xóa thư mục mã nguồn cũ. Đừng xóa các dữ liệu từ nhà cung cấp remote.

Script chép metadata (chạy **khi Home Assistant đã dừng**):

```bash
python3 tools/import_metadata.py \
  --source /config/.storage/<metadata-backup>.json \
  --destination /config/.storage/<library_filename>
```

Script **không bao giờ ghi đè** file đích đã tồn tại. Nếu đích đã có dữ liệu, hãy sao lưu rồi tự hợp nhất metadata ngoài Home Assistant. Metadata **không phải** dữ liệu waveform RF/IR do provider lưu.

## Ví dụ action

Học IR:

```yaml
action: universal_ir_rf_remote.learn_command
data:
  remote_entity: remote.living_room
  device: tv
  command: power
  command_type: ir
```

Học RF (chỉ với hub hỗ trợ):

```yaml
action: universal_ir_rf_remote.learn_command
data:
  remote_entity: remote.rf_hub
  device: blind
  command: open
  command_type: rf
```

Phát lệnh:

```yaml
action: universal_ir_rf_remote.send_command
data:
  remote_entity: remote.living_room
  device: tv
  command: power
  repeats: 1
```

Xóa **chỉ metadata** (không xóa mã tại provider):

```yaml
action: universal_ir_rf_remote.delete_command
data:
  remote_entity: remote.living_room
  device: tv
  command: power
  local_only: true
```

Nạp lại metadata:

```yaml
action: universal_ir_rf_remote.refresh_library
data:
  remote_entity: remote.living_room
```

Khi quản lý nhiều remote, **luôn truyền `remote_entity` hoặc `config_entry_id`** để tránh gửi nhầm hub. Nếu không có `command_type`, chức năng học mặc định IR. Với RF 315/433.92 MHz, không thể tự chọn dải tần trên mọi loại Hub: phải cấu hình entity số phù hợp trong phần Settings.

## Fan ảo

Chọn **Configure → Settings**, bật fan và điền tên `device` đã dùng lúc học các mã. Quạt gửi một lần phát mặc định, không biết trạng thái thực tế khi có điều khiển từ xa khác tác động, và không tạo kết nối trực tiếp tới phần cứng.

## Giới hạn và kiểm thử

- Mã thực tế do tích hợp của nhà cung cấp quản lý; metadata không chuyển waveform giữa các loại hub.
- Không bảo đảm các action tùy chọn được provider hỗ trợ.
- Không đo đạc thời gian khởi động trên HA thật; thiết kế chỉ tránh I/O thư viện ở `async_setup_entry`.
- Đã chạy unit tests cô lập và kiểm tra cấu trúc mã/tệp; vẫn cần thử trên Home Assistant và phần cứng thật.

## Tài liệu kỹ thuật

- [Home Assistant RemoteEntity](https://contributors.home-assistant.io/core/entities/remote/)
- [Home Assistant integration brand images](https://contributors.home-assistant.io/core/integrations/brands/)
- [Home Assistant custom integration packaging](https://contributors.home-assistant.io/marketplace/guides/integrations/)
- [Broadlink integration](https://www.home-assistant.io/integrations/broadlink/)
- [Tuya Local](https://github.com/make-all/tuya-local)

## Cài qua HACS / phát hành GitHub

Repository [khaisilk1910/universal_ir_rf_remote](https://github.com/khaisilk1910/universal_ir_rf_remote) đã cấu hình sẵn URL GitHub trong manifest, có `hacs.json` và workflow kiểm tra. Xem [hướng dẫn xuất bản đầy đủ](PUBLISHING.vi.md). Khi cài từ HACS, người dùng thêm repo dạng **Integration** từ **HACS → ⋮ → Custom repositories** rồi restart Home Assistant.

## Tự động cập nhật phiên bản khi phát hành

Mở **Actions → Publish GitHub release → Run workflow**, nhập `4.1.1` cho release đầu tiên hoặc phiên bản mới như `4.2.0`. GitHub Actions tự sửa `manifest.json`, kiểm thử, tạo commit, Git tag `v4.2.0` và GitHub Release. Xem [hướng dẫn chi tiết](PUBLISHING.vi.md#5-tạo-release-tự-động-cho-hacs-khuyến-nghị).
