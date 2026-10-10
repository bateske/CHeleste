// Cheleste's save (Save.h), a CHGame save record.
#include <CHGame.h>
#include "Save.h"

namespace saved {

static const uint32_t MAGIC = save::magic("CHLS");     // its own: every game shares the pages
static const uint8_t VERSION = 1;

static game::Progress data;
static bool valid, dirty;

void begin() {
    valid = save::load(MAGIC, VERSION, data);
    if (valid && (data.level == 0 || data.level >= 30)) valid = false;
}

bool has() { return valid; }
const game::Progress &get() { return data; }

void put(const game::Progress &p) {
    data = p;
    valid = p.level > 0 && p.level < 30;
    dirty = true;
}

void clear() {
    if (!valid) return;
    data.level = 0;
    valid = false;
    dirty = true;
}

void flush() {
    if (dirty) dirty = !save::store(MAGIC, VERSION, data);
}

}  // namespace saved
