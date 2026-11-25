"""chgame: the one entry point for the CHGame tools.

    chgame [--sketch NAME|DIR] [--board rev0|rev1] <command> [args]

From inside a game's folder (or any folder below it) the sketch is found by
itself; from anywhere else pass --sketch with a game's or app's name
(CHFour, CHSDtoUSB, Hello) or its folder. `pip install -e .` in the
repository root makes the `chgame` command; `python tools/chgame.py` is the
same thing uninstalled.

--board (or $CHGAME_BOARD) is the board to build for, given before the
command. Without it, build, upload, run --device and size take the newest
board the installed CHGame core has (tools/device.py), and check, export and
card take every board it has (a board it lacks is skipped, and said so);
with it, only that board. Given, it is also the --device of cart
prepare|flash|deploy|backup|new|add|build, pack pack and uploader
flash|pack, unless the command has its own --device. Not given, a binary in
a build/<board>/ folder names its board for cart new|add, pack pack and
uploader flash|pack (a raw image carries none); one from another board's
build folder than the board named is refused.

  build   [--debug] [-D FLAG ...]        compile for the board (release by default), print the size
                                         (into build/<board>/release, or debug)
  upload  [--debug] [--port P] [--arduino]
                                         compile and flash through the Python uploader
                                         (--arduino: through arduino-cli and the Go tool instead)
  sim     [-D NAME[=V] ...]              build the PC simulator, print the executable
          --free [--frames N] [--gif F | --png DIR] [--input SPEC] [--cost]
                                         run it free (no driver): the panel's frames to a GIF or PNGs
  run     SCRIPT OUTDIR [--device] [--port P] [--card IMG] [-D ...]
                                         run a chdrive script in the simulator (default) or,
                                         with --device, as a debug build on the board
  shot    OUT.png [--port P]             screenshot of the debug build running on the board
  check   [--quick] [--no-device] [--compare A B]
                                         everything checkable without a board (the device build:
                                         every installed board's)
  test    [ARGS ...]                     the host unit tests (--sketch CHGfx: the graphics library's)
  redraw  SCRIPT OUTDIR [TICKS]          the incremental-redraw check against a full redraw
  gif     [--check] [--no-run] [--every N] [--hold MS]
                                         record the README's docs/gameplay.gif (--check: all games)
  size    [BUILDDIR] [--top N] [--symbols]
                                         flash and RAM report of a build (default build/<board>/release)
  audio   OUTDIR [--only NAME ...]       the sound effects and songs as WAV, with a hash each
  export  [--no-build] [--out F] [--device B]
                                         the sketch as a .chgame (build/<Name>.chgame): to share it,
                                         with a binary per installed board
  cart    ...                            .chgame files: info, verify, new, build, add, remove, order,
                                         set, launch, background, picture, art, prepare, flash, deploy
                                         (tools/chcart)
  card    ...                            the repository's casino cart and its SD card, one per board:
                                         out/sdcard-<board>/ (tools/sdcard/mkcard.py)
  background IMAGE [--preview F] [--out F] [--card DIR] | --template F
                                         the list menu's picture: convert, preview, put on a card (docs/menu-image.md)
  picture IMAGE [--preview F] [--out F] [--card DIR] | --template F
                                         a picture for the visual menu: a game's, a cover (docs/visual-menu.md)
  boxart  [--check] [--sheet F]          draw the sketch's docs/cart.png from its tools/cart.py
                                         (--check: every program's is up to date)
  boxart  --export DIR | --import DIR    every program's picture into one folder to edit, and back
  uploader ARGS ...                      the uploader itself: probe, info, flash, selfupdate, burn ...
  pack    ...                            CHG files, the menu's install files (tools/chgpack.py)

Exit codes: 0 done, 1 the thing run failed (a compile, a test, a check),
2 usage or configuration (no sketch, a bad tools/game.py). `run` returns
the driver's own code (3: the simulator reported a BUG).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "chsim"))        # before tools/: `chsim` is the module chsim.py
import paths  # noqa: E402

NEEDS_SKETCH = {"build", "upload", "sim", "run", "shot", "check", "test", "redraw", "size", "audio", "export"}


def sketch_of(a):
    if a.sketch:
        return paths.sketch(a.sketch)
    s = paths.here()
    if s is None:
        print(f"{a.cmd}: not inside a sketch folder: pass --sketch CHFour (a game's or app's name, or its folder)",
              file=sys.stderr)
        raise SystemExit(2)
    return s


def py(script, *args, env=None, cwd=None):
    """Run one of the tools as a child, the way it runs by hand."""
    return subprocess.run([sys.executable, str(script), *map(str, args)], env=env, cwd=cwd).returncode


def where(sketch, p, must_exist=False):
    """A script or output path given on the command line: as written, from
    the current folder; else (from the root with --sketch) under the sketch."""
    q = Path(p)
    if q.is_absolute() or (must_exist and q.exists()) or (not must_exist and q.resolve().is_relative_to(sketch)):
        return q.resolve()
    return (sketch / q) if (not must_exist or (sketch / q).exists()) else q.resolve()


def game_tool(sketch, *rel):
    """A tool in the sketch's own tools/ folder, or None."""
    p = sketch.joinpath("tools", *rel)
    return p if p.exists() else None


