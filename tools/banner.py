"""Draw the README's banner, docs/banner.gif (and a still, banner.png), and the same
scene drawn 2:1 for GitHub's social preview, docs/social.gif and social.png.

    python tools/banner.py

Black, the title's CELESTE logo in the middle, the words saying what this is
on either side of it (WORDS), and one row of ground along
the bottom. Madeline runs in past a snowy tree, bounces off a spring into a
strawberry, jumps the pit and dashes across it, then climbs the chimney on
the right by wall jumps and dashes up out of the top.

Everything is the cart's own (assets/celeste.p8): the tiles, the logo, her
sprites, hair and smoke, the spring and the strawberry. Her movement is the
cart's player update, with its numbers:
  - the run's 0.6 / 0.4 acceleration, gravity 0.21 (halved at the top),
    a wall slide's 0.4;
  - a jump of -2, a wall jump of (-2, -2), the spring's -3;
  - a dash of 5 eased to 2 over four frames, with its freeze and shake;
  - move_x's 0..abs(amount) steps.
A small script decides when she presses jump and dash. The scene is drawn at
PICO-8's pixel size on a 320x88 canvas, then scaled 4x.
"""
import math
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import p8extract  # noqa: E402

W, H, SCALE = 320, 88, 4
GROUND = 80                         # the top of the ground row
PIT = (176, 216)                    # the pit's columns (whole tiles)
WALL = 304                          # the wall on the right: x >= WALL is solid, top to bottom
PILLAR = (272, 280, 64)             # an ice pillar hanging from the top (x0, x1, bottom): with the wall, a chimney
SPRING = 104                         # the spring's x (on the ground)
BERRY = (124, 34)                   # where the strawberry floats
LOGO_Y = 10                         # the logo's top
WORDS_DY = 0                        # the words moved down by this (screen pixels): layout() sets it


LOGO_SCALE = 1                      # logo and words pixel-doubled on the social card
CARD = False


def layout(h, card=False):
    """The scene for a frame h game pixels tall (88: the banner; 160: the 2:1 social card).
    The ground stays at the bottom, the chimney runs the full height, and the logo and
    the words are centred in what the extra height adds."""
    global H, GROUND, PILLAR, WALL, BERRY, SPRING, LOGO_Y, WORDS_DY, LOGO_SCALE, CARD
    dy = h - 88
    H, GROUND = h, 80 + dy
    PILLAR, WALL = (272, 280, 64 + dy), 304
    BERRY, SPRING = (124, 34 + dy), 104
    LOGO_Y, WORDS_DY, LOGO_SCALE, CARD = 10 + dy // 2, dy // 2 * SCALE, 1, card
    if card:
        # The card: the logo doubled and centred at the top, the words doubled and centred
        # under it; no spring or strawberry (her bounce would go through the words).
        # The chimney moves right, clear of the long first line.
        LOGO_Y, LOGO_SCALE, BERRY, SPRING = 4, 2, None, None
        PILLAR, WALL = (284, 292, 64 + dy), 312
RGB = [((c >> 16) & 255, (c >> 8) & 255, c & 255) for c in p8extract.P8PAL]

# "1000" in a 3x5 font (the lifeup's score).
DIGITS = {"1": ["010", "110", "010", "010", "111"], "0": ["111", "101", "101", "101", "111"]}


def appr(v, t, a):
    return max(v - a, t) if v > t else min(v + a, t)


def sign(v):
    return (v > 0) - (v < 0)


def solid(x, y):
    if x >= WALL or (PILLAR[0] <= x < PILLAR[1] and y < PILLAR[2]):
        return True
    return y >= GROUND and not (PIT[0] <= x < PIT[1])


