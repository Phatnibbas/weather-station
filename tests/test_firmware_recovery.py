"""Kiem chung ca hai firmware tram, chay tren PC.

Nap phan module TRUOC '# MAIN PROGRAM' (vong lap vo han nam sau do), voi
machine/network/requests/ntptime bi stub. Cac ham thuan duoc kiem tra that.

Chay:  py -3 test_firmware.py
"""
import sys
import types
import time as _time
import pathlib
import subprocess

FW = pathlib.Path(__file__).resolve().parent.parent / "firmware"

ok = 0
fail = []


def check(name, cond, detail=""):
    global ok
    if cond:
        ok += 1
    else:
        fail.append("{}  {}".format(name, detail))


# =====================================================================
# 0. Khoi dung chung phai TRUNG TUNG BYTE giua hai file
# =====================================================================
proc = subprocess.run(
    [sys.executable, str(FW / "sync_shared_blocks.py"), "--check"],
    capture_output=True, text=True, encoding="utf-8",
)
check("khoi self-recovery dong bo giua 2 firmware", proc.returncode == 0,
      (proc.stdout or "") + (proc.stderr or ""))


# =====================================================================
# Stub cac module chi co tren board
# =====================================================================
fed = []


class _WDT:
    def __init__(self, *a, **k):
        self.args = (a, k)

    def feed(self):
        fed.append(_time.monotonic())


def make_stubs():
    machine = types.ModuleType("machine")
    machine.WDT = _WDT
    machine.WDT_RESET = 3
    machine.SOFT_RESET = 5
    machine.PWRON_RESET = 1
    machine.reset_cause = lambda: 1
    machine.reset = lambda: (_ for _ in ()).throw(AssertionError("reset!"))
    machine.UART = lambda *a, **k: types.SimpleNamespace(
        any=lambda: 0, read=lambda *_: b"", write=lambda *_: None)
    machine.Pin = lambda *a, **k: None
    machine.I2C = lambda *a, **k: None
    machine.SoftI2C = lambda *a, **k: None

    network = types.ModuleType("network")
    network.STA_IF = 0
    network.WLAN = lambda *a, **k: types.SimpleNamespace(
        active=lambda *_: None, isconnected=lambda: False,
        connect=lambda *_: None, disconnect=lambda: None,
        ifconfig=lambda: ("0", "0", "0", "0"), status=lambda: 0)

    requests = types.ModuleType("requests")
    requests.post = lambda *a, **k: None

    ntptime = types.ModuleType("ntptime")
    ntptime.timeout = 1
    ntptime.settime = lambda: None

    sys.modules["machine"] = machine
    sys.modules["network"] = network
    sys.modules["requests"] = requests
    sys.modules["ntptime"] = ntptime
    return machine


for attr, fn in (
    ("sleep_ms", lambda ms: _time.sleep(ms / 1000.0)),
    ("sleep_us", lambda us: None),
    ("ticks_ms", lambda: int(_time.monotonic() * 1000)),
    ("ticks_add", lambda t, d: t + d),
    ("ticks_diff", lambda a, b: a - b),
):
    setattr(_time, attr, fn)


def load(path):
    text = path.read_text(encoding="utf-8")
    compile(text, str(path), "exec")          # ca file phai compile duoc
    head = text[: text.index("# MAIN PROGRAM")]
    head = head.rsplit("# " + "=" * 57, 1)[0]
    mod = types.ModuleType("fw")
    exec(compile(head, str(path), "exec"), mod.__dict__)
    return mod


# =====================================================================
# Hai tram, cung mot bo yeu cau, hai layout LCD khac nhau
# =====================================================================
STATIONS = [
    {
        "name": "bao_loc",
        "file": "bao_loc.py",
        "cols": 20,
        "rows": 4,
        "lines": lambda fw, s, link: fw.lcd_lines(s, link),
    },
    {
        "name": "saigon",
        "file": "saigon.py",
        "cols": 16,
        "rows": 2,
        "lines": lambda fw, s, link: fw.lcd_lines(
            s.get("temperature"), s.get("pm2_5"), s.get("light"),
            s.get("wind_speed"), s.get("wind_angle"), link),
    },
]

