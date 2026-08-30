# main.py
# ESP32-S3 - MicroPython
# Modbus Environmental Sensor -> ThingSpeak
#
# ThingSpeak channel:
# Channel ID: 3448221 (MakerLab Bao Loc Station)
#
# Field 1: Temperature
# Field 2: Humidity
# Field 3: Light
# Field 4: Wind Speed
# Field 5: Wind Direction
# Field 6: PM2.5
# Field 7: PM10
# Field 8: Pressure

import gc
import machine
import network

from machine import UART
from time import (
    sleep_ms,
    sleep_us,
    ticks_add,
    ticks_ms,
    ticks_diff,
    time as epoch_s,
)

try:
    import requests
except ImportError:
    import urequests as requests


# =========================================================
# WIFI CONFIG
# =========================================================

# Wi-Fi và Write API Key nằm ở station_secrets.py, KHÔNG nằm ở file này.
# => Phải upload CẢ HAI file lên board: file này và station_secrets.py
try:
    from station_secrets import WIFI_SSID, WIFI_PASSWORD
except ImportError:
    print()
    print("!" * 52)
    print("THIEU station_secrets.py - hay upload file do len board.")
    print("Board se KHONG ket noi Wi-Fi va KHONG upload duoc.")
    print("!" * 52)
    print()

    WIFI_SSID = "CHUA_CAU_HINH"
    WIFI_PASSWORD = ""

# Write API Key của riêng channel Bảo Lộc.
#
# Ưu tiên tên có hậu tố trạm, để MỘT station_secrets.py phục vụ được cả hai
# board mà không có đường nào nạp nhầm key của trạm kia. Nạp nhầm key thì
# ThingSpeak chỉ trả về "0" - một lỗi im lặng, đúng kiểu tốn nhiều giờ nhất
# để truy ra, và ở đây là tốn cả một chuyến lên trạm.
try:
    from station_secrets import (
        THINGSPEAK_WRITE_API_KEY_BAOLOC as THINGSPEAK_WRITE_API_KEY,
    )
except ImportError:
    try:
        from station_secrets import THINGSPEAK_WRITE_API_KEY
    except ImportError:
        print()
        print("!" * 52)
        print("THIEU Write API Key trong station_secrets.py.")
        print("Them THINGSPEAK_WRITE_API_KEY_BAOLOC = \"...\" vao file do.")
        print("Tram van doc cam bien va hien LCD, nhung KHONG upload duoc.")
        print("!" * 52)
        print()

        THINGSPEAK_WRITE_API_KEY = "NHAP_WRITE_API_KEY"

# Vòng lặp chính là đường sống của LCD. Mọi thao tác mạng phải có trần thời
# gian, nếu không màn hình TẠI TRẠM đứng hình vì một lỗi ở tận trên cloud.
#
# Cũ: 10 lần thử x 10 s = tới ~102 s mỗi kỳ upload không đọc cảm biến, không
# vẽ lại LCD. Người đứng ở trạm thấy màn hình chết trong khi board vẫn sống -
# đúng cái kết luận sai mà màn hình này sinh ra để ngăn.
# Mới: một lần thử ngắn; hỏng thì lùi WIFI_RETRY_BACKOFF_MS mới thử lại.
WIFI_RETRIES = 1
WIFI_TIMEOUT_MS = 8000

# Sau một lần kết nối hỏng, không thử lại trước mốc này. Router chết hẳn thì
# chỉ tốn ~8 s mỗi phút, thay vì chiếm gần trọn mọi chu kỳ đọc.
WIFI_RETRY_BACKOFF_MS = 60000


# =========================================================
# THINGSPEAK CONFIG
# =========================================================

CHANNEL_ID = 3448221

# Write API Key Bảo Lộc được cấu hình riêng ở phần Wi-Fi phía trên.
# Khi key bị lộ, tạo key mới tại: ThingSpeak -> Channel -> API Keys.

THINGSPEAK_URL = "https://api.thingspeak.com/update"

# Mapping cloud nam mot cho duy nhat. LCD khong dung mapping nay; no doc truc
# tiep sensor snapshot de viec doi field ThingSpeak khong lam doi man hinh.
THINGSPEAK_FIELD_MAP = (
    ("field1", "temperature"),
    ("field2", "humidity"),
    ("field3", "light"),
    ("field4", "wind_speed"),
    ("field5", "wind_angle"),
    ("field6", "pm2_5"),
    ("field7", "pm10"),
    ("field8", "pressure"),
)

# ThingSpeak Free yêu cầu tối thiểu 15 giây.
# Dùng 20 giây để có khoảng an toàn.
UPLOAD_INTERVAL_MS = 20000

# HTTP_TIMEOUT_S nằm ở khối SELF-RECOVERY phía dưới, cùng watchdog và reset.

# Chu kỳ đọc cảm biến
SENSOR_INTERVAL_MS = 5000


# =========================================================
# UART CONFIG
# =========================================================

RX_PIN = 5
TX_PIN = 4

uart = UART(
    1,
    baudrate=4800,
    bits=8,
    parity=None,
    stop=1,
    rx=RX_PIN,
    tx=TX_PIN,
    timeout=1000,
    timeout_char=20,
)


# =========================================================
# SETTINGS
# =========================================================

READ_WIND = True
DEBUG_WIND = False

# False = che do debug local: van doc Modbus + cap nhat LCD, bo qua hoan toan
# Wi-Fi/ThingSpeak. True = upload sau khi LCD da hien snapshot moi nhat.
CLOUD_UPLOAD_ENABLED = True

# Dưới ngưỡng này coi là lặng gió, không hiện hướng.
# 0.5 m/s = start wind speed theo datasheet SEN0658. Giữ khớp với dashboard.
CALM_MS = 0.5


# ========== SHARED-SELF-RECOVERY-CONFIG BEGIN ==========
# KHỐI NÀY GIỐNG HỆT Ở MỌI FILE FIRMWARE TRẠM. Đừng sửa tay ở một file.
# Sửa trong "bao_loc.py" rồi chạy:  py -3 firmware/sync_shared_blocks.py
# Có test khoá hai bản phải trùng từng byte; lệch là fail.
#
# =========================================================
# SELF-RECOVERY
# =========================================================
#
# Trạm ở xa, tại chỗ không có laptop, và mỗi lần sửa firmware là một chuyến đi.
# "Lên nhấn nút nguồn" không phải một phương án khắc phục. Ba lớp, từ hẹp tới rộng:
#
#   1. HTTP_TIMEOUT_S     - chặn phần DNS/TCP/đọc. KHÔNG chặn được TLS handshake.
#   2. WATCHDOG           - cứu cú treo bất kỳ mà firmware không tự thoát.
#   3. DAILY_RESTART_*    - đặt trần cho cú hỏng LỌT QUA cả hai lớp trên.
#
# ĐỌC docs/ESP32_HTTPS_TLS_POSTMORTEM_2026-07-22.md TRƯỚC KHI SỬA KHỐI NÀY.
# Không lớp nào ở đây sửa được cú treo TLS ngày 22/07 - cú đó VẪN CHƯA CÓ LỜI GIẢI.
# Chúng chỉ làm cho nó tự giới hạn và nhìn thấy được từ cloud. Đừng viết ngược lại.

