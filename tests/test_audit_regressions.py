"""SO CAI - cac phat hien cua ban ra soat 2026-08-30 ve FIRMWARE.

Xem docs/AUDIT-2026-08-30.md de biet chi tiet tung muc.

BO TEST NAY DO CO CHU Y. Moi muc con OPEN la mot loi CHUA sua. Sua xong thi no
tu chuyen sang FIXED. Khi tat ca FIXED, file nay xanh va tro thanh test chong
tai phat - dung xoa no di sau khi sua.

Khong can board, khong can mang.

Chay:  py -3 tests/test_audit_regressions.py
"""

import pathlib
import re
import sys
import types
import time as _time

ROOT = pathlib.Path(__file__).resolve().parent.parent
FW = ROOT / "firmware"
DOCS = ROOT / "docs"

FINDINGS = []


def finding(fid, title):
    def wrap(fn):
        FINDINGS.append((fid, title, fn))
        return fn
    return wrap


# ---------------------------------------------------------------------------
# Nap firmware tren PC: stub cac module chi co tren board, cat truoc vong lap.
# ---------------------------------------------------------------------------
for _attr, _fn in (
    ("sleep_ms", lambda ms: None),
    ("sleep_us", lambda us: None),
    ("ticks_ms", lambda: 0),
    ("ticks_add", lambda t, d: t + d),
    ("ticks_diff", lambda a, b: a - b),
):
    setattr(_time, _attr, _fn)


def _stub_board():
    machine = types.ModuleType("machine")
    machine.WDT = lambda *a, **k: None
    machine.WDT_RESET, machine.SOFT_RESET = 3, 5
    machine.reset_cause = lambda: 1
    machine.reset = lambda: None
    machine.UART = lambda *a, **k: types.SimpleNamespace(
        any=lambda: 0, read=lambda *_: b"", write=lambda *_: None)
    machine.Pin = machine.I2C = machine.SoftI2C = lambda *a, **k: None

    network = types.ModuleType("network")
    network.STA_IF = 0
    network.WLAN = lambda *a, **k: types.SimpleNamespace(
        active=lambda *_: None, isconnected=lambda: False, connect=lambda *_: None,
        disconnect=lambda: None, ifconfig=lambda: ("0",) * 4, status=lambda: 0)

    requests = types.ModuleType("requests")
    requests.post = lambda *a, **k: None

    ntptime = types.ModuleType("ntptime")
    ntptime.timeout = 1
    ntptime.settime = lambda: None

    sys.modules.update(machine=machine, network=network,
                       requests=requests, ntptime=ntptime)


def load(name):
    """Nap phan module cua mot firmware (truoc '# MAIN PROGRAM')."""
    _stub_board()
    path = FW / name
    text = path.read_text(encoding="utf-8")
    head = text[: text.index("# MAIN PROGRAM")].rsplit("# " + "=" * 57, 1)[0]
    mod = types.ModuleType("fw_" + name)
    # Firmware in canh bao ra stdout khi thieu station_secrets.py - dung y,
    # nhung o day chi lam ban ket qua, nen nuot lai.
    buf, sys.stdout = sys.stdout, open(__import__("os").devnull, "w", encoding="utf-8")
    try:
        exec(compile(head, str(path), "exec"), mod.__dict__)
    finally:
        sys.stdout.close()
        sys.stdout = buf
    return mod


def source(name):
    return (FW / name).read_text(encoding="utf-8")


# Gia tri toi da mot khung Modbus DUNG CRC van co the mang: thanh ghi u16 day.
# Firmware chia 10 cho ap suat / tieng on / toc do gio, nen 65535/10 = 6553.5.
GLITCH = {
    "temperature": 25.0, "humidity": 50.0, "noise": 6553.5,
    "pm2_5": 65535, "pm10": 65535, "pressure": 6553.5,
    "light": 4294967295, "wind_speed": 6553.5, "wind_angle": 65535,
}


def lcd_rows(fw, name, snap, link):
    if name == "saigon.py":
        return fw.lcd_lines(snap["temperature"], snap["pm2_5"], snap["light"],
                            snap["wind_speed"], snap["wind_angle"], link)
    return fw.lcd_lines(snap, link)


@finding("B1", "LCD khong duoc cat giua mot con so, va khong duoc nuot ky tu bao trang thai")
def b1():
    broken = []
    for name in ("bao_loc.py", "saigon.py"):
        fw = load(name)
        for link in (fw.LINK_OK, fw.LINK_NO_WIFI):
            rows = lcd_rows(fw, name, GLITCH, link)
            if not rows[-1].endswith(link):
                broken.append("%s: mat ky tu %r o dong cuoi -> |%s|"
                              % (name, link, rows[-1]))
            for row in rows:
                if len(row) > fw.LCD_COLS:
                    broken.append("%s: tran cot -> |%s| (%d)" % (name, row, len(row)))
    return broken, ("; ".join(broken[:3]) if broken
                    else "gia tri u16 day van giu duoc bo cuc va ky tu trang thai")