SNAPSHOTS = [
    ("worst", {"temperature": -12.34, "humidity": 100.0, "noise": 120.0,
               "pm2_5": 1000, "pm10": 1000, "pressure": 110.0,
               "light": 200000, "wind_speed": 44.44, "wind_angle": 359.0}),
    ("all-none", {}),
    ("calm", {"temperature": 25.0, "humidity": 80.0, "noise": 40.0,
              "pm2_5": 12, "pm10": 20, "pressure": 90.0,
              "light": 500, "wind_speed": 0.2, "wind_angle": 10.0}),
    ("typical", {"temperature": 25.1, "humidity": 77.0, "noise": 45.0,
                 "pm2_5": 5, "pm10": 15, "pressure": 90.0,
                 "light": 32201, "wind_speed": 1.3, "wind_angle": 217.0}),
]

GROUPS = ["THN", "LUX", "PM", "WIND"]


def dash_dead_groups(s):
    """Ban sao logic deadGroups() cua dashboard."""
    if "FAIL-ALL" in s:
        return list(GROUPS)
    i = s.find("FAIL-")
    if i >= 0:
        return [g for g in s[i + 5:].split("-") if g in GROUPS]
    return []


H = 3600 * 1000

for st in STATIONS:
    tag = st["name"]
    path = FW / st["file"]

    if not path.exists():
        # "bao_loc.py" phai co mat; neu thieu thi day la loi dong goi repo.
        # khong co no. Bo qua em con hon lam do CI vi mot file co y vang mat -
        # nhung phai IN RA, khong duoc im lang, keo lai thanh "test xanh vi
        # khong kiem tra gi ca".
        print("BO QUA %s - khong thay %s" % (tag, path.name))
        continue

    machine = make_stubs()
    fw = load(path)

    # ---- 1. LCD: moi dong <= so cot, ky tu link luon o cuoi ----
    for label, snap in SNAPSHOTS:
        for link in (fw.LINK_OK, fw.LINK_NO_WIFI, fw.LINK_PENDING):
            rows = st["lines"](fw, snap, link)
            check("%s LCD so dong [%s]" % (tag, label), len(rows) == st["rows"])
            for i, r in enumerate(rows):
                check("%s LCD len<=%d [%s/%r] L%d" % (tag, st["cols"], label, link, i + 1),
                      len(r) <= st["cols"], "len=%d %r" % (len(r), r))
            check("%s LCD link o cuoi [%s/%r]" % (tag, label, repr(link)),
                  rows[-1].endswith(link), repr(rows[-1]))

    print("\n=== %s (%dx%d) ===" % (tag, st["cols"], st["rows"]))
    for label in ("typical", "worst", "all-none"):
        snap = dict(SNAPSHOTS)[label]
        link = fw.LINK_OK if label != "all-none" else fw.LINK_NO_WIFI
        print("  %s:" % label)
        for r in st["lines"](fw, snap, link):
            print("    |%s|" % r)

    # ---- 2. build_status tuong thich parser dashboard ----
    for boot_tag in ("", "WDT", "DAILY"):
        fw.BOOT_TAG = boot_tag
        for failed, want in (([], []), (["THN"], ["THN"]),
                             (["PM", "WIND"], ["PM", "WIND"]),
                             (GROUPS, GROUPS)):
            for boot in (True, False):
                s = fw.build_status(failed, 4, boot)
                check("%s BOOT o index 0 [%s]" % (tag, s),
                      (not boot) or s.index("BOOT") == 0, s)
                check("%s deadGroups [%s]" % (tag, s),
                      dash_dead_groups(s) == want, "%s -> %s" % (s, dash_dead_groups(s)))
                check("%s status form-safe [%s]" % (tag, s),
                      all(c.isalnum() or c in "._-" for c in s), s)
    fw.BOOT_TAG = ""

    # ---- 3. watchdog ----
    fw.feed()                       # chua arm -> khong duoc nem
    check("%s feed() truoc arm an toan" % tag, True)
    fed.clear()
    fw._wdt = _WDT()
    t0 = _time.monotonic()
    fw.nap_ms(1200)
    el = _time.monotonic() - t0
    check("%s nap_ms ngu du lau" % tag, 1.15 <= el <= 1.7, "%.2fs" % el)
    check("%s nap_ms vo watchdog >=3 lan" % tag, len(fed) >= 3, str(len(fed)))
    fw._wdt = None

    # ---- 4. reset_cause_tag ----
    for cause, want in ((1, ""), (3, "WDT"), (5, "DAILY")):
        machine.reset_cause = (lambda c: (lambda: c))(cause)
        check("%s reset_cause_tag(%d)" % (tag, cause), fw.reset_cause_tag() == want)
    machine.reset_cause = lambda: (_ for _ in ()).throw(RuntimeError("n/a"))
    check("%s reset_cause_tag chiu port thieu" % tag, fw.reset_cause_tag() == "")

    # ---- 5. reset nua dem + chan reboot loop ----
    def at_local(h, m, s, _fw=fw):
        tod = h * 3600 + m * 60 + s
        _fw._clock_ok = True
        _fw.epoch_s = lambda: (tod - _fw.TIMEZONE_OFFSET_S) % 86400 + 86400 * 9000
        return tod

    at_local(0, 0, 30)
    check("%s local_seconds_of_day" % tag, fw.local_seconds_of_day() == 30)
    check("%s local_clock_text" % tag, fw.local_clock_text() == "00:00:30")
    check("%s CHAN REBOOT LOOP: uptime 30 s -> khong reset" % tag,
          fw.should_restart(30 * 1000) is False)
    check("%s CHAN REBOOT LOOP: uptime 1.99 h -> khong reset" % tag,
          fw.should_restart(int(1.99 * H)) is False)
    check("%s 00:00:30 + uptime 3 h -> reset" % tag, fw.should_restart(3 * H) is True)
    at_local(0, 4, 59)
    check("%s 00:04:59 con trong cua so -> reset" % tag, fw.should_restart(3 * H) is True)
    at_local(0, 5, 1)
    check("%s 00:05:01 ngoai cua so -> khong reset" % tag, fw.should_restart(3 * H) is False)
    at_local(12, 0, 0)
    check("%s giua trua -> khong reset" % tag, fw.should_restart(48 * H) is False)
    at_local(23, 59, 59)
    check("%s 23:59:59 -> khong reset" % tag, fw.should_restart(3 * H) is False)

    fw._clock_ok = False
    check("%s khong NTP: 23 h -> chua reset" % tag, fw.should_restart(23 * H) is False)
    check("%s khong NTP: 24 h -> reset (fallback)" % tag, fw.should_restart(24 * H) is True)
    check("%s khong NTP: local_seconds None" % tag, fw.local_seconds_of_day() is None)

    fw.DAILY_RESTART_ENABLED = False
    at_local(0, 0, 30)
    check("%s tat han -> khong bao gio reset" % tag, fw.should_restart(99 * H) is False)
    fw.DAILY_RESTART_ENABLED = True

    # ---- 6. hang so hop le ----
    check("%s WDT > tran HTTP" % tag,
          fw.WATCHDOG_TIMEOUT_MS > fw.HTTP_TIMEOUT_S * 1000)
    check("%s MIN_UPTIME < FALLBACK" % tag,
          fw.MIN_UPTIME_BEFORE_RESTART_MS < fw.FALLBACK_RESTART_MS)
    check("%s FALLBACK trong tam ticks_diff" % tag, fw.FALLBACK_RESTART_MS < 2 ** 29)
    check("%s cua so reset > 3 chu ky" % tag,
          fw.DAILY_RESTART_WINDOW_MS > fw.SENSOR_INTERVAL_MS * 3)
    check("%s wifi worst case <= 8 s" % tag,
          fw.WIFI_RETRIES * fw.WIFI_TIMEOUT_MS <= 8000,
          "%d ms" % (fw.WIFI_RETRIES * fw.WIFI_TIMEOUT_MS))
    check("%s http_post ton tai" % tag, callable(fw.http_post))

print("\n%d PASS, %d FAIL" % (ok, len(fail)))
for f in fail:
    print("  FAIL:", f)
sys.exit(1 if fail else 0)
