// Cheleste's build switches: every one is here (CHLS_*). A build sets them
// with -D (build.extra_flags), or leaves the defaults.
#pragma once

#define CHLS_VERSION "1.0"

// num as a double instead of PICO-8's 16.16 (host only: tools/ref/'s traces
// against the cart's Lua).
#ifndef CHLS_NUM_DOUBLE
#define CHLS_NUM_DOUBLE 0
#endif

// The buttons: PICO-8's O (jump) and X (dash). 1: A dashes and B jumps.
#ifndef CHLS_SWAP_AB
#define CHLS_SWAP_AB 0
#endif

// The title's buttons to start: PICO-8's keys were x and c.
#ifndef CHLS_TITLE_KEYS
#define CHLS_TITLE_KEYS "a+b"
#endif

// The cart's music (one voice: the lead line). 0: sound effects only.
#ifndef CHLS_MUSIC
#define CHLS_MUSIC 1
#endif

// Additions to the cart: START pauses (resume, restart the room, title);
// progress is saved and the title offers to continue.
#ifndef CHLS_EXTRAS
#define CHLS_EXTRAS 1
#endif
