// Celeste Classic, from the cart's Lua (Game.h). The sections and functions
// are the cart's, in its order; the Lua's comments are kept.
#include <string.h>
#include "Game.h"
#include "P8.h"
#include "Sounds.h"

namespace game {

uint8_t buttons;
static inline bool btn(uint8_t k) { return (buttons >> k) & 1; }

// globals --
//-----------

int8_t roomX, roomY;
Obj *objects[MAX_OBJECTS];
uint8_t objectCount, objectPeak;
int16_t freeze, shake;
static bool will_restart;
static int16_t delay_restart;
bool gotFruit[32];                  // got_fruit[1..30] is gotFruit[0..29]; 30, 31: the summit and title (never set)
static bool has_dashed;
static int16_t sfx_timer;
static bool has_key, pause_player, flash_bg, new_bg;
static int16_t music_timer;
int16_t frames, seconds, minutes, deaths;
int8_t maxDjump;
bool startGame;
static int16_t start_game_flash;

static Obj pool[MAX_OBJECTS];
static Obj spare;                   // init_object() with the pool full: drawn nowhere, kept nowhere
static Obj *running;                // the object whose update/draw is running (its slot is kept until it returns)

Hair hair[5];

static void psfx(int num_) { if (sfx_timer <= 0) snd::sfx(num_); }
static Obj *init_object(uint8_t type, num x, num y);
static void destroy_object(Obj *obj);
static void kill_player(Obj *obj);
static void restart_room();
static void next_room();
static void load_room(int x, int y);
static bool solid_at(num x, num y, int w, int h);
static bool ice_at(num x, num y, int w, int h);
static bool spikes_at(num x, num y, int w, int h, num xspd, num yspd);
static void draw_time(int x, int y);

// The tile each kind is placed with (0: none), and whether it is left out
// of a room whose fruit has been got (if_not_fruit).
static const uint8_t TILE[TYPE_COUNT] = {
    0, 1, 18, 22, 23, 0, 26, 28, 0, 64, 8, 20, 0, 86, 96, 0, 118, 0 };
static const bool IF_NOT_FRUIT[TYPE_COUNT] = {
    0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0 };
// The cart's types table, in its add() order: load_room() looks tiles up in it.
static const uint8_t TYPES[] = { PLAYER_SPAWN, SPRING, BALLOON, FALL_FLOOR, FRUIT, FLY_FRUIT, FAKE_WALL,
                                 KEY, CHEST, MESSAGE, BIG_CHEST, FLAG };

// The pool. A destroyed object leaves the list at once (del()); its slot is
// freed after the loop that is running it, as Lua keeps a table alive while
// a function still holds it.
static void sweep() {
    for (uint8_t i = 0; i < MAX_OBJECTS; i++)
        if (pool[i].used && !pool[i].listed && &pool[i] != running) pool[i].used = false;
}

// foreach(objects, f) with PICO-8's all(): the index moves on only when the
// object at it is still the one just visited, so deleting the current object
// skips nothing and objects added on the way are visited too.
template <class F> static void foreach_object(F f) {
    if (!objectCount) return;
    uint8_t i = 0;
    Obj *prev = nullptr;
    Obj *outer = running;
    for (;;) {
        if (i < objectCount && objects[i] == prev) i++;
        if (i >= objectCount) break;
        prev = objects[i];
        running = prev;
        f(prev);
    }
    running = outer;
    sweep();
}

int levelIndex() { return roomX % 8 + roomY * 8; }
static int level_index() { return levelIndex(); }
static bool is_title() { return level_index() == 31; }

// entry point --
//---------------

void titleScreen() {
    memset(gotFruit, 0, sizeof gotFruit);
    frames = 0;
    deaths = 0;
    maxDjump = 1;
    startGame = false;
    start_game_flash = 0;
    snd::music(40, 0, 7);
    load_room(7, 3);
}

static void begin_game() {
    frames = 0;
    seconds = 0;
    minutes = 0;
    music_timer = 0;
    startGame = false;
    snd::music(0, 0, 7);
    load_room(0, 0);
}

// effects --
//-----------

struct Cloud { num x, y, spd, w; };
static Cloud clouds[17];
struct Particle { num x, y, s, spd, off, c; };
static Particle particles[25];
struct DeadParticle { num x, y, t, spdx, spdy; };
static DeadParticle dead_particles[8];
static uint8_t deadCount;
// The big chest's light (its particles table: there is only ever one big chest opening).
struct Ray { num x, y, h, spd; };
static Ray rays[50];
static uint8_t rayCount;

void boot() {
    for (int i = 0; i <= 16; i++) {
        Cloud &c = clouds[i];
        c.x = rnd(128);
        c.y = rnd(128);
        c.spd = 1 + rnd(4);
        c.w = 32 + rnd(32);
    }
    for (int i = 0; i <= 24; i++) {
        Particle &p = particles[i];
        p.x = rnd(128);
        p.y = rnd(128);
        p.s = 0 + flr(rnd(5) / 4);
        p.spd = num(0.25) + rnd(5);
        p.off = rnd(1);
        p.c = 6 + flr(num(0.5) + rnd(1));
    }
    deadCount = 0;
    titleScreen();      // _init()
}

// object functions (the methods each object had) --
//---------------------------------------------------

static Obj *collide(Obj *obj, uint8_t type, int ox, int oy) {
    uint8_t n = objectCount;
    for (uint8_t i = 0; i < n && i < objectCount; i++) {
        Obj *other = objects[i];
        if (other->type == type && other != obj && other->collideable &&
            other->x + other->hbx + other->hbw > obj->x + obj->hbx + ox &&
            other->y + other->hby + other->hbh > obj->y + obj->hby + oy &&
            other->x + other->hbx < obj->x + obj->hbx + obj->hbw + ox &&
            other->y + other->hby < obj->y + obj->hby + obj->hbh + oy)
            return other;
    }
    return nullptr;
}

static bool check(Obj *obj, uint8_t type, int ox, int oy) { return collide(obj, type, ox, oy) != nullptr; }

static bool is_solid(Obj *obj, int ox, int oy) {
    if (oy > 0 && !check(obj, PLATFORM, ox, 0) && check(obj, PLATFORM, ox, oy)) return true;
    return solid_at(obj->x + obj->hbx + ox, obj->y + obj->hby + oy, obj->hbw, obj->hbh) ||
           check(obj, FALL_FLOOR, ox, oy) || check(obj, FAKE_WALL, ox, oy);
}

static bool is_ice(Obj *obj, int ox, int oy) {
    return ice_at(obj->x + obj->hbx + ox, obj->y + obj->hby + oy, obj->hbw, obj->hbh);
}

// for i=start,abs(amount): abs(amount)-start+1 steps (the cart's own count).
static void move_x(Obj *obj, int amount, int start) {
    if (obj->solids) {
        int step = amount > 0 ? 1 : amount < 0 ? -1 : 0;
        int n = amount < 0 ? -amount : amount;
        for (int i = start; i <= n; i++) {
            if (!is_solid(obj, step, 0)) {
                obj->x += step;
            } else {
                obj->spdx = 0;
                obj->remx = 0;
                break;
            }
        }
    } else {
        obj->x += amount;
    }
}

static void move_y(Obj *obj, int amount) {
    if (obj->solids) {
        int step = amount > 0 ? 1 : amount < 0 ? -1 : 0;
        int n = amount < 0 ? -amount : amount;
        for (int i = 0; i <= n; i++) {
            if (!is_solid(obj, 0, step)) {
                obj->y += step;
            } else {
                obj->spdy = 0;
                obj->remy = 0;
                break;
            }
        }
    } else {
        obj->y += amount;
    }
}

static void move(Obj *obj, num ox, num oy) {
    int amount;
    // [x] get move amount
    obj->remx += ox;
    amount = toi(obj->remx + num(0.5));
    obj->remx -= amount;
    move_x(obj, amount, 0);

    // [y] get move amount
    obj->remy += oy;
    amount = toi(obj->remy + num(0.5));
    obj->remy -= amount;
    move_y(obj, amount);
}

static bool maybe() { return rnd(1) < num(0.5); }

// player entity --
//-----------------

static void create_hair(Obj *obj) {
    for (int i = 0; i <= 4; i++) {
        hair[i].x = obj->x;
        hair[i].y = obj->y;
        int s = 3 - i;
        hair[i].size = (int8_t)(s > 2 ? 2 : s < 1 ? 1 : s);
    }
}

static void set_hair_color(int djump) {
    p8::pal(8, djump == 1 ? 8 : djump == 2 ? 7 + toi(mod(num(frames) / 3, 2)) * 4 : 12);
}

static void draw_hair(Obj *obj, int facing) {
    num lastx = obj->x + 4 - facing * 2, lasty = obj->y + (btn(K_DOWN) ? 4 : 3);
    for (int i = 0; i < 5; i++) {
        Hair &h = hair[i];
        h.x += (lastx - h.x) / num(1.5);
        h.y += (lasty + num(0.5) - h.y) / num(1.5);
        p8::circfill(toi(h.x), toi(h.y), h.size, 8);
        lastx = h.x;
        lasty = h.y;
    }
}

static void unset_hair_color() { p8::pal(8, 8); }

static void player_init(Obj *t) {
    t->u.pl.p_jump = false;
    t->u.pl.p_dash = false;
    t->u.pl.grace = 0;
    t->u.pl.jbuffer = 0;
    t->u.pl.djump = maxDjump;
    t->u.pl.dash_time = 0;
    t->u.pl.dash_effect_time = 0;
    t->u.pl.dash_target_x = t->u.pl.dash_target_y = 0;
    t->u.pl.dash_accel_x = t->u.pl.dash_accel_y = 0;
    t->hbx = 1; t->hby = 3; t->hbw = 6; t->hbh = 5;
    t->u.pl.spr_off = 0;
    t->u.pl.was_on_ground = false;
    create_hair(t);
}

static void player_update(Obj *t) {
    auto &p = t->u.pl;
    if (pause_player) return;

    int input = btn(K_RIGHT) ? 1 : (btn(K_LEFT) ? -1 : 0);

    // spikes collide
    if (spikes_at(t->x + t->hbx, t->y + t->hby, t->hbw, t->hbh, t->spdx, t->spdy)) kill_player(t);

    // bottom death
    if (t->y > 128) kill_player(t);

    bool on_ground = is_solid(t, 0, 1);
    bool on_ice = is_ice(t, 0, 1);

    // smoke particles
    if (on_ground && !p.was_on_ground) init_object(SMOKE, t->x, t->y + 4);

    bool jump = btn(K_JUMP) && !p.p_jump;
    p.p_jump = btn(K_JUMP);
    if (jump) {
        p.jbuffer = 4;
    } else if (p.jbuffer > 0) {
        p.jbuffer -= 1;
    }

    bool dash = btn(K_DASH) && !p.p_dash;
    p.p_dash = btn(K_DASH);

    if (on_ground) {
        p.grace = 6;
        if (p.djump < maxDjump) {
            psfx(54);
            p.djump = maxDjump;
        }
    } else if (p.grace > 0) {
        p.grace -= 1;
    }

    p.dash_effect_time -= 1;
    if (p.dash_time > 0) {
        init_object(SMOKE, t->x, t->y);
        p.dash_time -= 1;
        t->spdx = appr(t->spdx, p.dash_target_x, p.dash_accel_x);
        t->spdy = appr(t->spdy, p.dash_target_y, p.dash_accel_y);
    } else {
        // move
        num maxrun = 1;
        num accel = num(0.6);
        num deccel = num(0.15);

        if (!on_ground) {
            accel = num(0.4);
        } else if (on_ice) {
            accel = num(0.05);
            if (input == (t->flipX ? -1 : 1)) accel = num(0.05);
        }

        if (nabs(t->spdx) > maxrun) {
            t->spdx = appr(t->spdx, sign(t->spdx) * maxrun, deccel);
        } else {
            t->spdx = appr(t->spdx, input * maxrun, accel);
        }

        // facing
        if (t->spdx != 0) t->flipX = (t->spdx < 0);

        // gravity
        num maxfall = 2;
        num gravity = num(0.21);

        if (nabs(t->spdy) <= num(0.15)) gravity *= num(0.5);

        // wall slide
        if (input != 0 && is_solid(t, input, 0) && !is_ice(t, input, 0)) {
            maxfall = num(0.4);
            if (rnd(10) < 2) init_object(SMOKE, t->x + input * 6, t->y);
        }

        if (!on_ground) t->spdy = appr(t->spdy, maxfall, gravity);

        // jump
        if (p.jbuffer > 0) {
            if (p.grace > 0) {
                // normal jump
                psfx(1);
                p.jbuffer = 0;
                p.grace = 0;
                t->spdy = -2;
                init_object(SMOKE, t->x, t->y + 4);
            } else {
                // wall jump
                int wall_dir = (is_solid(t, -3, 0) ? -1 : is_solid(t, 3, 0) ? 1 : 0);
                if (wall_dir != 0) {
                    psfx(2);
                    p.jbuffer = 0;
                    t->spdy = -2;
                    t->spdx = -wall_dir * (maxrun + 1);
                    if (!is_ice(t, wall_dir * 3, 0)) init_object(SMOKE, t->x + wall_dir * 6, t->y);
                }
            }
        }

        // dash
        num d_full = 5;
        num d_half = d_full * num(0.70710678118);

        if (p.djump > 0 && dash) {
            init_object(SMOKE, t->x, t->y);
            p.djump -= 1;
            p.dash_time = 4;
            has_dashed = true;
            p.dash_effect_time = 10;
            int v_input = (btn(K_UP) ? -1 : (btn(K_DOWN) ? 1 : 0));
            if (input != 0) {
                if (v_input != 0) {
                    t->spdx = input * d_half;
                    t->spdy = v_input * d_half;
                } else {
                    t->spdx = input * d_full;
                    t->spdy = 0;
                }
            } else if (v_input != 0) {
                t->spdx = 0;
                t->spdy = v_input * d_full;
            } else {
                t->spdx = (t->flipX ? -1 : 1);
                t->spdy = 0;
            }

            psfx(3);
            freeze = 2;
            shake = 6;
            p.dash_target_x = 2 * sign(t->spdx);
            p.dash_target_y = 2 * sign(t->spdy);
            p.dash_accel_x = num(1.5);
            p.dash_accel_y = num(1.5);

            if (t->spdy < 0) p.dash_target_y *= num(.75);

            if (t->spdy != 0) p.dash_accel_x *= num(0.70710678118);
            if (t->spdx != 0) p.dash_accel_y *= num(0.70710678118);
        } else if (dash && p.djump <= 0) {
            psfx(9);
            init_object(SMOKE, t->x, t->y);
        }
    }

    // animation
    p.spr_off += num(0.25);
    if (!on_ground) {
        if (is_solid(t, input, 0)) {
            t->spr = 5;
        } else {
            t->spr = 3;
        }
    } else if (btn(K_DOWN)) {
        t->spr = 6;
    } else if (btn(K_UP)) {
        t->spr = 7;
    } else if ((t->spdx == 0) || (!btn(K_LEFT) && !btn(K_RIGHT))) {
        t->spr = 1;
    } else {
        t->spr = 1 + mod(p.spr_off, 4);
    }

    // next level
    if (t->y < -4 && level_index() < 30) next_room();

    // was on the ground
    p.was_on_ground = on_ground;
}

static void player_draw(Obj *t) {
    // clamp in screen
    if (t->x < -1 || t->x > 121) {
        t->x = mid3(t->x, -1, 121);
        t->spdx = 0;
    }

    set_hair_color(t->u.pl.djump);
    draw_hair(t, t->flipX ? -1 : 1);
    p8::spr(toi(t->spr), toi(t->x), toi(t->y), t->flipX, t->flipY);
    unset_hair_color();
}

static void spawn_init(Obj *t) {
    snd::sfx(4);
    t->spr = 3;
    t->u.spawn.target_x = t->x;
    t->u.spawn.target_y = t->y;
    t->y = 128;
    t->spdy = -4;
    t->u.spawn.state = 0;
    t->u.spawn.delay = 0;
    t->solids = false;
    create_hair(t);
}

static void spawn_update(Obj *t) {
    auto &s = t->u.spawn;
    // jumping up
    if (s.state == 0) {
        if (t->y < s.target_y + 16) {
            s.state = 1;
            s.delay = 3;
        }
    // falling
    } else if (s.state == 1) {
        t->spdy += num(0.5);
        if (t->spdy > 0 && s.delay > 0) {
            t->spdy = 0;
            s.delay -= 1;
        }
        if (t->spdy > 0 && t->y > s.target_y) {
            t->y = s.target_y;
            t->spdx = 0;
            t->spdy = 0;
            s.state = 2;
            s.delay = 5;
            shake = 5;
            init_object(SMOKE, t->x, t->y + 4);
            snd::sfx(5);
        }
    // landing
    } else if (s.state == 2) {
        s.delay -= 1;
        t->spr = 6;
        if (s.delay < 0) {
            destroy_object(t);
            init_object(PLAYER, t->x, t->y);
        }
    }
}

static void spawn_draw(Obj *t) {
    set_hair_color(maxDjump);
    draw_hair(t, 1);
    p8::spr(toi(t->spr), toi(t->x), toi(t->y), t->flipX, t->flipY);
    unset_hair_color();
}

static void break_fall_floor(Obj *obj);

static void spring_init(Obj *t) {
    t->u.spring.hide_in = 0;
    t->u.spring.hide_for = 0;
    t->u.spring.delay = 0;
}

static void spring_update(Obj *t) {
    auto &s = t->u.spring;
    if (s.hide_for > 0) {
        s.hide_for -= 1;
        if (s.hide_for <= 0) {
            t->spr = 18;
            s.delay = 0;
        }
    } else if (t->spr == 18) {
        Obj *hit = collide(t, PLAYER, 0, 0);
        if (hit && hit->spdy >= 0) {
            t->spr = 19;
            hit->y = t->y - 4;
            hit->spdx *= num(0.2);
            hit->spdy = -3;
            hit->u.pl.djump = maxDjump;
            s.delay = 10;
            init_object(SMOKE, t->x, t->y);

            // breakable below us
            Obj *below = collide(t, FALL_FLOOR, 0, 1);
            if (below) break_fall_floor(below);

            psfx(8);
        }
    } else if (s.delay > 0) {
        s.delay -= 1;
        if (s.delay <= 0) t->spr = 18;
    }
    // begin hiding
    if (s.hide_in > 0) {
        s.hide_in -= 1;
        if (s.hide_in <= 0) {
            s.hide_for = 60;
            t->spr = 0;
        }
    }
}

static void break_spring(Obj *obj) { obj->u.spring.hide_in = 15; }

static void balloon_init(Obj *t) {
    t->u.balloon.offset = rnd(1);
    t->u.balloon.start = t->y;
    t->u.balloon.timer = 0;
    t->hbx = -1; t->hby = -1; t->hbw = 10; t->hbh = 10;
}

static void balloon_update(Obj *t) {
    auto &b = t->u.balloon;
    if (t->spr == 22) {
        b.offset += num(0.01);
        t->y = b.start + p8sin(b.offset) * 2;
        Obj *hit = collide(t, PLAYER, 0, 0);
        if (hit && hit->u.pl.djump < maxDjump) {
            psfx(6);
            init_object(SMOKE, t->x, t->y);
            hit->u.pl.djump = maxDjump;
            t->spr = 0;
            b.timer = 60;
        }
    } else if (b.timer > 0) {
        b.timer -= 1;
    } else {
        psfx(7);
        init_object(SMOKE, t->x, t->y);
        t->spr = 22;
    }
}

static void balloon_draw(Obj *t) {
    if (t->spr == 22) {
        p8::spr(toi(13 + mod(t->u.balloon.offset * 8, 3)), toi(t->x), toi(t->y + 6));
        p8::spr(toi(t->spr), toi(t->x), toi(t->y));
    }
}

static void fall_floor_init(Obj *t) {
    t->u.ff.state = 0;
    t->u.ff.delay = 0;
}

static void fall_floor_update(Obj *t) {
    auto &f = t->u.ff;
    // idling
    if (f.state == 0) {
        if (check(t, PLAYER, 0, -1) || check(t, PLAYER, -1, 0) || check(t, PLAYER, 1, 0)) break_fall_floor(t);
    // shaking
    } else if (f.state == 1) {
        f.delay -= 1;
        if (f.delay <= 0) {
            f.state = 2;
            f.delay = 60;   // how long it hides for
            t->collideable = false;
        }
    // invisible, waiting to reset
    } else if (f.state == 2) {
        f.delay -= 1;
        if (f.delay <= 0 && !check(t, PLAYER, 0, 0)) {
            psfx(7);
            f.state = 0;
            t->collideable = true;
            init_object(SMOKE, t->x, t->y);
        }
    }
}

static void fall_floor_draw(Obj *t) {
    auto &f = t->u.ff;
    if (f.state != 2) {
        if (f.state != 1) {
            p8::spr(23, toi(t->x), toi(t->y));
        } else {
            p8::spr(toi(23 + (15 - num(f.delay)) / 5), toi(t->x), toi(t->y));
        }
    }
}

static void break_fall_floor(Obj *obj) {
    if (obj->u.ff.state == 0) {
        psfx(15);
        obj->u.ff.state = 1;
        obj->u.ff.delay = 15;   // how long until it falls
        init_object(SMOKE, obj->x, obj->y);
        Obj *hit = collide(obj, SPRING, 0, -1);
        if (hit) break_spring(hit);
    }
}

static void smoke_init(Obj *t) {
    t->spr = 29;
    t->spdy = num(-0.1);
    t->spdx = num(0.3) + rnd(num(0.2));
    t->x += -1 + rnd(2);
    t->y += -1 + rnd(2);
    t->flipX = maybe();
    t->flipY = maybe();
    t->solids = false;
}

static void smoke_update(Obj *t) {
    t->spr += num(0.2);
    if (t->spr >= 32) destroy_object(t);
}

static void fruit_init(Obj *t) {
    t->u.fruit.start = t->y;
    t->u.fruit.off = 0;
}

static void fruit_update(Obj *t) {
    Obj *hit = collide(t, PLAYER, 0, 0);
    if (hit) {
        hit->u.pl.djump = maxDjump;
        sfx_timer = 20;
        snd::sfx(13);
        gotFruit[level_index()] = true;
        init_object(LIFEUP, t->x, t->y);
        destroy_object(t);
    }
    t->u.fruit.off += 1;
    t->y = t->u.fruit.start + p8sin(t->u.fruit.off / 40) * num(2.5);
}

static void fly_fruit_init(Obj *t) {
    t->u.fly.start = t->y;
    t->u.fly.fly = false;
    t->u.fly.step = num(0.5);
    t->solids = false;
    t->u.fly.sfx_delay = 8;
}

static void fly_fruit_update(Obj *t) {
    auto &f = t->u.fly;
    // fly away
    if (f.fly) {
        if (f.sfx_delay > 0) {
            f.sfx_delay -= 1;
            if (f.sfx_delay <= 0) {
                sfx_timer = 20;
                snd::sfx(14);
            }
        }
        t->spdy = appr(t->spdy, num(-3.5), num(0.25));
        if (t->y < -16) destroy_object(t);
    // wait
    } else {
        if (has_dashed) f.fly = true;
        f.step += num(0.05);
        t->spdy = p8sin(f.step) * num(0.5);
    }
    // collect
    Obj *hit = collide(t, PLAYER, 0, 0);
    if (hit) {
        hit->u.pl.djump = maxDjump;
        sfx_timer = 20;
        snd::sfx(13);
        gotFruit[level_index()] = true;
        init_object(LIFEUP, t->x, t->y);
        destroy_object(t);
    }
}

static void fly_fruit_draw(Obj *t) {
    num off = 0;
    if (!t->u.fly.fly) {
        num dir = p8sin(t->u.fly.step);
        if (dir < 0) off = 1 + mx(0, sign(t->y - t->u.fly.start));
    } else {
        off = mod(off + num(0.25), 3);
    }
    p8::spr(toi(45 + off), toi(t->x - 6), toi(t->y - 2), true, false);
    p8::spr(toi(t->spr), toi(t->x), toi(t->y));
    p8::spr(toi(45 + off), toi(t->x + 6), toi(t->y - 2));
}

static void lifeup_init(Obj *t) {
    t->spdy = num(-0.25);
    t->u.lifeup.duration = 30;
    t->x -= 2;
    t->y -= 4;
    t->u.lifeup.flash = 0;
    t->solids = false;
}

static void lifeup_update(Obj *t) {
    t->u.lifeup.duration -= 1;
    if (t->u.lifeup.duration <= 0) destroy_object(t);
}

static void lifeup_draw(Obj *t) {
    t->u.lifeup.flash += num(0.5);
    p8::print("1000", toi(t->x - 2), toi(t->y), toi(7 + mod(t->u.lifeup.flash, 2)));
}

static void fake_wall_update(Obj *t) {
    t->hbx = -1; t->hby = -1; t->hbw = 18; t->hbh = 18;
    Obj *hit = collide(t, PLAYER, 0, 0);
    if (hit && hit->u.pl.dash_effect_time > 0) {
        hit->spdx = -sign(hit->spdx) * num(1.5);
        hit->spdy = num(-1.5);
        hit->u.pl.dash_time = -1;
        sfx_timer = 20;
        snd::sfx(16);
        destroy_object(t);
        init_object(SMOKE, t->x, t->y);
        init_object(SMOKE, t->x + 8, t->y);
        init_object(SMOKE, t->x, t->y + 8);
        init_object(SMOKE, t->x + 8, t->y + 8);
        init_object(FRUIT, t->x + 4, t->y + 4);
    }
    t->hbx = 0; t->hby = 0; t->hbw = 16; t->hbh = 16;
}

static void fake_wall_draw(Obj *t) {
    int x = toi(t->x), y = toi(t->y);
    p8::spr(64, x, y);
    p8::spr(65, x + 8, y);
    p8::spr(80, x, y + 8);
    p8::spr(81, x + 8, y + 8);
}

static void key_update(Obj *t) {
    int was = toi(t->spr);
    t->spr = 9 + (p8sin(num(frames) / 30) + num(0.5)) * 1;
    int is = toi(t->spr);
    if (is == 10 && is != was) t->flipX = !t->flipX;
    if (check(t, PLAYER, 0, 0)) {
        snd::sfx(23);
        sfx_timer = 10;
        destroy_object(t);
        has_key = true;
    }
}

static void chest_init(Obj *t) {
    t->x -= 4;
    t->u.chest.start = t->x;
    t->u.chest.timer = 20;
}

static void chest_update(Obj *t) {
    if (has_key) {
        t->u.chest.timer -= 1;
        t->x = t->u.chest.start - 1 + rnd(3);
        if (t->u.chest.timer <= 0) {
            sfx_timer = 20;
            snd::sfx(16);
            init_object(FRUIT, t->x, t->y - 4);
            destroy_object(t);
        }
    }
}

static void platform_init(Obj *t) {
    t->x -= 4;
    t->solids = false;
    t->hbw = 16;
    t->u.plat.last = t->x;
}

static void platform_update(Obj *t) {
    t->spdx = t->u.plat.dir * num(0.65);
    if (t->x < -16) t->x = 128;
    else if (t->x > 128) t->x = -16;
    if (!check(t, PLAYER, 0, 0)) {
        Obj *hit = collide(t, PLAYER, 0, -1);
        if (hit) move_x(hit, toi(t->x - t->u.plat.last), 1);
    }
    t->u.plat.last = t->x;
}

static void platform_draw(Obj *t) {
    p8::spr(11, toi(t->x), toi(t->y - 1));
    p8::spr(12, toi(t->x + 8), toi(t->y - 1));
}

static const char MESSAGE_TEXT[] = "-- celeste mountain --#this memorial to those# perished on the climb";

static void message_draw(Obj *t) {
    auto &m = t->u.msg;
    if (check(t, PLAYER, 4, 0)) {
        if (m.index < (int)(sizeof MESSAGE_TEXT - 1)) {
            m.index += num(0.5);
            if (m.index >= m.last + 1) {
                m.last += 1;
                snd::sfx(35);
            }
        }
        int offx = 8, offy = 96;
        for (int i = 1; i <= m.index; i++) {
            char ch = MESSAGE_TEXT[i - 1];
            if (ch != '#') {
                p8::rectfill(offx - 2, offy - 2, offx + 7, offy + 6, 7);
                char s[2] = { ch, 0 };
                p8::print(s, offx, offy, 0);
                offx += 5;
            } else {
                offx = 8;
                offy += 7;
            }
        }
    } else {
        m.index = 0;
        m.last = 0;
    }
}

static void big_chest_init(Obj *t) {
    t->u.big.state = 0;
    t->hbw = 16;
}

static void big_chest_draw(Obj *t) {
    auto &b = t->u.big;
    int x = toi(t->x), y = toi(t->y);
    if (b.state == 0) {
        Obj *hit = collide(t, PLAYER, 0, 8);
        if (hit && is_solid(hit, 0, 1)) {
            snd::music(-1, 500, 7);
            snd::sfx(37);
            pause_player = true;
            hit->spdx = 0;
            hit->spdy = 0;
            b.state = 1;
            init_object(SMOKE, t->x, t->y);
            init_object(SMOKE, t->x + 8, t->y);
            b.timer = 60;
            rayCount = 0;
        }
        p8::spr(96, x, y);
        p8::spr(97, x + 8, y);
    } else if (b.state == 1) {
        b.timer -= 1;
        shake = 5;
        flash_bg = true;
        if (b.timer <= 45 && rayCount < 50) {
            Ray &r = rays[rayCount++];
            r.x = 1 + rnd(14);
            r.y = 0;
            r.h = 32 + rnd(32);
            r.spd = 8 + rnd(8);
        }
        if (b.timer < 0) {
            b.state = 2;
            rayCount = 0;
            flash_bg = false;
            new_bg = true;
            init_object(ORB, t->x + 4, t->y + 4);
            pause_player = false;
        }
        for (uint8_t i = 0; i < rayCount; i++) {
            Ray &p = rays[i];
            p.y += p.spd;
            p8::line(toi(t->x + p.x), toi(t->y + 8 - p.y), toi(t->x + p.x),
                     toi(mn(t->y + 8 - p.y + p.h, t->y + 8)), 7);
        }
    }
    p8::spr(112, x, y + 8);
    p8::spr(113, x + 8, y + 8);
}

static void orb_init(Obj *t) {
    t->spdy = -4;
    t->solids = false;
}

static void orb_draw(Obj *t) {
    t->spdy = appr(t->spdy, 0, num(0.5));
    Obj *hit = collide(t, PLAYER, 0, 0);
    if (t->spdy == 0 && hit) {
        music_timer = 45;
        snd::sfx(51);
        freeze = 10;
        shake = 10;
        destroy_object(t);
        maxDjump = 2;
        hit->u.pl.djump = 2;
    }

    p8::spr(102, toi(t->x), toi(t->y));
    num off = num(frames) / 30;
    for (int i = 0; i <= 7; i++)
        p8::circfill(toi(t->x + 4 + p8cos(off + num(i) / 8) * 8), toi(t->y + 4 + p8sin(off + num(i) / 8) * 8), 1, 7);
}

static void flag_init(Obj *t) {
    t->x += 5;
    t->u.flag.score = 0;
    t->u.flag.show = false;
    for (int i = 0; i < 30; i++)
        if (gotFruit[i]) t->u.flag.score += 1;
}

// The cart's .. on numbers: the decimal digits.
static char *cat_int(char *d, int v) {
    char tmp[8];
    int n = 0;
    if (v < 0) { *d++ = '-'; v = -v; }
    do { tmp[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n) *d++ = tmp[--n];
    *d = 0;
    return d;
}

static char *cat(char *d, const char *s) {
    while (*s) *d++ = *s++;
    *d = 0;
    return d;
}

static void flag_draw(Obj *t) {
    t->spr = 118 + mod(num(frames) / 5, 3);
    p8::spr(toi(t->spr), toi(t->x), toi(t->y));
    if (t->u.flag.show) {
        char s[24];
        p8::rectfill(32, 2, 96, 31, 0);
        p8::spr(26, 55, 6);
        cat_int(cat(s, "x"), t->u.flag.score);
        p8::print(s, 64, 9, 7);
        draw_time(49, 16);
        cat_int(cat(s, "deaths:"), deaths);
        p8::print(s, 48, 24, 7);
    } else if (check(t, PLAYER, 0, 0)) {
        snd::sfx(55);
        sfx_timer = 30;
        t->u.flag.show = true;
    }
}

static void room_title_init(Obj *t) { t->u.title.delay = 5; }

static void room_title_draw(Obj *t) {
    t->u.title.delay -= 1;
    if (t->u.title.delay < -30) {
        destroy_object(t);
    } else if (t->u.title.delay < 0) {
        p8::rectfill(24, 58, 104, 70, 0);
        if (roomX == 3 && roomY == 1) {
            p8::print("old site", 48, 62, 7);
        } else if (level_index() == 30) {
            p8::print("summit", 52, 62, 7);
        } else {
            int level = (1 + level_index()) * 100;
            char s[12];
            cat(cat_int(s, level), " m");
            p8::print(s, 52 + (level < 1000 ? 2 : 0), 62, 7);
        }
        draw_time(4, 4);
    }
}

// The kinds' functions (nullptr: the kind has none).
typedef void (*Fn)(Obj *);
static const Fn INIT[TYPE_COUNT] = {
    player_init, spawn_init, spring_init, balloon_init, fall_floor_init, smoke_init, fruit_init, fly_fruit_init,
    lifeup_init, nullptr, nullptr, chest_init, platform_init, nullptr, big_chest_init, orb_init, flag_init,
    room_title_init };
static const Fn UPDATE[TYPE_COUNT] = {
    player_update, spawn_update, spring_update, balloon_update, fall_floor_update, smoke_update, fruit_update,
    fly_fruit_update, lifeup_update, fake_wall_update, key_update, chest_update, platform_update, nullptr, nullptr,
    nullptr, nullptr, nullptr };
static const Fn DRAW[TYPE_COUNT] = {
    player_draw, spawn_draw, nullptr, balloon_draw, fall_floor_draw, nullptr, nullptr, fly_fruit_draw, lifeup_draw,
    fake_wall_draw, nullptr, nullptr, platform_draw, message_draw, big_chest_draw, orb_draw, flag_draw,
    room_title_draw };

// object functions --
//--------------------

static Obj *alloc() {
    for (uint8_t pass = 0; pass < 2; pass++) {
        for (uint8_t i = 0; i < MAX_OBJECTS; i++)
            if (!pool[i].used) return &pool[i];
        sweep();    // destroyed objects no loop holds any more
    }
    return nullptr;
}

static Obj *init_object(uint8_t type, num x, num y) {
    if (IF_NOT_FRUIT[type] && gotFruit[level_index()]) return nullptr;
    Obj *obj = objectCount < MAX_OBJECTS ? alloc() : nullptr;
    if (!obj) obj = &spare;         // (never: MAX_OBJECTS is checked against objectPeak)
    memset(obj, 0, sizeof *obj);
    obj->type = type;
    obj->collideable = true;
    obj->solids = true;

    obj->spr = TILE[type];
    obj->flipX = obj->flipY = false;

    obj->x = x;
    obj->y = y;
    obj->hbx = 0; obj->hby = 0; obj->hbw = 8; obj->hbh = 8;

    obj->spdx = obj->spdy = 0;
    obj->remx = obj->remy = 0;

    if (obj != &spare) {
        obj->used = obj->listed = true;
        objects[objectCount++] = obj;     // add(objects,obj)
        if (objectCount > objectPeak) objectPeak = objectCount;
    }
    if (INIT[type]) INIT[type](obj);
    return obj;
}

static void destroy_object(Obj *obj) {
    // del(objects,obj)
    for (uint8_t i = 0; i < objectCount; i++) {
        if (objects[i] == obj) {
            for (uint8_t j = i; j + 1 < objectCount; j++) objects[j] = objects[j + 1];
            objectCount--;
            obj->listed = false;
            if (obj != running) obj->used = false;
            return;
        }
    }
}

static void kill_player(Obj *obj) {
    sfx_timer = 12;
    snd::sfx(0);
    deaths += 1;
    shake = 10;
    destroy_object(obj);
    deadCount = 0;
    for (int dir = 0; dir <= 7; dir++) {
        num angle = num(dir) / 8;
        DeadParticle &p = dead_particles[deadCount++];
        p.x = obj->x + 4;
        p.y = obj->y + 4;
        p.t = 10;
        p.spdx = p8sin(angle) * 3;
        p.spdy = p8cos(angle) * 3;
        restart_room();
    }
}

// room functions --
//------------------

static void restart_room() {
    will_restart = true;
    delay_restart = 15;
}

static void next_room() {
    if (roomX == 2 && roomY == 1) {
        snd::music(30, 500, 7);
    } else if (roomX == 3 && roomY == 1) {
        snd::music(20, 500, 7);
    } else if (roomX == 4 && roomY == 2) {
        snd::music(30, 500, 7);
    } else if (roomX == 5 && roomY == 3) {
        snd::music(30, 500, 7);
    }

    if (roomX == 7) {
        load_room(0, roomY + 1);
    } else {
        load_room(roomX + 1, roomY);
    }
}

static void load_room(int x, int y) {
    has_dashed = false;
    has_key = false;

    // remove existing objects
    while (objectCount) destroy_object(objects[0]);

    // current room
    roomX = (int8_t)x;
    roomY = (int8_t)y;

    // entities
    for (int tx = 0; tx <= 15; tx++) {
        for (int ty = 0; ty <= 15; ty++) {
            uint8_t tile = p8::mget(roomX * 16 + tx, roomY * 16 + ty);
            if (tile == 11) {
                Obj *o = init_object(PLATFORM, tx * 8, ty * 8);
                o->u.plat.dir = -1;
            } else if (tile == 12) {
                Obj *o = init_object(PLATFORM, tx * 8, ty * 8);
                o->u.plat.dir = 1;
            } else {
                for (uint8_t k = 0; k < sizeof TYPES; k++)
                    if (TILE[TYPES[k]] == tile) init_object(TYPES[k], tx * 8, ty * 8);
            }
        }
    }

    if (!is_title()) init_object(ROOM_TITLE, 0, 0);
}

void loadRoom(int x, int y) { load_room(x, y); }

void beginAt(int level, int djump) {
    begin_game();
    if (djump) maxDjump = (int8_t)djump;
    if (level) load_room(level % 8, level / 8);
}

void quitToTitle() {
    new_bg = flash_bg = pause_player = will_restart = false;
    freeze = shake = 0;
    p8::camera();
    titleScreen();
}

void restartRoom() { load_room(roomX, roomY); }

Progress progress() {
    Progress p;
    p.level = (uint8_t)level_index();
    p.djump = (uint8_t)maxDjump;
    p.deaths = (uint16_t)deaths;
    p.seconds = (uint16_t)seconds;
    p.minutes = (uint16_t)minutes;
    p.fruit = 0;
    for (int i = 0; i < 30; i++)
        if (gotFruit[i]) p.fruit |= 1ul << i;
    return p;
}

void resume(const Progress &p) {
    int level = p.level < 31 ? p.level : 0;
    beginAt(level, p.djump);
    deaths = (int16_t)p.deaths;
    seconds = (int16_t)p.seconds;
    minutes = (int16_t)p.minutes;
    for (int i = 0; i < 30; i++) gotFruit[i] = (p.fruit >> i) & 1;
    new_bg = maxDjump == 2;             // the orb has been got
    // The song next_room() and the orb would have left playing.
    int song = level <= 10 ? 0 : level == 11 ? 30 : level <= 20 ? 20 : 30;
    if (maxDjump == 2 && level < 30) song = 10;
    if (song) snd::music(song, 0, 7);
    load_room(level % 8, level / 8);    // again: its fruit is left out if it was got
}

// update function --
//-------------------

void update() {
    frames = (frames + 1) % 30;
    if (frames == 0 && level_index() < 30) {
        seconds = (seconds + 1) % 60;
        if (seconds == 0) minutes += 1;
    }

    if (music_timer > 0) {
        music_timer -= 1;
        if (music_timer <= 0) snd::music(10, 0, 7);
    }

    if (sfx_timer > 0) sfx_timer -= 1;

    // cancel if freeze
    if (freeze > 0) {
        freeze -= 1;
        return;
    }

    // screenshake
    if (shake > 0) {
        shake -= 1;
        p8::camera();
        if (shake > 0) p8::camera(toi(-2 + rnd(5)), toi(-2 + rnd(5)));
    }

    // restart (soon)
    if (will_restart && delay_restart > 0) {
        delay_restart -= 1;
        if (delay_restart <= 0) {
            will_restart = false;
            load_room(roomX, roomY);
        }
    }

    // update each object
    foreach_object([](Obj *obj) {
        move(obj, obj->spdx, obj->spdy);
        if (UPDATE[obj->type]) UPDATE[obj->type](obj);
    });

    // start game
    if (is_title()) {
        if (!startGame && (btn(K_JUMP) || btn(K_DASH))) {
            snd::music(-1, 0, 0);
            start_game_flash = 50;
            startGame = true;
            snd::sfx(38);
        }
        if (startGame) {
            start_game_flash -= 1;
            if (start_game_flash <= -30) begin_game();
        }
    }
}

// drawing functions --
//---------------------

bool frozen() { return freeze > 0; }

static void draw_object(Obj *obj) {
    if (DRAW[obj->type]) {
        DRAW[obj->type](obj);
    } else if (obj->spr > 0) {
        p8::spr(toi(obj->spr), toi(obj->x), toi(obj->y), obj->flipX, obj->flipY);
    }
}

void draw() {
    if (freeze > 0) return;

    // reset all palette values
    p8::pal();

    // start game flash
    if (startGame) {
        int c = 10;
        if (start_game_flash > 10) {
            if (frames % 10 < 5) c = 7;
        } else if (start_game_flash > 5) {
            c = 2;
        } else if (start_game_flash > 0) {
            c = 1;
        } else {
            c = 0;
        }
        if (c < 10) {
            p8::pal(6, c);
            p8::pal(12, c);
            p8::pal(13, c);
            p8::pal(5, c);
            p8::pal(1, c);
            p8::pal(7, c);
        }
    }

    // clear screen
    int bg_col = 0;
    if (flash_bg) {
        bg_col = frames / 5;
    } else if (new_bg) {
        bg_col = 2;
    }
    p8::rectfill(0, 0, 128, 128, bg_col);

    // clouds
    if (!is_title()) {
        for (int i = 0; i <= 16; i++) {
            Cloud &c = clouds[i];
            c.x += c.spd;
            p8::rectfill(toi(c.x), toi(c.y), toi(c.x + c.w), toi(c.y + 4 + (1 - c.w / 64) * 12), new_bg ? 14 : 1);
            if (c.x > 128) {
                c.x = -c.w;
                c.y = rnd(128 - 8);
            }
        }
    }

    // draw bg terrain
    p8::map(roomX * 16, roomY * 16, 0, 0, 16, 16, 4);

    // platforms/big chest
    foreach_object([](Obj *o) {
        if (o->type == PLATFORM || o->type == BIG_CHEST) draw_object(o);
    });

    // draw terrain
    int off = is_title() ? -4 : 0;
    p8::map(roomX * 16, roomY * 16, off, 0, 16, 16, 2);

    // draw objects
    foreach_object([](Obj *o) {
        if (o->type != PLATFORM && o->type != BIG_CHEST) draw_object(o);
    });

    // draw fg terrain
    p8::map(roomX * 16, roomY * 16, 0, 0, 16, 16, 8);

    // particles
    for (int i = 0; i <= 24; i++) {
        Particle &p = particles[i];
        p.x += p.spd;
        p.y += p8sin(p.off);
        p.off += mn(num(0.05), p.spd / 32);
        p8::rectfill(toi(p.x), toi(p.y), toi(p.x + p.s), toi(p.y + p.s), toi(p.c));
        if (p.x > 128 + 4) {
            p.x = -4;
            p.y = rnd(128);
        }
    }

    // dead particles (del() of the current one skips nothing: all())
    for (uint8_t i = 0; i < deadCount;) {
        DeadParticle p = dead_particles[i];
        p.x += p.spdx;
        p.y += p.spdy;
        p.t -= 1;
        bool gone = p.t <= 0;
        if (gone) {
            for (uint8_t j = i; j + 1 < deadCount; j++) dead_particles[j] = dead_particles[j + 1];
            deadCount--;
        } else {
            dead_particles[i++] = p;
        }
        num r = p.t / 5;
        p8::rectfill(toi(p.x - r), toi(p.y - r), toi(p.x + r), toi(p.y + r), toi(14 + mod(p.t, 2)));
    }

    // draw outside of the screen for screenshake
    p8::rectfill(-5, -5, -1, 133, 0);
    p8::rectfill(-5, -5, 133, -1, 0);
    p8::rectfill(-5, 128, 133, 133, 0);
    p8::rectfill(128, -5, 133, 133, 0);

    // credits
    if (is_title()) {
        p8::print(CHLS_TITLE_KEYS, 58, 80, 5);
        p8::print("matt thorson", 42, 96, 5);
        p8::print("noel berry", 46, 102, 5);
    }

    if (level_index() == 30) {
        Obj *p = findPlayer();
        if (p) {
            int diff = toi(mn(24, 40 - nabs(p->x + 4 - 64)));
            p8::rectfill(0, 0, diff, 128, 0);
            p8::rectfill(128 - diff, 0, 128, 128, 0);
        }
    }
}

Obj *findPlayer() {
    for (uint8_t i = 0; i < objectCount; i++)
        if (objects[i]->type == PLAYER) return objects[i];
    return nullptr;
}

static void draw_time(int x, int y) {
    int s = seconds;
    int m = minutes % 60;
    int h = minutes / 60;

    p8::rectfill(x, y, x + 32, y + 6, 0);
    char buf[16], *d = buf;
    if (h < 10) d = cat(d, "0");
    d = cat(cat_int(d, h), ":");
    if (m < 10) d = cat(d, "0");
    d = cat(cat_int(d, m), ":");
    if (s < 10) d = cat(d, "0");
    cat_int(d, s);
    p8::print(buf, x + 1, y + 1, 7);
}

// helper functions --
//--------------------

static bool tile_flag_at(num x, num y, int w, int h, uint8_t flag) {
    num iend = mn(15, (x + w - 1) / 8), jend = mn(15, (y + h - 1) / 8);
    for (int i = toi(mx(0, flr(x / 8))); i <= iend; i++)
        for (int j = toi(mx(0, flr(y / 8))); j <= jend; j++)
            if (p8::fget(p8::mget(roomX * 16 + i, roomY * 16 + j), flag)) return true;
    return false;
}

static bool solid_at(num x, num y, int w, int h) { return tile_flag_at(x, y, w, h, 0); }
static bool ice_at(num x, num y, int w, int h) { return tile_flag_at(x, y, w, h, 4); }

static bool spikes_at(num x, num y, int w, int h, num xspd, num yspd) {
    num iend = mn(15, (x + w - 1) / 8), jend = mn(15, (y + h - 1) / 8);
    for (int i = toi(mx(0, flr(x / 8))); i <= iend; i++) {
        for (int j = toi(mx(0, flr(y / 8))); j <= jend; j++) {
            uint8_t tile = p8::mget(roomX * 16 + i, roomY * 16 + j);
            if (tile == 17 && (mod(y + h - 1, 8) >= 6 || y + h == j * 8 + 8) && yspd >= 0) return true;
            if (tile == 27 && mod(y, 8) <= 2 && yspd <= 0) return true;
            if (tile == 43 && mod(x, 8) <= 2 && xspd <= 0) return true;
            if (tile == 59 && (mod(x + w - 1, 8) >= 6 || x + w == i * 8 + 8) && xspd >= 0) return true;
        }
    }
    return false;
}

}  // namespace game
