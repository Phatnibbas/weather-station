<!-- Ghi chú biên tập, thêm 2026-08-30 khi tách repo. -->

> ## ⚠️ TÀI LIỆU LỊCH SỬ — KHÔNG MÔ TẢ FIRMWARE HIỆN TẠI
>
> Giữ lại vì phần **đấu dây, bản đồ field, bẫy MicroPython, bảng sự cố thường gặp và
> các mục đã kiểm chứng** vẫn còn giá trị. Nhưng nó viết cho **bản firmware đã bị
> rollback ngày 2026-07-22**, nên những phần sau **KHÔNG khớp** với `firmware/` hiện tại:
>
> - Bảng cấu hình nhắc `WDT_ENABLED`, `WDT_TIMEOUT_MS`, `REBOOT_AFTER_NO_UPLOAD_MS`,
>   `MAX_LOOP_ERRORS`, `UART_FLUSH_MS` — firmware hiện tại **không có** các hằng số này.
>   Tên tương ứng bây giờ là `WATCHDOG_ENABLED`, `WATCHDOG_TIMEOUT_MS`,
>   `UPLOAD_STALL_RESET_MS`.
> - Marker `BOOT-WDT.` / `BOOT-HARD.` (gạch ngang) nay là `BOOT_WDT.` / `BOOT_DAILY.`
>   (gạch dưới), và dashboard parse theo dạng mới.
> - Nhịp upload thực đo ~24 s ở tài liệu này; đo lại 2026-08-30 trên cả hai channel
>   cho trung vị **27–28 s**.
> - `bao loc.py` nay là `firmware/bao_loc.py` và **không còn hardcode API key**.
>
> Mô tả đúng của bản hiện tại nằm ở `README.md` ở gốc repo.
> Phần mạng thì đọc `docs/ESP32_HTTPS_TLS_POSTMORTEM_2026-07-22.md`.

---

# Firmware trạm thời tiết — `saigon.py`

> ⚠ **Đọc trước, kiểm chứng 2026-08-11.** File này mô tả một số thứ **KHÔNG có trong
> firmware thật**:
>
> - Sáu hằng số `WDT_ENABLED`, `WDT_TIMEOUT_MS`, `HTTP_TIMEOUT_S`,
>   `REBOOT_AFTER_NO_UPLOAD_MS`, `MAX_LOOP_ERRORS`, `UART_FLUSH_MS` **không tồn tại**
>   trong `saigon.py` lẫn `bao loc.py`. Cả hai file chỉ `from machine import UART`.
> - Bảng tiền tố `BOOT-PWR.` / `BOOT-WDT.` / `BOOT-HARD.` … **không tồn tại**; code chỉ
>   phát tiền tố `BOOT.` trơn, không mang lý do reset.
> - **Không có watchdog, không có `machine.reset()`, và `requests.post()` gọi HTTPS
>   không truyền timeout nào.** Nghĩa là không có lớp tự phục hồi nào cả.
>
> Phần "Trạng thái HTTPS và tự phục hồi" bên dưới mô tả bản hardening **đã bị rollback**.
> Giữ lại vì nó ghi đúng những gì board thật đã chứng minh về TLS, nhưng đừng đọc nó như
> mô tả code hiện tại.
>
> Tên file cũng đã đổi: `siuuuu.py` → **`saigon.py`** (channel 3428136) và
> **`bao loc.py`** (channel 3448221, ESP32-S3, LCD 20×4, thứ tự field khác, hiện không chạy).
> `bao loc.py` **hardcode Write API Key** nên đã bị gitignore — chuyển key sang
> `station_secrets.py` trước khi track lại.

MicroPython trên **ESP32-WROOM (ESP32 classic, không phải S3)**. Đọc cảm biến môi trường
9-trong-1 DFRobot **SEN0658** qua RS485/Modbus RTU, đẩy lên ThingSpeak channel **3428136**,
và hiện số liệu lên LCD 16×2 I2C.

Cặp với `deliverables/saigon-telemetry-live.html` — dashboard đọc chuỗi `status` do firmware
gửi kèm, nên hai file **chia sẻ một wire format**; sửa một bên phải sửa bên kia.

## Nạp lên board

