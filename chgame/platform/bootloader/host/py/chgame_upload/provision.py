"""Factory provisioning and recovery through the WCH factory ISP.

This is the ONLY path that uses the BOOT button, and it exists for exactly two
situations: the first flash of a blank device, and recovery from a damaged
bootloader. Everything else goes over USB CDC with no driver and no button.

It is wired to Arduino's standard mechanisms rather than a bespoke workflow:

    Tools -> Burn Bootloader          -> bootloader only
    Sketch -> Upload Using Programmer -> bootloader + this sketch, in one write

Both require the device to already be in factory ISP mode, which on this board
means holding BOOT across a power cycle (BOOT pulls USB D+ high through R10 and
the part samples it at reset). See docs/recovery.md.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
from typing import Callable

from .chg import board_name
from .image import boot_image_board, build_image, check_boot_board, trim


class WchispNotFound(Exception):
    pass


def find_wchisp(explicit: str | None = None) -> str:
    """Locate wchisp.

    Order: explicit argument, CHGAME_WCHISP, PATH. The board package declares
    wchisp as a tool dependency and names its path in the recipe, so this
    normally succeeds on the first entry.
    """
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("CHGAME_WCHISP"):
        candidates.append(os.environ["CHGAME_WCHISP"])
    found = shutil.which("wchisp") or shutil.which("wchisp.exe")
    if found:
        candidates.append(found)

    for c in candidates:
        if not c:
            continue
        cand = pathlib.Path(c)
        if cand.is_file():
            return str(cand)
        # Arduino recipes may hand us a name without the platform extension.
        exe = cand.with_name(cand.name + ".exe")
        if exe.is_file():
            return str(exe)
    raise WchispNotFound(
        "wchisp not found. It ships with this board package; if you are running the tool standalone, "
        "set CHGAME_WCHISP to its full path.\n"
        "It is needed only for the first flash of a blank board and for recovery; normal uploads do not use it.")


BOOT_HELP = """no device is in factory ISP mode.

  1. Hold the BOOT button down.
  2. Switch the power OFF, then ON, while still holding BOOT.
  3. Release BOOT.
  4. Try again.

  BOOT must be held ACROSS the power cycle: the chip samples it only at reset,
  so pressing it while the board is already running does nothing."""


SEVERAL_HELP = """wchisp finds {n} devices in factory ISP mode ({names}).

  Provisioning erases and writes the whole chip, and wchisp would pick one of
  them by itself. Leave only the board to provision in ISP mode (unplug or
  power off the others) and try again."""


def devices_in(output: str) -> list[str]:
    """The devices `wchisp probe` lists, as it names them ("0: CH32X035G8U6[0x5623]").

    Keyed on the POSITIVE signal - a "Device #" line - rather than on error
    wording. wchisp changed "Found 0 devices" to "Found 0 USB devices" between
    0.2.3 and 0.3.0, and matching the failure text meant a missing device
    sailed past this check and surfaced later as a raw wchisp error instead of
    the instruction the user actually needs.
    """
    return [line.split("Device #", 1)[1].strip() for line in output.splitlines() if "Device #" in line]


_UID = re.compile(r"Chip UID:\s*([0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2})+)")


def uid_in(output: str) -> str | None:
    """The chip's unique ID in `wchisp info`'s output ("CD-AB-88-D8-60-BE-B5-42",
    in capitals), or None if it names none."""
    m = _UID.search(output)
    return m.group(1).upper() if m else None


def probe(wchisp: str) -> str:
    """Confirm exactly one device is in factory ISP mode, and name it."""
    r = subprocess.run([wchisp, "probe"], capture_output=True, text=True)
    found = devices_in(r.stdout + r.stderr)
    if not found:
        raise RuntimeError(BOOT_HELP)
    if len(found) > 1:
        raise RuntimeError(SEVERAL_HELP.format(n=len(found), names=", ".join(found)))
    return found[0]


def chip_uid(wchisp: str) -> str | None:
    """The chip's unique ID as `wchisp info` reports it, or None."""
    try:
        r = subprocess.run([wchisp, "info"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return uid_in(r.stdout + r.stderr)


def provision(boot_path: pathlib.Path, app_path: pathlib.Path | None = None,
              wchisp: str | None = None, app_version: int = 0, *, device: str | None = None,
              ask: Callable[[str], bool] | None = None) -> None:
    """Write the bootloader (and a sketch) through the factory ISP. `device`,
    the board picked, refuses a bootloader image built for another before
    anything else (ValueError); the ROM knows nothing of boards, so this
    catches a wrong image, not a wrong board. `ask`, when given (the
    standalone provision command; burn never asks), is asked before the chip
    is erased: no stops with RuntimeError. Mirrors the Go tool's provision."""
    boot = boot_path.read_bytes()
    try:
        check_boot_board(boot, device)
    except ValueError as e:
        raise ValueError(f"{boot_path}: {e}") from e
    app = app_path.read_bytes() if app_path else None
    board = board_name(boot_image_board(boot))

    tool = find_wchisp(wchisp)
    print(f"wchisp      : {tool}")
    print(f"device      : {probe(tool)}")
    uid = chip_uid(tool)
    print(f"chip UID    : {uid}" if uid else "chip UID    : not reported by wchisp")
    print(f"bootloader  : {boot_path.name}  ({len(boot)} bytes, for {board})")
    if app is not None:
        print(f"application : {app_path.name}  ({len(app)} bytes)")
    else:
        print("application : none - the device will come up in the bootloader,")
        print("              enumerate as a COM port, and wait for a normal upload")

    image = trim(build_image(boot, app, app_version))

    if ask is not None:
        print(f"This erases the whole chip and writes a bootloader for {board}.")
        print("The factory ISP cannot see which board the chip is on: check that it is")
        print("that board (another board's bootloader drives the wrong pins).")
        if not ask("erase and write? [y/N] "):
            raise RuntimeError("not confirmed: nothing was erased (-yes provisions without asking)")

    # FULL CHIP ERASE FIRST. wchisp flash erases only the sectors it is about to
    # write. Provisioning a bootloader-only image would leave the previous
    # application AND its metadata page intact, and the fresh bootloader would
    # then do what it is designed to do: find metadata that still checksums and
    # launch the stale application, so Burn Bootloader appeared to do nothing.
    # Doing the erase here rather than in Arduino's separate erase recipe means
    # every provisioning path gets it, Upload Using Programmer included.
    print("erasing     : whole code flash")
    r = subprocess.run([tool, "erase"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"wchisp erase failed:\n{r.stdout + r.stderr}")

    with tempfile.TemporaryDirectory() as td:
        blob = pathlib.Path(td) / "chgame_provision.bin"
        blob.write_bytes(image)
        r = subprocess.run([tool, "flash", str(blob)], capture_output=True, text=True)
        out = r.stdout + r.stderr
        if r.returncode != 0 or "Verify OK" not in out:
            raise RuntimeError(f"wchisp failed:\n{out}")

    print(f"written     : {len(image)} bytes, verified")
    print("done        - the BOOT button is not needed again; use Upload from here on")
