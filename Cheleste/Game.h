// Celeste Classic's game, ported from the cart's Lua (assets/celeste.p8).
//
// Game.cpp follows the Lua function by function, in its order, with its
// names: read the two side by side. What differs is only what C++ needs:
// the objects are a fixed pool instead of tables, each kind's fields are a
// union, and numbers are PICO-8's (Fix.h).
//
// Game.cpp knows nothing of CHGame: it draws through P8.h, plays through
// sfx()/music() (Sounds.h) and reads buttons from game::buttons, so the same
// file runs on the board, in the simulator and in tools/ref/'s trace harness.
#pragma once
#include <stdint.h>
#include "Fix.h"

namespace game {

// The cart's buttons (k_left ... k_dash), as bits of game::buttons.
enum : uint8_t { K_LEFT = 0, K_RIGHT = 1, K_UP = 2, K_DOWN = 3, K_JUMP = 4, K_DASH = 5 };
extern uint8_t buttons;

enum Type : uint8_t {
    PLAYER, PLAYER_SPAWN, SPRING, BALLOON, FALL_FLOOR, SMOKE, FRUIT, FLY_FRUIT, LIFEUP,
    FAKE_WALL, KEY, CHEST, PLATFORM, MESSAGE, BIG_CHEST, ORB, FLAG, ROOM_TITLE, TYPE_COUNT
};

struct Obj {
    uint8_t type;
    bool used, listed;              // the pool's: a slot taken; in the objects list
    bool collideable, solids, flipX, flipY;
    int8_t hbx, hby, hbw, hbh;      // hitbox
    num spr, x, y, spdx, spdy, remx, remy;
    union {
        struct { bool p_jump, p_dash, was_on_ground; int8_t grace, jbuffer, djump; int16_t dash_time, dash_effect_time;
                 num dash_target_x, dash_target_y, dash_accel_x, dash_accel_y, spr_off; } pl;
        struct { num target_x, target_y; int16_t state, delay; } spawn;
        struct { int16_t hide_in, hide_for, delay; } spring;
        struct { num offset, start; int16_t timer; } balloon;
        struct { int16_t state, delay; } ff;
        struct { num start, off; } fruit;
        struct { num start, step; bool fly; int16_t sfx_delay; } fly;
        struct { int16_t duration; num flash; } lifeup;
        struct { num start; int16_t timer; } chest;
        struct { int16_t dir; num last; } plat;
        struct { num index; int16_t last; } msg;
        struct { int16_t state, timer; } big;
        struct { int16_t score; bool show; } flag;
        struct { int16_t delay; } title;
    } u;
};

enum : uint8_t { MAX_OBJECTS = 40 };
extern Obj *objects[MAX_OBJECTS];   // the cart's objects table, in its order
extern uint8_t objectCount;
extern uint8_t objectPeak;          // the most ever at once (a check of MAX_OBJECTS)

struct Hair { num x, y; int8_t size; };
extern Hair hair[5];                // the player's (or the spawning player's): there is only ever one

// The cart's globals that the frame around the game, the tests and the
// traces look at.
extern int8_t roomX, roomY;
extern int16_t freeze, shake, deaths, frames, seconds, minutes;
extern int8_t maxDjump;
extern bool gotFruit[32];
extern bool startGame;

void boot();        // what the cart does on load: the clouds and particles, then _init()
void update();      // _update()
void draw();        // _draw(); draws nothing while frozen (the last frame stays)
bool frozen();      // the next draw() will draw nothing

int levelIndex();
void loadRoom(int x, int y);       // (tests and the debug hook) straight to a room
void beginAt(int level, int djump); // begin_game(), then on to level 0-30 (djump 0: the cart's)
void titleScreen();
Obj *findPlayer();

// Where a game has got to (CHLS_EXTRAS: saved at each new level, and the
// title's CONTINUE). Not the cart's: it had no saves.
struct Progress {
    uint8_t level, djump;
    uint16_t deaths, seconds, minutes;
    uint32_t fruit;             // got_fruit, a bit a level
};
Progress progress();
void resume(const Progress &p);
void quitToTitle();                 // (the pause menu) back to the title, the sky put back
void restartRoom();                 // (the pause menu) the room from its start, no death counted     // begin_game(), then on to p's level with p's counts, music and sky

}  // namespace game
