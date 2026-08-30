# Trạm thời tiết

Hai trạm quan trắc ESP32 đọc cảm biến DFRobot SEN0658 qua Modbus RTU rồi đẩy lên
ThingSpeak, cộng một trang dashboard đọc được **bất kỳ channel ThingSpeak công khai nào**.

Thiết kế xoay quanh một ràng buộc: **trạm đặt xa, tại chỗ không có laptop, mỗi lần sửa
firmware là một chuyến đi.** Vì vậy có hai đường quan sát tách bạch — LCD trả lời "trạm
có đang chạy không" ngay tại chỗ, dashboard trả lời "trạm gửi được gì lên" từ xa — và
firmware ưu tiên tự phục hồi hơn là thêm tính năng.

## Hai trạm

| | Bảo Lộc | Sài Gòn |
|---|---|---|
| Channel | [`3448221`](https://thingspeak.com/channels/3448221) | [`3428136`](https://thingspeak.com/channels/3428136) |
| Board | ESP32-S3 | ESP32-WROOM |
| LCD | 20×4, SDA 8 / SCL 9 | 16×2, SDA 22 / SCL 21 |
| RS485 | RX 5 / TX 4 | RX 16 / TX 17 |
| Firmware | `firmware/bao_loc.py` | `firmware/saigon.py` |

Cả hai đọc **cùng bốn lệnh Modbus** (4800 8N1) nhưng **đẩy vào field khác nhau** —
Bảo Lộc để nhiệt độ ở field1, Sài Gòn để ở field3. Dashboard vì thế nhận diện cảm biến
theo *ý nghĩa* chứ không theo số field.

Sài Gòn publish thêm độ ồn nhưng không publish PM10; Bảo Lộc thì ngược lại. Cả hai
đều đọc đủ 9 tham số, chỉ là ThingSpeak Free có 8 field.

## Cấu trúc

```
firmware/
  bao_loc.py                    nạp lên board Bảo Lộc, đổi tên thành main.py
  saigon.py                     nạp lên board Sài Gòn, đổi tên thành main.py
  station_secrets.example.py    mẫu; copy thành station_secrets.py rồi điền
  sync_shared_blocks.py         đồng bộ khối self-recovery giữa hai firmware
public/
  index.html                    dashboard, một file, không cần build
tests/
  test_firmware_recovery.py     chạy firmware trên PC với module board bị stub
  test_dashboard.mjs            chạy dashboard trên Node, đánh vào channel thật
docs/
  ESP32_HTTPS_TLS_POSTMORTEM_2026-07-22.md    ĐỌC TRƯỚC KHI SỬA PHẦN MẠNG
  firmware-notes-2026-07-22.md                ghi chép cũ, mô tả bản đã rollback
```

## Dashboard

Một file tĩnh, không build. Mở thẳng `public/index.html`, hoặc deploy lên Vercel
(repo này đã có `vercel.json`; Vercel tự phục vụ thư mục `public/`).

Gõ Channel ID vào ô trên cùng, hoặc mở bằng `?channel=3428136`. Tên field lấy từ
chính channel đó. Field nào nhận ra được thì có đơn vị và dải hợp lý; field lạ hiện
trần, không bịa đơn vị.

Phần **Diagnostics** chỉ bật khi channel có đủ bốn lệnh Modbus của firmware nhà mình —
với channel lạ nó tắt hẳn thay vì mô tả một firmware channel đó chưa từng chạy.

## Nạp firmware

1. `cp firmware/station_secrets.example.py firmware/station_secrets.py` rồi điền
   Wi-Fi và Write API Key. **Mỗi channel một key riêng** — xem chú thích trong file.
2. Đặt `WATCHDOG_ENABLED = False` trước khi nạp. Watchdog đang chạy sẽ reset board
   sau ~2 phút nếu bạn Ctrl-C vào REPL. Nạp xong bật lại.
3. Upload **cả hai file** lên board: firmware (đổi tên thành `main.py`) và
   `station_secrets.py`. Thiếu file thứ hai thì trạm vẫn đọc cảm biến và vẽ LCD,
   nhưng không upload được và LCD hiện `?`.

`mpremote` upload trực tiếp được; không cần Thonny, và nếu mở Thonny thì phải đóng
vì nó giữ cổng serial.

## Sửa khối self-recovery

Phần tự phục hồi **giống hệt nhau** ở hai firmware và được sinh ra, không chép tay:

```bash
py -3 firmware/sync_shared_blocks.py           # sửa bao_loc.py rồi chạy lệnh này
py -3 firmware/sync_shared_blocks.py --check   # chỉ kiểm tra, không ghi
```

Test khoá hai bản phải trùng **từng byte**. Một bản vá watchdog chỉ sửa ở một file sẽ
làm fail test, thay vì âm thầm để trạm còn lại không được bảo vệ.

## Test

```bash
py -3 tests/test_firmware_recovery.py    # cả hai firmware, không cần board
node tests/test_dashboard.mjs            # cần mạng: đánh vào ThingSpeak thật
```

**Test này chứng minh được gì:** định dạng LCD không tràn cột ở mọi trường hợp, chuỗi
`status` parse đúng bằng chính logic dashboard, mốc reset nửa đêm không sinh reboot
loop, dashboard phục vụ đúng cả hai field map.

**Không chứng minh được gì:** mọi thứ thuộc runtime của board — DNS, TCP, TLS, mbedTLS,
watchdog thật, `ntptime` có tồn tại trên build đang nạp hay không. Chỉ serial log từ
ESP32 thật mới trả lời được. Xem `docs/ESP32_HTTPS_TLS_POSTMORTEM_2026-07-22.md`.

## Tự phục hồi — và giới hạn của nó

Ba lớp, từ hẹp tới rộng:

| Lớp | Chặn được gì | Giới hạn đã đo |
|---|---|---|
| `HTTP_TIMEOUT_S = 15` | DNS, TCP connect, giai đoạn đọc | **KHÔNG** chặn được TLS handshake |
| `WATCHDOG_TIMEOUT_MS = 120000` | treo bất kỳ mà firmware không tự thoát | watchdog ngắn có thể tạo BOOT-WDT loop |
| Reset 00:00 giờ địa phương | lỗi lọt qua hai lớp trên | cần NTP; không có thì rơi về uptime 24 h |

**Không lớp nào trong đây sửa được cú treo TLS ngày 22/07 — cú đó vẫn chưa có lời giải.**
Đo trên board thật: `requests.post(timeout=15)` không tạo hạn chót cứng, firmware vẫn kẹt
trong `tls.SSLContext.wrap_socket()` sau khi DNS và TCP đã xong. Ba lớp trên chỉ làm cho
lỗi **tự giới hạn và nhìn thấy được từ cloud**, chứ không làm nó biến mất.

Firmware gắn nguyên nhân reset vào bản ghi đầu tiên sau mỗi lần khởi động, nên nhìn từ
dashboard phân biệt được ba thứ vốn trông giống hệt nhau:

| status | Nghĩa |
|---|---|
| `BOOT.` | bật nguồn / mất điện, hoặc không đọc được nguyên nhân |
| `BOOT_WDT.` | firmware treo, watchdog đã cắn và cứu — lỗi thật, phải truy |
| `BOOT_DAILY.` | reset theo lịch của chính firmware — bình thường |

## Đã biết, chưa xử lý

- **Cú treo TLS 2026-07-22 chưa có lời giải.** Đọc postmortem trước khi đụng vào phần
  mạng. Guardrail đã đặt: chỉ mở lại kèm kế hoạch điều tra tài nguyên/runtime cụ thể và
  phải kiểm chứng trên board thật.
- **Bản vá self-recovery hiện tại chưa từng chạy trên board.** Toàn bộ bằng chứng là
  test trên PC. Ba thứ chỉ board mới trả lời được: ESP32 có nhận `WDT(0, 120000)` không,
  build MicroPython có `ntptime` không, và `requests` có nhận `timeout=` không. Cả ba
  đều có nhánh dự phòng và in cảnh báo, nhưng đó là thiết kế chứ chưa phải phép đo.
- **Channel Bảo Lộc trộn ba lớp dữ liệu.** Entry 1–53 được ghi bằng field map của
  firmware Sài Gòn, nên đọc theo nhãn hiện tại là sai (gió 100,8 m/s, áp suất 21 kPa).
  Entry 54–140 đúng map nhưng áp suất ~100,8 kPa, tức là còn chạy thử ở nơi ngang mực
  nước biển. Từ entry 141 mới là dữ liệu thật tại Bảo Lộc. `dataEpochs["3448221"]` trong
  dashboard vẫn để rỗng, nên nút xuất CSV toàn bộ lịch sử **vẫn kèm cả phần sai nhãn**.
- **Cấu hình Vercel chưa deploy thử lần nào**, nên chưa có gì xác nhận nó chạy.
