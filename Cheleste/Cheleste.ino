// Cheleste: Celeste Classic for CHGame.
//
// Matt Thorson and Noel Berry's PICO-8 Celeste, rewritten in C++ from the
// cart's Lua (Game.cpp) with the cart's own sprites, map and sound
// (tools/p8extract.py, tools/p8audio.py). PICO-8's screen is this one,
// 128x128 in 16 colours, and the game runs at the cart's 30 frames a second.
//
// The frame: the buttons, the cart's _update() (while the last frame goes
// out to the panel by DMA), then gfx_wait() and the cart's _draw() into the
// framebuffer, then gfx_flushAsync(). A frozen frame (the dash's and the
// orb's freeze) draws nothing, as on PICO-8: the last picture goes out again.
//
// What the cart did not have (CHLS_EXTRAS): START pauses (CONTINUE,
// RESTART ROOM, TITLE) over the last picture, the game held; each new level
// is saved, and the title then offers B to continue from it (A starts afresh).
#include <CHGame.h>
#include "config.h"
#include "Game.h"
#include "P8.h"
#include "Save.h"
#include "Sounds.h"
#include "src/assets/Cart.h"

static const uint8_t JUMP_BUTTON = CHLS_SWAP_AB ? B_BUTTON : A_BUTTON;
static const uint8_t DASH_BUTTON = CHLS_SWAP_AB ? A_BUTTON : B_BUTTON;

// The CHGame's buttons as the cart's (btn(0) ... btn(5)).
static uint8_t cartButtons() {
    uint8_t b = 0;
    if (chgame.pressed(LEFT_BUTTON)) b |= 1 << game::K_LEFT;
    if (chgame.pressed(RIGHT_BUTTON)) b |= 1 << game::K_RIGHT;
    if (chgame.pressed(UP_BUTTON)) b |= 1 << game::K_UP;
    if (chgame.pressed(DOWN_BUTTON)) b |= 1 << game::K_DOWN;
    if (chgame.pressed(JUMP_BUTTON)) b |= 1 << game::K_JUMP;
    if (chgame.pressed(DASH_BUTTON)) b |= 1 << game::K_DASH;
    return b;
}

#if CHLS_EXTRAS
static bool paused;
static uint8_t choice;              // the pause menu's: CONTINUE, RESTART ROOM, TITLE
static bool wantContinue;           // the title was left with B: on to the saved level
static bool holdOff;                // the menu closed with A or B: the game sees neither until both are let go
static const char *const CHOICES[] = { "continue", "restart room", "title" };

// The pause menu: a box over the held game's last picture.
static void drawPause() {
    gfx_fillRect(28, 44, 72, 40, 0);
    gfx_rect(28, 44, 72, 40, 7);
    p8::print("paused", 52, 49, 6);
    for (uint8_t i = 0; i < 3; i++) {
        gfx_fillRect(34, 60 + i * 7, 3, 5, 0);
        if (i == choice) text35(34, 60 + i * 7, ">", 8);
        p8::print(CHOICES[i], 40, 60 + i * 7, i == choice ? 7 : 5);
    }
}

// The pause menu's buttons; false when it has closed.
static bool pauseInput() {
    if (chgame.justPressed(START_BUTTON)) return false;
    if (chgame.justPressed(UP_BUTTON)) choice = (uint8_t)((choice + 2) % 3);
    if (chgame.justPressed(DOWN_BUTTON)) choice = (uint8_t)((choice + 1) % 3);
    if (chgame.justPressed(JUMP_BUTTON) || chgame.justPressed(DASH_BUTTON)) {
        if (choice == 1) game::restartRoom();
        if (choice == 2) game::quitToTitle();
        holdOff = true;
        return false;
    }
    return true;
}

// The title with a saved game: A starts afresh, B goes on (over the cart's "a+b").
static void drawContinue() {
    char s[24] = "b: continue ";
    int level = (saved::get().level + 1) * 100;
    char *d = s + 12;
    char tmp[6];
    int n = 0;
    do { tmp[n++] = (char)('0' + level % 10); level /= 10; } while (level);
    while (n) *d++ = tmp[--n];
    *d++ = ' '; *d++ = 'm'; *d = 0;
    p8::rectfill(40, 78, 90, 86, 0);
    p8::print("a: new game", 42, 80, 5);
    p8::print(s, 34, 87, 5);
}
#endif

#if CHGAME_DEBUG
// The debug protocol's game commands (scripts: `say R 12`):
//   R <level> [djump]   play from level 0-30, as begin_game() would (djump 2: after the orb)
static bool hook(char cmd, const char *args) {
    if (cmd == 'R') {
        int level = (int)dbg::parseNum(args, 10), djump = (int)dbg::parseNum(args, 10);
        game::beginAt(level, djump);
        return true;
    }
    return false;
}
#endif

void setup() {
    chgame.boot();
    dbg::begin("CHLS " CHLS_VERSION);
#if CHGAME_DEBUG
    dbg::hook = hook;
#endif
    gfx_begin(GFX_DIV2, GFX_12BPP);
    gfx_setPalette(cart::PALETTE, 16);
    snd::begin();
#if CHLS_EXTRAS
    saved::begin();
#endif
    chgame.setFrameRate(30);
    game::boot();
}

void loop() {
    dbg::poll();
    if (!chgame.nextFrame()) return;

    dbg::markUpdateStart();
    chgame.pollButtons();
#if CHLS_EXTRAS
    bool title = game::levelIndex() == 31;
    if (paused) {
        paused = pauseInput();
        if (paused) {
            audio::update();
            dbg::markRenderStart();
            gfx_wait();
            saved::flush();
            drawPause();
            dbg::markRenderEnd();
            gfx_flushAsync();
            return;
        }
    } else if (!title && chgame.justPressed(START_BUTTON)) {
        paused = true;
        choice = 0;
        audio::update();
        gfx_wait();
        drawPause();                // over the last picture, which stays
        gfx_flushAsync();
        return;
    }
    if (title && !game::startGame && saved::has() && chgame.pressed(DASH_BUTTON) && !chgame.pressed(JUMP_BUTTON))
        wantContinue = true;
    int before = game::levelIndex();
#endif
    game::buttons = cartButtons();
#if CHLS_EXTRAS
    if (holdOff) {
        if (!chgame.pressed(JUMP_BUTTON) && !chgame.pressed(DASH_BUTTON)) holdOff = false;
        else game::buttons &= (uint8_t)~((1 << game::K_JUMP) | (1 << game::K_DASH));
    }
#endif
    game::update();
#if CHLS_EXTRAS
    int after = game::levelIndex();
    if (before == 31 && after == 0 && wantContinue) {
        game::resume(saved::get());
        wantContinue = false;
    } else if (after != before && after != 31) {
        if (after == 30) saved::clear();                // the summit: nothing left to continue
        else if (after > 0) saved::put(game::progress());
    }
#endif
    audio::update();

    dbg::markRenderStart();
    gfx_wait();
    if (game::frozen()) {           // the last picture again (a frame still goes out: the simulator's lockstep counts them)
        dbg::markRenderEnd();
        gfx_flushAsync();
        return;
    }
#if CHLS_EXTRAS
    saved::flush();
#endif
    game::draw();
#if CHLS_EXTRAS
    if (game::levelIndex() == 31 && saved::has() && !game::startGame) drawContinue();
#endif
    dbg::markRenderEnd();
    gfx_flushAsync();
}
