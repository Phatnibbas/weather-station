# self_check.py - chay MOT LAN tren board that, roi dan log ve.
#
# VI SAO CO FILE NAY
# ------------------
# Toan bo phan tu phuc hoi (HTTP timeout -> watchdog -> reset 00:00) moi chi
# duoc kiem tren PC voi module board bi stub. Ba thu duoi day KHONG the biet
# duoc tu PC, va neu doan bua thi ca ba lop bao ve deu co the la do trang tri:
#
#   1. ESP32 nay co nhan machine.WDT(0, 120000) khong?
#   2. Build MicroPython nay co ntptime khong? (khong co -> khong biet 00:00 la luc nao)
#   3. requests tren board nay co nhan tham so timeout= khong?
#
# File nay hoi board ba cau do, cong voi Modbus / LCD / Wi-Fi, roi in ra mot
# bang tom tat. No KHONG ghi ban ghi nao len ThingSpeak (dung key sai co y).
#
# CACH DUNG
# ---------
#   1. Nap file nay len board (khong doi ten):
#          py -3 -m mpremote connect COM25 fs cp firmware/self_check.py :self_check.py
#   2. Chay:
#          py -3 -m mpremote connect COM25 run self_check.py
#      hoac vao REPL:  import self_check
#   3. Copy toan bo log dan lai.
#
# main.py KHONG bi dung toi. File nay chi DOC main.py de dung lai chinh cac ham
# that cua firmware - nen khong co ban sao nao de troi khoi nhau.

import gc
import sys

# Bat watchdog o buoc cuoi. De True thi moi TRA LOI DUOC cau hoi so 1, nhung
# WDT tren ESP32 BAT ROI KHONG TAT DUOC: board se tu reset sau
# WATCHDOG_TIMEOUT_MS ke tu luc do. Doc xong log thi rut dien la xong.
# De False neu chi muon soi Modbus/LCD ma khong muon board reset.
TEST_WATCHDOG = True

# Firmware de doc lai. Tren board that no ten main.py.
FIRMWARE_CANDIDATES = ("main.py", "bao_loc.py", "saigon.py")

# Key co y SAI. ThingSpeak tra ve "0" va KHONG tao ban ghi nao, nen buoc kiem
# tra duong mang khong lam ban du lieu that cua tram.
INVALID_KEY = "0000000000000000"

results = []


def say(label, verdict, detail=""):
    """Ghi mot dong ket qua va in ngay, de mat dien giua chung van con log."""
    results.append((label, verdict, detail))
    print("[{}] {}{}".format(verdict, label, "  -  " + detail if detail else ""))


def rule(title):
    print()
    print("-" * 60)
    print(title)
    print("-" * 60)


# =========================================================
# 0. Danh tinh runtime
# =========================================================

rule("0. RUNTIME")

try:
    print("implementation :", sys.implementation)
except Exception as error:
    print("implementation : khong doc duoc:", error)

try:
    import os
    print("uname          :", os.uname())
except Exception as error:
    print("uname          : khong doc duoc:", error)

gc.collect()
print("gc.mem_free    :", gc.mem_free(), "byte")
print()
print("LUU Y: gc.mem_free() la heap cua MicroPython. No KHONG do duoc heap cua")
print("mbedTLS/ESP-IDF - thu tung lam hong RSA handshake ngay 2026-07-22.")
print("Dung dung con so nay de ket luan 'du bo nho cho TLS'.")


# =========================================================
# 1. Nap lai chinh firmware dang chay
# =========================================================

rule("1. NAP FIRMWARE (chi phan truoc vong lap)")

firmware = None
firmware_name = None

for candidate in FIRMWARE_CANDIDATES:
    try:
        with open(candidate) as handle:
            source = handle.read()
    except OSError:
        continue

    if "# MAIN PROGRAM" not in source:
        say("doc {}".format(candidate), "FAIL",
            "khong thay moc '# MAIN PROGRAM' - file nay khong phai firmware tram")
        continue

    head = source[: source.index("# MAIN PROGRAM")]
    # Bo not dong ke tieu de cua chinh khoi MAIN PROGRAM.
    head = head.rsplit("# " + "=" * 57, 1)[0]

    namespace = {}

    try:
        exec(head, namespace)
    except Exception as error:
        say("nap {}".format(candidate), "FAIL", repr(error))
        continue

    firmware = namespace
    firmware_name = candidate
    say("nap {}".format(candidate), "OK",
        "channel {}".format(namespace.get("CHANNEL_ID")))
    break

if firmware is None:
    say("nap firmware", "FAIL", "khong nap duoc file nao trong " + str(FIRMWARE_CANDIDATES))
    raise SystemExit("Khong co firmware de kiem tra. Dung o day.")

print()
print("Cau hinh tu phuc hoi DANG NAP tren board nay:")
for key in ("HTTP_TIMEOUT_S", "WATCHDOG_ENABLED", "WATCHDOG_TIMEOUT_MS",
            "DAILY_RESTART_ENABLED", "DAILY_RESTART_HOUR", "TIMEZONE_OFFSET_S",
            "DAILY_RESTART_WINDOW_MS", "MIN_UPTIME_BEFORE_RESTART_MS",
            "FALLBACK_RESTART_MS", "UPLOAD_STALL_RESET_MS",
            "CLOUD_UPLOAD_ENABLED", "UPLOAD_INTERVAL_MS", "SENSOR_INTERVAL_MS"):
    print("  {:32s} {}".format(key, firmware.get(key, "<khong co>")))