def board_of(a):
    """The one board a command builds for: --board (or $CHGAME_BOARD), else
    the newest the installed core has (tools/device.py)."""
    import device
    return a.board or device.default_board()


def boards_of(a):
    """The boards a command that takes several (check, export, card) is
    limited to: [--board], or None for every board the installed core has."""
    return [a.board] if a.board else None


def device_arg(rest):
    """The value of rest's own --device (or the uploader's -device), "" when
    it has no value, None when there is none."""
    for i, r in enumerate(rest):
        if r in ("--device", "-device"):
            return rest[i + 1] if i + 1 < len(rest) else ""
        if r.startswith(("--device=", "-device=")):
            return r.split("=", 1)[1]
    return None


def built_for(rest):
    """The boards whose build folders (.../build/<board>/...) rest's paths are in."""
    import device
    found = set()
    for r in rest:
        parts = Path(r).parts
        found |= {b for x, b in zip(parts, parts[1:]) if x == "build" and b in device.BOARDS}
    return found


def with_device(rest, verbs, board, infer=False):
    """rest, plus --device BOARD when a board was named (--board,
    $CHGAME_BOARD), its verb is one of `verbs`, and it has no --device of
    its own (or the uploader's -device). infer, for the commands that take a
    built binary (a raw image carries no board): with no board named, a
    binary in build/<board>/ names it; one in another board's build folder
    than the board named is refused, rather than labelled with the wrong board."""
    if not any(r in verbs for r in rest):
        return rest
    own = device_arg(rest)
    seen = built_for(rest) if infer else set()
    named = own if own is not None else board
    if named:
        wrong = sorted(seen - {named})
        if wrong:
            fix = f"--device {wrong[0]}" if own is not None else f"chgame --board {wrong[0]} ..."
            raise SystemExit(f"the binary in build/{wrong[0]}/ was built for {wrong[0]}, not {named}: "
                             f"name its board ({fix}), or pass {named}'s build")
    elif len(seen) > 1:
        raise SystemExit(f"binaries built for {' and '.join(sorted(seen))} (build/<board>/): "
                         "one board per command, named with chgame --board B")
    if own is not None:
        return rest
    b = board or next(iter(seen), None)
    if not b:
        return rest
    if not board:
        print(f"(--device {b}: the binary is in build/{b}/)", file=sys.stderr)
    return [*rest, "--device", b]


def cmd_build(a, sketch):
    import device
    device.build(sketch, a.debug, " ".join(a.D), board=a.target)
    return 0


def cmd_upload(a, sketch):
    import device
    device.upload(sketch, device.build(sketch, a.debug, board=a.target), a.port, arduino=a.arduino, board=a.target)
    return 0


def cmd_sim(a, sketch):
    import chsim
    if not a.free:
        print(chsim.build(sketch, a.D))
        return 0
    return chsim.run(sketch, a.D, a.frames, a.every, a.start, a.scale, a.png, a.gif, a.input, a.cost, a.max_seconds)


