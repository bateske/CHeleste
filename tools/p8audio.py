"""Turn the Celeste cart's sound (assets/celeste.p8) into the piezo's.

    python tools/p8audio.py [--cart assets/celeste.p8] [--wav DIR]

Writes Cheleste/src/audio/Audio.{h,cpp} (where `cl audio` finds them:
SOUNDS, enum class Sfx and Song):

  - the sound effects the game plays, each a CHGame audio::Effect: one step
    a note (PICO-8's note length: speed x 183/22050 s), slides as sweeps,
    drops as falls, noise as a quick scatter of pitches (300-3000 Hz). Effects pitched
    below the piezo's range are moved up whole octaves.
  - the five songs (music 0, 10, 20, 30, 40) as Playtune scores for
    audio::music() in LEAD mode: each song's patterns from its loop start to
    its loop end, the melody in channel 0 and up to SONG_VOICES-1 others
    filling its rests. Noise (the drums) is left out.

PICO-8 has 4 voices with 8 waveforms and volume; the piezo has one square
wave. What survives is the tunes and the shapes of the effects.

Deterministic: the same cart gives the same files byte for byte.
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Cheleste" / "src" / "audio"

# The effects Game.cpp plays (sfx(n) / psfx(n)), with a priority each
# (CHGame's 0-15: a playing effect is only cut off by one as high).
USED = {0: ("death", 14), 1: ("jump", 9), 2: ("wall_jump", 9), 3: ("dash", 10),
        4: ("spawn", 6), 5: ("spawn_land", 6), 6: ("balloon", 8), 7: ("restore", 5),
        8: ("spring", 9), 9: ("no_dash", 7), 13: ("fruit", 11), 14: ("fruit_flies", 7),
        15: ("crumble", 6), 16: ("break", 11), 23: ("key", 11), 35: ("letter", 2),
        37: ("big_chest", 12), 38: ("start", 12), 51: ("orb", 13), 54: ("dash_back", 4),
        55: ("flag", 12)}
SONG_NAMES = ["area1", "area3", "area2", "wind", "title"]
SONGS = [0, 10, 20, 30, 40]
SONG_VOICES = 2              # the melody and one more
TICK_S = 183 / 22050         # one PICO-8 note at speed 1


def hz(pitch):
    return 65.40639 * 2 ** (pitch / 12)


def parse(path):
    text = Path(path).read_text(encoding="latin-1")
    sec, cur = {}, None
    for line in text.splitlines():
        m = re.fullmatch(r"__(\w+)__", line.strip())
        if m:
            cur = sec.setdefault(m.group(1), [])
        elif cur is not None and line.strip():
            cur.append(line.strip())
    sfx = []
    for line in sec["sfx"][:64]:
        speed, ls, le = int(line[2:4], 16), int(line[4:6], 16), int(line[6:8], 16)
        notes = []
        for i in range(32):
            n = line[8 + 5 * i:13 + 5 * i]
            notes.append((int(n[0:2], 16), int(n[2], 16) & 7, int(n[3], 16), int(n[4], 16)))
        sfx.append(dict(speed=max(1, speed), loop=(ls, le), notes=notes))
    music = []
    for line in sec["music"]:
        flags, chans = line.split()
        music.append((int(flags, 16), [int(chans[i:i + 2], 16) for i in range(0, 8, 2)]))
    return sfx, music


# --- effects -----------------------------------------------------------------

def effect_steps(s):
    """[(hz, endHz, ms)] for one sfx: hz 0 = a rest."""
    notes = s["notes"]
    last = max((i for i, n in enumerate(notes) if n[2]), default=-1)
    ms = s["speed"] * TICK_S * 1000
    audible = [hz(n[0]) for n in notes[:last + 1] if n[2]]
    if not audible:
        return []
    shift = 1
    while min(audible) * shift < 180:
        shift *= 2
    steps, prev, seed = [], None, 0x1234
    for pitch, wave, vol, fx in notes[:last + 1]:
        f = hz(pitch) * shift
        if not vol:
            steps.append((0, 0, ms))
            prev = None
            continue
        if wave == 6:                                   # noise: a scatter of pitches, 6 ms each
            t = ms
            while t > 0:
                seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
                g = f * (0.5 + 1.5 * (seed >> 16 & 1023) / 1023)
                steps.append((min(3000, max(300, g)), 0, min(6, t)))
                t -= 6
        elif fx == 1 and prev:                          # slide from the last note
            steps.append((prev, f, ms))
        elif fx == 3:                                   # drop
            steps.append((f, max(40, f / 8), ms))
        else:
            steps.append((f, 0, ms))
        prev = f
    # Join repeats of a held note.
    out = []
    for st in steps:
        if out and st[1] == 0 and out[-1][1] == 0 and round(out[-1][0] / 20) == round(st[0] / 20):
            out[-1] = (out[-1][0], 0, out[-1][2] + st[2])
        else:
            out.append(st)
    # 2 ms units in a byte: split what is longer than 510 ms.
    res = []
    for h, e, t in out:
        while t > 0:
            res.append((h, e, min(t, 510)))
            t -= 510
    return res


def step_c(h, e, t):
    q = lambda v: max(1, min(255, round(v / 20))) if v else 0
    return f"{{ {q(h)}, {q(e)}, {max(1, min(255, round(t / 2)))} }}"


# --- music -------------------------------------------------------------------

def channel_notes(s, length):
    """[(t0_ms, t1_ms, midi)] for an sfx played for `length` ticks in a pattern."""
    ls, le = s["loop"]
    seq, i = [], 0
    ticks = 0
    while ticks < length:
        if le > ls and i >= le:
            i = ls
        if i >= 32:
            break
        seq.append(s["notes"][i])
        i += 1
        ticks += 1
    out = []
    ms = s["speed"] * TICK_S * 1000
    for k, (pitch, wave, vol, fx) in enumerate(seq):
        if not vol or wave == 6:
            continue
        m = pitch + 36
        t0, t1 = k * ms, (k + 1) * ms
        if out and out[-1][2] == m and abs(out[-1][1] - t0) < 0.01:   # PICO-8 holds a repeated note
            out[-1] = (out[-1][0], t1, m)
        else:
            out.append((t0, t1, m))
    return out


def pattern_ms(sfx, chans):
    """The pattern's length: its first channel that does not loop, else its longest."""
    lens = []
    for c in chans:
        if c & 0x40:
            continue
        s = sfx[c & 0x3F]
        ls, le = s["loop"]
        lens.append((le > ls, 32 * s["speed"] * TICK_S * 1000, s["speed"]))
    plain = [l for loops, l, _ in lens if not loops]
    return plain[0] if plain else max((l for _, l, _ in lens), default=0)