# Trần thời gian cho một lần POST.
#
# ĐO TRÊN BOARD THẬT 2026-07-22: `requests.post(timeout=15)` KHÔNG tạo ra hạn
# chót cứng cho TLS. Full firmware vẫn kẹt trong `tls.SSLContext.wrap_socket()`
# SAU khi DNS và TCP đã xong, quá mốc 15 s này. Nên đừng mô tả nó như bản vá cho
# kịch bản treo - nó chỉ chặn được DNS, TCP connect và giai đoạn đọc.
# Với cú treo trong handshake, watchdog mới là thứ duy nhất còn tác dụng.
HTTP_TIMEOUT_S = 15

WATCHDOG_ENABLED = True

# HAI ĐIỀU KHÔNG ĐƯỢC QUÊN VỀ WDT TRÊN ESP32:
#   1. Bật rồi thì KHÔNG tắt được, cũng không đổi được timeout.
#   2. Nếu timeout ngắn hơn một chu kỳ HỢP LỆ, board reboot vô hạn và không
#      còn đường nào vào REPL từ xa. Với trạm này đó là mất trạm thật.
#
# 120 s là mốc đã từng được vận hành thật trên trạm này trước lần rollback
# 2026-07-22, giữ nguyên thay vì tự chọn số mới. Đoạn dài nhất không được feed
# là lệnh POST, mà POST thì có thể kẹt VÔ HẠN trong TLS (xem HTTP_TIMEOUT_S),
# nên con số này không phải "biên an toàn quanh một trần đã biết" - nó chỉ
# quyết định phản ứng nhanh hay chậm.
#
# BẪY VẬN HÀNH đã ghi nhận: watchdog đang chạy sẽ reset board sau ~2 phút nếu
# anh Ctrl-C vào REPL để nạp file. Đặt WATCHDOG_ENABLED = False, nạp xong bật lại.
WATCHDOG_TIMEOUT_MS = 120000

# Reboot chủ động mỗi ngày lúc 00:00 giờ địa phương. False = tắt.
#
# Watchdog chỉ cứu được cú treo mà nó NHẬN RA. Kiểu hỏng khó chịu hơn là board
# vẫn "sống" theo mọi tiêu chí nội bộ - vòng lặp vẫn quay, watchdog vẫn được
# feed - nhưng đã ngừng làm việc đúng: Wi-Fi stack kẹt, socket rò, heap phân
# mảnh. Nó nằm im như vậy nhiều ngày cho tới khi có người nhớ ra phải mở
# dashboard lên xem.
#
# Đây KHÔNG phải bản sửa nguyên nhân, và không được kể như một bản sửa. Nó chỉ
# giới hạn thời gian một lỗi chưa biết được phép tồn tại. Giá phải trả: mất
# khoảng một chu kỳ dữ liệu mỗi ngày, và mốc 00:00 là lúc rẻ nhất để mất.
DAILY_RESTART_ENABLED = True
DAILY_RESTART_HOUR = 0
TIMEZONE_OFFSET_S = 7 * 3600          # ICT = UTC+7

# Cửa sổ cho phép reset, tính từ DAILY_RESTART_HOUR. Vòng lặp quay ~8 s nên
# 5 phút là thừa rộng; đừng hẹp tới mức một lần Modbus chậm là trượt cả ngày.
DAILY_RESTART_WINDOW_MS = 300000

# CHỐNG REBOOT LOOP - KHÔNG ĐƯỢC BỎ ĐIỀU KIỆN NÀY.
# Reset lúc 00:00:30 xong, board khởi động lại và VẪN đang trong cửa sổ
# 00:00-00:05, nên nếu chỉ xét giờ thì nó reset tiếp, lặp cho tới hết cửa sổ.
# Ở trạm không có ai để rút điện. Mốc uptime tối thiểu là thứ cắt vòng lặp đó.
MIN_UPTIME_BEFORE_RESTART_MS = 2 * 3600 * 1000

# Không đồng bộ được NTP thì không biết 00:00 là lúc nào. Vẫn phải giữ nhịp
# reset, nên rơi về mốc uptime: lệch giờ, nhưng không bao giờ thành "không
# bao giờ reset" - mà đó mới đúng là thứ cần tránh.
FALLBACK_RESTART_MS = 24 * 60 * 60 * 1000

# RTC của ESP32 trôi. Lệch vài giây một ngày thì không sao, sau vài tuần thì
# mốc 00:00 lệch thấy rõ, nên đồng bộ lại định kỳ.
NTP_RESYNC_MS = 6 * 3600 * 1000
NTP_RETRY_MS = 300000

# Mất mạng KHÔNG kích hoạt reset. Reset vì lỗi cloud là bắt LCD - con mắt tại
# chỗ - chịu phạt thay cho router, đúng thứ kiến trúc hai đường này tránh.
# Đặt > 0 (ms) chỉ khi ĐÃ ĐO được rằng Wi-Fi stack kẹt thật và chỉ reset mới gỡ.
UPLOAD_STALL_RESET_MS = 0
# ========== SHARED-SELF-RECOVERY-CONFIG END ==========


# =========================================================
# LCD 20x4 I2C (tùy chọn)
# =========================================================

LCD_ENABLED = True

# Đấu dây thực tế trên trạm Bảo Lộc: SDA = 8, SCL = 9.
# Nếu sai thứ tự, lcd_init() sẽ tự thử cặp đảo và in ra cặp nào chạy được.
LCD_SDA_PIN = 8
LCD_SCL_PIN = 9

# 0 = tự dò (0x27 cho PCF8574, 0x3F cho PCF8574A)
LCD_ADDR = 0

LCD_COLS = 20
LCD_ROWS = 4

# DFRobot: "Host polling interval and waiting response time are too short,
# both need to be set above 200ms" - đây là nguyên nhân số 4 gây mất phản hồi
# trong mục troubleshooting của SEN0658. Trước đây khoảng cách chỉ 20 ms.
MODBUS_GAP_MS = 220


# =========================================================
# MODBUS COMMANDS
# =========================================================

# Wind speed and direction
COM_WIND = bytes([
    0x01, 0x03, 0x01, 0xF4,
    0x00, 0x04, 0x04, 0x07
])

# Temperature, humidity, noise
COM_THN = bytes([
    0x01, 0x03, 0x01, 0xF8,
    0x00, 0x03, 0x85, 0xC6
])

# Light
COM_LUX = bytes([
    0x01, 0x03, 0x01, 0xFE,
    0x00, 0x02, 0xA4, 0x07
])

# PM2.5, PM10, atmospheric pressure
COM_PM = bytes([
    0x01, 0x03, 0x01, 0xFB,
    0x00, 0x03, 0x75, 0xC6
])


