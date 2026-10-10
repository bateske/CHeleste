// Fix.h against PICO-8's own answers (16.16: what `?tostr(x, true)` prints).
#include <stdio.h>
#include "../../Fix.h"

static int fails;
#define EQ(got, want) do { long g = (long)(got), w = (long)(want); \
    if (g != w) { printf("FAIL %s:%d %s = 0x%lx, want 0x%lx\n", __FILE__, __LINE__, #got, g, w); fails++; } } while (0)
#define NEAR(got, want, tol) do { long g = (long)(got), w = (long)(want); \
    if (g - w > (tol) || w - g > (tol)) { printf("FAIL %s:%d %s = 0x%lx, want 0x%lx +- %d\n", __FILE__, __LINE__, #got, g, w, (tol)); fails++; } } while (0)

int main() {
    // Literals round to the nearest 1/65536, as PICO-8's do (0.1 is 0x0000.199a).
    EQ(num(0.1).v, 0x199A);
    EQ(num(0.21).v, 0x35C3);
    EQ(num(-0.1).v, -0x199A);
    EQ(num(0.70710678118).v, 0xB505);
    // flr floors; toi too.
    EQ(flr(num(-0.5)).v, -0x10000);
    EQ(flr(num(2.75)).v, 0x20000);
    EQ(toi(num(-0.25)), -1);
    // % has the divisor's sign: -1 % 8 is 7, 7.5 % 3 is 1.5.
    EQ(mod(num(-1), num(8)).v, 7 << 16);
    EQ(mod(num(7.5), num(3)).v, 0x18000);
    EQ(mod(num(-0.25), num(1)).v, 0xC000);
    // * keeps 16 fraction bits (floored), + - wrap at 32768.
    EQ((num(1.5) * num(-0.5)).v, -0xC000);
    EQ((num(32767) + num(1)).v, (int32_t)0x80000000);
    EQ((num::bits(1) * num(0.5)).v, 0);
    EQ((num::bits(-1) * num(0.5)).v, -1);
    // / truncates; by 0 it saturates.
    EQ((num(1) / num(3)).v, 0x5555);
    EQ((num(-1) / num(3)).v, -0x5555);
    EQ((num(1) / num(0)).v, 0x7FFFFFFF);
    EQ((num(-1) / num(0)).v, (int32_t)0x80000001);
    // sin is upside down; both take turns.
    EQ(p8sin(num(0)).v, 0);
    EQ(p8sin(num(0.25)).v, -0x10000);
    EQ(p8sin(num(0.75)).v, 0x10000);
    EQ(p8cos(num(0)).v, 0x10000);
    EQ(p8cos(num(0.5)).v, -0x10000);
    NEAR(p8sin(num(0.125)).v, -0xB505, 2);
    NEAR(p8cos(num(1.0 / 3)).v, -0x8000, 2);
    NEAR(p8sin(num(-0.125)).v, 0xB505, 2);
    // Every angle within 2/65536 of the real thing.
    int worst = 0;
    for (int32_t b = -0x20000; b < 0x20000; b += 7) {
        double want = -__builtin_sin(b / 65536.0 * 6.283185307179586) * 65536.0;
        int d = (int)(p8sin(num::bits(b)).v - want);
        if (d < 0) d = -d;
        if (d > worst) worst = d;
    }
    if (worst > 2) { printf("FAIL sin off by %d/65536\n", worst); fails++; }
    // rnd stays in [0, x).
    rndSeed(7);
    for (int i = 0; i < 2000; i++) {
        num r = rnd(num(0.2));
        if (r < 0 || r >= num(0.2)) { printf("FAIL rnd(0.2) = 0x%lx\n", (long)r.v); fails++; break; }
    }
    EQ(rnd(num(0)).v, 0);
    // appr / sign / mid3 (Celeste's helpers).
    EQ(appr(num(1), num(0), num(0.15)).v, num(0.85).v);
    EQ(appr(num(-0.1), num(0), num(0.15)).v, 0);
    EQ(sign(num(-0.01)).v, -0x10000);
    EQ(mid3(num(130), num(-1), num(121)).v, 121 << 16);
    printf(fails ? "fix: %d failed\n" : "fix: ok\n", fails);
    return fails != 0;
}
