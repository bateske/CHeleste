"""Build, upload and drive a CHGame sketch on the attached board.

    chgame [--board B] build [--debug]                 compile (release by default)
    chgame [--board B] upload [--debug] [--arduino]    compile + flash
    chgame [--board B] run --device SCRIPT OUTDIR      debug build, upload, run a chdrive script
    chgame shot OUT.png                                screenshot of a running debug build

(or `python tools/device.py [--sketch DIR] [--board B] build|upload|run|shot`,
the same without the entry point). The sketch is DIR (a folder, or the name
of a game or app: CHFour, CHSDtoUSB), else the current folder.

The board (BOARDS: chcart.model.DEVICES, spec/chgame.md's device table) is
--board, else $CHGAME_BOARD, else the newest board the installed CHGame core
has (default_board(): the highest rev<n> that `arduino-cli board details`
knows), so the tools default to the most recent board as soon as its board
package is installed. A build goes to <sketch>/build/<board>/release (or
debug): build_dir(). Its FQBN is the sketch's tools/game.py FQBN (or the
release/debug default below) with the board field swapped for the board's
(fqbn()), its options kept. A board the installed core lacks is a clear error.

Builds use the CHGfx, CHGame and CHSd libraries in
platform/board/arduino/CHGame/libraries (the copies the simulator uses
too), and a sketch from another repository the libraries beside its own
(paths.sketch_libraries(): CHPower's repository, say). Both use opt=oslto (Tools > Optimize > "Smallest + LTO": -Os -flto,
about 3.9 KB smaller than plain -Os) and periph=game (the default
Peripherals setting). Release builds add usb=uploadonly (Tools > USB >
"Upload only": compiles out Serial, which release code never uses, but
keeps the 1200-baud upload handshake, so uploading still needs no button
press). Debug builds keep USB Serial, which the debug protocol talks over,
and turn the protocol on with -DCHGAME_DEBUG=1 in build.extra_flags (empty
on this platform). A build ends with tools/check_size.py's report: flash,
the image against the save pages, and RAM. A release build fails when its
image leaves fewer save pages than the sketch's SAVE_PAGES (tools/game.py;
two by default), so a game cannot lose its A/B saves unnoticed.

Uploads go through the Python uploader (platform/bootloader/host/py), which
does the 1200-baud touch, the flash, the verify and the restart itself;
`--arduino` uses `arduino-cli upload` and the board package's Go tool
instead, the path an IDE user takes. `run` and `shot` talk to the sketch
through its tools/chsim/chdrive.py. Needs the CHGame board package 0.2.4+.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))
import paths  # noqa: E402

LIBRARIES = paths.LIBRARIES
# The release and debug options. The board field (rev0 here) is swapped for
# the board a build is for: fqbn().
FQBN_DEBUG = "CHGame:ch32v:rev0:opt=oslto,rtlib=nano,periph=game"
FQBN_RELEASE = FQBN_DEBUG + ",usb=uploadonly"


def _devices():
    """chcart.model.DEVICES. This module is imported from many places (tools/
    on sys.path or not, chcart importing it back), so: the package, else
    model.py by its path, else rev0 alone."""
    try:
        from chcart.model import DEVICES
        return DEVICES
    except Exception:                       # noqa: BLE001 (any failure: fall back)
        pass
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_chcart_model", REPO / "tools" / "chcart" / "model.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.DEVICES
    except Exception:                       # noqa: BLE001
        return {"rev0": type("Device", (), {"fqbn": "CHGame:ch32v:rev0"})()}


DEVICES = _devices()
BOARDS = list(DEVICES)                      # the boards there are, in the table's order (oldest first)


def _rev(board):
    m = re.fullmatch(r"rev(\d+)", board)
    return int(m.group(1)) if m else -1


_installed = {}
_reported = set()
_no_cli = []                                # [True] once arduino-cli could not be started


def installed(board):
    """Whether the installed CHGame core has this board (`arduino-cli board
    details`; asked once per board per process). False too when arduino-cli
    is not there at all (not_installed() says which)."""
    if board not in _installed:
        ok = False
        if board in DEVICES:
            try:
                r = subprocess.run(["arduino-cli", "board", "details", "-b", DEVICES[board].fqbn, "--format", "json"],
                                   capture_output=True, text=True, timeout=120)
                ok = r.returncode == 0 and "error" not in json.loads(r.stdout or "{}")
            except OSError:
                _no_cli[:] = [True]         # no arduino-cli on PATH
            except (ValueError, subprocess.TimeoutExpired):
                ok = False                  # no answer: not installed
        _installed[board] = ok
    return _installed[board]


def installed_boards(boards=None, log=print):
    """The boards of `boards` (default: every one, oldest first) that the
    installed core has. Each one it lacks is reported once per process:
    "rev1: skipped (the installed core has no rev1)"."""
    out = []
    for b in (boards or BOARDS):
        if installed(b):
            out.append(b)
        elif b not in _reported:
            _reported.add(b)
            if log:
                log(f"{b}: skipped (the installed core has no {b})")
    return out


def default_board():
    """$CHGAME_BOARD if set, else the newest board (highest rev<n>) the
    installed core has, else rev0."""
    env = os.environ.get("CHGAME_BOARD")
    if env:
        if env not in DEVICES:
            raise SystemExit(f"CHGAME_BOARD={env}: not a board (the boards: {', '.join(BOARDS)})")
        return env
    for b in sorted(BOARDS, key=_rev, reverse=True):
        if installed(b):
            return b
    return "rev0"


def for_boards(sketch):
    """The boards a sketch is for: its tools/game.py's BOARDS, else every one."""
    import gamecfg
    return tuple(gamecfg.load(paths.sketch(sketch)).BOARDS or BOARDS)


