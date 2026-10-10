// Cheleste's save (CHLS_EXTRAS): where the last game got to, kept in flash.
#pragma once
#include "Game.h"

namespace saved {

void begin();                               // read it, once, at start-up
bool has();                                 // a game to continue (past the first level, before the summit)
const game::Progress &get();
void put(const game::Progress &p);          // remember p (written by flush())
void clear();                               // nothing to continue (the summit reached)
void flush();                               // write what changed: between gfx_wait() and the flush

}  // namespace saved
