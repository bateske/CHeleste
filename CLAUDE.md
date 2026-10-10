# Cheleste: working notes for Claude

Celeste Classic (PICO-8) ported to CHGame in C++. Read `Cheleste/NOTES.md`
first: the layout, how faithfulness is checked, the measured budgets.

## Rules

- `Cheleste/Game.cpp` is the cart's Lua (`assets/celeste.p8`, not in the
  repo; see BUILDING.md) translated in order. Keep it that way: no
  CHGame calls in it (it also builds for the PC in `tools/ref/`), no
  "improvements" to the cart's behaviour. A change to the game is a
  `config.h` switch in `Cheleste.ino`, not an edit of the port.
- After touching `Game.cpp`, `Fix.*` or anything the game calls, run
  `python tools/ref/compare.py` (all must agree) and `./cl check`.
- Numbers are `num` (Fix.h): never `float`/`double` in device code. Write
  literals as `num(0.5)`; `cl size` must show no soft-float (`__adddf3` ...).
- `Cheleste/src/` is generated (`tools/p8extract.py`, `tools/p8audio.py`):
  never edit it by hand. `chgame/` is vendored CHGame: changes go upstream.
- Draw only between `gfx_wait()` and `gfx_flushAsync()`, and every frame
  must flush (the simulator's lockstep counts flushed frames).
- Budgets: flash <= 50,432 B (both save pages), static RAM <= 18,416 B;
  `./cl build` prints both. About 1 KB of RAM is free.
- LF line endings (Python on Windows writes CRLF in text mode: use
  `newline=""`).

## Commands

`./cl build | upload | test | check | gif | audio out/audio`,
`./cl run Cheleste/tools/scripts/<s>.txt out/<s>`; `say R <level> [djump]`
in a script jumps to a level (debug builds and the simulator).