# ========== SHARED-SELF-RECOVERY-CODE BEGIN ==========
# KHỐI NÀY GIỐNG HỆT Ở MỌI FILE FIRMWARE TRẠM. Đừng sửa tay ở một file.
# Sửa trong "bao_loc.py" rồi chạy:  py -3 firmware/sync_shared_blocks.py
#
# =========================================================
# WATCHDOG + NGỦ CÓ VỖ CHÓ
# =========================================================

_wdt = None


def watchdog_arm():
    """
    Bật WDT. Gọi ĐÚNG MỘT LẦN, và chỉ SAU khi một chu kỳ đầy đủ đã chạy trót lọt.

    Arm trễ có HAI lý do, cả hai đều là an toàn chứ không phải tối ưu.

    1. WDT trên ESP32 không tắt được. Nếu bản firmware này crash ở đâu đó trên
       đường khởi động, watchdog chưa từng được bật và board còn nằm ở REPL -
       thứ duy nhất cứu được một trạm không có laptop tại chỗ.

    2. Nó chặn BOOT-WDT loop. Postmortem 2026-07-22 kết luận thẳng: "Short WDT
       resets a blocked handshake but can create a BOOT-WDT loop; not a usable
       uploader." Vì arm nằm ở CUỐI chu kỳ, mà lần upload đầu sau mỗi lần boot
       lại nằm TRƯỚC đó, nên lần upload đầu KHÔNG được watchdog bảo vệ. Nghe
       như thiếu sót, nhưng chính nó cắt vòng lặp: một cú treo TLS gây đúng
       MỘT lần reset rồi dừng hẳn, thay vì reset - boot - treo - reset mãi.

       Đánh đổi phải nói rõ: nếu handshake treo ngay lần upload đầu sau boot,
       board sẽ nằm im vô hạn chứ không tự cứu. Lúc đó dashboard báo "Station
       offline", và đó là sự thật - không phải bug của lớp này.

    Mọi lỗi đều bị nuốt: không bật được watchdog thì trạm vẫn phải chạy.
    """

    global _wdt

    if _wdt is not None or not WATCHDOG_ENABLED:
        return

    try:
        _wdt = machine.WDT(0, WATCHDOG_TIMEOUT_MS)
        print("WDT: da bat, timeout {} ms".format(WATCHDOG_TIMEOUT_MS))
    except Exception as error:
        _wdt = None
        print("WDT: khong bat duoc. Tram chay KHONG co watchdog:", error)


def feed():
    """
    Vỗ watchdog. No-op khi chưa arm, nên gọi ở đâu cũng an toàn.

    TUYỆT ĐỐI KHÔNG gọi bên trong một thao tác mạng đang chờ. Feed ở đó là dạy
    watchdog rằng treo là bình thường, và cả lớp bảo vệ này thành vô nghĩa.
    """

    if _wdt is not None:
        try:
            _wdt.feed()
        except Exception:
            pass


def nap_ms(total_ms):
    """
    sleep_ms có vỗ watchdog. Dùng cho MỌI khoảng nghỉ CHỦ ĐỘNG của firmware.

    Ngủ theo lát <= 500 ms. Nghỉ đúng lịch là tiến triển hợp lệ nên phải được
    feed; còn kẹt trong socket thì không, và đó mới là thứ WDT sinh ra để bắt.
    """

    slept = 0

    while slept < total_ms:
        step = total_ms - slept

        if step > 500:
            step = 500

        sleep_ms(step)
        slept += step
        feed()


def reset_cause_tag():
    """
    Hậu tố cho nhãn BOOT của lần khởi động này:

        ""        bật nguồn / mất điện, hoặc không đọc được nguyên nhân
        "WDT"     firmware treo, watchdog đã cắn và cứu
        "DAILY"   reboot do chính firmware này gọi

    Đây là thứ DUY NHẤT phân biệt được, NHÌN TỪ CLOUD, ba kiểu khởi động lại
    cần ba cách xử lý khác hẳn nhau. Không có nó thì cả ba hiện ra y hệt
    "board restarted", và cú đáng lo chìm lẫn vào cú bình thường.

    Giới hạn của "DAILY": nó suy ra từ SOFT_RESET, nghĩa là "có ai đó gọi
    reset", KHÔNG phải bằng chứng trực tiếp rằng bộ đếm 24 h đã gọi. Ctrl-D ở
    REPL cũng cho SOFT_RESET. Trong firmware này chỉ daily restart và
    UPLOAD_STALL_RESET_MS gọi machine.reset(), nên suy luận đó đủ chắc - nhưng
    nó là suy luận, không phải phép đo.
    """

    try:
        cause = machine.reset_cause()
    except Exception:
        return ""

    try:
        if cause == machine.WDT_RESET:
            return "WDT"
    except AttributeError:
        pass

    try:
        if cause == machine.SOFT_RESET:
            return "DAILY"
    except AttributeError:
        pass

    return ""


BOOT_TAG = reset_cause_tag()


# =========================================================
# ĐỒNG HỒ + MỐC RESET NỬA ĐÊM
# =========================================================

_clock_ok = False
_ntp_next_try = None


def sync_clock():
    """
    Đồng bộ đồng hồ qua NTP. CHỈ gọi khi đã có Wi-Fi.

    Trả về True nếu đồng hồ đang tin được. Mọi lỗi đều bị nuốt: không có giờ
    thì reset theo uptime, chứ không được làm chết vòng lặp đọc cảm biến.
    """

    global _clock_ok, _ntp_next_try

    if (
        _ntp_next_try is not None
        and ticks_diff(_ntp_next_try, ticks_ms()) > 0
    ):
        return _clock_ok

    try:
        import ntptime

        # ntptime ở một số build chờ vô hạn. Đặt trần nếu build này cho phép -
        # đây đúng là kiểu treo mà cả file đang đi vá, không được tự tạo thêm.
        try:
            ntptime.timeout = 5
        except Exception:
            pass

        ntptime.settime()
        _clock_ok = True
        _ntp_next_try = ticks_add(ticks_ms(), NTP_RESYNC_MS)
        print("NTP: dong bo xong. Gio dia phuong:", local_clock_text())

    except Exception as error:
        _ntp_next_try = ticks_add(ticks_ms(), NTP_RETRY_MS)
        print("NTP: khong dong bo duoc:", error)

    return _clock_ok


def local_seconds_of_day():
    """
    Số giây kể từ 00:00 giờ địa phương, hoặc None nếu đồng hồ chưa tin được.

    epoch của MicroPython trên ESP32 là 2000-01-01 00:00 UTC, của CPython là
    1970-01-01 00:00 UTC. Cả hai đều bắt đầu ĐÚNG nửa đêm UTC, nên phép
    (epoch + offset) % 86400 ra đúng giây-trong-ngày trên cả hai mà không cần
    biết đang chạy trên cái nào - nhờ vậy hàm này kiểm thử được trên máy tính.
    """

    if not _clock_ok:
        return None

    return (epoch_s() + TIMEZONE_OFFSET_S) % 86400