@finding("B2", "Chuoi hien tren LCD khong duoc gan cung Channel ID")
def b2():
    hits = []
    for name in ("bao_loc.py", "saigon.py"):
        text = source(name)
        match = re.search(r"^CHANNEL_ID\s*=\s*(\d+)", text, re.M)
        if not match:
            hits.append("%s: khong tim thay CHANNEL_ID" % name)
            continue
        cid = match.group(1)
        for lit in re.findall(r'"[^"\n]*"', text):
            if cid in lit:
                hits.append("%s: %s" % (name, lit))
    return hits, ("; ".join(hits) if hits
                  else "moi cho hien channel deu lay tu CHANNEL_ID")


@finding("B3", "Hai firmware phai co cung cong tac debug tai cho (CLOUD_UPLOAD_ENABLED)")
def b3():
    missing = []
    for name in ("bao_loc.py", "saigon.py"):
        text = source(name)
        declared = re.search(r"^CLOUD_UPLOAD_ENABLED\s*=", text, re.M) is not None
        mentioned = "CLOUD_UPLOAD_ENABLED" in text
        if mentioned and not declared:
            missing.append("%s: nhac CLOUD_UPLOAD_ENABLED nhung KHONG khai bao "
                           "-> LINK_OFF la code chet, khong tat duoc upload de debug" % name)
        elif not declared:
            missing.append("%s: khong co CLOUD_UPLOAD_ENABLED" % name)
    return missing, ("; ".join(missing) if missing
                     else "ca hai firmware deu tat duoc upload de debug tai tram")


@finding("B4", "Khong con tro toi ten file cu 'siuuuu.py'")
def b4():
    # Chi quet noi RA LENH cho nguoi dung: firmware va README. `docs/` la bien
    # ban lich su - postmortem 2026-07-22 va ban ra soat deu PHAI nhac ten file
    # cu de ke lai chuyen da xay ra, do la ban ghi dung chu khong phai tham
    # chieu chet. Bat ca docs se bien test nay thanh thu phat nguoi ghi su.
    stale = []
    for path in sorted(FW.glob("*.py")) + [ROOT / "README.md"]:
        if path.name == "station_secrets.py":       # gitignore, khong thuoc repo
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "siuuuu" in line:
                stale.append("%s:%d" % (path.relative_to(ROOT).as_posix(), i))
    return stale, ("; ".join(stale) if stale
                   else "khong con huong dan nao tro toi ten file da doi")


@finding("B5", "Cau 'DO TRAN BOARD THAT' phai noi ro do tren BOARD NAO")
def b5():
    post = (DOCS / "ESP32_HTTPS_TLS_POSTMORTEM_2026-07-22.md").read_text(encoding="utf-8")
    # Postmortem ghi runtime la ESP32_GENERIC va file la siuuuu.py -> tram Sai Gon
    # (ESP32-WROOM). Bao Loc chay ESP32-S3, mot con chip khac.
    measured_on_wroom = "ESP32_GENERIC" in post
    bad = []
    for name in ("bao_loc.py", "saigon.py"):
        text = source(name)
        for i, line in enumerate(text.splitlines(), 1):
            if "BOARD TH" in line.upper() and "2026-07-22" in line:
                window = "\n".join(text.splitlines()[i - 1:i + 8])
                names_board = re.search(r"WROOM|ESP32_GENERIC|Sai Gon|Sài Gòn", window)
                if not names_board:
                    bad.append("%s:%d neu 'do tren board that' ma khong noi board nao" % (name, i))
    if bad and not measured_on_wroom:
        bad.append("(khong xac minh duoc board tu postmortem)")
    return bad, ("; ".join(bad) if bad
                 else "moi trich dan phep do deu ghi ro board da do")


def main():
    print("SO CAI FIRMWARE - ban ra soat 2026-08-30\n")
    open_count = 0
    for fid, title, fn in FINDINGS:
        try:
            problems, evidence = fn()
        except Exception as error:                  # noqa: BLE001 - probe hong = con OPEN
            problems, evidence = [1], "probe nem loi: %r" % (error,)
        is_open = bool(problems)
        open_count += is_open
        print("  [%s] %s  %s" % ("OPEN " if is_open else "FIXED", fid, title))
        print("           %s\n" % evidence)
    print("%d FIXED, %d OPEN" % (len(FINDINGS) - open_count, open_count))
    if open_count:
        print("\nBo test nay do la DUNG cho toi khi cac muc tren duoc sua.")
    return 1 if open_count else 0


if __name__ == "__main__":
    sys.exit(main())
