<div align="center">
  <img src="custom_components/universal_ir_rf_remote/brand/icon@2x.png" alt="Universal IR RF Remote Manager icon" width="144" />

  # Universal IR RF Remote Manager

  **Quản lý nhiều remote IR/RF trong Home Assistant — Multi-remote IR/RF command manager**

  [![Validate integration](https://github.com/khaisilk1910/universal_ir_rf_remote/actions/workflows/validate.yml/badge.svg)](https://github.com/khaisilk1910/universal_ir_rf_remote/actions/workflows/validate.yml)
  [![Latest release](https://img.shields.io/github/v/release/khaisilk1910/universal_ir_rf_remote?label=release)](https://github.com/khaisilk1910/universal_ir_rf_remote/releases)
  [![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.md)

  [Cài đặt](#cài-đặt) · [Hướng dẫn sử dụng](#sử-dụng) · [Ví dụ](#ví-dụ-automation) · [English](#english-summary) · [Báo lỗi](https://github.com/khaisilk1910/universal_ir_rf_remote/issues)
</div>

## Giới thiệu

**Universal IR RF Remote Manager** là một custom integration dành cho Home Assistant, giúp học, lưu **thông tin mô tả**, phát thử, quản lý và xóa các lệnh IR/RF thông qua những thực thể `remote.*` đã có trong hệ thống. Mỗi remote có một cấu hình và thư viện metadata riêng.

> [!IMPORTANT]
> Đây **không phải driver phần cứng IR/RF**. Bạn cần cài và cấu hình trước một tích hợp cung cấp entity `remote.*` (ví dụ Broadlink, Tuya Local hoặc một nhà cung cấp tương thích). Khả năng học/phát IR, học/phát RF, xóa mã và chọn tần số hoàn toàn phụ thuộc vào thiết bị và tích hợp gốc. Việc thêm manager **không** biến thiết bị chỉ hỗ trợ IR thành thiết bị RF.

### Tính năng

- Quản lý **nhiều remote**, mỗi remote có một config entry và thư viện metadata riêng.
- Học, phát, thử và xóa lệnh bằng các Home Assistant actions `remote.learn_command`, `remote.send_command`, `remote.delete_command` **nếu nhà cung cấp hỗ trợ**.
- Quản lý tên thiết bị/tên lệnh; xóa chỉ metadata nếu không muốn xóa mã lưu ở nhà cung cấp.
- Tích hợp **fan entity tùy chọn**, gửi lệnh `speed_1` đến `speed_N` và `turn_off`; trạng thái quạt mang tính giả định (*optimistic*).
- Sensor đếm lệnh, chẩn đoán riêng từng config entry, giao diện tiếng Việt và tiếng Anh.
- Không mở socket hay kết nối phần cứng thứ hai; trì hoãn đọc thư viện để hạn chế công việc trong giai đoạn khởi động.
- Ghi dữ liệu JSON metadata theo kiểu thay thế nguyên tử; icon/logo hỗ trợ giao diện sáng/tối.

### Khả năng tương thích

| Thành phần | Yêu cầu / ghi chú |
| --- | --- |
| Home Assistant | Từ **2026.3.0** theo metadata HACS của dự án; ưu tiên phiên bản ổn định mới |
| HACS | Cài dưới loại **Integration** từ custom repository |
| Backend | Entity `remote.*` đã hoạt động; provider phải hỗ trợ action cần sử dụng |
| IR | Khi hub và provider hỗ trợ |
| RF | Chỉ trên hub và provider hỗ trợ RF; chọn 315/433.92 MHz cần entity `number.*` phù hợp |
| ESPHome hoặc các hệ khác | Chỉ khi thực sự cung cấp entity `remote.*` tương thích với action chuẩn |

Thư viện của manager chỉ lưu **metadata** (ví dụ tên lệnh, loại tín hiệu, thời điểm), không tự sở hữu hay chuyển đổi waveform lưu tại Broadlink, Tuya Local hoặc nhà cung cấp khác.

## Cài đặt

### Tự thêm vào HACS


## Cài đặt qua HACS

Nhấn nút dưới đây để mở trực tiếp repository này trong HACS:

[![Mở repository trong HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=khaisilk1910&repository=universal_ir_rf_remote&category=integration)

Sau đó:

1. Chọn **Download** trong HACS để cài đặt tích hợp.
2. Khởi động lại Home Assistant.
3. Vào **Settings → Devices & services → Add integration**.
4. Tìm **Universal IR RF Remote Manager** và hoàn tất cấu hình theo giao diện.


### Thủ công trên HACS

1. Cài và cấu hình [HACS](https://www.hacs.xyz/) trong Home Assistant.
2. Mở **HACS → ⋮ → Custom repositories**.
3. Nhập URL: `https://github.com/khaisilk1910/universal_ir_rf_remote`.
4. Chọn loại **Integration**, rồi thêm repository.
5. Tìm **Universal IR RF Remote Manager**, chọn bản release cần cài và tải xuống.
6. Khởi động lại Home Assistant.
7. Vào **Settings → Devices & services → Add integration**, tìm **Universal IR RF Remote Manager**.
8. Chọn entity `remote.*` cần quản lý; lặp lại thao tác để thêm các remote khác.

> Với repository mới, bạn cần [xuất bản GitHub Release](#phát-hành-bản-mới) trước để HACS hiển thị một phiên bản phát hành rõ ràng. Cài qua **Custom repositories** không đồng nghĩa repository đã được chấp thuận vào danh mục mặc định của HACS.

### Cách 2 — Cài thủ công

Sao chép thư mục sau từ repository:

```text
custom_components/universal_ir_rf_remote/
```

vào Home Assistant:

```text
/config/custom_components/universal_ir_rf_remote/
```

Khởi động lại Home Assistant và thêm tích hợp trong **Settings → Devices & services**.

## Sử dụng

1. Bảo đảm thiết bị IR/RF đã tạo thành công entity `remote.*` và hoạt động với tích hợp gốc.
2. Thêm **Universal IR RF Remote Manager**, chọn một remote.
3. Trong trang tích hợp, chọn **Configure** để học lệnh, phát thử, xem thư viện hoặc cấu hình fan.
4. Khi có nhiều remote, **chỉ định `remote_entity` hoặc `config_entry_id`** khi gọi action để tránh phát lệnh nhầm hub.

Lưu ý: Các tác vụ học/phát hoạt động **đồng bộ với hành động người dùng**, không khởi động quét toàn bộ hub khi Home Assistant mở lên. Chưa có số liệu benchmark thời gian startup trên mọi thiết bị.

## Ví dụ automation

### Học một mã IR

```yaml
action: universal_ir_rf_remote.learn_command
data:
  remote_entity: remote.living_room
  device: television
  command: power
  command_type: ir
```

### Phát một lệnh đã học

```yaml
action: universal_ir_rf_remote.send_command
data:
  remote_entity: remote.living_room
  device: television
  command: power
  repeats: 1
```

### Học mã RF (nếu được phần cứng hỗ trợ)

```yaml
action: universal_ir_rf_remote.learn_command
data:
  remote_entity: remote.rf_hub
  device: blinds
  command: open
  command_type: rf
```

### Chỉ xóa metadata (không xóa mã ở provider)

```yaml
action: universal_ir_rf_remote.delete_command
data:
  remote_entity: remote.living_room
  device: television
  command: power
  local_only: true
```

### Tải lại metadata

```yaml
action: universal_ir_rf_remote.refresh_library
data:
  remote_entity: remote.living_room
```

Các action hiện có: `universal_ir_rf_remote.learn_command`, `.send_command`, `.delete_command`, `.refresh_library`. Tham số chi tiết nằm trong [`services.yaml`](custom_components/universal_ir_rf_remote/services.yaml).

## Phát hành bản mới

Repository bao gồm workflow **Publish GitHub release** để đồng bộ GitHub tag và `manifest.json`.

1. Đẩy thay đổi lên `main`; kiểm tra workflow [Validate integration](https://github.com/khaisilk1910/universal_ir_rf_remote/actions/workflows/validate.yml).
2. Mở [GitHub Actions](https://github.com/khaisilk1910/universal_ir_rf_remote/actions) → **Publish GitHub release** → **Run workflow**.
3. Nhập phiên bản, ví dụ `4.2.0` (không bắt buộc có chữ `v`).
4. Workflow cập nhật `custom_components/universal_ir_rf_remote/manifest.json`, chạy kiểm thử, commit version, tạo tag `v4.2.0` và xuất bản GitHub Release.

HACS nhận diện phiên bản từ release tag; Home Assistant đọc số `version` trong manifest của **cùng release**. Đừng tạo tag/release thủ công trước khi đồng bộ manifest. Nếu nhánh `main` được bảo vệ, workflow sẽ cần quyền hoặc quy trình chấp thuận phù hợp.

Hướng dẫn chi tiết: [`docs/PUBLISHING.vi.md`](docs/PUBLISHING.vi.md).

## Nâng cấp và bảo toàn dữ liệu

- Sao lưu Home Assistant (đặc biệt thư mục `.storage`) trước khi cập nhật.
- Mã phát IR/RF thực tế thuộc về provider; dữ liệu trong manager chỉ là metadata.
- Nếu bạn nâng cấp từ một tích hợp có **domain khác**, Home Assistant coi đây là tích hợp mới: cần thêm lại config entry và cập nhật automation/entity ID; **không sửa trực tiếp** `.storage/core.config_entries`.
- Có thể dùng [`tools/import_metadata.py`](tools/import_metadata.py) để hỗ trợ nhập metadata (chỉ chạy khi Home Assistant đã dừng; không ghi đè file đích).
- Xem thêm [hướng dẫn tiếng Việt](docs/README.vi.md).

## Phát triển và kiểm thử

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python tools/verify_repository.py --strict
```

GitHub Actions còn chạy HACS Action và Hassfest. Các unit tests độc lập **không** thay thế kiểm thử thực tế trên Home Assistant hoặc hub IR/RF.

## Khắc phục sự cố

- **Không tìm thấy tích hợp sau khi cài:** khởi động lại Home Assistant, kiểm tra `/config/custom_components/universal_ir_rf_remote/`, xem log và thử làm mới trình duyệt.
- **Không học được RF:** kiểm tra hub/provider có hỗ trợ `remote.learn_command` cho RF hay không; xác nhận chế độ và tần số theo tài liệu thiết bị.
- **Không phát được lệnh:** thử action `remote.send_command` trực tiếp trên entity gốc để xác định lỗi nằm ở provider hay manager.
- **Lệnh gửi nhầm hub:** thêm `remote_entity` hoặc `config_entry_id` vào action.
- **Không thấy bản mới trong HACS:** kiểm tra GitHub Release đã xuất bản, tag có khớp `manifest.json` và HACS đã làm mới dữ liệu.
- **Báo lỗi:** mở [GitHub Issues](https://github.com/khaisilk1910/universal_ir_rf_remote/issues), gửi log đã **ẩn token, IP nhạy cảm và dữ liệu mã điều khiển**.

## English summary

**Universal IR RF Remote Manager** is a Home Assistant custom integration that organizes named IR/RF commands for multiple **existing** `remote.*` entities. It delegates learning, sending and deletion to the original remote provider, maintains isolated command metadata for each remote, and offers an optional optimistic fan entity.

**Requirements:** Home Assistant 2026.3.0+ (project metadata), HACS custom Integration repository, and a working remote provider such as Broadlink or Tuya Local implementing the necessary `remote.*` actions. This integration does not add RF support to IR-only hardware.

**Install:** HACS → Custom repositories → `https://github.com/khaisilk1910/universal_ir_rf_remote` → Integration → Download → Restart Home Assistant → Settings → Devices & services → Add integration.

**Support:** [Issues](https://github.com/khaisilk1910/universal_ir_rf_remote/issues) · **Releases:** [GitHub releases](https://github.com/khaisilk1910/universal_ir_rf_remote/releases) · **Details (VI):** [`docs/README.vi.md`](docs/README.vi.md).

## Giấy phép và ghi nhận

Dự án dự kiến phân phối theo [MIT License](LICENSE.md); việc công bố lại mã nguồn cần tuân thủ quyền tác giả và giấy phép của mọi thành phần nguồn gốc. Tài liệu dự án ban đầu ghi nhận tác giả `@nguyen_viet_hung` và nêu MIT; bản tái cấu trúc được duy trì tại repository của `@khaisilk1910`. Chủ repository cần **xác minh quyền phân phối của mã gốc** trước khi phát hành công khai. Không xóa thông báo bản quyền của tác giả gốc.

### Tài liệu tham khảo

- [Home Assistant RemoteEntity](https://developers.home-assistant.io/docs/core/entity/remote/)
- [Home Assistant integrations for HACS](https://www.hacs.dev/docs/publish/integration/)
- [Home Assistant Marketplace publishing](https://contributors.home-assistant.io/marketplace/guides/integrations/)
- [Broadlink](https://www.home-assistant.io/integrations/broadlink/)
- [Tuya Local](https://github.com/make-all/tuya-local)
