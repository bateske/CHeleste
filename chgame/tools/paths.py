"""Where things are in the repository, for the shared tools.

The games and apps are the CHGame library's examples, so that the Arduino
IDE lists them under File > Examples > CHGame:

    platform/board/arduino/CHGame/libraries/CHGame/examples/Games/<Name>
    platform/board/arduino/CHGame/libraries/CHGame/examples/Apps/<Name>

That is a long way down, so the shared tools take a sketch by its name as
well as by its folder (`chgame --sketch CHFour build`, `python
tools/readme_gif.py CHFour`), and `chgame` run from inside a game's folder
finds the game by itself (`here()`).

Sketches for the repository's own use, which the board package does not
ship (CHSDtest, the SD card test bench), are in tools/sketches/<Name>.

A sketch from another repository works too (`chgame --sketch
D:/src/CHPower/libraries/CHPower/examples/CHPDTrigger build`): when it is
an example of a library there, it builds with that library and the ones
beside it (sketch_libraries()), and the scripts the tools run find these
tools through $CHGAME_TOOLS, set here.
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIBRARIES = REPO / "platform" / "board" / "arduino" / "CHGame" / "libraries"
EXAMPLES = LIBRARIES / "CHGame" / "examples"
GAMES = EXAMPLES / "Games"
APPS = EXAMPLES / "Apps"
SKETCHES = REPO / "tools" / "sketches"
# The Python uploader, the package chgame_upload (the bootloader's host side;
# the Go tool in host/go is what the board package ships). On sys.path when
# not installed: `import chgame_upload`.
UPLOADER_DIR = REPO / "platform" / "bootloader" / "host" / "py"
if str(UPLOADER_DIR) not in sys.path:
    sys.path.append(str(UPLOADER_DIR))
# For a sketch's own scripts (tools/chsim/chdrive.py) outside this repository.
os.environ.setdefault("CHGAME_TOOLS", str(REPO / "tools"))


def sketch_libraries(sketch):
    """The Arduino libraries a sketch from another repository builds with:
    the library it is an example of (the first folder above it with a
    library.properties) and every library beside that one, as in that
    repository's libraries/ folder. Empty for this repository's sketches,
    whose libraries are LIBRARIES. A sketch in another repository but in
    no library (its extras/, say) gets that repository's libraries/ folder."""
    sketch = Path(sketch).resolve()
    if REPO.resolve() in sketch.parents:
        return []
    for up in sketch.parents:
        if (up / "library.properties").exists():
            return sorted(p for p in up.parent.iterdir() if (p / "library.properties").exists())
    for up in sketch.parents:
        libs = sorted(p for p in (up / "libraries").glob("*") if (p / "library.properties").exists())
        if libs:
            return libs
    return []


def games():
    """Every game's folder, in name order."""
    return sorted(d for d in GAMES.iterdir() if (d / f"{d.name}.ino").exists())


def sketch(arg="."):
    """A sketch's folder from a path or from a bare name (CHFour, CHSDtoUSB,
    Hello, GameKit, or a library: CHGfx)."""
    p = Path(arg)
    if p.is_dir() and list(p.resolve().glob("*.ino")):
        return p.resolve()
    if str(arg) == p.name:
        for base in (GAMES, APPS, EXAMPLES, LIBRARIES / "CHGfx" / "examples", SKETCHES):
            d = base / p.name
            if (d / f"{p.name}.ino").exists():
                return d
        if (LIBRARIES / p.name / "library.properties").exists():
            return LIBRARIES / p.name
    if p.is_dir():
        return p.resolve()
    raise SystemExit(f"{arg}: not a sketch folder, and not the name of a game or app in {EXAMPLES}")


def here(start=None):
    """The sketch folder at or above `start` (the current folder): the first
    one whose <Name>.ino matches its name, or a library folder. None if
    there is none."""
    d = Path(start or Path.cwd()).resolve()
    for up in (d, *d.parents):
        if (up / f"{up.name}.ino").exists() or (up / "library.properties").exists():
            return up
    return None


def repo_from(path):
    """The repository root above `path` (a game's own tool finding the shared
    ones): the folder holding tools/chsim/chsim.py and platform/. A sketch
    copied out to a sketchbook has none, and gets told so."""
    for up in Path(path).resolve().parents:
        if (up / "tools" / "chsim" / "chsim.py").exists() and (up / "platform").is_dir():
            return up
    raise SystemExit(f"{path}: the CHGame repository's tools/ was not found above this file; run it from a "
                     "checkout, or `pip install -e <repo>`")
