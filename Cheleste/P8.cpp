// The PICO-8 calls on gfx_fb (P8.h).
#include <CHGame.h>
#include "P8.h"
#include "src/assets/Cart.h"

namespace p8 {

static int camX, camY;
static uint8_t drawPal[16] = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 };

void camera(int x, int y) { camX = x; camY = y; }

void pal() {
    for (uint8_t i = 0; i < 16; i++) drawPal[i] = i;
}

void pal(uint8_t c0, uint8_t c1) { drawPal[c0 & 15] = c1 & 15; }

void cls(uint8_t c) {
    c = drawPal[c & 15];
    memset(gfx_fb, c | (c << 4), GFX_FB_BYTES);
}

// One sprite row is 4 bytes of the sheet: 8 pixels, the left one low.
RAMFUNC(p8spr) void spr(int n, int x, int y, bool flipX, bool flipY) {
    if (n < 0 || n > 127) return;
    x -= camX;
    y -= camY;
    if (x <= -8 || x >= 128 || y <= -8 || y >= 128) return;
    const uint8_t *src = cart::GFX + (n >> 4) * 8 * 64 + (n & 15) * 4;
    int c0 = x < 0 ? -x : 0, c1 = x > 120 ? 128 - x : 8;
    int r0 = y < 0 ? -y : 0, r1 = y > 120 ? 128 - y : 8;
    for (int r = r0; r < r1; r++) {
        const uint8_t *s = src + (flipY ? 7 - r : r) * 64;
        uint32_t row = s[0] | (s[1] << 8) | (s[2] << 16) | ((uint32_t)s[3] << 24);   // pixel i in bits 4i..4i+3
        uint8_t *d = gfx_fb + (y + r) * GFX_FB_STRIDE;
        for (int i = c0; i < c1; i++) {
            uint8_t c = (row >> ((flipX ? 7 - i : i) * 4)) & 15;
            if (!c) continue;
            int xx = x + i;
            uint8_t *p = d + (xx >> 1);
            uint8_t v = drawPal[c];
            *p = (xx & 1) ? (uint8_t)((*p & 0x0F) | (v << 4)) : (uint8_t)((*p & 0xF0) | v);
        }
    }
}

void map(int cx, int cy, int sx, int sy, int w, int h, uint8_t layer) {
    for (int ty = 0; ty < h; ty++) {
        const uint8_t *row = cart::MAP + (cy + ty) * 128 + cx;
        for (int tx = 0; tx < w; tx++) {
            uint8_t t = row[tx];
            if (!t || t > 127) continue;
            if (layer && (cart::FLAGS[t] & layer) != layer) continue;
            spr(t, sx + tx * 8, sy + ty * 8);
        }
    }
}

RAMFUNC(p8rectfill) void rectfill(int x0, int y0, int x1, int y1, uint8_t c) {
    if (x0 > x1) { int t = x0; x0 = x1; x1 = t; }
    if (y0 > y1) { int t = y0; y0 = y1; y1 = t; }
    x0 -= camX; x1 -= camX; y0 -= camY; y1 -= camY;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > 127) x1 = 127;
    if (y1 > 127) y1 = 127;
    if (x0 > x1 || y0 > y1) return;
    c = drawPal[c & 15];
    uint8_t both = c | (c << 4);
    for (int y = y0; y <= y1; y++) {
        uint8_t *d = gfx_fb + y * GFX_FB_STRIDE;
        int x = x0;
        if (x & 1) { d[x >> 1] = (d[x >> 1] & 0x0F) | (c << 4); x++; }
        int end = x1 + 1;                 // exclusive
        if (end & 1) { d[end >> 1] = (d[end >> 1] & 0xF0) | c; end--; }
        if (end > x) memset(d + (x >> 1), both, (end - x) >> 1);
    }
}

// The small circles as PICO-8 draws them (Celeste's hair and the orb's ring).
void circfill(int x, int y, int r, uint8_t c) {
    if (r <= 0) {
        rectfill(x, y, x, y, c);
    } else if (r == 1) {
        rectfill(x - 1, y, x + 1, y, c);
        rectfill(x, y - 1, x, y + 1, c);
    } else if (r == 2) {
        rectfill(x - 2, y - 1, x + 2, y + 1, c);
        rectfill(x - 1, y - 2, x + 1, y + 2, c);
    } else if (r == 3) {
        rectfill(x - 3, y - 1, x + 3, y + 1, c);
        rectfill(x - 1, y - 3, x + 1, y + 3, c);
        rectfill(x - 2, y - 2, x + 2, y + 2, c);
    } else {
        gfx_fillCircle(x - camX, y - camY, r, drawPal[c & 15]);
    }
}

void line(int x0, int y0, int x1, int y1, uint8_t c) {
    if (x0 == x1) { rectfill(x0, y0, x1, y1, c); return; }
    gfx_line(x0 - camX, y0 - camY, x1 - camX, y1 - camY, drawPal[c & 15]);
}

// CHGame's 3x5 font has PICO-8's metrics: 3x5 glyphs, 4 pixels a character.
// PICO-8 shows lower case as its small capitals: here, the capitals.
void print(const char *s, int x, int y, uint8_t c) {
    char buf[64];
    uint8_t n = 0;
    for (; *s && n < sizeof buf - 1; s++) buf[n++] = (*s >= 'a' && *s <= 'z') ? (char)(*s - 32) : *s;
    buf[n] = 0;
    text35(x - camX, y - camY, buf, drawPal[c & 15]);
}

uint8_t mget(int x, int y) {
    if (x < 0 || x > 127 || y < 0 || y > 63) return 0;
    return cart::MAP[y * 128 + x];
}

bool fget(uint8_t sprite, uint8_t flag) {
    return sprite < 128 && (cart::FLAGS[sprite] >> flag) & 1;
}

}  // namespace p8
