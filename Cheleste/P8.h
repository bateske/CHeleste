// The PICO-8 calls Celeste makes, drawn straight into CHGfx's framebuffer.
//
// PICO-8's screen is this one: 128x128, 16 colours, 4 bits a pixel. The
// cart's sheet is stored packed the way gfx_fb is (the left pixel in the low
// nibble), so a sprite row is four bytes copied with a transparency test.
// Like PICO-8: everything is offset by camera(), colours go through the draw
// palette pal(), colour 0 is transparent in spr() and map(), and coordinates
// are whole pixels (the caller floors: toi()).
#pragma once
#include <stdint.h>

namespace p8 {

void camera(int x = 0, int y = 0);
void pal();                                     // reset the draw palette
void pal(uint8_t c0, uint8_t c1);               // draw c0 as c1

void cls(uint8_t c);
void spr(int n, int x, int y, bool flipX = false, bool flipY = false);    // one 8x8 sprite
void map(int cx, int cy, int sx, int sy, int w, int h, uint8_t layer);   // layer: a flag mask (0 = every tile)
void rectfill(int x0, int y0, int x1, int y1, uint8_t c);              // inclusive corners, either order
void circfill(int x, int y, int r, uint8_t c);
void line(int x0, int y0, int x1, int y1, uint8_t c);
void print(const char *s, int x, int y, uint8_t c);

uint8_t mget(int x, int y);
bool fget(uint8_t sprite, uint8_t flag);

}  // namespace p8