def local_clock_text():
    seconds = local_seconds_of_day()

    if seconds is None:
        return "chua dong bo"

    return "{:02d}:{:02d}:{:02d}".format(
        seconds // 3600,
        (seconds % 3600) // 60,
        seconds % 60
    )


def should_restart(uptime_ms):
    """
    Đã tới lúc reset theo lịch chưa.

    Hai lớp: có giờ thật thì bám mốc DAILY_RESTART_HOUR; không có thì rơi về
    uptime. CẢ HAI đều bị chặn bởi MIN_UPTIME_BEFORE_RESTART_MS, và đó là thứ
    duy nhất ngăn reboot loop ngay sau lần reset nửa đêm.
    """

    if not DAILY_RESTART_ENABLED:
        return False

    if uptime_ms < MIN_UPTIME_BEFORE_RESTART_MS:
        return False

    seconds = local_seconds_of_day()

    if seconds is None:
        return uptime_ms >= FALLBACK_RESTART_MS

    # Lấy dư theo 86400 để cửa sổ quanh 00:00 không phải xử lý riêng phần
    # vắt qua nửa đêm - đó là chỗ dễ viết sai nhất của bài toán này.
    offset_s = (seconds - DAILY_RESTART_HOUR * 3600) % 86400

    return offset_s * 1000 < DAILY_RESTART_WINDOW_MS
# ========== SHARED-SELF-RECOVERY-CODE END ==========


# =========================================================
# WIFI FUNCTIONS
# =========================================================

wlan = network.WLAN(network.STA_IF)


def connect_wifi():
    """
    Kết nối Wi-Fi tối đa WIFI_RETRIES lần.
    Trả về True nếu kết nối thành công.
    """

    wlan.active(True)

    if wlan.isconnected():
        print("Wi-Fi already connected")
        print("IP:", wlan.ifconfig()[0])
        return True

    print("Connecting to Wi-Fi:", WIFI_SSID)

    for attempt in range(1, WIFI_RETRIES + 1):
        print(
            "Wi-Fi attempt {}/{}".format(
                attempt,
                WIFI_RETRIES
            )
        )

        try:
            wlan.disconnect()
        except Exception:
            pass

        nap_ms(200)

        try:
            wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        except Exception as error:
            print("Wi-Fi connect error:", error)
            nap_ms(1000)
            continue

        start = ticks_ms()

        while ticks_diff(ticks_ms(), start) < WIFI_TIMEOUT_MS:
            if wlan.isconnected():
                network_info = wlan.ifconfig()

                print("Wi-Fi connected")
                print("IP address:", network_info[0])
                print("Subnet:", network_info[1])
                print("Gateway:", network_info[2])
                print("DNS:", network_info[3])
                print()

                return True

            nap_ms(500)

        print("Connection timed out, status:", wlan.status())

    print("Could not connect to Wi-Fi")
    return False


_wifi_backoff_until = None


def ensure_wifi():
    """
    True nếu có Wi-Fi. Thất bại thì lùi WIFI_RETRY_BACKOFF_MS mới thử lại.

    Backoff là thứ giữ cho LCD sống khi router chết. Không có nó, mỗi kỳ upload
    lại đứng nguyên WIFI_TIMEOUT_MS và màn hình tại trạm gần như không nhảy số -
    đúng lúc người ta cần nó nhất để biết trạm còn chạy hay không.
    """

    global _wifi_backoff_until

    if wlan.isconnected():
        _wifi_backoff_until = None
        return True

    if (
        _wifi_backoff_until is not None
        and ticks_diff(_wifi_backoff_until, ticks_ms()) > 0
    ):
        print("Wi-Fi: dang backoff, bo qua ky upload nay")
        return False

    print("Wi-Fi disconnected. Reconnecting...")

    if connect_wifi():
        _wifi_backoff_until = None
        return True

    _wifi_backoff_until = ticks_add(ticks_ms(), WIFI_RETRY_BACKOFF_MS)

    print(
        "Wi-Fi: that bai, thu lai sau {} s".format(
            WIFI_RETRY_BACKOFF_MS // 1000
        )
    )

    return False


# =========================================================
# MODBUS HELPER FUNCTIONS
# =========================================================

def clear_uart():
    while uart.any():
        uart.read()
        sleep_ms(2)


def hex_bytes(data):
    """
    Đổi bytes thành chuỗi hex cách nhau bởi dấu cách.

    Không dùng data.hex(" ") vì tham số dấu phân cách không có ở mọi bản
    MicroPython. Các chỗ gọi đều nằm trong nhánh xử lý lỗi, mà nhánh lỗi
    lại là chỗ tuyệt đối không được ném thêm exception.
    """

    return " ".join("{:02x}".format(b) for b in data)


def crc16_modbus(data):
    crc = 0xFFFF

    for b in data:
        crc ^= b

        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1

    return crc & 0xFFFF


def read_n(length, timeout_ms=1000):
    buf = bytearray()
    start = ticks_ms()

    while len(buf) < length:
        if uart.any():
            chunk = uart.read(length - len(buf))

            if chunk:
                buf.extend(chunk)

        if ticks_diff(ticks_ms(), start) > timeout_ms:
            break

        sleep_ms(1)

    return bytes(buf)


def u16_be(data, index):
    return (
        (data[index] << 8)
        | data[index + 1]
    )


def s16_be(data, index):
    """
    Signed 16-bit big-endian.

    Theo protocol SEN0658, nhiệt độ dưới 0 độ C được gửi ở dạng bù hai.
    Ví dụ 0xFF9B = -101 => -10.1 độ C.
    Đọc bằng u16_be sẽ cho 65435 => 6543.5 độ C.
    """

    value = u16_be(data, index)

    if value & 0x8000:
        return value - 0x10000

    return value


def u32_be(data, index):
    return (
        (data[index] << 24)
        | (data[index + 1] << 16)
        | (data[index + 2] << 8)
        | data[index + 3]
    )


def read_modbus_frame(
    request,
    expected_byte_count,
    name="sensor",
    timeout_ms=1000
):
    """
    Modbus response:

    ADDRESS
    FUNCTION
    BYTE_COUNT
    DATA...
    CRC_LOW
    CRC_HIGH
    """

    clear_uart()
    sleep_ms(MODBUS_GAP_MS)

    uart.write(request)

    expected_len = 3 + expected_byte_count + 2
    frame = read_n(expected_len, timeout_ms)

    if len(frame) != expected_len:
        print("Time out:", name)

        if frame:
            print("Received {} bytes: {}".format(
                len(frame),
                hex_bytes(frame)
            ))
        else:
            print("Received nothing")

        return None

    if frame[0] != 0x01:
        print(
            "Wrong sensor address:",
            name,
            hex_bytes(frame)
        )
        return None

    if frame[1] != 0x03:
        print(
            "Wrong function code:",
            name,
            hex_bytes(frame)
        )
        return None

    if frame[2] != expected_byte_count:
        print(
            "Wrong byte count:",
            name,
            hex_bytes(frame)
        )
        return None

    received_crc = frame[-2] | (frame[-1] << 8)
    calculated_crc = crc16_modbus(frame[:-2])

    if received_crc != calculated_crc:
        print("CRC error:", name)
        print("RX   :", hex_bytes(frame))
        print("Got  :", hex(received_crc))
        print("Calc :", hex(calculated_crc))
        return None

    return frame


