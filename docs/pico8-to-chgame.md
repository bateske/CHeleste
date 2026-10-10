# Porting a PICO-8 cart to CHGame: how Cheleste was done

This is a record of how Celeste Classic's Lua became native C++ on CHGame. It focuses on what will matter the next time a PICO-8 cart is ported. Cheleste's own details are in [../Cheleste/NOTES.md](../Cheleste/NOTES.md).

## Why it can work at all

PICO-8 and CHGame are close relatives:

| | PICO-8 | CHGame |
|---|---|---|
| Screen | 128x128, 16 colours | 128x128, 16-colour palette (`gfx_fb`, 4 bpp) |
| Pixel packing | 2 pixels a byte, left pixel in the low nibble | the same |
| Frame rate | `_update` at 30 (or `_update60`) | `chgame.setFrameRate(30)` |
| Numbers | 16.16 fixed point | no FPU: integers are free, floats cost KBs |
| Buttons | ⬅➡⬆⬇ O X | D-pad, A, B (+ START, SELECT) |
| Sound | 4 voices, 8 waves, volume | one piezo, square wave |
| Code | Lua, 8192 tokens | C++, 50 KB flash, 18 KB RAM |

So the screen, sprites and map carry across untouched. The code has to be rewritten, and the sound has to be reduced.

## The approach in one paragraph

1. Don't run Lua. Translate it by hand into C++, function by function, in the cart's order and with the cart's names, so the two files can be read side by side.
2. Extract the data (`__gfx__`, `__map__`, `__gff__`, `__sfx__`, `__music__`) with a script into generated, committed C++ arrays.
3. Prove the translation by running the original Lua on the PC next to the C++, on the same inputs, and comparing the whole game state every frame.