Phải upload **CẢ HAI** file, thiếu `station_secrets.py` là không vào được Wi-Fi:

```
saigon.py            -> đổi tên thành main.py trên board (hoặc import từ main.py)
station_secrets.py   -> chứa SSID, mật khẩu Wi-Fi, ThingSpeak Write API Key
```

Có thể nạp trực tiếp bằng `mpremote`; không cần mở/copy qua editor Thonny:

```powershell
py -3 -m mpremote connect COM25 fs cp firmware/saigon.py :main.py
py -3 -m mpremote connect COM25 fs sha256sum :main.py
py -3 -m mpremote connect COM25 reset
```

Đóng Thonny trước vì backend của nó giữ cổng serial. `COM25` chỉ là cổng quan sát trong phiên
2026-07-22; sau khi rút/cắm USB phải dò lại bằng `py -3 -m serial.tools.list_ports -v`.

> ⚠ **`station_secrets.py` không nằm trong gói chia sẻ.** Nó chứa mật khẩu Wi-Fi thật và
> Write API Key thật. Xoá khỏi thư mục trước khi gửi cho bất kỳ ai. Write API Key trước đó đã bị
> lộ ngày 2026-07-21 và **vẫn chưa rotate** — vào ThingSpeak → Channel → API Keys →
> *Generate New Write API Key*, rồi dán key mới vào `station_secrets.py`.

## Đấu dây

| Thiết bị | Chân ESP32 | Ghi chú |
|---|---|---|
| RS485 → cảm biến | UART1 **RX = 16**, **TX = 17** | 4800 baud, 8N1 |
| LCD 16×2 (PCF8574) | **SDA = 22**, **SCL = 21** | Đã xác nhận trên phần cứng 2026-07-22 |

**LCD đấu ngược so với mặc định của ESP32 classic** (mặc định là SDA 21 / SCL 22), rất dễ
"sửa cho đúng" thành sai. `lcd_init()` thử cặp khai báo trước, không thấy thì thử cặp đảo,
rồi in ra cặp nào thực sự chạy:

```
LCD: san sang tai 0x27 voi SDA=22, SCL=21
LCD: san sang tai 0x27 voi SDA=21, SCL=22  <-- DAO so voi khai bao!
```

Địa chỉ I2C tự dò (0x27 cho PCF8574, 0x3F cho PCF8574A). Ép cứng bằng `LCD_ADDR`.

## Chỗ chỉnh cấu hình

Tất cả nằm ở đầu file, không phải lục vào logic:

| Hằng số | Giá trị | Ý nghĩa |
|---|---|---|
| `UPLOAD_INTERVAL_MS` | 20000 | Ngưỡng tối thiểu, không phải nhịp thực. Vòng lặp chỉ kiểm tra mốc này mỗi ~6 s nên **nhịp thực đo được là ~24 s** (p50 trên 8000 bản ghi). ThingSpeak Free yêu cầu ≥15 s |
| `SENSOR_INTERVAL_MS` | 5000 | Nhịp đọc cảm biến (và vẽ lại LCD) |
| `WDT_ENABLED` / `WDT_TIMEOUT_MS` | True / 120000 | Watchdog phần cứng. Đặt False khi vọc trên bàn — **bật rồi thì MicroPython không cho tắt hay chỉnh lại** |
| `HTTP_TIMEOUT_S` | 15 | Được truyền xuống socket của POST. **Không phải hard deadline đã chứng minh cho TLS**: bản ESP32 thật vẫn từng treo trong `SSLContext.wrap_socket()` quá mốc này |
| `REBOOT_AFTER_NO_UPLOAD_MS` | 900000 | Không upload nổi 15 phút → `machine.reset()` |
| `MAX_LOOP_ERRORS` | 5 | Số exception liên tiếp của vòng lặp trước khi reset |
| `UART_FLUSH_MS` | 200 | Chặn trên cho `clear_uart()` |
| `MODBUS_GAP_MS` | 220 | DFRobot yêu cầu **>200 ms** giữa các lệnh; dưới ngưỡng này cảm biến hay không trả lời |
| `CALM_MS` | 0.5 | Dưới ngưỡng = lặng gió, không hiện hướng. Là *start wind speed* của SEN0658 — dưới đó cánh quạt không quay nên góc gió vô nghĩa. **Phải khớp `calmThresholdMs` bên dashboard** |
| `LCD_ENABLED` | True | Đặt False nếu tháo màn hình |
| `READ_WIND` / `DEBUG_WIND` | True / False | `DEBUG_WIND` in ra register thô của cụm gió |