# =========================================================
# 2. Nguyen nhan khoi dong lan nay
# =========================================================

rule("2. RESET CAUSE")

try:
    import machine
    cause = machine.reset_cause()
    tag = firmware["reset_cause_tag"]()
    names = {}
    for name in ("PWRON_RESET", "HARD_RESET", "WDT_RESET", "DEEPSLEEP_RESET",
                 "SOFT_RESET"):
        if hasattr(machine, name):
            names[getattr(machine, name)] = name
    say("reset_cause", "OK",
        "{} ({}) -> nhan BOOT{}".format(
            cause, names.get(cause, "khong ro"), "_" + tag if tag else ""))
except Exception as error:
    say("reset_cause", "FAIL", repr(error))


# =========================================================
# 3. CAU HOI 1 - build nay co ntptime khong
# =========================================================

rule("3. CAU HOI 1/3: ntptime co ton tai khong")

try:
    import ntptime
    say("import ntptime", "OK", "co module")
    try:
        ntptime.timeout = 5
        say("ntptime.timeout dat duoc", "OK", "5 s")
    except Exception as error:
        say("ntptime.timeout dat duoc", "WARN",
            "khong dat duoc ({}) - ntptime co the cho VO HAN".format(error))
except ImportError:
    say("import ntptime", "FAIL",
        "KHONG co ntptime -> khong bao gio biet 00:00 la luc nao "
        "-> reset roi ve moc uptime 24 h, lech gio")


# =========================================================
# 4. Wi-Fi
# =========================================================

rule("4. WI-FI")

wlan = None

try:
    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        print("dang ket noi toi:", firmware.get("WIFI_SSID"))
        firmware["connect_wifi"]()

    if wlan.isconnected():
        info = wlan.ifconfig()
        detail = "IP {}".format(info[0])
        try:
            detail += ", RSSI {} dBm".format(wlan.status("rssi"))
        except Exception:
            pass
        say("Wi-Fi", "OK", detail)
    else:
        say("Wi-Fi", "FAIL", "khong ket noi duoc - cac buoc mang duoi day se bo qua")
except Exception as error:
    say("Wi-Fi", "FAIL", repr(error))

online = wlan is not None and wlan.isconnected()


# =========================================================
# 5. Dong ho + moc reset 00:00
# =========================================================

rule("5. DONG HO + MOC RESET 00:00")

if not online:
    say("NTP", "BO QUA", "khong co mang")