class Player:
    def __init__(self):
        self.x, self.y = -12.0, GROUND - 8.0
        self.sx = self.sy = self.rx = self.ry = 0.0
        self.tx = self.ty = 0.0
        self.djump, self.dash_time, self.grace, self.jbuffer = 1, 0, 0, 0
        self.p_jump = self.p_dash = False
        self.spr_off, self.spr, self.was_ground, self.face = 0.0, 1, True, 1

    def box(self, ox=0, oy=0):          # the player's hitbox (1, 3, 6, 5)
        x, y = int(self.x // 1) + 1 + ox, int(self.y // 1) + 3 + oy
        return any(solid(x + i, y + j) for i in range(6) for j in range(5))

    def move(self):
        self.rx += self.sx
        amount = int((self.rx + 0.5) // 1)
        self.rx -= amount
        step = sign(amount)
        for _ in range(abs(amount) + 1):
            if self.box(step, 0):
                self.sx = self.rx = 0.0
                break
            self.x += step
        self.ry += self.sy
        amount = int((self.ry + 0.5) // 1)
        self.ry -= amount
        step = sign(amount)
        for _ in range(abs(amount) + 1):
            if self.box(0, step):
                self.sy = self.ry = 0.0
                break
            self.y += step


def simulate():
    """Every frame: the player, the smoke, the spring, the berry, the camera."""
    p = Player()
    smoke, out = [], []
    spring_t, berry, lifeup = 0, True, None
    pit_jumped = pit_dashed = top_dashed = False
    shake, seed, frame = 0, 7, 0
    go = 1                                              # the way she holds the d-pad
    while frame < 600:
        frame += 1
        p.move()
        on_ground = p.box(0, 1)
        on_wall = not on_ground and p.box(3, 0)
        # The script: right held; jump and dash pressed where the climb needs them.
        up, jump, dash = False, False, False
        if not pit_jumped and on_ground and p.x >= PIT[0] - 14:
            jump = pit_jumped = True
        elif pit_jumped and not pit_dashed and p.sy > -0.6:
            dash = pit_dashed = True
        elif p.x > PIT[1] and on_ground and p.box(3, 0) and not p.p_jump:
            jump = True                                   # up off the ground at the wall
        elif p.x > PIT[1] and not on_ground and not p.p_jump and (p.box(3, 0) or p.box(-3, 0)) and p.sy > -1.6:
            jump = True                                   # up the chimney, wall to wall
            go = -1 if p.box(3, 0) else 1
        right = go
        if p.y < 18 and p.x > PILLAR[1] and p.djump and not top_dashed:
            right, up, dash, top_dashed = 0, True, True, True     # straight up (then on up the walls)
            go = 1
        frozen = False

        if on_ground and not p.was_ground:
            smoke.append([p.x, p.y + 4, 29.0])
        jpress = jump and not p.p_jump
        p.p_jump = jump
        p.jbuffer = 4 if jpress else max(0, p.jbuffer - 1)
        dpress = dash and not p.p_dash
        p.p_dash = dash
        if on_ground:
            p.grace, p.djump = 6, 1
        elif p.grace > 0:
            p.grace -= 1
        inp = right
        if p.dash_time > 0:
            smoke.append([p.x, p.y, 29.0])
            p.dash_time -= 1
            p.sx = appr(p.sx, p.tx, 1.5 if p.sy == 0 else 1.5 * 0.70710678)
            p.sy = appr(p.sy, p.ty, 1.5 if p.sx == 0 else 1.5 * 0.70710678)
        else:
            accel = 0.6 if on_ground else 0.4
            p.sx = appr(p.sx, sign(p.sx), 0.15) if abs(p.sx) > 1 else appr(p.sx, inp, accel)
            maxfall, grav = 2, 0.21 * (0.5 if abs(p.sy) <= 0.15 else 1)
            if inp and p.box(inp, 0):
                maxfall = 0.4                               # wall slide
            if not on_ground:
                p.sy = appr(p.sy, maxfall, grav)
            if p.jbuffer > 0:
                if p.grace > 0:
                    p.jbuffer = p.grace = 0
                    p.sy = -2.0
                    smoke.append([p.x, p.y + 4, 29.0])
                else:
                    wall = -1 if p.box(-3, 0) else 1 if p.box(3, 0) else 0
                    if wall:
                        p.jbuffer = 0
                        p.sy, p.sx = -2.0, -wall * 2.0
                        smoke.append([p.x + wall * 6, p.y, 29.0])
            if p.djump > 0 and dpress:
                smoke.append([p.x, p.y, 29.0])
                p.djump -= 1
                p.dash_time = 4
                vi = -1 if up else 0
                if inp and vi:
                    p.sx, p.sy = inp * 5 * 0.70710678, vi * 5 * 0.70710678
                elif inp:
                    p.sx, p.sy = 5.0, 0.0
                else:
                    p.sx, p.sy = 0.0, vi * 5.0
                p.tx, p.ty = 2 * sign(p.sx), 2 * sign(p.sy) * (0.75 if p.sy < 0 else 1)
                frozen, shake = True, 6
        # The spring.
        if SPRING is None:
            pass
        elif spring_t == 0 and p.sy >= 0 and SPRING - 6 < p.x < SPRING + 6 and p.y > GROUND - 14:
            p.y, p.sx, p.sy, p.djump, spring_t = GROUND - 12, p.sx * 0.2, -3.0, 1, 10
            smoke.append([SPRING, GROUND - 8, 29.0])
        elif spring_t > 0:
            spring_t -= 1
        # The strawberry.
        by = BERRY[1] + math.sin(frame / 40 * 2 * math.pi) * -2.5 if BERRY else 0
        berry = berry and BERRY is not None
        if berry and abs(p.x - BERRY[0]) < 7 and abs(p.y - by) < 7:
            berry, lifeup = False, [BERRY[0] - 2, by - 4, 30, 0.0]
            p.djump = 1
        if lifeup:
            lifeup[1] -= 0.25
            lifeup[2] -= 1
            lifeup[3] += 0.5
            if lifeup[2] <= 0:
                lifeup = None
        # Sprite: the cart's animation.
        if p.sx:
            p.face = sign(p.sx)                             # the cart's flip.x
        p.spr_off += 0.25
        if not on_ground:
            p.spr = 5 if inp and p.box(inp, 0) else 3
        else:
            p.spr = 1 + int(p.spr_off % 4)
        smoke = [[a, b - 0.1, s + 0.2] for a, b, s in smoke if s + 0.2 < 32]
        if shake:
            shake -= 1
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            cam = ((seed >> 8) % 5 - 2, (seed >> 12) % 5 - 2) if shake else (0, 0)
        else:
            cam = (0, 0)
        out.append(dict(x=p.x, y=p.y, spr=p.spr, djump=p.djump, smoke=[s[:] for s in smoke], frozen=frozen,
                        cam=cam, spring=19 if spring_t else 18, berry=(BERRY[0], by) if berry else None,
                        lifeup=lifeup[:] if lifeup else None, facing=p.face))
        p.was_ground = on_ground
        if p.y < -32:                                       # well off the top, hair and all (the walls go on up)
            break
    return out


class Canvas:
    def __init__(self, gfx):
        self.gfx = gfx
        self.px = [[0] * W for _ in range(H)]
        self.cam = (0, 0)
        self.pal = list(range(16))

    def pset(self, x, y, c):
        x, y = x - self.cam[0], y - self.cam[1]
        if 0 <= x < W and 0 <= y < H:
            self.px[y][x] = self.pal[c]

    def spr(self, n, x, y, flipx=False):
        sx, sy = (n % 16) * 8, (n // 16) * 8
        x, y = int(x // 1), int(y // 1)
        for j in range(8):
            for i in range(8):
                c = self.gfx[sy + j][sx + (7 - i if flipx else i)]
                if c:
                    self.pset(x + i, y + j, c)

    def rect(self, x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.pset(x, y, c)

    def circ(self, x, y, r, c):           # PICO-8's small circles, as P8.cpp draws them
        x, y = int(x // 1), int(y // 1)
        if r <= 1:
            self.rect(x - 1, y, x + 1, y, c)
            self.rect(x, y - 1, x, y + 1, c)
        else:
            self.rect(x - 2, y - 1, x + 2, y + 1, c)
            self.rect(x - 1, y - 2, x + 1, y + 2, c)

    def text(self, s, x, y, c):
        x, y = int(x // 1), int(y // 1)
        for k, ch in enumerate(s):
            for j, row in enumerate(DIGITS[ch]):
                for i, b in enumerate(row):
                    if b == "1":
                        self.pset(x + k * 4 + i, y + j, c)

    def image(self):
        im = Image.new("P", (W, H))
        im.putpalette([v for c in RGB for v in c])
        im.putdata([c for row in self.px for c in row])
        return im.resize((W * SCALE, H * SCALE), Image.NEAREST)


def logo_points(gfx, tiles, flags):
    """The title room's terrain tiles (map(.., 2) at x-4, as _draw does), cropped to the logo."""
    pts = {}
    for ty in range(16):
        for tx in range(16):
            n = tiles[(3 * 16 + ty) * 128 + 7 * 16 + tx]
            if n and n < 128 and flags[n] & 2:
                for j in range(8):
                    for i in range(8):
                        c = gfx[(n // 16) * 8 + j][(n % 16) * 8 + i]
                        if c:
                            pts[(tx * 8 + i - 4, ty * 8 + j)] = c
    x0, y0 = min(x for x, _ in pts), min(y for _, y in pts)
    w = max(x for x, _ in pts) - x0 + 1
    return [(x - x0, y - y0, c) for (x, y), c in pts.items()], w


def scenery(cv):
    """The ground row, the wall, and the scenery at the edges."""
    for tx in range(-1, WALL // 8):
        gx = tx * 8
        if PIT[0] <= gx < PIT[1]:
            continue
        cv.spr(33 if gx == PIT[1] else 35 if gx + 8 == PIT[0] else 34, gx, GROUND)
    for ty in range(-1, H // 8 + 1):                     # the wall: its snowy face, then ice
        cv.spr(36, WALL, ty * 8)
        cv.spr(37, WALL + 8, ty * 8)
    for ty in range(-1, PILLAR[2] // 8):                 # the pillar, its icy end at the bottom
        cv.spr(37 if ty < PILLAR[2] // 8 - 1 else 53, PILLAR[0], ty * 8)
    # The left: two snowy trees, grass and flowers.
    for x in (10, 28):
        cv.spr(44, x, GROUND - 16)
        cv.spr(60, x, GROUND - 8)
    for x, n in ((44, 61), (52, 62), (60, 63), (128, 61), (150, 63), (232, 62), (244, 61), (262, 63), (280, 61)):
        cv.spr(n, x, GROUND - 8)


# The words on the banner, in CHGame's 3x5 font (the one the port prints with):
# (text, colour, scale in screen pixels: 4 is a game pixel, x, y, anchor), on the 1280x352 picture.
# One block at the far left: what this is, how, and whose game it is.
WORDS = [("CELESTE CLASSIC FOR THE PICO-8", 7, 4, 24, 40, "left"),
         ("NOW ON CHGAME", 7, 4, 24, 72, "left"),
         ("PORTED TO NATIVE C++", 6, 3, 24, 112, "left"),
         ("ORIGINAL GAME BY", 13, 2, 24, 144, "left"),
         ("MADDY THORSON & NOEL BERRY", 13, 2, 24, 160, "left")]
FONT_SRC = ROOT / "chgame/platform/board/arduino/CHGame/libraries/CHGame/src/chgame/Draw.cpp"


def font35():
    """{char: 3 column bytes} from CHGfx's FONT35 table (PPOT Font3x5, Apache-2.0), '!' to 'z'."""
    import re
    src = FONT_SRC.read_text(encoding="utf-8")
    body = src[src.index("FONT35[FONT35_LAST"):]
    body = body[body.index("{") + 1:body.index("};")]
    cols = [[int(v, 16) for v in g.split(",")] for g in re.findall(r"\{(0x[0-9A-F]{2},0x[0-9A-F]{2},0x[0-9A-F]{2})\}", body)]
    return {chr(ord("!") + i): c for i, c in enumerate(cols)}


def card_words(top):
    """WORDS for the card: doubled, centred, one under another from `top` (screen pixels)."""
    out, y = [], top
    for k, (text, colour, scale, _, _, _) in enumerate(WORDS):
        out.append((text, colour, scale * 2, 640, y, "center"))
        y += 6 * scale * 2 + (6 if k in (0, 3) else 16)
    return out


def words(im, font, cam=(0, 0), lines=None):
    """WORDS (or `lines`) onto a frame (a palette image: the colours are PICO-8's indices)."""
    for text, colour, scale, x, y, anchor in lines or WORDS:
        w = (len(text) * 4 - 1) * scale
        x0 = (x - w if anchor == "right" else x - w // 2 if anchor == "center" else x) - cam[0] * SCALE
        y0 = y + (0 if anchor == "center" else WORDS_DY) - cam[1] * SCALE
        for k, ch in enumerate(text):
            for i, bits in enumerate(font.get(ch, (0, 0, 0))):
                for j in range(6):
                    if bits >> j & 1:
                        px, py = x0 + (k * 4 + i) * scale, y0 + j * scale
                        im.paste(colour, (px, py, px + scale, py + scale))
    return im


def render():
    """The scene's frames at the current layout(), and the index of its still (mid-dash over the pit)."""
    gfx, _, tiles, flags = p8extract.read_cart(ROOT / "assets" / "celeste.p8")
    logo, lw = logo_points(gfx, tiles, flags)
    lh = max(y for _, y, _ in logo) + 1
    font = font35()
    lines = card_words((LOGO_Y + lh * LOGO_SCALE + 3) * SCALE) if CARD else None
    hair = None
    frames, still = [], None
    for f in simulate():
        cv = Canvas(gfx)
        cv.cam = f["cam"]                           # the shake moves everything: the logo and the words too
        n = LOGO_SCALE
        for lx, ly, c in logo:
            for i in range(n * n):
                cv.pset((W - lw * n) // 2 + lx * n + i % n, LOGO_Y + ly * n + i // n, c)
        scenery(cv)
        if SPRING is not None:
            cv.spr(f["spring"], SPRING, GROUND - 8)
        if f["berry"]:
            cv.spr(26, *f["berry"])
        for sx, sy, s in f["smoke"]:
            cv.spr(int(s), sx, sy)
        x, y = f["x"], f["y"]
        facing = f["facing"]
        if hair is None:
            hair = [[x, y, max(1, min(2, 3 - i))] for i in range(5)]
        lx, ly = x + 4 - facing * 2, y + 3          # draw_hair
        for h in hair:
            h[0] += (lx - h[0]) / 1.5
            h[1] += (ly + 0.5 - h[1]) / 1.5
            lx, ly = h[0], h[1]
        cv.pal[8] = 8 if f["djump"] == 1 else 12    # red with a dash, blue without
        for h in hair:
            cv.circ(h[0], h[1], h[2], 8)
        cv.spr(f["spr"], x, y, flipx=facing < 0)
        cv.pal[8] = 8
        if f["lifeup"]:
            lx, ly, _, flash = f["lifeup"]
            cv.text("1000", lx - 2, ly, 7 + int(flash % 2))
        frames.append(words(cv.image(), font, f["cam"], lines))
        if f["frozen"]:                              # the dash's two frozen frames
            if still is None:
                still = len(frames) + 2
            frames += [frames[-1]] * 2
    frames += [frames[-1]] * 24                      # a beat before she comes round again
    return frames, still if still is not None and still < len(frames) else len(frames) // 2


def save_gif(path, frames):
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=True, disposal=1)


def save_png(path, im):                              # (through a temporary file: a viewer may hold the old one)
    tmp = path.with_suffix(".tmp.png")
    im.save(tmp)
    tmp.replace(path)


def main():
    docs = ROOT / "docs"
    layout(88)                                       # the README's banner, 1280x352
    frames, still = render()
    save_gif(docs / "banner.gif", frames)
    save_png(docs / "banner.png", frames[still])
    print(f"banner.gif: {len(frames)} frames, {(docs / 'banner.gif').stat().st_size:,} B")
    layout(160, card=True)                           # GitHub's social preview, 1280x640, drawn for it
    frames, still = render()
    save_png(docs / "social.png", frames[still])
    # Most sites show a GIF's first frame only: it starts on the still.
    save_gif(docs / "social.gif", frames[still:] + frames[:still])
    print(f"social.gif: {len(frames)} frames, {(docs / 'social.gif').stat().st_size:,} B (GitHub's limit: 1,000,000)")


if __name__ == "__main__":
    main()