That third step did most of the work. Translating ~1,400 lines of Lua took one pass; the comparison is what made it possible to trust the pass. (The NoelFB C# version of Celeste was a useful cross-check for intent, but it is not the original. It differs in object iteration, particle count and a sprite flag, so the cart's Lua stayed the source of truth.)

## The pieces, and what to reuse

| File | Role | Reusable for another cart? |
|---|---|---|
| `tools/p8extract.py` | `.p8` → sheet, map, flags, palette as C arrays | Yes, almost as is |
| `tools/p8audio.py` | `__sfx__`/`__music__` → `audio::` effects and Playtune scores | Yes; the effect list and priorities are per game |
| `Cheleste/Fix.h/.cpp` | `num`: PICO-8 16.16 numbers, `sin`/`cos`/`rnd` | Yes, as is |
| `Cheleste/P8.h/.cpp` | `spr map rectfill circfill line print pal camera mget fget` on `gfx_fb` | Yes; add calls the next cart uses (`sspr`, `pset`, `palt`, `fillp` ...) |
| `Cheleste/Game.cpp` | the translated Lua | No: this is the per-game work |
| `tools/ref/compare.py`, `trace.cpp` | Lua-vs-C++ golden traces | Yes: change the state dump to the new cart's objects |

## Translating the Lua: the rules that mattered

### 1. Numbers: write `num`, never `float`

PICO-8 numbers are 16.16 fixed point, and gameplay depends on their rounding. In Celeste, gravity 0.21, ice friction 0.05 and the sub-pixel remainders all sit on rounding edges. `Fix.h`'s `num` copies PICO-8 exactly:

- `+ - *` wrap at ±32768, and `*` floors to 1/65536.
- `/` truncates, and division by zero saturates.
- `flr` floors toward minus infinity.
- `%` returns a result in `[0, |b|)` (`-1 % 8 == 7`).
- `sin` is upside down, and both `sin` and `cos` take turns, not radians.
- Literals round to the nearest 1/65536 (`0.1` is `0x0000.199a`). `num(0.21)` is folded at compile time.

Write literals as `num(0.5)`, and check `cl size` for soft-float symbols (`__adddf3`, `__muldf3`). If any appear, a runtime double has slipped in.

The same code also compiles with `num` as a `double` (`CHLS_NUM_DOUBLE`). That build exists only so the C++ can be compared exactly with Lua on the PC, which uses doubles.

Watch counters: Lua counters never overflow in practice, but PICO-8's do, at 32768. Celeste's `dash_effect_time` counts down forever, so it is an `int16_t`, which wraps the same way. Use `int16_t` (or `num`), not `int8_t`, for anything that counts frames.

### 2. Objects: a fixed pool, a union, and PICO-8's exact `foreach`

Lua objects are tables with methods and fields added at will. In C++:

- **Storage:** `struct Obj` holds the common fields (type, x, y, spd, rem, hitbox, spr, flips), plus a `union` with each kind's own fields.
- **Pool:** a fixed `pool[MAX_OBJECTS]` and an ordered `objects[]` list, which is the Lua table. Check the peak count against the pool size (Cheleste peaked at 25 of 40).
- **Per-kind functions:** tables of `INIT[]`, `UPDATE[]` and `DRAW[]` function pointers, indexed by type, replace the Lua method tables.
- **Uninitialised fields:** a Lua field that is never initialised reads as `nil`. Decide what it means and set it in `init` (Celeste's spring `delay`, message `index`).

Iteration order is gameplay. PICO-8's `foreach` is `for v in all(t)`, and `all()` (copied from zepto8's BIOS) moves its index on only when the element at it is still the one it just visited. So:

- deleting the current object skips nothing;
- objects added during the loop are visited in the same loop, so a player created by its spawn's update is updated that frame;
- a `load_room` inside the loop carries on over the new room's objects from the same index.

Copy this exactly (`foreach_object` in Game.cpp). The C# Celeste does it differently, and its traces would not match the cart.

Lua also keeps a destroyed object alive while its function still runs. Celeste's player keeps executing after `kill_player(this)`, and may even call `next_room()`. So a destroyed object leaves the list at once, but its pool slot is not reused until the loop that is running it has finished (the `running` pointer and `sweep()`). Otherwise a new smoke object can overwrite a player whose update is half done.

### 3. Translate quirks, don't fix them

Port the cart's behaviour, including what looks like bugs. Examples from Celeste:

- `for i=start,abs(amount)` runs `abs(amount)+1` steps, so `move_x` moves one step more than you would expect. The game's speeds are tuned with that.
- `kill_player` calls `restart_room()` inside its loop, eight times.
- The player's `draw` clamps its position and zeroes its speed. That is game state changed during drawing.
- `_draw` returns early while `freeze > 0`.

`_draw` is also part of the simulation. Hair, clouds, particles, the big chest, the orb, the flag and the room title all change state while drawing. The trace harness therefore runs `draw()` with stub drawing, and the game must never skip `draw()` when PICO-8 would not.

### 4. Lua syntax and semantics to watch

- **PICO-8 shorthand:** `+=`, `!=`, `if (cond) stmt` with no `then`, and `?` for print. Find them with grep first; this cart had two unusual lines.
- **`a and b or c`:** this is a ternary only if `b` can't be false or nil. Translate each case carefully.
- **Numeric `for` loops:** their limits are evaluated once and may be fractional (`for i=1,this.index` with `index` 2.5).
- **Fractional values where C wants integers:** coordinates, sprite numbers and colours. PICO-8 floors them, so use `toi()` (flr to int) at every call into the drawing shim, never a C cast (which truncates toward zero).
- **Concatenation:** `..` of a number prints its decimal form. Write a tiny int-to-string helper rather than pulling in `snprintf`, which costs 3.5 KB.
- **Table constructors** are evaluated left to right. That matters for the order of `rnd()` calls (`{x=rnd(128), y=rnd(128)}`).
- **Top-level code** (clouds and particles built outside any function) runs before `_init`. Keep that order (`game::boot()`).
- **Arduino macros:** `min`, `max`, `map`, `abs`, `sq` and `word` can be macros. Use other names (`mn`, `mx`, `nabs`, `p8::map`).

### 5. Randomness

Exact PICO-8 `rnd()` can't be reproduced, so any cart is "the same game, different dice". Use one deterministic generator (`Fix.cpp`, xorshift32), and use the same one in the Lua shim when comparing.

Know which random values affect gameplay. In Celeste it was the balloons' bob phase, and that was enough to make a frame-perfect speedrun route miss.

### 6. Keep the game file platform-free

`Game.cpp` includes only `Fix.h`, `P8.h` and `Sounds.h`, and reads buttons from a global byte. The `.ino` owns CHGame: the frame loop, button mapping, saves, the pause menu and the debug hook.

This is what lets the same `Game.cpp` build into `tools/ref/trace.cpp` on the PC with no-op drawing. Additions that the cart didn't have go in the `.ino` behind a `config.h` switch, never into the translation.

## The frame loop on CHGame

```
dbg::poll(); if (!chgame.nextFrame()) return;
pollButtons → game::buttons; game::update();       // _update, while the last frame DMAs out
gfx_wait(); game::draw(); gfx_flushAsync();         // _draw
```

Two CHGame-specific lessons:

- **Every loop must flush a frame**, even when PICO-8 would show the old picture (frozen frames). The simulator's lockstep counts presented frames; without one it deadlocks. Re-flushing the unchanged framebuffer looks identical on the panel.
- **Don't let a menu's button leak into the game.** The A that picked TITLE also started a game on the title screen, because the cart tests `btn()`, which is held, not pressed. Mask jump and dash until they are released.

## The data

- **`__gfx__`:** each hex digit is a pixel, left to right. Pack two pixels a byte with the left one low, and the bytes copy straight into `gfx_fb` rows. Only sprites 0-127 are sprites if the cart uses the map's lower half.
- **`__map__`:** holds rows 0-31. Rows 32-63 live in the sheet's lower half (shared memory, `0x1000-0x1FFF`), read as bytes. Get this wrong and half the levels are garbage.
- **`__gff__`:** one flag byte per sprite. `map(..., layer)` draws a tile when `flags & layer == layer`, and never draws tile 0.
- **Palette:** the PICO-8 colours as RGB565 into `gfx_setPalette`. `pal(a,b)` is a 16-entry remap applied to every draw call, not only sprites.
- **Sound:** a note lasts `speed * 183/22050` s.
  - Slides become sweeps.
  - Noise becomes a scatter of pitches, or is dropped from music.
  - Notes below about 180 Hz go up whole octaves for the piezo.
  - Effects use `audio::GLIDE` to avoid clicks.
  - Music runs a song's patterns from loop start to loop end, as a Playtune score in LEAD mode.
  - It will need tuning by ear.
- **Verify the cart:** public copies are often modded (practice timers, TAS hooks). Fingerprint several copies section by section and take the consensus.

## Proving it: the golden trace harness

This was the part that made the port trustworthy, and it is cheap to build.

1. **Lua side** (`tools/ref/compare.py`): Lua 5.4 through Python's `lupa`.
   - A small text pass rewrites the PICO-8 syntax.
   - A shim provides `btn`, `rnd` (the same xorshift as the C++), `sin`/`cos`, `flr`, `add`/`del`/`count`/`all`/`foreach` (zepto8's), and `mget`/`fget` from the extracted data.
   - Drawing calls and `print` are no-ops; `sfx`/`music` are logged.
2. **C++ side** (`tools/ref/trace.cpp`): `Game.cpp` built for the PC with `num` as a double, the same stubs, and the same button file.
3. **Both** print one line per frame: room, deaths, timers, sounds, and every object's type, position, speed, remainder and sprite. The first differing frame is shown with the two before it.

Rules learned:

- **Compare doubles to 1e-9, not exactly.** The C library's `sin` and Lua's differ in the last bit.
- **Check the checker:** a 0.0000001 change to gravity has to fail it.
- **Make the inputs cover the game:** random but human-like presses (runs of a direction, jumps, dashes), started in every room by loading it directly, with and without later-game abilities.
- **Random presses rarely finish a room,** so also replay real routes. The community TAS for Celeste exists per level. Start its inputs on the frame the player appears, not on the room's first frame.
- **On 16.16** the C++ legitimately parts from Lua's doubles. That's PICO-8's own rounding, which the board follows. Use a looser comparison there (rooms, deaths, sounds, whole-pixel player position), and treat the double comparison as the correctness proof.

Then the same routes became `tools/ref/playthrough.py`: the whole game from boot, on the board's numbers and random seed, written out as a simulator script (`playthrough.txt`) with a picture per level. A level whose route misses on the board's numbers gets its start delayed a few frames, up to one balloon period.

## Checklist for the next cart

1. Get a clean `.p8`, and fingerprint it against other copies.
2. Copy `tools/p8extract.py`, `Fix.*` and `P8.*`; vendor CHGame (`tools/vendor_chgame.py`).
3. Grep the Lua for PICO-8 syntax and for every API call; extend `P8.cpp` and the Lua shim to match.
4. Translate in order, keeping names. Use `num` everywhere, `int16_t` counters, the pool with `all()` semantics, and quirks kept.
5. Build the trace harness before the game works on the device, and make it fail on a planted bug.
6. Run every room against the Lua until it all agrees; only then tune for the device.
7. Measure: `cl build` (flash, RAM), `cal` + `perf` in a script per room, `cl size` for soft-float.
8. Sound last, by ear on the board.