def cmd_run(a, sketch):
    if a.device:
        import device
        return device.run(sketch, where(sketch, a.script, must_exist=True), where(sketch, a.outdir), a.port,
                          board=a.target)
    drv = game_tool(sketch, "chsim", "chdrive.py") or TOOLS / "chsim" / "chdrive.py"
    env = dict(os.environ)
    env.pop("CHSD_CARD", None)
    if a.card:
        env["CHSD_CARD"] = str(Path(a.card).resolve())
    args = ["--sim", sketch] + [f"-D{d}" for d in a.D]
    args += [where(sketch, a.script, must_exist=True), where(sketch, a.outdir)]
    return py(drv, *args, env=env, cwd=sketch)


def cmd_shot(a, sketch):
    import device
    device.shot(sketch, a.out, a.port)
    return 0


def cmd_check(a, sketch):
    import check
    rest = list(a.rest)
    if "--compare" in rest:
        i = rest.index("--compare")
        rest[i + 1:i + 3] = [str(where(sketch, p, must_exist=True)) for p in rest[i + 1:i + 3]]
    return check.main(sketch, rest, boards=boards_of(a))


def cmd_test(a, sketch):
    if sketch.name == "CHGfx" and (sketch / "library.properties").exists():
        import chsim                        # the graphics library's own tests, on the simulator's panel model
        return chsim.test()
    import hosttests
    return hosttests.main(sketch, list(a.rest))


def cmd_redraw(a, sketch):
    import diffdrive                   # chgame redraw (tools/chsim is on sys.path)
    rest = list(a.rest)
    if len(rest) < 2:
        raise SystemExit("usage: chgame redraw SCRIPT OUTDIR [TICKS]")
    rest[0] = str(where(sketch, rest[0], must_exist=True))
    rest[1] = str(where(sketch, rest[1]))
    return diffdrive.main(sketch, rest)


def cmd_gif(a, sketch):
    import readme_gif
    if a.check:
        return readme_gif.main(["--check"])
    return readme_gif.main([str(sketch), *a.rest])


def cmd_size(a, sketch):
    import check_size
    rest = list(a.rest)
    if rest and not rest[0].startswith("-"):
        build = rest.pop(0)
    else:
        import device
        build = str(device.build_dir(sketch, False, a.target))
    return check_size.main([build, *rest])


def cmd_audio(a, sketch):
    from audio import preview
    return preview.main([str(sketch), *a.rest])


def cmd_uploader(a, _sketch):
    from chgame_upload.cli import main as uploader_main
    return uploader_main(with_device(list(a.rest), {"flash", "pack"}, a.board, infer=True))


def cmd_export(a, sketch):
    from chcart import cli
    return cli.export_main(list(a.rest), sketch, boards=boards_of(a))


def cmd_background(a, _sketch):
    from chcart import cli
    return cli.background_main(list(a.rest))


def cmd_picture(a, _sketch):
    from chcart import cli
    return cli.picture_main(list(a.rest))


def cmd_boxart(a, sketch):
    import boxart
    return boxart.cli(list(a.rest) + (["--check"] if a.check else []), sketch)


def cmd_cart(a, _sketch):
    from chcart import cli
    rest = list(a.rest)
    if rest and rest[0] in {"prepare", "flash", "deploy", "backup", "new", "add", "build"}:
        board = a.board
        if not board and rest[0] in {"prepare", "flash", "deploy"} and device_arg(rest) is None:
            # A card or a board is for one board: the newest by default, as
            # for every other command (CLAUDE.md rule 9), not chcart's rev0.
            import device
            board = device.default_board()
            print(f"(--device {board}: the default board; chgame --board B for another)", file=sys.stderr)
        rest = with_device(rest, {rest[0]}, board, infer=rest[0] in {"new", "add"})
    return cli.main(rest)


def cmd_pack(a, _sketch):
    import chgpack
    rest = list(a.rest)
    if rest and rest[0] == "pack":
        rest = with_device(rest, {"pack"}, a.board, infer=True)
    return chgpack.main(rest)


