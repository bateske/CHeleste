# Building Cheleste

Needs Python 3 (with Pillow and ziglang, for the simulator), arduino-cli and
the CHGame board package 0.3.0, the same as any CHGame game (`chgame/tools/README.md`).
The CHGame tools are vendored in `chgame/` (`chgame/VENDORED.md` names the
commit; `python tools/vendor_chgame.py <CHGame checkout>` refreshes them).

`cl` (Git Bash) and `cl.cmd` (Windows) run the CHGame tools on the sketch:

```bash
./cl build
```

| Command | What |
|---|---|
| `./cl build` | the release image, with its flash and RAM |
| `./cl build --debug` | with the debug protocol (scripts on the board) |
| `./cl upload` | onto the board |
| `./cl run Cheleste/tools/scripts/smoke.txt out/smoke` | a script in the simulator (pictures in `Cheleste/out/smoke`) |
| `./cl test` | the host tests |
| `./cl check` | everything that needs no board: tests, every script twice, the device build |
| `./cl gif` | the README's `docs/gameplay.gif` |
| `./cl audio out/audio` | the effects and songs as WAV |

## From the cart

The cart is not in the repository; the files made from it are. To make them
again, put `celeste.p8` in `assets/` (in PICO-8: `load #celeste`, then
`save celeste.p8`) and run:

```bash
python tools/p8extract.py
```

```bash
python tools/p8audio.py
```

## Checking against the original

With the cart in `assets/` and `pip install lupa`:

```bash
python tools/ref/compare.py
```

That runs the cart's own Lua and the port side by side, in every room, frame by frame.

```bash
python tools/ref/tas.py --lua
```

That replays the community's TAS level by level. `python tools/ref/playthrough.py`
writes the whole-game script `Cheleste/tools/scripts/playthrough.txt`.
Cheleste/NOTES.md has what they check.