def song(sfx, music, start):
    """The song from pattern `start` to its loop end: [voices of (t0, t1, midi)], length ms."""
    voices = [[], [], [], []]
    t, p = 0.0, start
    while p < len(music):
        flags, chans = music[p]
        plen = pattern_ms(sfx, chans)
        for v, c in enumerate(chans):
            if c & 0x40:
                continue
            s = sfx[c & 0x3F]
            ticks = round(plen / (s["speed"] * TICK_S * 1000))
            voices[v] += [(t + a, t + b, m) for a, b, m in channel_notes(s, ticks)]
        t += plen
        if flags & 2 or flags & 4:
            break
        p += 1
    return voices, t


def lead_first(voices):
    """The voices ordered melody first: the most notes, then the highest."""
    def score(v):
        return (len(v) > 0, sum(t1 - t0 for t0, t1, _ in v) * (sum(m for *_, m in v) / max(1, len(v))))
    return sorted(voices, key=score, reverse=True)


def playtune(voices, length):
    """A Playtune score: 0x9c note, 0x8c off, waits in ms (2 bytes), 0xE0 restart."""
    ev = []
    for ch, v in enumerate(voices):
        for t0, t1, m in v:
            ev.append((round(t1), 0, ch, m))     # offs before ons at the same ms
            ev.append((round(t0), 1, ch, m))
    ev.sort()
    out, now = bytearray(), 0
    on = [None] * 4
    for t, kind, ch, m in ev:
        if t > now:
            w = t - now
            while w > 0:
                c = min(w, 0x7FFF)
                out += bytes([c >> 8, c & 0xFF])
                w -= c
            now = t
        if kind:
            out += bytes([0x90 | ch, m])
            on[ch] = m
        elif on[ch] == m:
            out += bytes([0x80 | ch])
            on[ch] = None
    if length > now:
        w = round(length - now)
        out += bytes([w >> 8, w & 0xFF])
    out.append(0xE0)
    return bytes(out)