Mốc cắt dữ liệu (`dataStartIso`) **không nằm ở đây** — nó ở trong dashboard HTML.

## Bản đồ field ThingSpeak

| Field | Đại lượng | Register | Nhóm đọc |
|---|---|---|---|
| 1 | Tốc độ gió (m/s) | `0x01F4` | WIND |
| 2 | Góc gió (0–360°) | `0x01F7` | WIND |
| 3 | Nhiệt độ (°C) | `0x01F9` | THN |
| 4 | Áp suất (kPa) | `0x01FD` | PM |
| 5 | Ánh sáng (lux) | `0x01FE`+`0x01FF` (32-bit) | LUX |
| 6 | Độ ẩm (%RH) | `0x01F8` | THN |
| 7 | Tiếng ồn (dB) | `0x01FA` | THN |
| 8 | PM2.5 (µg/m³) | `0x01FB` | PM |

PM10 (`0x01FC`) có đọc nhưng **không gửi** — channel đã dùng hết 8 field.

Ba lưu ý về cách giải mã, mỗi cái đều từng là bug:

- **Tốc độ gió chia `/10`**, không phải `/100`. Tài liệu DFRobot tự mâu thuẫn (bảng protocol
  ghi "10 times the actual value", code mẫu Arduino lại chia 100). `/10` là đúng: đã kiểm
  197/197 mẫu rơi đúng lưới 0.1, và mọi giá trị đều nằm trên ngưỡng khởi động 0.5 m/s.
- **Nhiệt độ là số có dấu** (bù hai), đọc bằng `s16_be()`. Dùng `u16_be` thì −10.1 °C sẽ
  thành 6543.5 °C.
- **Ánh sáng là 32-bit**, ghép hai register.

## Chuỗi `status` (nhịp tim)

Mỗi lần upload đều gửi kèm `status`. Trường này **không chiếm field nào** trong 8 field, và
ThingSpeak vẫn tạo entry khi *chỉ có* `status` — nhờ vậy kênh vẫn có nhịp tim ngay cả khi
mọi lệnh Modbus đều timeout. Đó là thứ phân biệt được "cảm biến chết, board còn sống" với
"board chết", hai thứ trước đây nhìn giống hệt nhau từ phía dashboard.

| Chuỗi | Nghĩa |
|---|---|
| `ALL_OK` | Cả 4 lệnh Modbus đều trả lời |
| `FAIL-PM-WIND` | Cụm PM và WIND timeout, các cụm khác OK |
| `FAIL-ALL` | Cả 4 cụm im — bản thân cảm biến hoặc cặp dây RS485 |
| `BOOT-PWR.ALL_OK` | Lần upload **đầu tiên sau khi board reset**, kèm lý do reset |

Tiền tố `BOOT` chỉ xuất hiện **đúng một lần mỗi lần reset** (cờ `first_upload` bị xoá sau
lần gửi thành công đầu tiên). Nên hai marker `BOOT` là **hai lần reset riêng biệt** — dashboard
dựa vào đúng tính chất này để phát hiện crash-loop.

Tiền tố mang luôn **lý do khởi động lại**, lấy từ `machine.reset_cause()`. Đây là cách duy nhất
để chẩn đoán một trạm ở xa mà không mang laptop tới:

| Tiền tố | Nghĩa | Việc cần làm |
|---|---|---|
| `BOOT-PWR.` | Port báo `PWRON_RESET` | Không tự kết luận rút điện hay brownout; marker không phân biệt được nguyên nhân điện cụ thể |
| `BOOT-WDT.` | Firmware treo, watchdog cứu | Board tự khỏi. Lặp lại nhiều thì soi mạng hoặc RS485 |
| `BOOT-HARD.` | Port báo lớp `HARD_RESET` | Source có nhánh gọi `machine.reset()` sau lỗi kéo dài, nhưng marker một mình không chứng minh caller cụ thể |
| `BOOT-SOFT.` | Ctrl-D, hoặc vừa nạp lại từ laptop | Do người làm, không phải sự cố |
| `BOOT-SLEEP.` | Port báo `DEEPSLEEP_RESET` | Ghi nhận reset từ deep sleep; không tự suy ra nguyên nhân khác |
| `BOOT-U<n>.` | Mã reset lạ | Ghi lại `<n>` rồi tra tài liệu port ESP32 |