def sketch_boards(sketch, boards):
    """`boards` less those the sketch is not for (tools/game.py's BOARDS)."""
    mine = for_boards(sketch)
    return [b for b in boards if b in mine]


def _board(board, sketch=None):
    """`board`, or the default: default_board(), or for a sketch made for
    some boards alone (BOARDS) the newest of those the core has. A sketch
    is never built for a board it is not for."""
    mine = for_boards(sketch) if sketch is not None else BOARDS
    if not board:
        board = default_board()
        if board not in mine and not os.environ.get("CHGAME_BOARD"):
            board = next((b for b in sorted(mine, key=_rev, reverse=True) if installed(b)), mine[-1])
    if board not in DEVICES:
        raise SystemExit(f"{board}: not a board (the boards: {', '.join(BOARDS)})")
    if board not in mine:
        raise SystemExit(f"{paths.sketch(sketch).name} is for {', '.join(mine)} alone, not {board} "
                         "(its tools/game.py's BOARDS)")
    return board


def not_installed(board):
    """The message for a board the installed core lacks (or for no
    arduino-cli at all)."""
    if _no_cli:
        return (f"cannot build for {board}: arduino-cli is not on PATH "
                "(install it and the CHGame board package: CLAUDE.md, Setup)")
    if _rev(board) > min(map(_rev, BOARDS)) and installed(min(BOARDS, key=_rev)):
        return (f"the installed CHGame core has no {board}: install board package 0.4.0 or later, "
                f"or pass --board {min(BOARDS, key=_rev)}")
    return (f"the installed CHGame core has no {board}: install the CHGame board package "
            "(arduino-cli core install CHGame:ch32v; CLAUDE.md, Setup)")


def with_board(f, board):
    """An FQBN with its vendor:arch:board swapped for `board`'s, options kept."""
    parts = f.split(":", 3)
    return ":".join(DEVICES[board].fqbn.split(":")[:3] + parts[3:])


def fqbn(sketch, debug=False, board=None):
    """The board and options a sketch builds with: its tools/game.py's FQBN,
    else the release or debug default, for `board` (default_board())."""
    import gamecfg
    f = gamecfg.load(paths.sketch(sketch)).FQBN or (FQBN_DEBUG if debug else FQBN_RELEASE)
    return with_board(f, _board(board, sketch))


def build_dir(sketch, debug=False, board=None):
    """Where a build goes: <sketch>/build/<board>/<release|debug>."""
    return paths.sketch(sketch) / "build" / _board(board, sketch) / ("debug" if debug else "release")


def defines(sketch):
    """The -D flags a sketch always builds with (its tools/game.py's DEFINES),
    as one build.extra_flags string; "" for most."""
    import gamecfg
    return " ".join(f"-D{d}" for d in gamecfg.load(sketch).DEFINES)


