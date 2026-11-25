"""The protocol's shared test vectors: what the Python uploader computes,
written down so the Go tool (host/go/*_test.go) and the Python tests
(test/protocol/test_vectors.py) check the same frames, checksums, image
rules and layout.

    python -m chgame_upload.vectors --write platform/bootloader/test/protocol/vectors.json
    python -m chgame_upload.vectors --check platform/bootloader/test/protocol/vectors.json

Regenerate the file when the protocol or the layout changes (and update
platform/board/docs/protocol.md); --check is what the test suite runs, so a
stale file fails rather than drifting. Everything binary is hex.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import struct
import sys
from pathlib import Path

from . import __version__
from . import chg as C
from . import image as I
from . import layout as L
from . import protocol as P
from . import provision as W
from . import upload as U

SAMPLE_HELLO = bytes([P.ST_OK, 1, P.MODE_BOOTLOADER, 0]) + struct.pack("<HIIHH", 2, L.APP_START, L.APP_MAX_SIZE, 256, 56) \
    + bytes(range(0xA0, 0xAC))


def generate() -> dict:
    crc_cases = [b"", b"123456789", SAMPLE_HELLO[:4], bytes((i * 7) & 0xFF for i in range(516))]
    frames = [
        (P.CMD_HELLO, b""), (P.CMD_STATUS, b""),
        (P.CMD_BEGIN, struct.pack("<II", 0x2000, 0xDEADBEEF)),
        (P.CMD_WRITE, struct.pack("<I", 0x100) + bytes(range(32))),
        (P.CMD_END, b""), (P.CMD_RUN, b""), (P.CMD_ABORT, b""),
        (P.CMD_READ, struct.pack("<IH", L.APP_START, 55)),
        (P.CMD_DEV_UNLOCK, struct.pack("<I", U.DEV_KEY)),
        (P.CMD_DEV_WRITE_BOOT, struct.pack("<II", 0x2A00, 0x01020304)),
    ]
    h = P.Hello.parse(SAMPLE_HELLO)
    bad_status = bytes([0x02]) + SAMPLE_HELLO[1:]
    boot_cases = {
        "small": bytes(255),
        "ok_min": bytes(256),
        "ok_vector0": bytes(4) + struct.pack("<I", 0) + bytes(1000),
        "big": bytes(L.BOOT_SIZE + 4),
        "sketch": bytes(4) + struct.pack("<I", L.APP_START) + bytes(300),
        "other": bytes(4) + struct.pack("<I", 0x08000000) + bytes(300),
    }
    app = bytes(((i * 31) + 7) & 0xFF for i in range(1000))
    boot = bytes(((i * 13) + 5) & 0xFF for i in range(2000))
    boot = boot[:4] + struct.pack("<I", 0) + boot[8:]
    img = I.trim(I.build_image(boot, app))
    return {
        "version": __version__,
        "crc16": [{"data": d.hex(), "crc": P.crc16(d)} for d in crc_cases],
        "frames": [{"cmd": c, "payload": p.hex(), "frame": P.build_frame(c, p).hex()} for c, p in frames],
        "frame_too_big": {"cmd": P.CMD_WRITE, "payload_len": P.MAX_PAYLOAD + 1},
        "hello": {
            "payload": SAMPLE_HELLO.hex(),
            "fields": {"proto_version": h.proto_version, "mode": h.mode, "app_state": h.app_state,
                       "boot_version": h.boot_version, "app_start": h.app_start, "app_max_size": h.app_max_size,
                       "page_size": h.page_size, "max_payload": h.max_payload, "uid": h.uid.hex()},
            "bad_status": {"payload": bad_status.hex(), "status": 0x02},
            "short": {"payload": SAMPLE_HELLO[:29].hex()},
        },
        "chunk_size": [{"max_payload": m, "page": 256, "chunk": U.chunk_size(m, 256)} for m in (56, 64, 260, 512, 1028)],
        "pad_to_word": [{"len": n, "padded": len(U.pad_to_word(bytes(n)))} for n in (0, 1, 3, 4, 5, 50943)],
        "boot_image": [{"name": k, "image": v.hex(), "verdict": _verdict(v)} for k, v in boot_cases.items()],
        "metadata": {"app": app.hex(), "page": I.build_metadata(app).hex()},
        "image": {"boot": boot.hex(), "app": app.hex(), "length": len(img),
                  "sha256": hashlib.sha256(img).hexdigest()},
        "layout": L.as_dict(),
        "chg": _chg_cases(),
        "board": _board_cases(),
        "wchisp": _wchisp_cases(),
        "platform_txt": _recipe_cases(),
    }


# The board package's recipes that run this tool
# (platform/board/arduino/CHGame/platform.txt), word for word. Both tools
# must take the command lines Arduino makes of them, so they are part of the
# vectors: the tests check platform.txt says exactly this and parse the
# expansions below. Change them here and in platform.txt together.
RECIPES = {
    "recipe.hooks.objcopy.postobjcopy.1.pattern":
        '"{tools.chgame_upload.path}/{tools.chgame_upload.cmd}" pack -device {build.chgame_device} '
        '"{build.path}/{build.project_name}.bin"',
    "tools.chgame_upload.upload.pattern":
        '"{path}/{cmd}" {upload.verbose} -port "{serial.port}" flash -device {build.chgame_device} '
        '"{build.path}/{build.project_name}.bin" -run',
    "tools.chgame_upload.bootloader.pattern":
        '"{path}/{cmd}" {bootloader.verbose} {burn.port} burn -method {burn.method} -device {build.chgame_device} '
        '-wchisp "{tools.chgame_upload.wchisp}" -bootloader "{runtime.platform.path}/bootloaders/{bootloader.file}"',
    "tools.chgame_upload.program.pattern":
        '"{path}/{cmd}" {program.verbose} {burn.port} burn -method {burn.method} -device {build.chgame_device} '
        '-wchisp "{tools.chgame_upload.wchisp}" -bootloader "{runtime.platform.path}/bootloaders/{bootloader.file}" '
        '-app "{build.path}/{build.project_name}.bin"',
}
# What Arduino puts in for each property (a build folder with a space in it;
# {burn.port} is the programmer's own text, with a property inside).
EXPAND = {
    "tools.chgame_upload.path": "T", "tools.chgame_upload.cmd": "chgame-upload", "path": "T", "cmd": "chgame-upload",
    "upload.verbose": "-verbose", "bootloader.verbose": "-quiet", "program.verbose": "-quiet",
    "serial.port": "COM7", "burn.port": '-port "{serial.port}"', "build.path": "B dir", "build.project_name": "X.ino",
    "build.chgame_device": "rev1", "tools.chgame_upload.wchisp": "W/wchisp.exe", "runtime.platform.path": "P",
    "bootloader.file": "CHGame/rev1/chgame_sdboot.bin",
}


def _expand(pattern: str, extra: dict) -> list[str]:
    """The command line Arduino runs for a recipe (its words, without the program)."""
    props = {**EXPAND, **extra}
    while "{" in pattern:
        pattern = re.sub(r"\{([^{}]+)\}", lambda m: props[m.group(1)], pattern)
    return shlex.split(pattern)[1:]


def _recipe_cases() -> dict:
    """platform.txt's recipes, and what each tool must make of them: the verb,
    its file, and the flags (unnamed ones as they are when absent)."""
    image, boot = "B dir/X.ino.bin", "P/bootloaders/CHGame/rev1/chgame_sdboot.bin"
    plain = {"port": "", "verbose": False, "quiet": False, "positional": [], "run": False, "device": "",
             "method": "usb", "wchisp": "", "bootloader": "", "app": ""}
    cases = []
    for key, extra, want in (
            ("recipe.hooks.objcopy.postobjcopy.1.pattern", {},
             {"cmd": "pack", "positional": [image], "device": "rev1"}),
            ("tools.chgame_upload.upload.pattern", {},
             {"cmd": "flash", "port": "COM7", "verbose": True, "positional": [image], "run": True, "device": "rev1"}),
            ("tools.chgame_upload.bootloader.pattern", {"burn.method": "usb"},
             {"cmd": "burn", "port": "COM7", "quiet": True, "method": "usb", "device": "rev1",
              "wchisp": "W/wchisp.exe", "bootloader": boot}),
            ("tools.chgame_upload.bootloader.pattern", {"burn.method": "isp"},
             {"cmd": "burn", "port": "COM7", "quiet": True, "method": "isp", "device": "rev1",
              "wchisp": "W/wchisp.exe", "bootloader": boot}),
            ("tools.chgame_upload.program.pattern", {"burn.method": "usb"},
             {"cmd": "burn", "port": "COM7", "quiet": True, "method": "usb", "device": "rev1",
              "wchisp": "W/wchisp.exe", "bootloader": boot, "app": image}),
            ("tools.chgame_upload.program.pattern", {"burn.method": "isp"},
             {"cmd": "burn", "port": "COM7", "quiet": True, "method": "isp", "device": "rev1",
              "wchisp": "W/wchisp.exe", "bootloader": boot, "app": image})):
        cases.append({"key": key, "argv": _expand(RECIPES[key], extra), "want": {**plain, **want}})
    return {"recipes": RECIPES, "default_device": "rev0", "cases": cases}


# A board reserved for the tests: none is at present (rev1 was until it was
# defined), so the reserved path is checked with this one patched in.
RESERVED_EXAMPLE = ("rev2", 0x32524743)         # "CGR2"


def _board_cases() -> dict:
    """Which board: the device table, the names shown, HELLO's board field
    (absent on rev0; bytes past it ignored), a bootloader image's board word
    (0 on rev0), and -device against a bootloader image (burn, provision,
    selfupdate)."""
    hellos = [SAMPLE_HELLO, SAMPLE_HELLO + struct.pack("<I", C.TARGET_REV1),
              SAMPLE_HELLO + struct.pack("<I", C.TARGET_REV1) + bytes(range(6))]
    boots = {"rev0": bytes(256), "rev1": bytes(0x14) + struct.pack("<I", C.TARGET_REV1) + bytes(236),
             "short": bytes(0x10),
             "rev0-explicit": bytes(0x14) + struct.pack("<I", C.TARGET_REV0) + bytes(236),
             "unknown": bytes(0x14) + struct.pack("<I", 0x12345678) + bytes(236)}
    checks = []
    for k, v in boots.items():
        for d in ("", *C.DEVICES, "rev9"):
            try:
                I.check_boot_board(v, d)
                ok = True
            except ValueError:
                ok = False
            checks.append({"image": k, "device": d, "ok": ok})
    name, target = RESERVED_EXAMPLE
    C.RESERVED[name] = target
    try:
        reserved = {"device": name, "target": target, "name": C.board_name(target)}
        try:
            C.target_of(name)
            raise AssertionError("a reserved device must be refused")
        except ValueError as e:
            assert "reserved" in str(e), e
    finally:
        del C.RESERVED[name]
    return {
        "devices": C.DEVICES,
        "reserved": C.RESERVED,
        "known": C.known_devices(),
        "names": [{"target": t, "name": C.board_name(t)} for t in (C.TARGET_REV0, C.TARGET_REV1, 0x12345678)],
        "hello": [{"payload": p.hex(), "board": P.Hello.parse(p).board, "reported": P.Hello.parse(p).board_reported}
                  for p in hellos],
        "boot_image": [{"name": k, "image": v.hex(), "board": I.boot_image_board(v)} for k, v in boots.items()],
        "device_check": checks,
        "reserved_example": reserved,
        "packs": [{"device": d, "header": C.pack(bytes(64), "X", device=d)[:C.HEADER_BYTES].hex()} for d in C.DEVICES],
    }


def _wchisp_cases() -> dict:
    """What provision reads from wchisp: the devices `probe` lists (one is
    written to, none or several refused) and the chip UID `info` reports."""
    probes = [
        "Found 0 USB devices\n",
        "Found 1 devices\nDevice #0: CH32X035G8U6[0x5623]\n",
        "14:51:24 [INFO] Found 2 USB devices\n14:51:24 [INFO] Device #0: CH32X035G8U6[0x5623]\n"
        "14:51:24 [INFO] Device #1: CH32X035G8U6[0x5623]\n",
    ]
    infos = [
        "Chip: CH32X035G8U6[0x5623]\nChip UID: CD-AB-88-D8-60-BE-B5-42\nBTVER(bootloader ver): 02.60\n",
        "14:51:24 [INFO] Chip: CH32V307VCT6[0x7017] (Code Flash: 256KiB)\n"
        "14:51:24 [INFO] Chip UID: 30-78-3e-26-3b-38-a9-d6\n",
        "Error: no device\n",
    ]
    return {"probe": [{"output": o, "devices": W.devices_in(o)} for o in probes],
            "info": [{"output": o, "uid": W.uid_in(o) or ""} for o in infos]}


def _chg_cases() -> dict:
    """`pack`: the same package bytes from the same image and fields, the same
    refusals, the same default name and title."""
    app = bytes(((i * 29) + 3) & 0xFF for i in range(1001))     # not a multiple of 4: padded with 0xFF
    packs = []
    for title, author, ver, appver in (("MY GAME", "ME", "1.2", 7), ("FOUR IN A ROW", "", "", 0)):
        pkg = C.pack(app, title, author, ver, appver)
        packs.append({"title": title, "author": author, "version": ver, "app_version": appver,
                      "header": pkg[:C.HEADER_BYTES].hex(), "length": len(pkg),
                      "sha256": hashlib.sha256(pkg).hexdigest()})
    boot_like = bytes(8) + struct.pack("<I", C.BOOT_SIG) + bytes(100)
    return {
        "app": app.hex(),
        "packs": packs,
        "refused": [{"name": "empty", "length": 0}, {"name": "too_big", "length": L.APP_MAX_SIZE + 1},
                    {"name": "bootloader", "image": boot_like.hex()}],
        "max_ok_length": L.APP_MAX_SIZE,
        "names": [{"path": p, "title": C.default_title(p), "out": C.default_output(p)}
                  for p in ("MyGame.ino.bin", "build/CHFour.ino.bin", "x.bin", "Hello")],
    }


def _verdict(image: bytes) -> str:
    try:
        I.check_boot_image(image)
        return "ok"
    except ValueError as e:
        s = str(e)
        if "too small" in s:
            return "small"
        if "over the" in s:
            return "big"
        if "is a sketch" in s:
            return "sketch"
        return "other"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", metavar="FILE")
    g.add_argument("--check", metavar="FILE")
    a = ap.parse_args(argv)
    text = json.dumps(generate(), indent=1) + "\n"
    if a.write:
        Path(a.write).parent.mkdir(parents=True, exist_ok=True)
        Path(a.write).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {a.write}")
        return 0
    have = Path(a.check).read_text(encoding="utf-8")
    if json.loads(have) != json.loads(text):
        print(f"{a.check} is stale: regenerate it with --write (and update docs/protocol.md if the protocol changed)",
              file=sys.stderr)
        return 1
    print(f"{a.check}: up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