Lý do reset còn hiện luôn trên **dòng 1 của LCD** trong lúc nối Wi-Fi, nên ra tới trạm là đọc
được ngay mà không cần cắm gì.

> ⚠ Lý do reset phải là **tiền tố**, tuyệt đối không được là hậu tố. Dashboard bắt nhóm Modbus
> hỏng bằng regex `/FAIL-(.+)$/` neo ở cuối chuỗi. `BOOT-WDT.FAIL-THN` → `THN` (đúng), còn
> `BOOT.FAIL-THN.WDT` → `THN.WDT`, không khớp nhóm nào, và dashboard sẽ báo *không có gì hỏng*.
> Đã kiểm 224 tổ hợp (7 tiền tố × 2 × 16 tổ hợp hỏng) với bản sao Python của đúng đoạn JS đó.

Thứ tự đọc là **THN → LUX → PM → WIND**. Nếu phần *đuôi* của thứ tự đó fail, đấy là dấu hiệu
cảm biến mất nguồn giữa chu kỳ (ESP32 chạy nguồn USB riêng nên vẫn upload bản ghi thiếu).

## Trạng thái HTTPS và tự phục hồi

Đọc `docs/ESP32_HTTPS_TLS_POSTMORTEM_2026-07-22.md` trước khi sửa networking.

Trạng thái cuối ngày 2026-07-22 là **rollback về firmware legacy**. Local source, `/main.py` và
`/main_legacy.py` trên board cùng SHA-256:

```text
b783ed14fa623c33b9e8435253c6dd6c82f7db35976fbed152081fd771d4c5bb
```

Board thật đã chứng minh:

- Full firmware có thể dừng trong synchronous `tls.SSLContext.wrap_socket()` sau khi DNS và
  TCP connect đã xong; `timeout=15` không làm call đó trả về.
- WDT có thể reset một call bị block, nhưng timeout ngắn tạo `BOOT-WDT` loop chứ không tạo uploader
  hoạt động.
- Deferred nonblocking TLS chạy trong probe tối giản nhưng full firmware báo
  `MBEDTLS_ERR_RSA_PUBLIC_FAILED+MBEDTLS_ERR_MPI_ALLOC_FAILED`.
- Vì vậy lỗi phù hợp với một vấn đề resource/runtime state của full firmware, nhưng nguyên nhân
  heap/mbedTLS cụ thể vẫn chưa được đo và chưa được kết luận; endpoint, API key, payload và TLS
  stack không bị chứng minh là hỏng hoàn toàn.

Firmware legacy hiện vẫn có WDT 120 s, supervisor exception, bounded UART cleanup và reset sau
15 phút không upload. Tuy nhiên **HTTPS hang chưa được sửa vĩnh viễn**. Phát đã chấp nhận vận hành
tạm thời bằng power-cycle/reload khi cần. Không nâng trạng thái này thành “stable” hoặc “fixed”.

## LCD hiện gì

```
+----------------+     dòng 1: tốc độ gió + hướng chữ + góc
|2.4m/s NW   313°|     dòng 2: nhiệt độ + PM2.5 + ánh sáng (tiền tố L)
|29.3C PM24  L12k|
+----------------+
```

Lặng gió thì dòng 1 là `0.4m/s      CALM`. Đọc hỏng thì hiện `--`, **không giữ lại giá trị cũ**.
Mất cả 4 cụm thì hiện `SENSOR NO REPLY` / `Check RS485/pwr`.

Khi chật chỗ, firmware rút gọn theo bậc ở mức **trường dữ liệu** (bỏ số lẻ nhiệt độ trước, rồi
rút nhãn `PM`→`P`), **không bao giờ cắt chuỗi**: mất một chữ số thập phân thì nhìn ra ngay, còn
`200000` lux bị cắt thành `200` vẫn đọc được như số thật và sẽ đánh lừa người xem.

