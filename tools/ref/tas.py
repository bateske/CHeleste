"""Replay the community's Celeste Classic TAS (CelesteClassic/ClassicTAS,
Any%) through the port, level by level: each level must be left upwards.

    python tools/ref/tas.py [--fixed] [--levels 1-30] [--lua]

The .tas files are downloaded into out/tas/ (they are not part of this
repository). A file is "[balloon seeds]" then one btn() bitmask a frame,
from the frame the player appears (the spawn has landed). The balloon and chest seeds are that tool's
RNG, not ours, so a level whose route rides a balloon's exact height may
miss: those are reported, not failed, unless --lua shows the cart's own Lua
clearing them on the same inputs (then the port is wrong).
"""
import argparse
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare  # noqa: E402

URL = "https://raw.githubusercontent.com/CelesteClassic/ClassicTAS/master/Celeste/TAS%20files/Any%25/TAS{}.tas"
CACHE = compare.ROOT / "out" / "tas"


def tas(level):
    f = CACHE / f"TAS{level}.tas"
    if not f.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_bytes(urllib.request.urlopen(URL.format(level), timeout=30).read())
    text = f.read_text()
    body = text[text.index("]") + 1:] if "]" in text else text
    return [int(x) for x in re.findall(r"\d+", body)]


def left_at(lines, room):
    for i, line in enumerate(lines):
        r = int(line.split()[1][1:])
        if r != room:
            return i, r
    return None, room


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixed", action="store_true")
    ap.add_argument("--lua", action="store_true")
    ap.add_argument("--levels", default="1-30")
    a = ap.parse_args(argv)
    lo, hi = map(int, a.levels.split("-")) if "-" in a.levels else (int(a.levels), int(a.levels))
    exe = compare.build(a.fixed)
    cleared = 0
    for level in range(lo, hi + 1):
        room = level - 1
        djump = 2 if room >= 22 else 0          # the orb is in level 22's big chest
        # The tool's first input is the frame the player appears (the spawn's landing ends).
        idle, _ = compare.c_trace(exe, [0] * 90, room, djump)
        start = next(i for i, l in enumerate(idle) if re.search(r"[|;] 0 ", l))
        inputs = [0] * start + tas(level) + [0] * 60
        lines, _ = compare.c_trace(exe, inputs, room, djump)
        at, to = left_at(lines, room)
        deaths = lines[at - 1 if at else -1].split()[2]
        msg = f"level {level:2d}: " + (f"left to {to} at frame {at} ({deaths})" if at else f"stayed ({deaths})")
        if a.lua:
            ref = compare.lua_trace(compare.ROOT / "assets" / "celeste.p8", inputs, room, djump, a.fixed)
            lat, lto = left_at(ref, room)
            msg += f"   lua: " + (f"left to {lto} at frame {lat}" if lat else "stayed")
        cleared += at is not None and to == room + 1
        print(msg)
    print(f"{cleared} of {hi - lo + 1} levels cleared")


if __name__ == "__main__":
    main()
