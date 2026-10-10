"""Golden traces: the port (Game.cpp) against the cart's own Lua, frame by frame.

    python tools/ref/compare.py [--fixed] [--frames N] [--seeds K] [--rooms 0-31]

For each room (and the title), the same made-up button presses go to both:
  - the cart's Lua (assets/celeste.p8), run by Lua 5.4 (pip install lupa)
    under a PICO-8 shim: PICO-8's foreach/all/del, the same rnd() generator
    as Fix.cpp, no drawing;
  - tools/ref/trace.cpp: Game.cpp built for the PC with num a double
    (CHLS_NUM_DOUBLE), or with --fixed the device's 16.16.
Every object's position, speed, remainder and sprite, the room, deaths,
freeze, shake and the sounds are compared after every frame; the first
difference is printed with the frames before it.

With doubles the two must agree (to 1e-9: the last bit of a sin() is the C
library's; any real difference is a porting bug).
With --fixed, PICO-8's own number format, they part a little (the Lua runs
on doubles, PICO-8 and the device on 16.16; 0.1 is not quite 0.1): what is
compared is the room, deaths, freeze, shake, sounds and the player's whole
pixel, and how long they agree is what to look at.
"""
import argparse
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKETCH = ROOT / "Cheleste"
BUILD = ROOT / "out" / "ref"
sys.path.insert(0, str(ROOT / "tools"))
import p8extract  # noqa: E402

TYPES = ["player", "player_spawn", "spring", "balloon", "fall_floor", "smoke", "fruit", "fly_fruit", "lifeup",
         "fake_wall", "key", "chest", "platform", "message", "big_chest", "orb", "flag", "room_title"]

SHIM = r"""
local bxor, band = function(a,b) return a ~ b end, function(a,b) return a & b end
__rng = 1
function rnd(x)
  if x == nil then x = 1 end
  if not (x > 0) then return 0 end
  local s = __rng
  s = (s ~ (s << 13)) & 0xffffffff
  s = (s ~ (s >> 17)) & 0xffffffff
  s = (s ~ (s << 5)) & 0xffffffff
  __rng = s
  if __fixed then return (s % math.floor(x * 65536 + 0.5)) / 65536 end
  return (s / 4294967296.0) * x
end
function sin(a) return -math.sin(a * 6.283185307179586) end
function cos(a) return math.cos(a * 6.283185307179586) end
flr = math.floor
abs = math.abs
function min(a,b) if a < b then return a else return b end end
function max(a,b) if a > b then return a else return b end end
function add(c, x) c[#c+1] = x return x end
function del(c, v)
  local n = #c
  for i=1,n do
    if c[i] == v then
      for j=i,n do c[j] = c[j+1] end
      return v
    end
  end
end
function count(c) return #c end
function all(c)
  if c == nil or #c == 0 then return function() end end
  local i, prev = 1, nil
  return function()
    if c[i] == prev then i = i + 1 end
    while i <= #c and c[i] == nil do i = i + 1 end
    prev = c[i]
    return prev
  end
end
function foreach(c, f) for v in all(c) do f(v) end end
sub = string.sub
__btn = 0
function btn(k) return (__btn >> k) & 1 == 1 end
function mget(x, y)
  if x < 0 or x > 127 or y < 0 or y > 63 then return 0 end
  return __map[flr(y) * 128 + flr(x) + 1]
end
function fget(n, f) return n < 128 and ((__flags[n + 1] >> f) & 1) == 1 end
__events = ""
function sfx(n) __events = __events .. " sfx" .. n end
function music(n) __events = __events .. " mus" .. n end
function spr() end
function map() end
function rectfill() end
function circfill() end
function line() end
function print() end
function pal() end
function camera() end
"""

DUMP = r"""
__names = {}
for i, n in ipairs(__typenames) do __names[_G[n]] = i - 1 end
local function put(v)
  if v == 0 then v = 0 end
  return string.format(" %.17g", v)
end
function __frame(i, inp)
  __events = ""
  __btn = inp
  _update()
  _draw()
  local t = {string.format("%d r%d d%d fz%d sh%d mdj%d%s |", i, level_index(), deaths, freeze, shake,
                           max_djump, __events)}
  for _, o in ipairs(objects) do
    t[#t+1] = " " .. __names[o.type] .. put(o.x) .. put(o.y) .. put(o.spd.x) .. put(o.spd.y) ..
              put(o.rem.x) .. put(o.rem.y) .. put(o.spr or 0)
    if o.type == player then t[#t+1] = " dj" .. o.djump end
    t[#t+1] = ";"
  end
  return table.concat(t)
end
"""


def pico_to_lua(src):
    """The few PICO-8 extensions this cart uses, as plain Lua."""
    out = []
    for line in src.splitlines():
        if line.startswith("__lua__"):
            continue
        line = line.replace("!=", "~=")
        line = re.sub(r"^(\s*)if\s*\((.*)\)\s*return\s*$", r"\1if \2 then return end", line)
        m = re.search(r"([\w.\[\]]+)\s*([-+*/%])=\s*", line)
        if m:
            rest = line[m.end():]
            k = re.search(r"\s+(return|end|then|else)\b", rest)
            rhs, tail = (rest[:k.start()], rest[k.start():]) if k else (rest, "")
            line = line[:m.start()] + f"{m.group(1)} = {m.group(1)} {m.group(2)} ({rhs.strip()})" + tail
        out.append(line)
    return "\n".join(out)