def cmd_card(a, _sketch):
    from sdcard import mkcard
    return mkcard.main(list(a.rest), boards=boards_of(a))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="chgame", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sketch", help="a game's or app's name (CHFour, CHSDtoUSB, Hello) or folder")
    import device
    ap.add_argument("--board", choices=device.BOARDS, default=os.environ.get("CHGAME_BOARD") or None,
                    help="the board to build for ($CHGAME_BOARD; default: the newest the installed core has, "
                         "or for check, export and card every one it has)")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="command")

    p = sub.add_parser("build", help="compile for the board and print the size")
    p.add_argument("--debug", action="store_true", help="debug build: USB Serial and the debug protocol on")
    p.add_argument("-D", action="append", default=[], metavar="FLAG", help="extra build.extra_flags (e.g. -DX=1)")
    p = sub.add_parser("upload", help="compile and flash")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--port")
    p.add_argument("--arduino", action="store_true", help="upload through arduino-cli (the Go tool)")
    p = sub.add_parser("sim", help="build the PC simulator (--free: run it, frames to a GIF or PNGs)")
    p.add_argument("-D", action="append", default=[], metavar="NAME[=V]")
    p.add_argument("--free", action="store_true", help="free-run: no driver, virtual time, buttons from --input")
    p.add_argument("--frames", type=int, default=300, help="free-run: stop after N presented frames")
    p.add_argument("--gif", help="free-run: write the frames as a GIF, timed as shown")
    p.add_argument("--png", help="free-run: write the frames as PNGs into this folder")
    p.add_argument("--input", help='free-run: buttons, "F:BTN+BTN,F:" from presented frame F on')
    p.add_argument("--every", type=int, default=1)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--scale", type=int, default=3)
    p.add_argument("--cost", action="store_true", help="free-run: charge the sketch's own CPU time, scaled to the board")
    p.add_argument("--max-seconds", type=float)
    p = sub.add_parser("run", help="run a chdrive script")
    p.add_argument("script")
    p.add_argument("outdir")
    p.add_argument("--device", action="store_true", help="debug build, upload, and run on the board")
    p.add_argument("--sim", action="store_true", help="(the default)")
    p.add_argument("--port")
    p.add_argument("--card", help="an SD card image or file for the simulator ($CHSD_CARD)")
    p.add_argument("-D", action="append", default=[], metavar="NAME[=V]")
    p = sub.add_parser("shot", help="screenshot of the running debug build")
    p.add_argument("out")
    p.add_argument("--port")
    for name, help_ in (("check", "everything checkable without a board"),
                        ("test", "the host unit tests"),
                        ("redraw", "the incremental-redraw check"),
                        ("size", "flash and RAM report"),
                        ("audio", "sound effects and songs to WAV"),
                        ("export", "the sketch as a .chgame"),
                        ("cart", ".chgame files: make, inspect, edit, prepare a card, deploy"),
                        ("uploader", "the uploader: probe, info, flash, selfupdate, burn ..."),
                        ("pack", "CHG files (the menu's install files)"),
                        ("card", "the casino cart and its SD card"),
                        ("background", "the list menu's picture: convert, preview, put on a card"),
                        ("picture", "a picture for the visual menu: convert, preview, put on a card")):
        sub.add_parser(name, help=help_, add_help=False)
    p = sub.add_parser("gif", help="record the README's GIF", add_help=False)
    p.add_argument("--check", action="store_true")
    p = sub.add_parser("boxart", help="draw docs/cart.png, the game's picture for the visual menu", add_help=False)
    p.add_argument("--check", action="store_true")

    # The pass-through commands take whatever follows them as it is.
    a, rest = ap.parse_known_args(argv)
    a.rest = rest
    if rest and a.cmd in {"build", "upload", "sim", "run", "shot"}:
        ap.error(f"unrecognized arguments: {' '.join(rest)}")
    if a.board is not None and a.board not in device.BOARDS:
        ap.error(f"CHGAME_BOARD={a.board}: not a board (the boards: {', '.join(device.BOARDS)})")
    # The one board a building command is for (None for the rest).
    a.target = None
    if (a.cmd in {"build", "upload"} or (a.cmd == "run" and a.device)
            or (a.cmd == "size" and not (a.rest and not a.rest[0].startswith("-")))):
        a.target = board_of(a)
    sketch = None
    if a.cmd in NEEDS_SKETCH or (a.cmd in ("gif", "boxart") and not a.check
                                 and not (a.cmd == "boxart" and {"--sheet", "--export", "--import"} & set(a.rest))):
        sketch = sketch_of(a)
        print(f"{sketch.name}: {a.cmd}" + (f" ({a.target})" if a.target else ""), flush=True)
    fn = globals()[f"cmd_{a.cmd}"]
    rc = fn(a, sketch)
    return int(rc or 0)


if __name__ == "__main__":
    sys.exit(main())
