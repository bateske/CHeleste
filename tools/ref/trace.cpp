// The port's side of the golden traces (tools/ref/compare.py): Game.cpp on
// the PC with nothing drawn, fed a file of buttons, printing its state after
// every frame in the format ref.lua prints the cart's.
//
//   trace <inputs> [room] [maxdjump]
//
// <inputs>: one byte a frame (the cart's btn() bits). room 0-31 starts there
// (straight after the title, as begin_game() does); -1 (the default) starts
// at the title; -2 starts at the title as the board does (its own rnd()
// seed: the frames match a simulator run from boot).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "Game.h"
#include "P8.h"
#include "Sounds.h"
#include "src/assets/Cart.h"

// Nothing is drawn; the map and flags are the cart's.
namespace p8 {
void camera(int, int) {}
void pal() {}
void pal(uint8_t, uint8_t) {}
void cls(uint8_t) {}
void spr(int, int, int, bool, bool) {}
void map(int, int, int, int, int, int, uint8_t) {}
void rectfill(int, int, int, int, uint8_t) {}
void circfill(int, int, int, uint8_t) {}
void line(int, int, int, int, uint8_t) {}
void print(const char *, int, int, uint8_t) {}
uint8_t mget(int x, int y) { return x < 0 || x > 127 || y < 0 || y > 63 ? 0 : cart::MAP[y * 128 + x]; }
bool fget(uint8_t s, uint8_t f) { return s < 128 && (cart::FLAGS[s] >> f) & 1; }
}  // namespace p8

static char events[512];
static void event(const char *s) {
    size_t n = strlen(events);
    snprintf(events + n, sizeof events - n, "%s", s);
}

namespace snd {
void begin() {}
void sfx(int n) { char b[16]; snprintf(b, sizeof b, " sfx%d", n); event(b); }
void music(int n, int, int) { char b[16]; snprintf(b, sizeof b, " mus%d", n); event(b); }
}  // namespace snd

static void put(double v) {
    if (v == 0) v = 0;       // no -0
    printf(" %.17g", v);
}

static double d(num v) {
#if CHLS_NUM_DOUBLE
    return v;
#else
    return v.v / 65536.0;
#endif
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: trace <inputs> [room] [maxdjump]\n"); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 2; }
    static uint8_t in[1 << 20];
    size_t frames = fread(in, 1, sizeof in, f);
    fclose(f);
    int room = argc > 2 ? atoi(argv[2]) : -1;

    if (room != -2) rndSeed(1);
    game::boot();
    if (room >= 0) {
        game::startGame = false;
        game::loadRoom(room % 8, room / 8);
        if (argc > 3) game::maxDjump = (int8_t)atoi(argv[3]);
    }
    for (size_t i = 0; i < frames; i++) {
        events[0] = 0;
        game::buttons = in[i];
        game::update();
        game::draw();
        printf("%zu r%d d%d fz%d sh%d mdj%d%s |", i, game::levelIndex(), game::deaths, game::freeze, game::shake,
               game::maxDjump, events);
        for (uint8_t k = 0; k < game::objectCount; k++) {
            game::Obj *o = game::objects[k];
            printf(" %d", o->type);
            put(d(o->x)); put(d(o->y)); put(d(o->spdx)); put(d(o->spdy)); put(d(o->remx)); put(d(o->remy));
            put(d(o->spr));
            if (o->type == game::PLAYER) printf(" dj%d", o->u.pl.djump);
            printf(";");
        }
        printf("\n");
    }
    fprintf(stderr, "peak objects %d\n", game::objectPeak);
    return 0;
}