else:
    try:
        if firmware["sync_clock"]():
            say("NTP dong bo", "OK",
                "gio dia phuong {}".format(firmware["local_clock_text"]()))
            seconds = firmware["local_seconds_of_day"]()
            window = firmware["DAILY_RESTART_WINDOW_MS"]
            hour = firmware["DAILY_RESTART_HOUR"]
            offset = (seconds - hour * 3600) % 86400
            say("dang o trong cua so reset?", "OK",
                "con {} s nua toi {:02d}:00 (cua so {} s)".format(
                    (86400 - offset) % 86400, hour, window // 1000))
        else:
            say("NTP dong bo", "FAIL",
                "khong dong bo duoc -> reset se theo uptime 24 h, khong theo 00:00")
    except Exception as error:
        say("NTP dong bo", "FAIL", repr(error))


# =========================================================
# 6. CAU HOI 2 - requests co nhan timeout= khong
# =========================================================

rule("6. CAU HOI 2/3: requests co nhan timeout= khong")

if not online:
    say("requests timeout=", "BO QUA", "khong co mang")
else:
    try:
        import requests
    except ImportError:
        import urequests as requests

    payload = "api_key={}&field1=0".format(INVALID_KEY)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    url = firmware["THINGSPEAK_URL"]
    timeout_s = firmware["HTTP_TIMEOUT_S"]

    from time import ticks_diff, ticks_ms

    started = ticks_ms()
    response = None

    try:
        response = requests.post(url, data=payload, headers=headers,
                                 timeout=timeout_s)
        elapsed = ticks_diff(ticks_ms(), started)
        body = response.text.strip()
        say("requests.post(timeout=)", "OK",
            "duoc chap nhan; HTTP {} body {!r} sau {} ms".format(
                response.status_code, body, elapsed))
        if body == "0":
            say("key sai bi tu choi dung nhu mong doi", "OK",
                "KHONG co ban ghi nao duoc tao")
        else:
            say("key sai bi tu choi dung nhu mong doi", "WARN",
                "body {!r} - kiem tra lai, dang le phai la '0'".format(body))
    except TypeError as error:
        say("requests.post(timeout=)", "FAIL",
            "build nay KHONG nhan timeout= ({}) -> POST khong co tran thoi gian, "
            "chi con WDT do lai".format(error))
    except Exception as error:
        say("requests.post(timeout=)", "WARN",
            "goi duoc nhung loi mang: {!r} sau {} ms".format(
                error, ticks_diff(ticks_ms(), started)))
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        gc.collect()

    print()
    print("LUU Y: buoc nay CHI chung minh chu ky ham co nhan timeout=.")
    print("No KHONG chung minh timeout= chan duoc TLS handshake - ngay 2026-07-22")
    print("board da chung minh dieu nguoc lai. Doc postmortem truoc khi ket luan.")


# =========================================================
# 7. I2C / LCD
# =========================================================

rule("7. I2C / LCD")

sda = firmware.get("LCD_SDA_PIN")
scl = firmware.get("LCD_SCL_PIN")

for pair in ((sda, scl), (scl, sda)):
    try:
        bus, found = firmware["_open_i2c"](pair[0], pair[1])
        if found:
            say("I2C SDA={} SCL={}".format(pair[0], pair[1]), "OK",
                "thay {}".format([hex(a) for a in found])
                + ("" if pair[0] == sda else "   <-- DAO so voi khai bao!"))
        else:
            say("I2C SDA={} SCL={}".format(pair[0], pair[1]), "WARN",
                "khong thay thiet bi nao")
    except Exception as error:
        say("I2C SDA={} SCL={}".format(pair[0], pair[1]), "FAIL", repr(error))


# =========================================================
# 8. Modbus - bon lenh doc, kem danh gia dai hop ly
# =========================================================

rule("8. MODBUS (4 lenh, dung chinh ham cua firmware)")

reads = (
    ("THN  0x01F8", "read_temperature_humidity_noise",
     ("temperature", "humidity", "noise")),
    ("LUX  0x01FE", "read_light", ("light",)),
    ("PM   0x01FB", "read_pm_pressure", ("pm2_5", "pm10", "pressure")),
    ("WIND 0x01F4", "read_wind", ("wind_speed", "wind_direction", "wind_angle")),
)

snapshot = {}

for label, function_name, names in reads:
    try:
        value = firmware[function_name]()
    except Exception as error:
        say(label, "FAIL", repr(error))
        continue

    if value is None:
        say(label, "FAIL", "khong tra loi (timeout / CRC / sai dia chi)")
        continue

    if not isinstance(value, tuple):
        value = (value,)

    parts = []
    suspect = False

    for name, item in zip(names, value):
        snapshot[name] = item
        flag = ""
        if not firmware["sane"](name, item):
            flag = "  <-- NGOAI DAI HOP LY"
            suspect = True
        parts.append("{}={}{}".format(name, item, flag))

    say(label, "WARN" if suspect else "OK", ", ".join(parts))

print()
print("LCD se ve dung nhu duoi day voi so vua doc (ky tu cuoi = trang thai cloud):")

try:
    if firmware_name == "saigon.py" or firmware.get("LCD_COLS") == 16:
        rows = firmware["lcd_lines"](
            snapshot.get("temperature"), snapshot.get("pm2_5"),
            snapshot.get("light"), snapshot.get("wind_speed"),
            snapshot.get("wind_angle"), firmware["LINK_PENDING"])
    else:
        rows = firmware["lcd_lines"](snapshot, firmware["LINK_PENDING"])
    for row in rows:
        print("    |{}|".format(row))
except Exception as error:
    print("    khong dung duoc lcd_lines():", repr(error))


# =========================================================
# 9. CAU HOI 3 - ESP32 nay co nhan WDT(0, timeout) khong
# =========================================================

rule("9. CAU HOI 3/3: machine.WDT(0, {}) co duoc chap nhan khong".format(
    firmware.get("WATCHDOG_TIMEOUT_MS")))

if not TEST_WATCHDOG:
    say("watchdog", "BO QUA", "TEST_WATCHDOG = False o dau file nay")
else:
    print("CANH BAO: WDT bat roi KHONG tat duoc. Neu buoc nay OK, board se tu")
    print("reset sau khoang {} s. Doc xong log thi rut dien.".format(
        firmware.get("WATCHDOG_TIMEOUT_MS", 0) // 1000))
    print()
    try:
        import machine
        wdt = machine.WDT(0, firmware["WATCHDOG_TIMEOUT_MS"])
        wdt.feed()
        say("machine.WDT(0, timeout)", "OK",
            "duoc chap nhan va feed() chay duoc")
    except Exception as error:
        say("machine.WDT(0, timeout)", "FAIL",
            "{!r} -> firmware se chay KHONG co watchdog "
            "(no nuot loi nay va van chay tiep)".format(error))


# =========================================================
# TOM TAT
# =========================================================

rule("TOM TAT")

for label, verdict, detail in results:
    print("  {:6s} {}".format(verdict, label))

counts = {}
for _, verdict, _ in results:
    counts[verdict] = counts.get(verdict, 0) + 1

print()
print("  " + ", ".join("{} {}".format(v, k) for k, v in sorted(counts.items())))
print()
print("Dan TOAN BO log nay ve. Dong nao FAIL la mot lop bao ve khong ton tai")
print("tren board nay - phai sua truoc khi mang tram di xa.")
