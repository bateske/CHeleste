// PICO-8's sin, cos and rnd (Fix.h).
#include "Fix.h"

static uint32_t rngState = 0x2545F491;

void rndSeed(uint32_t seed) { rngState = seed ? seed : 0x2545F491; }

static uint32_t next32() {
    uint32_t x = rngState;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return rngState = x;
}

#if CHLS_NUM_DOUBLE

num p8sin(num a) { return -sin(a * 6.283185307179586); }
num p8cos(num a) { return cos(a * 6.283185307179586); }
num rnd(num x) { return x > 0 ? (next32() / 4294967296.0) * x : 0; }

#else

extern const uint16_t SINE_QUARTER[256];

// sin(2 pi t) for t a 16-bit fraction of a turn, linearly between 1024 points.
static int32_t sine16(uint32_t t) {
    t &= 0xFFFF;
    uint32_t q = t >> 14, f = t & 0x3FFF;           // quadrant; position in it
    if (q & 1) f = 0x4000 - f;                      // the falling quarters run backwards
    uint32_t i = f >> 6, frac = f & 63;
    int32_t a = i < 256 ? SINE_QUARTER[i] : 65536;
    int32_t b = i + 1 < 256 ? SINE_QUARTER[i + 1] : 65536;
    int32_t v = i >= 256 ? 65536 : a + (((b - a) * (int32_t)frac) >> 6);
    return q & 2 ? -v : v;
}

num p8sin(num a) { return num::bits(-sine16((uint32_t)a.v)); }
num p8cos(num a) { return num::bits(sine16((uint32_t)a.v + 0x4000)); }

num rnd(num x) {
    if (x.v <= 0) return 0;
    return num::bits((int32_t)(next32() % (uint32_t)x.v));
}

#endif