# =========================================================
# SENSOR READ FUNCTIONS
# =========================================================

def read_temperature_humidity_noise():
    frame = read_modbus_frame(
        COM_THN,
        expected_byte_count=6,
        name="temperature/humidity/noise"
    )

    if frame is None:
        return None

    data = frame[3:-2]

    humidity = u16_be(data, 0) / 10.0
    temperature = s16_be(data, 2) / 10.0
    noise = u16_be(data, 4) / 10.0

    return temperature, humidity, noise


def read_light():
    frame = read_modbus_frame(
        COM_LUX,
        expected_byte_count=4,
        name="light"
    )

    if frame is None:
        return None

    data = frame[3:-2]
    lux = u32_be(data, 0)

    return lux


def read_pm_pressure():
    frame = read_modbus_frame(
        COM_PM,
        expected_byte_count=6,
        name="PM/pressure"
    )

    if frame is None:
        return None

    data = frame[3:-2]

    pm2_5 = u16_be(data, 0)
    pm10 = u16_be(data, 2)
    pressure = u16_be(data, 4) / 10.0

    return pm2_5, pm10, pressure


def read_wind():
    frame = read_modbus_frame(
        COM_WIND,
        expected_byte_count=8,
        name="wind"
    )

    if frame is None:
        return None

    if DEBUG_WIND:
        print("WIND RAW:", hex_bytes(frame))

    data = frame[3:-2]

    r0 = u16_be(data, 0)
    r1 = u16_be(data, 2)
    r2 = u16_be(data, 4)
    r3 = u16_be(data, 6)

    if DEBUG_WIND:
        print("WIND REG:", r0, r1, r2, r3)

    wind_speed = r0 / 10.0

    # Mã hướng gió từ cảm biến
    wind_direction = r2

    # Góc hướng gió, thường từ 0 đến 360 độ
    wind_angle = r3

    return wind_speed, wind_direction, wind_angle


# =========================================================
# THINGSPEAK FUNCTIONS
# =========================================================

def build_sensor_snapshot(
    temperature,
    humidity,
    noise,
    pm2_5,
    pm10,
    pressure,
    light,
    wind_speed,
    wind_direction,
    wind_angle
):
    """Ban ghi cuc bo cua mot chu ky Modbus; khong phu thuoc Wi-Fi/cloud."""

    return {
        "temperature": temperature,
        "humidity": humidity,
        "noise": noise,
        "pm2_5": pm2_5,
        "pm10": pm10,
        "pressure": pressure,
        "light": light,
        "wind_speed": wind_speed,
        "wind_direction": wind_direction,
        "wind_angle": wind_angle,
    }


def build_thingspeak_fields(snapshot):
    """Tao mot ban sao payload cloud; khong sua sensor snapshot cua LCD."""

    fields = {}

    for field_name, sensor_name in THINGSPEAK_FIELD_MAP:
        value = snapshot.get(sensor_name)

        if value is not None:
            fields[field_name] = value

    return fields

def format_value(value):
    """
    Chuyển số thành chuỗi trước khi gửi.
    Giới hạn số float ở 2 chữ số thập phân.
    """

    if isinstance(value, float):
        return "{:.2f}".format(value)

    return str(value)


def build_status(failed_reads, attempted, is_first_upload):
    """
    Chuỗi trạng thái gửi kèm mỗi lần upload, qua trường `status` của ThingSpeak.

    `status` KHÔNG chiếm field nào trong 8 field đang dùng, và ThingSpeak vẫn tạo
    entry khi chỉ có status. Nhờ vậy kênh vẫn có nhịp tim ngay cả khi TẤT CẢ lệnh
    Modbus timeout - phân biệt được "cảm biến chết, board còn sống" với "board chết".

    Chỉ dùng chữ cái, số, dấu chấm, gạch ngang và gạch dưới, nên luôn an toàn khi
    form-encode mà không cần hàm urlencode.
    """

    if not failed_reads:
        status = "ALL_OK"
    elif len(failed_reads) >= attempted:
        status = "FAIL-ALL"
    else:
        status = "FAIL-" + "-".join(failed_reads)

    if is_first_upload:
        # Tiền tố PHẢI bắt đầu bằng "BOOT": dashboard nhận diện reboot bằng
        # status.indexOf('BOOT') === 0, nên "BOOT_WDT." vẫn khớp còn
        # "WDT_BOOT." thì không. Đuôi ".FAIL-..." giữ nguyên để deadGroups()
        # phía dashboard vẫn parse được y như cũ.
        if BOOT_TAG:
            status = "BOOT_" + BOOT_TAG + "." + status
        else:
            status = "BOOT." + status

    return status


_post_timeout_supported = True


def http_post(payload):
    """
    POST có trần thời gian.

    `timeout=` chỉ được thêm vào requests của micropython-lib khá muộn, nên
    KHÔNG được giả định build đang nằm trên board có nó. Thử một lần; nếu build
    này không nhận thì ghi nhớ và từ đó gọi bản không timeout - lúc ấy watchdog
    là lớp duy nhất còn lại, và mấy dòng in ra dưới đây là thứ nói cho ta biết
    mình đang ở tình trạng đó thay vì tưởng là đã được bảo vệ.
    """

    global _post_timeout_supported

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    if _post_timeout_supported:
        try:
            return requests.post(
                THINGSPEAK_URL,
                data=payload,
                headers=headers,
                timeout=HTTP_TIMEOUT_S
            )
        except TypeError:
            # Chữ ký hàm sai thì lỗi xảy ra TRƯỚC khi có byte nào lên mạng,
            # nên không có nguy cơ gửi trùng bản ghi khi thử lại phía dưới.
            _post_timeout_supported = False

            print()
            print("!" * 52)
            print("Build requests nay KHONG nhan timeout=.")
            print("POST se KHONG co tran thoi gian; chi con WDT do lai.")
            print("!" * 52)
            print()

    return requests.post(
        THINGSPEAK_URL,
        data=payload,
        headers=headers
    )


