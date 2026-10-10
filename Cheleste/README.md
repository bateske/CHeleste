# Cheleste: Celeste Classic

Climb Celeste Mountain in 31 single-screen rooms: run, jump, wall-jump and dash past spikes, crumbling floors and springs to the summit. This is Maddy Thorson and Noel Berry's PICO-8 game, rewritten in C++ for CHGame.

![Cheleste gameplay](docs/gameplay.gif)

## Controls

| Button | Action |
|---|---|
| D-pad | Run left and right; with B, the direction of the dash; DOWN crouches, UP looks up |
| A | Jump; next to a wall, wall-jump |
| B | Dash (one in the air, two after the orb); a dash breaks cracked walls |
| START | Pause: continue, restart the room, or go back to the title |

## Rules

- Leave each room by its top edge. The fall at the bottom, and spikes, are fatal: the room starts again.
- A dash is used up in the air and comes back on the ground, from a balloon, from a spring, or from a strawberry.
- Crumbling blocks fall a moment after you touch them and come back later. Springs throw you up; a key opens a chest.
- Strawberries are optional. Some fly away when you dash, some are hidden in chests or behind cracked walls.
- The summit's flag shows your strawberries, your time and your deaths.

## How to play

Press A on the title to start. The time runs from the first room to the summit. Each new room is saved, and the title then offers B to continue from it. A starts a new climb. The game is the cart's, frame for frame, at its 30 frames a second, and its tunes and sound effects are played on the piezo.

To get it onto the handheld: in the Arduino IDE, open *File > Examples*, set *Tools > USB* to **Upload only**, and upload. From a clone, run `chgame upload`. Or copy the release's SD card zip to a card ([Installing](https://github.com/bateske/CHGame#installing)).

## Developer notes

- `Game.cpp` is the cart's Lua, function by function, in its order, and knows nothing of CHGame. `tools/ref/compare.py` runs it against the cart's own Lua frame by frame, in every room.
- `Fix.h` has PICO-8's 16.16 numbers on a chip with no FPU: wrapping `+ - *`, a truncating `/`, a flooring `flr`, and PICO-8's `%`. Literals are folded at compile time, so no floating point reaches the board.
- `P8.cpp` has PICO-8's drawing calls straight into `gfx_fb`. The cart's sheet is already packed the way the framebuffer is, so a sprite row is four bytes.
- `tools/p8extract.py` and `tools/p8audio.py` turn the cart into `src/assets/` and `src/audio/`. The sound becomes `audio::` effects and Playtune scores in LEAD mode.
- `tools/scripts/playthrough.txt` plays the whole game, boot to summit. It is generated from the community's Any% TAS by `tools/ref/playthrough.py`.
- More in [NOTES.md](NOTES.md).

## Credits

Celeste Classic (2015) by Maddy Thorson and Noel Berry: the game, its sprites, map, music and sound effects, from its PICO-8 cart. The port's code is MIT licensed; see [NOTICE](NOTICE).
