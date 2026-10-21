"""Assemble a .dc.html from parts: kit helmet verbatim + own CSS + body + logic.
usage: python3 assemble.py <Name> "<title>" <width> <height>
reads v2parts/<name>.css, <name>.body.html, <name>.js; writes dm-canvas/project/<Name>.dc.html
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent / "dm-canvas"
name, title, width, height = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
low = name.lower()
kit = (ROOT / "kit" / "helmet.html").read_text(encoding="utf-8").rstrip("\n")
css = (HERE / f"{low}.css").read_text(encoding="utf-8").strip("\n")
body = (HERE / f"{low}.body.html").read_text(encoding="utf-8").strip("\n")
js = (HERE / f"{low}.js").read_text(encoding="utf-8").strip("\n")
tail = "</style>\n</helmet>"
assert kit.endswith(tail), "kit tail changed"
helmet = kit[: -len(tail)] + css + "\n" + tail
out = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
{helmet}
{body}
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":{width},"height":{height}}}}}'>
{js}
</script>
</body>
</html>
"""
(ROOT / "project" / f"{name}.dc.html").write_text(out, encoding="utf-8")
print("wrote", name, len(out))