def send_to_thingspeak(field_values, status=""):
    """
    field_values có dạng:

    {
        "field1": 1.2,
        "field2": 180,
        "field3": 28.5
    }
    """

    # Không còn bỏ qua upload khi mọi lệnh đọc đều fail: vẫn gửi status làm nhịp tim,
    # nếu không kênh sẽ im lặng và dashboard tưởng nhầm là board mất điện.
    if not field_values and not status:
        print("No sensor data and no status to upload")
        return False

    if not ensure_wifi():
        print("Upload cancelled: no Wi-Fi")
        return False

    if (
        not THINGSPEAK_WRITE_API_KEY
        or THINGSPEAK_WRITE_API_KEY == "NHAP_WRITE_API_KEY"
    ):
        print("ThingSpeak Write API Key has not been configured")
        return False

    form_items = [
        "api_key={}".format(
            THINGSPEAK_WRITE_API_KEY
        )
    ]

    for field_name in sorted(field_values):
        value = field_values[field_name]

        if value is not None:
            form_items.append(
                "{}={}".format(
                    field_name,
                    format_value(value)
                )
            )

    if status:
        form_items.append("status={}".format(status))

    payload = "&".join(form_items)

    response = None

    try:
        print("Sending data to ThingSpeak...")

        response = http_post(payload)

        response_body = response.text.strip()

        print("HTTP status:", response.status_code)
        print("ThingSpeak response:", response_body)

        if response.status_code != 200:
            print("ThingSpeak HTTP error")
            return False

        if response_body == "0":
            print(
                "ThingSpeak rejected the update. "
                "Check API key or upload interval."
            )
            return False

        print(
            "Upload successful. Entry ID:",
            response_body
        )

        return True

    except Exception as error:
        print("ThingSpeak upload error:", error)
        return False

    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

        gc.collect()


# =========================================================
# LCD DRIVER + LAYOUT
# =========================================================

# Driver HD44780 qua bo mo rong I2C PCF8574, viet gon ngay trong file nay
# de khong phai upload them thu vien len board.
# Bit map cua bo mo rong: P0=RS, P1=RW, P2=EN, P3=den nen, P4..P7=D4..D7
_LCD_RS = 0x01
_LCD_EN = 0x04
_LCD_BACKLIGHT = 0x08

DEGREE = chr(0xDF)          # ky tu do trong bang ma A00 cua HD44780

DIRS_16 = (
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW"
)


class Lcd2004:
    def __init__(self, i2c, addr):
        self.i2c = i2c
        self.addr = addr
        self.buf = bytearray(1)
        self._setup()

    def _raw(self, value):
        self.buf[0] = value | _LCD_BACKLIGHT
        self.i2c.writeto(self.addr, self.buf)

    def _pulse(self, value):
        self._raw(value | _LCD_EN)
        sleep_us(1)
        self._raw(value & 0xFB)
        sleep_us(50)

    def _write4(self, value):
        self._raw(value)
        self._pulse(value)

    def _write(self, value, rs=0):
        self._write4((value & 0xF0) | rs)
        self._write4(((value << 4) & 0xF0) | rs)

    def _setup(self):
        sleep_ms(50)

        # Ba lan 0x30 de ep ve che do 8 bit da biet, roi chuyen sang 4 bit
        for _ in range(3):
            self._write4(0x30)
            sleep_ms(5)

        self._write4(0x20)
        sleep_ms(1)

        self._write(0x28)   # 4 bit, 2 dong, font 5x8
        self._write(0x08)   # tat hien thi
        self._write(0x01)   # xoa man hinh
        sleep_ms(2)
        self._write(0x06)   # con tro tu tang
        self._write(0x0C)   # bat hien thi, an con tro

    def line(self, row, text):
        # Dia chi DDRAM chuan cua LCD 20x4: 0x00, 0x40, 0x14, 0x54.
        row_offsets = (0x00, 0x40, 0x14, 0x54)
        self._write(0x80 | row_offsets[row])

        # MicroPython KHÔNG có str.ljust() (chỉ CPython mới có), nên tự chèn
        # khoảng trắng. Phải ghi đủ 20 ký tự để xoá phần thừa của lần vẽ trước.
        text = text[:LCD_COLS]
        text = text + " " * (LCD_COLS - len(text))

        for ch in text:
            code = ord(ch)
            self._write(code if code < 256 else 0x3F, _LCD_RS)


_lcd = None
_lcd_failures = 0


def _open_i2c(sda, scl):
    """
    Mở I2C trên một cặp chân và quét bus.
    Trả về (bus, danh_sach_dia_chi). Ưu tiên I2C phần cứng, không được thì SoftI2C.
    """

    from machine import Pin, I2C

    try:
        bus = I2C(0, scl=Pin(scl), sda=Pin(sda), freq=100000)
    except Exception:
        from machine import SoftI2C
        bus = SoftI2C(scl=Pin(scl), sda=Pin(sda), freq=100000)

    return bus, bus.scan()


def lcd_init():
    """
    Khoi tao LCD. Moi loi deu bi nuot: man hinh chi la phu, khong duoc
    phep lam chet phan doc cam bien va upload.
    """

    global _lcd

    if not LCD_ENABLED:
        return

    # Thử đúng cặp chân khai báo trước; nếu không thấy thiết bị nào thì thử đảo
    # SDA/SCL rồi in ra cặp thực sự chạy được. Đảo hai dây này là nhầm lẫn rất
    # hay gặp, và bắt board tự trả lời thì chắc hơn là ngồi đoán.
    for sda, scl in (
        (LCD_SDA_PIN, LCD_SCL_PIN),
        (LCD_SCL_PIN, LCD_SDA_PIN)
    ):
        try:
            i2c, found = _open_i2c(sda, scl)
        except Exception as error:
            print(
                "LCD: khong mo duoc I2C tren SDA={}, SCL={}: {}".format(
                    sda, scl, error
                )
            )
            continue

        if not found:
            print(
                "LCD: khong thay thiet bi I2C nao tren SDA={}, SCL={}".format(
                    sda, scl
                )
            )
            continue

        if LCD_ADDR:
            addr = LCD_ADDR
        elif 0x27 in found:
            addr = 0x27
        elif 0x3F in found:
            addr = 0x3F
        else:
            addr = found[0]

        try:
            _lcd = Lcd2004(i2c, addr)
        except Exception as error:
            print("LCD: khoi tao man hinh that bai:", error)
            _lcd = None
            continue

        print(
            "LCD: san sang tai {} voi SDA={}, SCL={}{}".format(
                hex(addr),
                sda,
                scl,
                "" if sda == LCD_SDA_PIN else "  <-- DAO so voi khai bao!"
            )
        )
        return

    print("LCD: bo qua. Tram van chay binh thuong.")
    _lcd = None


def lcd_write(line1, line2="", line3="", line4=""):
    global _lcd, _lcd_failures

    if _lcd is None:
        return

    try:
        _lcd.line(0, line1)
        _lcd.line(1, line2)
        _lcd.line(2, line3)
        _lcd.line(3, line4)
        _lcd_failures = 0

    except Exception as error:
        _lcd_failures += 1
        print("LCD: loi ghi:", error)

        if _lcd_failures >= 3:
            print("LCD: tat han sau 3 loi lien tiep. Tram van chay binh thuong.")
            _lcd = None


def compass(deg):
    return DIRS_16[int((deg % 360) / 22.5 + 0.5) % 16]