Mọi lệnh gọi LCD đều bọc try/except và **tự tắt sau 3 lỗi liên tiếp** — màn hình là phụ, không
được phép làm chết phần đọc cảm biến và upload.

## Bẫy MicroPython đã gặp

MicroPython **không có** một số thứ của CPython. Cả hai lỗi dưới đây đều pass trên máy tính rồi
crash trên board, nên **phải test đúng lớp driver, không chỉ test hàm format thuần**:

- `str.ljust()` / `rjust()` / `center()` → tự chèn khoảng trắng bằng tay.
- `bytes.hex(sep)` (tham số dấu phân cách) → dùng `hex_bytes()` tự viết. Cả 6 chỗ gọi đều nằm
  trong nhánh xử lý lỗi — chỗ tuyệt đối không được ném thêm exception.

## Sự cố thường gặp

| Hiện tượng | Nguyên nhân hay gặp |
|---|---|
| `THIEU station_secrets.py` | Quên upload file thứ hai |
| `Time out: <tên cụm>` | Cảm biến mất nguồn, sai dây A/B RS485, hoặc `MODBUS_GAP_MS` bị hạ xuống dưới 200 |
| `CRC error` | Nhiễu đường truyền hoặc sai baud (phải 4800) |
| `ThingSpeak rejected the update` | Sai Write API Key, hoặc gửi dày hơn 15 s |
| `LCD: khong thay thiet bi I2C nao` | Sai chân, chưa cấp nguồn LCD, hoặc backpack hỏng |
| Nhiệt độ ~6543 °C | Đang đọc bằng `u16_be` thay vì `s16_be` |
| Gió luôn dưới 0.5 m/s | Đang chia `/100` thay vì `/10` |
| Board reset mỗi ~2 phút lúc đang nạp file | Watchdog đang chạy. Đặt `WDT_ENABLED = False` rồi nạp, xong bật lại |
| Thấy nhiều `BOOT-WDT.` liên tiếp | Có chỗ treo thật. Xem log serial ngay trước khi reset để biết kẹt ở đâu |
| Thấy nhiều `BOOT-HARD.` liên tiếp | Port đang báo lớp `HARD_RESET`; lấy serial log và control-flow evidence, không suy nguyên nhân chỉ từ marker |
| Dừng ở `Sending data to ThingSpeak...` | HTTPS/TLS hang chưa giải quyết. Không giả định `timeout=15` sẽ cắt được; xem postmortem trước khi thử lại |
| `MBEDTLS_ERR_RSA_PUBLIC_FAILED+MBEDTLS_ERR_MPI_ALLOC_FAILED` | Full firmware không cấp phát đủ bộ nhớ cho RSA handshake trong thử nghiệm nonblocking; rollback, không retry bằng cùng kiến trúc |

## Đã kiểm chứng (2026-07-22)

- 140 bản ghi có `status` đối chiếu với field thực nhận — **0 bất đồng**.
- 4 CRC Modbus hardcode: tính lại đúng cả 4; `expected_byte_count` khớp số register.
- `compass()` khớp `label()` của dashboard trên **721/721** bước nửa độ.
- Driver LCD: giải mã ngược luồng I2C, 9/9 pass; quét 127.413 tổ hợp layout, 0 dòng sai 16 ký tự.
- Nhiệt độ âm: `0xFF9B → −10.1 °C`, đúng ví dụ trong tài liệu SEN0658.

## Ranh giới kiểm chứng

- Host tests có thể kiểm wire format, parsing, payload và control flow.
- Chỉ serial log từ ESP32 thật mới kiểm được DNS/TCP/TLS/mbedTLS và watchdog runtime.
- Matching SHA-256 chỉ chứng minh file đã được nạp đúng, không chứng minh firmware chạy ổn.
- Suite thử nghiệm firmware của các branch TLS đã bị loại khỏi active path sau rollback. Không
  resurrect nó làm gate cho bản deployed; nếu mở lại phải tạo test plan mới gắn với firmware mới.
