// The cart's sfx() and music(), on CHGame's piezo (Sounds.cpp).
#pragma once
#include <stdint.h>

namespace snd {

void begin();
void sfx(int n);                            // sfx(n): one of the cart's 64 effects
void music(int n, int fadeMs, int mask);    // music(n, fade, mask): -1 stops

}  // namespace snd