def build(sketch, debug=False, flags="", board=None):
    """Compile for `board` (default_board()); returns the build folder
    (build/<board>/release or build/<board>/debug)."""
    sketch = paths.sketch(sketch)
    board = _board(board, sketch)
    if not installed(board):
        raise SystemExit(not_installed(board))
    out = build_dir(sketch, debug, board)
    cmd = ["arduino-cli", "compile", "-b", fqbn(sketch, debug, board), "--build-path", str(out)]
    extra = " ".join(f for f in (("-DCHGAME_DEBUG=1" if debug else ""), defines(sketch), flags) if f)
    if extra.strip():
        cmd += ["--build-property", "build.extra_flags=" + extra.strip()]
    # All of them every time: Arduino links only the ones a sketch includes.
    # A sketch from another repository adds the libraries beside its own.
    for lib in [LIBRARIES / n for n in ("CHGfx", "CHGame", "CHSd")] + paths.sketch_libraries(sketch):
        cmd += ["--library", str(lib)]
    cmd.append(str(sketch))
    sys.stdout.flush()                      # what was said so far, before the children's output
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout[-3000:] + r.stderr[-3000:])
        raise SystemExit("compile failed")
    import gamecfg
    need = 0 if debug else gamecfg.load(sketch).SAVE_PAGES
    r = subprocess.run([sys.executable, str(REPO / "tools" / "check_size.py"), str(out), "--top", "0",
                        "--save-pages", str(need)])
    if r.returncode:
        raise SystemExit("the build does not fit (tools/check_size.py, above)")
    return out


def image(sketch, out):
    """The .bin arduino-cli wrote in the build folder."""
    return Path(out) / f"{paths.sketch(sketch).name}.ino.bin"


def upload(sketch, out, port=None, arduino=False, board=None):
    """Flash the build in `out`, built for `board` (default_board()): the
    uploader refuses a board whose bootloader says it is another one."""
    sketch = paths.sketch(sketch)
    board = _board(board, sketch)
    from serialcap import find_port
    port = port or find_port()
    if not port:
        raise SystemExit("no CHGame found on USB (VID 16C0:27DD): plug it in, or pass --port")
    if arduino:
        # The board's FQBN, so the board package's upload recipe passes its -device.
        r = subprocess.run(["arduino-cli", "upload", "-b", fqbn(sketch, False, board), "-p", port,
                            "--input-dir", str(out), str(sketch)], capture_output=True, text=True)
        if r.returncode:
            sys.stderr.write(r.stdout + r.stderr)
            raise SystemExit("upload failed")
        print(r.stdout.strip().splitlines()[-1])
        return
    from chgame_upload.upload import flash_file
    try:
        flash_file(image(sketch, out), port=port, run=True, device=board)
    except Exception as e:                  # NoDevice, StatusError, TimeoutError ...
        raise SystemExit(f"upload failed: {e}")


def run(sketch, script, outdir, port=None, flags="", board=None):
    """Debug build for `board`, upload, then the sketch's chdrive.py --device on the script."""
    sketch = paths.sketch(sketch)
    board = _board(board, sketch)
    upload(sketch, build(sketch, True, flags, board), port, board=board)
    chdrive = sketch / "tools" / "chsim" / "chdrive.py"
    if not chdrive.exists():
        chdrive = REPO / "tools" / "chsim" / "chdrive.py"
    cmd = [sys.executable, str(chdrive), "--device", str(script), str(outdir)]
    if port:
        cmd[3:3] = ["--port", port]
    return subprocess.run(cmd, cwd=sketch).returncode


def shot(sketch, out, port=None):
    sketch = paths.sketch(sketch)
    sys.path.insert(0, str(REPO / "tools" / "chsim"))
    from chdrivelib import Driver, SerialTransport
    from fbimage import to_image
    d = Driver(SerialTransport(port))
    d.handshake()
    to_image(d.shot(), 3).save(out)
    print(out)


def main(sketch=None, flags=""):
    """flags: extra build.extra_flags for this sketch (both builds)."""
    ap = argparse.ArgumentParser()
    if sketch is None:
        ap.add_argument("--sketch", type=Path, default=Path.cwd(), help="the sketch's folder")
    ap.add_argument("--board", choices=BOARDS,
                    help="the board to build for (default: $CHGAME_BOARD, else the newest the installed core has)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "upload"):
        p = sub.add_parser(name)
        p.add_argument("--debug", action="store_true")
        p.add_argument("--port")
        if name == "upload":
            p.add_argument("--arduino", action="store_true", help="through arduino-cli and the Go tool")
    p = sub.add_parser("run")
    p.add_argument("script")
    p.add_argument("outdir")
    p.add_argument("--port")
    p = sub.add_parser("shot")
    p.add_argument("out")
    p.add_argument("--port")
    a = ap.parse_args()
    sketch = paths.sketch(sketch or a.sketch)
    board = None if a.cmd == "shot" else _board(a.board, sketch)
    if a.cmd == "build":
        build(sketch, a.debug, flags, board)
    elif a.cmd == "upload":
        upload(sketch, build(sketch, a.debug, flags, board), a.port, a.arduino, board)
    elif a.cmd == "run":
        raise SystemExit(run(sketch, a.script, a.outdir, a.port, flags, board))
    elif a.cmd == "shot":
        shot(sketch, a.out, a.port)


if __name__ == "__main__":
    main()