def lua_trace(cart, inputs, room, djump, fixed=False):
    from lupa.lua54 import LuaRuntime
    text = Path(cart).read_text(encoding="latin-1")
    code = text[text.index("__lua__"):text.index("__gfx__")]
    _, _, tiles, flags = p8extract.read_cart(cart)
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(SHIM)
    g = lua.globals()
    g.__fixed = fixed
    g.__map = lua.table_from(list(tiles))
    g.__flags = lua.table_from(list(flags))
    g.__typenames = lua.table_from(TYPES)
    lua.execute(pico_to_lua(code))
    lua.execute(DUMP)
    lua.execute("_init()")
    if room >= 0:
        lua.execute(f"start_game=false seconds=0 minutes=0 load_room({room % 8},{room // 8})"
                    + (f" max_djump={djump}" if djump else ""))
    frame = g.__frame
    return [frame(i, b) for i, b in enumerate(inputs)]


def build(fixed):
    BUILD.mkdir(parents=True, exist_ok=True)
    exe = BUILD / ("trace_fixed.exe" if fixed else "trace.exe")
    srcs = [ROOT / "tools/ref/trace.cpp", SKETCH / "Game.cpp", SKETCH / "Fix.cpp",
            SKETCH / "src/assets/Cart.cpp", SKETCH / "src/assets/Sine.cpp"]
    cmd = [sys.executable, "-m", "ziglang", "c++", "-std=gnu++17", "-O1", "-g0", "-I", str(SKETCH),
           f"-DCHLS_NUM_DOUBLE={0 if fixed else 1}", "-o", str(exe)] + [str(s) for s in srcs]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("trace build failed:\n" + r.stderr)
    return exe


def c_trace(exe, inputs, room, djump):
    f = BUILD / "inputs.bin"
    f.write_bytes(bytes(inputs))
    args = [str(exe), str(f), str(room)] + ([str(djump)] if djump else [])
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("trace failed:\n" + r.stderr)
    return r.stdout.splitlines(), r.stderr.strip()


def presses(rng, n):
    """Buttons a player might hold: runs of a direction, jumps and dashes."""
    out, cur, left = [], 0, 0
    while len(out) < n:
        if left <= 0:
            cur = 0
            h = rng.random()
            if h < 0.45: cur |= 2       # right
            elif h < 0.7: cur |= 1      # left
            if rng.random() < 0.35: cur |= 4    # up
            elif rng.random() < 0.15: cur |= 8  # down
            if rng.random() < 0.5: cur |= 16    # jump
            if rng.random() < 0.25: cur |= 32   # dash
            left = rng.randint(1, 14)
        out.append(cur)
        left -= 1
    return out


def numbers(line):
    return [float(x) for x in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", line.split("|", 1)[1])] if "|" in line else []


def player_px(line):
    """The player's (or the spawn's) whole-pixel position in a trace line."""
    for obj in line.split("|", 1)[1].split(";"):
        f = obj.split()
        if f and f[0] in ("0", "1"):
            return f[0], int(float(f[1]) // 1), int(float(f[2]) // 1)
    return None


def same(a, b, fixed):
    """Doubles: the header (room, deaths, timers, sounds) exactly and the
    numbers to 1e-9 (Lua's sin and the C library's differ in the last bit).
    16.16: the header and the player's whole-pixel position (the Lua runs on
    doubles, so the fractions part)."""
    if a == b:
        return True
    ha, hb = a.split("|", 1)[0], b.split("|", 1)[0]
    if ha.split()[1:] != hb.split()[1:]:
        return False
    if fixed:
        return player_px(a) == player_px(b)
    na, nb = numbers(a), numbers(b)
    return len(na) == len(nb) and all(abs(x - y) <= 1e-9 for x, y in zip(na, nb))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixed", action="store_true")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--rooms", default="-1,0-30")
    ap.add_argument("--cart", default=str(ROOT / "assets" / "celeste.p8"))
    a = ap.parse_args(argv)
    rooms = []
    for part in a.rooms.split(","):
        if re.fullmatch(r"\d+-\d+", part):
            lo, hi = map(int, part.split("-"))
            rooms += range(lo, hi + 1)
        else:
            rooms.append(int(part))
    exe = build(a.fixed)
    bad = 0
    for room in rooms:
        for seed in range(a.seeds):
            djump = 2 if seed % 2 else 0
            inputs = presses(random.Random(room * 1000 + seed), a.frames)
            if room < 0:
                inputs[:40] = [0] * 40
                inputs[40:45] = [16] * 5
            ref = lua_trace(a.cart, inputs, room, djump, a.fixed)
            got, info = c_trace(exe, inputs, room, djump)
            first = next((i for i, (x, y) in enumerate(zip(ref, got)) if not same(x, y, a.fixed)), None)
            if first is None and len(ref) != len(got):
                first = min(len(ref), len(got))
            tag = f"room {room:2d} seed {seed}{' djump2' if djump else ''}"
            if first is None:
                deaths = ref[-1].split()[2]
                print(f"ok   {tag}: {len(ref)} frames, end {ref[-1].split()[1]} {deaths} ({info})")
            else:
                bad += 1
                print(f"DIFF {tag} at frame {first}:")
                for i in range(max(0, first - 2), first + 1):
                    print(f"  lua {ref[i] if i < len(ref) else '-'}")
                    print(f"  c++ {got[i] if i < len(got) else '-'}")
    print(f"{'all agree' if not bad else f'{bad} differ'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
