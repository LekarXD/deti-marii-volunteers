"""Assemble <name>.src.html + <name>.css into ROOT/project/<Name>.dc.html with kit helmet verbatim."""
import sys
from pathlib import Path
HERE = Path(__file__).parent
ROOT = HERE.parent / "dm-canvas"
kit = (ROOT / "kit" / "helmet.html").read_text(encoding="utf-8").rstrip("\n")
END = "</style>\n</helmet>"
assert kit.endswith(END), repr(kit[-40:])
for name in sys.argv[1:]:
    src = (HERE / "src" / f"{name}.src.html").read_text(encoding="utf-8")
    css = (HERE / "src" / f"{name}.css").read_text(encoding="utf-8").strip("\n")
    helmet = kit[: -len(END)] + "\n" + css + "\n" + END
    assert src.count("<!--HELMET-->") == 1
    out = src.replace("<!--HELMET-->", helmet)
    (ROOT / "project" / f"{name}.dc.html").write_text(out, encoding="utf-8")
    print("wrote", name, len(out))
