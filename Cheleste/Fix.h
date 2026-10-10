// PICO-8's numbers: 16.16 fixed point, with PICO-8's rules.
//
// Celeste's Lua runs on PICO-8 numbers, and its physics (0.21 gravity, 0.6
// acceleration, sub-pixel remainders) depend on them. This chip has no FPU,
// so `num` is a 32-bit integer holding the value times 65536, and every
// operation does what PICO-8 does: + - * wrap, / truncates (x/0 saturates),
// flr floors, % gives a result with the divisor's sign... The literals
// (num(0.21)) are folded by the compiler: no floating point reaches the
// device (check: no __adddf3 / __muldf3 in `cl size`).
//
// With CHLS_NUM_DOUBLE (a host-only build: tools/ref/, the golden traces),
// num is a plain double instead, so the port can be compared with the cart's
// Lua run on the PC, number for number.
#pragma once
#include <stdint.h>
#include "config.h"

#if CHLS_NUM_DOUBLE
#include <math.h>

typedef double num;
static inline num flr(num a) { return floor(a); }
static inline int toi(num a) { return (int)floor(a); }   // flr, as an int (coordinates, indices)
static inline num nabs(num a) { return a < 0 ? -a : a; }
static inline num mod(num a, num b) { return a - floor(a / b) * b; }
static inline num mn(num a, num b) { return a < b ? a : b; }
static inline num mx(num a, num b) { return a > b ? a : b; }
num p8sin(num a);
num p8cos(num a);

#else

struct num {
    int32_t v;      // the value times 65536

    num() = default;   // trivial (num lives in unions); globals start at 0
    constexpr num(int i) : v((int32_t)((uint32_t)i << 16)) {}
    // Literals only (folded at compile time): rounded to the nearest 1/65536.
    constexpr num(double d) : v((int32_t)(d * 65536.0 + (d < 0 ? -0.5 : 0.5))) {}
    static constexpr num bits(int32_t b) { num n(0); n.v = b; return n; }

    num operator-() const { return bits((int32_t)(0u - (uint32_t)v)); }
    num operator+(num b) const { return bits((int32_t)((uint32_t)v + (uint32_t)b.v)); }
    num operator-(num b) const { return bits((int32_t)((uint32_t)v - (uint32_t)b.v)); }
    num operator*(num b) const { return bits((int32_t)(((int64_t)v * b.v) >> 16)); }
    num operator/(num b) const {
        if (b.v == 0) return bits(v < 0 ? (int32_t)0x80000001 : 0x7FFFFFFF);
        int64_t q = (int64_t)v * 65536 / b.v;
        if (q > 0x7FFFFFFF) return bits(0x7FFFFFFF);
        if (q < -0x7FFFFFFF) return bits((int32_t)0x80000001);
        return bits((int32_t)q);
    }
    num &operator+=(num b) { return *this = *this + b; }
    num &operator-=(num b) { return *this = *this - b; }
    num &operator*=(num b) { return *this = *this * b; }
    num &operator/=(num b) { return *this = *this / b; }

    bool operator==(num b) const { return v == b.v; }
    bool operator!=(num b) const { return v != b.v; }
    bool operator<(num b) const { return v < b.v; }
    bool operator>(num b) const { return v > b.v; }
    bool operator<=(num b) const { return v <= b.v; }
    bool operator>=(num b) const { return v >= b.v; }
};

// Mixed with ints: the int is promoted (PICO-8 has only the one number type).
static inline num operator+(int a, num b) { return num(a) + b; }
static inline num operator-(int a, num b) { return num(a) - b; }
static inline num operator*(int a, num b) { return num(a) * b; }
static inline num operator/(int a, num b) { return num(a) / b; }
static inline bool operator<(int a, num b) { return num(a) < b; }
static inline bool operator>(int a, num b) { return num(a) > b; }
static inline bool operator<=(int a, num b) { return num(a) <= b; }
static inline bool operator>=(int a, num b) { return num(a) >= b; }
static inline bool operator==(int a, num b) { return num(a) == b; }
static inline bool operator!=(int a, num b) { return num(a) != b; }
// And with double literals (0.5*x), which would otherwise go through int.
static inline num operator+(double a, num b) { return num(a) + b; }
static inline num operator-(double a, num b) { return num(a) - b; }
static inline num operator*(double a, num b) { return num(a) * b; }
static inline num operator/(double a, num b) { return num(a) / b; }

static inline num flr(num a) { return num::bits(a.v & (int32_t)0xFFFF0000); }
static inline int toi(num a) { return a.v >> 16; }       // flr, as an int
static inline num nabs(num a) { return a.v < 0 ? -a : a; }
// PICO-8's %: the result is in [0, |b|).
static inline num mod(num a, num b) {
    int32_t m = b.v < 0 ? -b.v : b.v;
    if (!m) return a;
    int32_t r = a.v % m;
    return num::bits(r < 0 ? r + m : r);
}
static inline num mn(num a, num b) { return a < b ? a : b; }
static inline num mx(num a, num b) { return a > b ? a : b; }
// sin and cos take turns (1 = a full circle); sin is upside down, as on PICO-8.
num p8sin(num a);
num p8cos(num a);

#endif

static inline num mid3(num a, num lo, num hi) { return mx(lo, mn(hi, a)); }   // Celeste's clamp(val,a,b)
static inline num appr(num val, num target, num amount) {
    return val > target ? mx(val - amount, target) : mn(val + amount, target);
}
static inline num sign(num v) { return v > 0 ? num(1) : v < 0 ? num(-1) : num(0); }

// rnd(x): [0, x). A small deterministic generator (xorshift32), reseedable
// for tests. Mostly looks (smoke, clouds, shake), but a balloon's bob phase
// comes from it too.
void rndSeed(uint32_t seed);
num rnd(num x);
