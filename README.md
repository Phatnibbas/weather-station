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
  self_check.py                 chạy MỘT LẦN trên board để kiểm tra phần cứng
  station_secrets.example.py    mẫu; copy thành station_secrets.py rồi điền
  sync_shared_blocks.py         đồng bộ các khối dùng chung giữa hai firmware
public/
  index.html                    dashboard, một file, không cần build
tests/
  harness.mjs                   DOM giả + sandbox, dùng chung cho test dashboard
  test_firmware_recovery.py     chạy firmware trên PC với module board bị stub
  test_dashboard.mjs            chạy dashboard trên Node, đánh vào channel thật
  test_audit_regressions.py     sổ cái bản rà soát 2026-08-30 — firmware
  test_audit_regressions.mjs    sổ cái bản rà soát 2026-08-30 — dashboard
docs/
  ESP32_HTTPS_TLS_POSTMORTEM_2026-07-22.md    ĐỌC TRƯỚC KHI SỬA PHẦN MẠNG
  AUDIT-2026-08-30.md                         bản rà soát overclaim/hardcode
  firmware-notes-2026-07-22.md                ghi chép cũ, mô tả bản đã rollback
```

## Dashboard

Một file tĩnh, không build. Mở thẳng `public/index.html` cũng chạy.

Deploy: Vercel dựng lại từ repo GitHub `weather-station` mỗi lần push lên `main`
(Phát xác nhận đang chạy như vậy — chưa có bước kiểm chứng nào trong repo này chứng
minh nó). **Sửa `public/index.html` xong phải push thì trang live mới đổi.**

**Chọn trạm:** ô đầu trang liệt kê sẵn Bảo Lộc và Sài Gòn theo tên, không phải nhớ mã
channel. Mục cuối là `Another channel…`, mở ô gõ ID cho bất kỳ kênh ThingSpeak công
khai nào. URL vẫn chia sẻ được: `?channel=3428136`. Danh sách trạm nằm ở
`knownChannels` trong khối config của `index.html` — thêm trạm là thêm một dòng ở đó,
không đụng vào JavaScript.

Tên field lấy từ **chính channel đó**. Field nào nhận ra được thì có đơn vị và dải hợp
lý; field kênh **không khai báo** thì biến mất hẳn khỏi bảng, biểu đồ và CSV — không
mượn nhãn của trạm khác.

Phần **Diagnostics** chỉ bật khi channel có đủ bốn lệnh Modbus của firmware nhà mình —
với channel lạ nó tắt hẳn thay vì mô tả một firmware channel đó chưa từng chạy.

**Mốc dữ liệu (`dataEpochs`)** cắt bỏ bản ghi cũ khỏi biểu đồ, bảng *và* file CSV. Mỗi
kênh có mốc và **lý do riêng**, hiện ngay trên trang:

| Channel | Mốc | Lý do |
|---|---|---|
| 3428136 Sài Gòn | 2026-07-21T17:17:02Z | firmware đổi thang đo gió `/100 → /10` |
| 3448221 Bảo Lộc | 2026-08-09T04:41:28Z | entry 1–53 sai field map; 54–140 là chạy thử ở Sài Gòn (100,8 kPa). Từ 141 mới là số đo tại Bảo Lộc (90,1 kPa) |

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

### Kiểm tra board trước khi mang đi xa

Toàn bộ phần tự phục hồi mới **chỉ được kiểm trên PC**. Ba thứ chỉ chính con board trả
lời được, và nếu đoán bừa thì cả ba lớp bảo vệ đều có thể chỉ là trang trí:

1. ESP32 này có nhận `machine.WDT(0, 120000)` không?
2. Build MicroPython này có `ntptime` không? (không có → không biết 00:00 là lúc nào)
3. `requests` trên board này có nhận tham số `timeout=` không?

`firmware/self_check.py` hỏi board đúng ba câu đó, cộng Modbus / I2C / Wi-Fi, rồi in ra
bảng tóm tắt. Nó **không ghi bản ghi nào lên ThingSpeak** (dùng key sai có chủ ý, kênh
trả về `"0"` và không tạo entry), và **không đụng vào `main.py`** — chỉ đọc lại chính
file đó để dùng đúng các hàm thật của firmware, nên không có bản sao nào để trôi.

```powershell
py -3 -m mpremote connect COM25 fs cp firmware/self_check.py :self_check.py
py -3 -m mpremote connect COM25 run self_check.py
```

Dán toàn bộ log về. Dòng nào `FAIL` là một lớp bảo vệ **không tồn tại** trên board đó.

> Bước cuối bật watchdog thật. WDT trên ESP32 bật rồi **không tắt được**, nên board sẽ
> tự reset sau ~120 s — đọc xong log thì rút điện. Không muốn vậy thì đặt
> `TEST_WATCHDOG = False` ở đầu file, đổi lại là câu hỏi số 1 không có câu trả lời.

## LCD — con mắt tại trạm

LCD đọc thẳng snapshot Modbus của chu kỳ hiện tại, **không đi qua ThingSpeak**. Nó trả
lời đúng một câu: *trạm có đang chạy không*. Mất mạng thì nó vẫn phải đầy đủ số.

Ba trạng thái của một trường, **cố ý phân biệt được** vì ba cách xử lý khác hẳn nhau:

| Hiện | Nghĩa | Đi tìm ở đâu |
|---|---|---|
| số thật | đọc được, nằm trong dải hợp lý | — |
| `--` | lệnh Modbus **không trả lời** | dây RS485, nguồn cảm biến |
| `!!!` | có trả lời nhưng **số vô lý** | cảm biến còn sống mà đang nói bậy |

`!!!` không phải trang trí: một khung Modbus **đúng CRC** vẫn mang được thanh ghi u16
đầy, và firmware chia 10 thành `6553.5 kPa`. Trước bản vá 2026-08-30 màn hình cắt nó
thành `P655` — một con số **sai mà đọc vẫn xuôi**, và cùng lúc đẩy mất ký tự trạng thái
cloud ở cột cuối. Dải hợp lý nằm ở khối `SHARED-SENSOR-PLAUSIBILITY`, **cố ý rộng hơn
datasheet SEN0658**: việc của nó là bắt khung rác, không phải chứng nhận phép đo. Trạm
này chưa từng được hiệu chuẩn.

Ký tự cuối dòng cuối = trạng thái đường lên cloud, **nhìn từ tại trạm**:
`*` gửi được · `!` mất Wi-Fi hoặc đang backoff · `?` có mạng nhưng ThingSpeak từ chối ·
`-` đã tắt upload · `` ` ` `` chưa tới kỳ gửi đầu.

**Debug tại chỗ:** đặt `CLOUD_UPLOAD_ENABLED = False` rồi nạp lại — trạm vẫn đọc Modbus
và vẽ LCD, bỏ qua hoàn toàn Wi-Fi/ThingSpeak, ký tự cuối thành `-`. Dùng khi cần tách
bạch "cảm biến hỏng" với "đường mạng hỏng". Cả **hai** firmware đều có công tắc này.

## Sửa khối dùng chung

Hai khối **giống hệt nhau từng byte** ở cả hai firmware và được sinh ra, không chép tay:
`SHARED-SELF-RECOVERY-*` (watchdog, timeout, reset 00:00) và `SHARED-SENSOR-PLAUSIBILITY`
(dải hợp lý + `!!!`).

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

Cộng thêm **sổ cái của bản rà soát 2026-08-30** — 10 lỗi đã đo được, nay đã sửa hết.
Giữ lại làm test chống tái phát, đừng xoá:

```bash
py -3 tests/test_audit_regressions.py    # firmware  — 5 mục
node tests/test_audit_regressions.mjs    # dashboard — 5 mục
```

Chi tiết từng mục và bằng chứng: [`docs/AUDIT-2026-08-30.md`](docs/AUDIT-2026-08-30.md).

**Test này chứng minh được gì:** LCD không tràn cột và không cắt giữa một con số ở mọi
trường hợp, kể cả thanh ghi u16 đầy; ký tự trạng thái cloud không bao giờ bị đẩy mất;
chuỗi `status` parse đúng bằng chính logic dashboard; mốc reset nửa đêm không sinh
reboot loop; dashboard phục vụ đúng cả hai field map và không bịa nhãn cho kênh lạ;
mọi tên mà `self_check.py` gọi vào firmware đều có thật ở cả hai bản.

**Không chứng minh được gì:** mọi thứ thuộc runtime của board — DNS, TCP, TLS, mbedTLS,
watchdog thật, `ntptime` có tồn tại trên build đang nạp hay không. Chỉ serial log từ
ESP32 thật mới trả lời được: chạy `firmware/self_check.py`. Xem thêm
`docs/ESP32_HTTPS_TLS_POSTMORTEM_2026-07-22.md`.

## Tự phục hồi — và giới hạn của nó

Ba lớp, từ hẹp tới rộng:

| Lớp | Chặn được gì | Giới hạn đã đo |
|---|---|---|
| `HTTP_TIMEOUT_S = 15` | DNS, TCP connect, giai đoạn đọc | **KHÔNG** chặn được TLS handshake |
| `WATCHDOG_TIMEOUT_MS = 120000` | treo bất kỳ mà firmware không tự thoát | watchdog ngắn có thể tạo BOOT-WDT loop |
| Reset 00:00 giờ địa phương | lỗi lọt qua hai lớp trên | cần NTP; không có thì rơi về uptime 24 h |

**Không lớp nào trong đây sửa được cú treo TLS ngày 22/07 — cú đó vẫn chưa có lời giải.**
Đo ngày 2026-07-22 **trên trạm Sài Gòn (ESP32-WROOM, runtime tự khai `ESP32_GENERIC`)**:
`requests.post(timeout=15)` không tạo hạn chót cứng, firmware vẫn kẹt trong
`tls.SSLContext.wrap_socket()` sau khi DNS và TCP đã xong. Ba lớp trên chỉ làm cho lỗi
**tự giới hạn và nhìn thấy được từ cloud**, chứ không làm nó biến mất.

**Phạm vi của phép đo đó:** nó chạy trên ESP32-WROOM. Bảo Lộc là **ESP32-S3** — chip
khác, build khác, heap khác — và chưa từng đo lại trên đó. Áp kết luận sang S3 là giả
định **thận trọng**, không phải phép đo. `firmware/self_check.py` là cách trả lời.

Firmware gắn nguyên nhân reset vào bản ghi đầu tiên sau mỗi lần khởi động, nên nhìn từ
dashboard phân biệt được ba thứ vốn trông giống hệt nhau:

| status | Nghĩa |
|---|---|
| `BOOT.` | bật nguồn / mất điện, hoặc không đọc được nguyên nhân |
| `BOOT_WDT.` | firmware treo, watchdog đã cắn và cứu — lỗi thật, phải truy |
| `BOOT_DAILY.` | reset theo lịch của chính firmware — bình thường |

## Đã biết, chưa xử lý

- **Bản vá self-recovery vẫn CHƯA TỪNG chạy trên board.** Đây là mục quan trọng nhất
  còn mở. Toàn bộ bằng chứng hiện có là test trên PC — kể cả phần LCD `!!!` vừa thêm.
  Ba thứ chỉ board mới trả lời được: ESP32 có nhận `WDT(0, 120000)` không, build
  MicroPython có `ntptime` không, và `requests` có nhận `timeout=` không. Cả ba đều có
  nhánh dự phòng và in cảnh báo, nhưng **đó là thiết kế, chưa phải phép đo**. Chạy
  `firmware/self_check.py` rồi cập nhật lại mục này bằng kết quả thật.
- **Cú treo TLS 2026-07-22 chưa có lời giải.** Đọc postmortem trước khi đụng vào phần
  mạng. Guardrail đã đặt: chỉ mở lại kèm kế hoạch điều tra tài nguyên/runtime cụ thể và
  phải kiểm chứng trên board thật. Ngoài ra phép đo đó chạy trên **ESP32-WROOM**, chưa
  lặp lại trên **ESP32-S3** của Bảo Lộc.
- **Hai Write API Key chưa rotate.** Key Sài Gòn là key đã từng lộ.
- **Bảo Lộc chưa được nạp lại firmware.** Phần cứng đang có vấn đề; bản trong repo là
  bản đúng, board thì chưa mang bản đó.

### Đã đóng ngày 2026-08-30

- **10 lỗi của bản rà soát** (bịa nhãn field cho kênh lạ, chữ ký reboot khoá theo số
  field, LCD cắt giữa số, và các câu khẳng định rộng hơn thứ đã đo) — sửa hết, sổ cái
  `tests/test_audit_regressions.*` đang xanh. Xem
  [`docs/AUDIT-2026-08-30.md`](docs/AUDIT-2026-08-30.md).
- **Mốc dữ liệu Bảo Lộc** chốt ở `2026-08-09T04:41:28Z` (entry 141), nên CSV toàn bộ
  lịch sử **không còn kèm** 53 dòng sai field map lẫn phần chạy thử ở Sài Gòn.
- **Vercel** — Phát xác nhận trang đã deploy và tự dựng lại từ repo. Trước đây README
  khẳng định điều này như một sự thật trong khi chính nó ghi "chưa deploy thử lần nào";
  giờ ghi đúng nguồn: **user-confirmed**, không phải do repo này kiểm chứng.
