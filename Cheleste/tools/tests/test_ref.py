"""The port against the cart's Lua (tools/ref/compare.py), a quick round:
the title and every room, 300 frames each. Skipped without the cart
(assets/celeste.p8 is not in the repository) or without lupa."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if not (ROOT / "assets" / "celeste.p8").exists():
    print("ref: skipped (no assets/celeste.p8)")
    sys.exit(0)
try:
    import lupa  # noqa: F401
except ImportError:
    print("ref: skipped (pip install lupa)")
    sys.exit(0)
r = subprocess.run([sys.executable, str(ROOT / "tools" / "ref" / "compare.py"), "--frames", "300", "--seeds", "2"],
                   capture_output=True, text=True)
last = (r.stdout.strip().splitlines() or ["?"])[-1]
print(f"ref: {last}")
if r.returncode:
    print("\n".join(l for l in r.stdout.splitlines() if not l.startswith("ok"))[:4000])
sys.exit(r.returncode)
