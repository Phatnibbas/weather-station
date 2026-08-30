"""Đồng bộ các khối self-recovery dùng chung giữa những file firmware trạm.

VÌ SAO CÓ FILE NÀY
------------------
Mỗi trạm là MỘT file MicroPython tự chứa. Đó là chủ ý: board ở xa, không có
laptop tại chỗ, nên "upload đúng một file" là quy trình ít sai nhất. Cái giá
phải trả là phần self-recovery bị lặp ở mọi file — và một bản vá watchdog chỉ
sửa ở một nơi sẽ âm thầm để trạm còn lại không được bảo vệ, mà không gì báo.

Script này biến bản sao đó thành thứ sinh ra được, và test đi kèm khoá lại:
`--check` fail nếu hai bản lệch nhau dù chỉ một byte.

DÙNG
----
    py -3 firmware/sync_shared_blocks.py           # ghi lại các target
    py -3 firmware/sync_shared_blocks.py --check   # chỉ kiểm tra, không ghi

Sửa khối dùng chung trong SOURCE (`bao_loc.py`) rồi chạy lệnh trên.
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent

SOURCE = HERE / "bao_loc.py"
TARGETS = [HERE / "saigon.py"]

# Tên khối -> (marker mở, marker đóng). Marker là dòng nguyên vẹn.
BLOCKS = (
    "SHARED-SELF-RECOVERY-CONFIG",
    "SHARED-SELF-RECOVERY-CODE",
    "SHARED-SENSOR-PLAUSIBILITY",
)


def read(path):
    # newline="" để giữ nguyên kiểu xuống dòng; script này không được phép
    # lặng lẽ đổi CRLF/LF của file firmware.
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def markers(name):
    return (
        "# ========== {} BEGIN ==========".format(name),
        "# ========== {} END ==========".format(name),
    )


def extract(text, name, origin):
    """Nội dung GIỮA hai marker, không gồm chính hai dòng marker."""

    begin, end = markers(name)

    if text.count(begin) != 1 or text.count(end) != 1:
        raise SystemExit(
            "{}: cần đúng một cặp marker {} (thấy {} BEGIN, {} END)".format(
                origin, name, text.count(begin), text.count(end)
            )
        )

    start = text.index(begin) + len(begin)
    stop = text.index(end)

    if stop < start:
        raise SystemExit("{}: marker {} bị đảo thứ tự".format(origin, name))

    return text[start:stop]


def replace(text, name, body, origin):
    begin, end = markers(name)
    before = extract(text, name, origin)
    return text.replace(begin + before + end, begin + body + end, 1)


def main():
    check_only = "--check" in sys.argv
    source = read(SOURCE)
    bodies = {name: extract(source, name, SOURCE.name) for name in BLOCKS}

    drifted = []

    for target in TARGETS:
        original = read(target)
        updated = original

        for name in BLOCKS:
            current = extract(updated, name, target.name)

            if current != bodies[name]:
                drifted.append("{} :: {}".format(target.name, name))

            updated = replace(updated, name, bodies[name], target.name)

        if updated == original:
            print("OK    {} - da khop {}".format(target.name, SOURCE.name))
            continue

        if check_only:
            print("LECH  {}".format(target.name))
            continue

        write(target, updated)
        print("GHI   {} - da dong bo tu {}".format(target.name, SOURCE.name))

    if check_only and drifted:
        print()
        print("Khoi dung chung bi lech:")

        for item in drifted:
            print("  -", item)

        print()
        print("Chay:  py -3 firmware/sync_shared_blocks.py")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