# --- output ------------------------------------------------------------------

def write_if_changed(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def generate(cart):
    sfx, music = parse(cart)
    head = f"// GENERATED by tools/p8audio.py from {Path(cart).name}: do not edit.\n"
    cpp = [head, '#include "Audio.h"\n\n']
    index = [0xFF] * 64
    effects, names = [], []
    for n in sorted(USED):
        steps = effect_steps(sfx[n])
        if not steps:
            continue
        cpp.append(f"AUDIO_STEPS(SFX{n}) = {{ " + ", ".join(step_c(*s) for s in steps) + " };\n")
        index[n] = len(effects)
        effects.append(f"AUDIO_EFFECT(SFX{n}, {USED[n][1]} | audio::GLIDE)")
        names.append(f"{USED[n][0].upper()},   // sfx({n})")
    cpp.append("\nconst audio::Effect SOUNDS[] = {\n    " + ",\n    ".join(effects) + "\n};\n")
    cpp.append("\nnamespace cartaudio {\n\n")
    cpp.append(f"const uint8_t EFFECT_COUNT = {len(effects)};\n\n")
    cpp.append("const uint8_t SFX_EFFECT[64] = {\n    " +
               ",\n    ".join(", ".join(f"0x{v:02X}" for v in index[i:i + 16]) for i in range(0, 64, 16)) + "\n};\n\n")
    sizes = []
    for i, start in enumerate(SONGS):
        voices, length = song(sfx, music, start)
        score = playtune(lead_first(voices)[:SONG_VOICES], length)
        sizes.append(len(score))
        rows = [", ".join(f"0x{b:02X}" for b in score[k:k + 24]) for k in range(0, len(score), 24)]
        cpp.append(f"static const uint8_t SONG{start}[{len(score)}] = {{  // {length / 1000:.1f} s a loop\n    "
                   + ",\n    ".join(rows) + "\n};\n")
    cpp.append("\nconst uint8_t *const SONGS[5] = { " + ", ".join(f"SONG{s}" for s in SONGS) + " };\n\n}\n")
    h = (head + "#pragma once\n#include <chgame/Audio.h>\n\n"
         "// The cart's effects the game plays, in SOUNDS' order.\n"
         "enum class Sfx : uint8_t {\n    " + "\n    ".join(names) + "\n    COUNT\n};\n"
         "// music(0), music(10) ... music(40).\n"
         "enum class Song : uint8_t { " + ", ".join(n.upper() for n in SONG_NAMES) + ", COUNT };\n\n"
         "extern const audio::Effect SOUNDS[];\n"
         "void playSong(Song s, bool loop);       // (Sounds.cpp; `cl audio` plays the songs with it)\n\n"
         "namespace cartaudio {\n"
         "extern const uint8_t EFFECT_COUNT;\n"
         "extern const uint8_t SFX_EFFECT[64];    // sfx(n)'s effect in SOUNDS (0xFF: not kept)\n"
         "extern const uint8_t *const SONGS[5];   // by Song: Playtune scores\n"
         "}\n")
    a = write_if_changed(OUT / "Audio.h", h)
    b = write_if_changed(OUT / "Audio.cpp", "".join(cpp))
    print(f"Audio.*: {'written' if a or b else 'unchanged'}; {len(effects)} effects, songs {sizes} B")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cart", default=str(ROOT / "assets" / "celeste.p8"))
    a = ap.parse_args(argv)
    generate(a.cart)


if __name__ == "__main__":
    main()