def fmt_lux(value):
    """
    Anh sang 0..200000 lux gon trong toi da 4 ky tu.
    0 -> "0", 999 -> "999", 1234 -> "1.2k", 200000 -> "200k"
    """

    if value is None:
        return "--"

    if value < 1000:
        return str(value)

    # Cận trên là 9950 chứ không phải 10000: 9999/1000 làm tròn thành "10.0k",
    # dài 5 ký tự và phá mất bố cục.
    if value < 9950:
        return "{:.1f}k".format(value / 1000.0)

    return "{}k".format(int(round(value / 1000.0)))


def pad_row(left, right):
    """
    Hai cot: trai cang trai, phai cang phai, khoang trong don o giua.
    Chieu rong thay doi thi khoang giua co gian, nen bo cuc khong bao gio vo.
    """

    gap = LCD_COLS - len(left) - len(right)

    if gap < 1:
        # Lưới an toàn cuối cùng. Người gọi phải rút gọn ở mức TRƯỜNG dữ liệu
        # trước khi tới đây: cắt giữa một con số sẽ tạo ra giá trị sai mà vẫn
        # đọc được như thật (200000 lux -> "200"), tệ hơn là không hiện gì.
        return (left + " " + right)[:LCD_COLS]

    return left + (" " * gap) + right


# Ky tu cuoi dong 4 = trang thai duong len cloud, NHIN TU TAI TRAM.
# Day la cho duy nhat hai consumer gap nhau, va co y chi ton dung mot ky tu:
# LCD sinh ra de tra loi "tram co chay khong", khong phai "cloud co nhan khong".
# Man hinh van phai day du so khi ky tu nay bao mat mang.
LINK_OK = "*"        # lan upload gan nhat thanh cong
LINK_NO_WIFI = "!"   # khong co Wi-Fi, hoac dang trong backoff
LINK_REJECTED = "?"  # co mang nhung ThingSpeak tu choi / POST loi
LINK_OFF = "-"       # CLOUD_UPLOAD_ENABLED = False
LINK_PENDING = " "   # chua toi ky upload dau tien


def lcd_lines(snapshot, link=""):
    """
    Dung bon dong 20 ky tu. Ham thuan tuy, khong dung toi phan cung,
    nen kiem thu duoc tren may tinh.

    Dong 1: nhiet do + do am
    Dong 2: PM2.5 + PM10
    Dong 3: toc do gio + huong chu + goc
    Dong 4: anh sang + tieng on + ap suat + 1 ky tu trang thai cloud
    Gia tri doc hong hien "--" chu khong giu lai so cu.

    `link` la trang thai cua lan upload TRUOC. Do la su that duy nhat co that
    o thoi diem ve man hinh, va noi dung nay chay truoc buoc upload trong moi
    chu ky. Khong duoc doan truoc ket qua lan gui sap toi.
    """

    temperature = snapshot.get("temperature")
    humidity = snapshot.get("humidity")
    noise = snapshot.get("noise")
    pm2_5 = snapshot.get("pm2_5")
    pm10 = snapshot.get("pm10")
    pressure = snapshot.get("pressure")
    light = snapshot.get("light")
    wind_speed = snapshot.get("wind_speed")
    wind_angle = snapshot.get("wind_angle")

    temp_txt = "--" if temperature is None else "{:.1f}C".format(temperature)
    humidity_txt = "--" if humidity is None else "{:.1f}%".format(humidity)
    line1 = pad_row("T:" + temp_txt, "H:" + humidity_txt)

    pm25_txt = "--" if pm2_5 is None else str(pm2_5)
    pm10_txt = "--" if pm10 is None else str(pm10)
    line2 = pad_row("PM2.5:" + pm25_txt, "PM10:" + pm10_txt)

    if wind_speed is None:
        line3 = pad_row("Wind:--", "ERR")
    elif wind_speed <= CALM_MS or wind_angle is None:
        line3 = pad_row("Wind:{:.1f}m/s".format(wind_speed), "CALM")
    else:
        line3 = pad_row(
            "W:{:.1f}m/s {}".format(wind_speed, compass(wind_angle)),
            "{:.0f}{}".format(wind_angle, DEGREE)
        )

    lux_txt = "L" + fmt_lux(light)
    noise_txt = "N--" if noise is None else "N{:.0f}".format(noise)
    pressure_txt = "P--" if pressure is None else "P{:.1f}".format(pressure)

    # Ba truong nay dai toi da 5 + 4 + 6 = 15 ky tu cong hai dau cach = 17,
    # nen con du cho ky tu link o cot 20 ma khong cham luoi an toan cua pad_row.
    line4 = pad_row(
        "{} {} {}".format(lux_txt, noise_txt, pressure_txt),
        link
    )

    return line1, line2, line3, line4


# =========================================================
# MAIN PROGRAM
# =========================================================

print()
print("--- System Start ---")
print("ESP32-S3 Modbus Environmental Station")
print("ThingSpeak channel:", CHANNEL_ID)
print(
    "UART1 RX={}, TX={}, baud=4800".format(
        RX_PIN,
        TX_PIN
    )
)
print(
    "Reset cause: {}".format(
        BOOT_TAG if BOOT_TAG else "PWRON/unknown"
    )
)
print(
    "Self-recovery: HTTP {} s | WDT {} | daily restart {}".format(
        HTTP_TIMEOUT_S,
        "{} ms".format(WATCHDOG_TIMEOUT_MS) if WATCHDOG_ENABLED else "off",
        "{:02d}:00 local (fallback {} h uptime)".format(
            DAILY_RESTART_HOUR,
            FALLBACK_RESTART_MS // 3600000
        ) if DAILY_RESTART_ENABLED else "off"
    )
)
print()

lcd_init()
lcd_write(
    "BAO LOC STATION",
    "Reading local data",
    "ThingSpeak:3448221",
    "Starting sensors..."
)

# Khong ket noi Wi-Fi luc boot. Tram doc va hien snapshot Modbus truoc;
# chi den ky upload moi goi ensure_wifi() ben trong send_to_thingspeak().

# Đặt thời điểm upload trước đó lùi về quá khứ
# để lần đọc đầu tiên được gửi ngay.
last_upload = ticks_ms() - UPLOAD_INTERVAL_MS

# Lần upload đầu sau khi khởi động được đánh dấu BOOT., để dashboard biết chắc
# board vừa reset thay vì phải đoán qua các giá trị cảm biến bằng 0.
first_upload = True

# Mốc uptime cho reboot theo lịch. ticks_diff hợp lệ tới ~6,2 ngày nên mốc 24 h
# an toàn; KHÔNG được trừ ticks_ms() trực tiếp vì nó quay vòng.
boot_ticks = ticks_ms()

# Watchdog chỉ được arm sau chu kỳ đầy đủ đầu tiên. Xem watchdog_arm().
first_cycle_done = False

