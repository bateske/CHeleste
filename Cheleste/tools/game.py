"""Cheleste: what the shared CHGame tools need to know (the schema is
chgame/tools/gamecfg.py's docstring; `cl test`, `cl check` and `cl redraw`
read this)."""

# fix: Fix.h's PICO-8 numbers against PICO-8's own answers.
TESTS = {
    "fix": dict(sources=["tools/tests/test_fix.cpp", "Fix.cpp", "src/assets/Sine.cpp"]),
}

# The port against the cart's Lua, every room (needs assets/celeste.p8 and lupa; else skipped).
EXTRA_TEST_SCRIPTS = ["tools/tests/test_ref.py"]

# The playthrough is the whole game (several minutes in the simulator): once, not twice.
ONCE_SCRIPTS = {"playthrough"}