# Trạng thái đường lên cloud, giữ NGUYÊN qua các chu kỳ: nó mô tả lần upload
# gần nhất, không phải chu kỳ hiện tại, nên không được reset đầu vòng lặp.
link = LINK_PENDING if CLOUD_UPLOAD_ENABLED else LINK_OFF
last_good_upload = ticks_ms()


while True:
    # Tên các lệnh Modbus đọc hỏng trong chu kỳ này, theo đúng thứ tự đọc
    failed_reads = []
    attempted_reads = 4 if READ_WIND else 3

    # Đặt lại mỗi chu kỳ: LCD phải hiện "--" khi đọc hỏng,
    # không được giữ lại giá trị cũ của chu kỳ trước.
    # `lux` trước đây bị bỏ sót ở đây. Nó chỉ an toàn vì read_light() được gọi
    # vô điều kiện ngay dưới; thêm một chữ `if` là màn hình giữ số cũ mà không
    # ai biết. Liệt kê tường minh để lời hứa của khối này là thật.
    temperature = humidity = noise = None
    lux = None
    pm2_5 = pm10 = pressure = None
    wind_speed = wind_direction = wind_angle = None

    feed()

    print("----------------------------------------")
    print("Reading sensors...")

    # -----------------------------------------------------
    # Temperature, humidity and noise
    # -----------------------------------------------------

    thn = read_temperature_humidity_noise()
    feed()

    if thn is not None:
        temperature, humidity, noise = thn

        print(
            "Temperature = {:.1f} C".format(
                temperature
            )
        )
        print(
            "Humidity    = {:.1f} %RH".format(
                humidity
            )
        )
        print(
            "Noise       = {:.1f} dB".format(
                noise
            )
        )

    else:
        failed_reads.append("THN")

    # -----------------------------------------------------
    # Light
    # -----------------------------------------------------

    lux = read_light()
    feed()

    if lux is not None:
        print("Light       = {} lux".format(lux))
    else:
        failed_reads.append("LUX")

    # -----------------------------------------------------
    # PM2.5, PM10 and pressure
    # -----------------------------------------------------

    pm = read_pm_pressure()
    feed()

    if pm is not None:
        pm2_5, pm10, pressure = pm

        print(
            "PM2.5       = {} ug/m3".format(
                pm2_5
            )
        )
        print(
            "PM10        = {} ug/m3".format(
                pm10
            )
        )
        print(
            "Pressure    = {:.1f} kPa".format(
                pressure
            )
        )

    else:
        failed_reads.append("PM")

    # -----------------------------------------------------
    # Wind
    # -----------------------------------------------------

    if READ_WIND:
        wind = read_wind()
        feed()

        if wind is not None:
            wind_speed, wind_direction, wind_angle = wind

            print(
                "Wind Speed = {:.2f} m/s".format(
                    wind_speed
                )
            )
            print(
                "Wind Code  = {}".format(
                    wind_direction
                )
            )
            print(
                "Wind Angle = {} deg".format(
                    wind_angle
                )
            )

        else:
            failed_reads.append("WIND")

    # Snapshot chi phan anh ket qua Modbus cua chu ky hien tai. LCD va cloud la
    # hai consumer tach biet; consumer cloud chi nhan mot dict moi o luc upload.
    snapshot = build_sensor_snapshot(
        temperature,
        humidity,
        noise,
        pm2_5,
        pm10,
        pressure,
        lux,
        wind_speed,
        wind_direction,
        wind_angle
    )

    # -----------------------------------------------------
    # LCD
    # -----------------------------------------------------

    if len(failed_reads) >= attempted_reads:
        lcd_write(
            "SENSOR NO REPLY",
            "Check RS485/power",
            "ThingSpeak:3448221",
            pad_row("Bao Loc station", link)
        )
    else:
        lcd_rows = lcd_lines(snapshot, link)
        lcd_write(*lcd_rows)

    feed()

    # -----------------------------------------------------
    # ThingSpeak upload
    # -----------------------------------------------------

    current_time = ticks_ms()

    if (
        CLOUD_UPLOAD_ENABLED
        and
        ticks_diff(current_time, last_upload)
        >= UPLOAD_INTERVAL_MS
    ):
        status = build_status(
            failed_reads,
            attempted_reads,
            first_upload
        )

        print()
        print("Status      = {}".format(status))

        # Payload duoc tao sau khi LCD da cap nhat. Upload khong duoc thay doi
        # snapshot dang hien tren man hinh.
        fields = build_thingspeak_fields(snapshot)

        # Feed NGAY TRUOC va NGAY SAU lan gui, khong bao gio o giua. Doan giua
        # chinh la thu WDT phai bat duoc neu HTTP_TIMEOUT_S khong an.
        feed()

        if send_to_thingspeak(fields, status):
            first_upload = False
            last_good_upload = ticks_ms()
            link = LINK_OK
        elif not wlan.isconnected():
            link = LINK_NO_WIFI
        else:
            link = LINK_REJECTED

        feed()

        # Đồng bộ đồng hồ SAU khi đã gửi xong. NTP chỉ phục vụ mốc reset nửa
        # đêm, nó không được phép làm trễ một bản ghi. Hàm tự lo backoff nên
        # gọi mỗi kỳ upload cũng không sinh thêm lưu lượng đáng kể.
        if wlan.isconnected():
            sync_clock()
            feed()

        # Ghi nhận cả lần gửi thành công hoặc thất bại,
        # tránh gửi liên tục gây vượt giới hạn ThingSpeak.
        last_upload = ticks_ms()

    # -----------------------------------------------------
    # Self-recovery
    # -----------------------------------------------------

    # Arm watchdog SAU chu ky day du dau tien. Xem watchdog_arm(): arm tre la
    # dieu kien an toan, vi WDT tren ESP32 bat roi khong tat duoc.
    if not first_cycle_done:
        first_cycle_done = True
        watchdog_arm()

    # Reboot theo lich. Dat o day - sau khi LCD da ve va ky upload da xong -
    # nen khong cat ngang mot ban ghi dang gui do.
    if should_restart(ticks_diff(ticks_ms(), boot_ticks)):
        print()
        print("Reset theo lich. Gio dia phuong:", local_clock_text())

        lcd_write(
            "BAO LOC STATION",
            "Scheduled restart",
            local_clock_text() if _clock_ok else "no NTP - by uptime",
            "Back in a few sec"
        )

        nap_ms(500)
        machine.reset()

    # Mac dinh tat. Xem UPLOAD_STALL_RESET_MS o phan cau hinh: mat mang KHONG
    # duoc lam ly do reset, vi nhu vay la bat LCD chiu phat thay cho router.
    if (
        UPLOAD_STALL_RESET_MS
        and CLOUD_UPLOAD_ENABLED
        and ticks_diff(ticks_ms(), last_good_upload) >= UPLOAD_STALL_RESET_MS
    ):
        print()
        print("Khong upload duoc qua lau - reset chu dong.")
        nap_ms(500)
        machine.reset()

    print()
    nap_ms(SENSOR_INTERVAL_MS)

