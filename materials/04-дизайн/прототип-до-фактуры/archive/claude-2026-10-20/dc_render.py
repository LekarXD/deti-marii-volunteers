"""Render one scenario of a .dc.html into static HTML for visual review (uses dc_runtime_check internals)."""
import html, json, re, subprocess, sys, tempfile
from pathlib import Path
sys.argv_backup = list(sys.argv)
import importlib.util
spec = importlib.util.spec_from_file_location("rc", str(Path(__file__).parent / "dc_runtime_check.py"))
src_rc = Path(spec.origin).read_text(encoding="utf-8").replace("\nmain()\n", "\n")
rc = {}
exec(compile(src_rc, "rc", "exec"), rc)
VOID = rc["VOID"]; HOLE = rc["HOLE"]; lookup = rc["lookup"]; MISSING = rc["MISSING"]

def fill(text, scopes):
    def rep(m):
        v = lookup(m.group(1), scopes)
        if v is MISSING: return "??"
        if isinstance(v, bool): return "true" if v else "false"
        return str(v)
    return HOLE.sub(rep, text)

def render(node, scopes, out, selectval=None):
    if isinstance(node, tuple):
        out.append(html.escape(fill(node[1], scopes), quote=False)); return
    if isinstance(node, str):
        out.append(html.escape(node, quote=False)); return
    a = dict(node.attrs)
    if node.tag == "sc-if":
        v = lookup(HOLE.fullmatch(a["value"]).group(1), scopes)
        if v is True:
            for ch in node.children: render(ch, scopes, out)
        return
    if node.tag == "sc-for":
        v = lookup(HOLE.fullmatch(a["list"]).group(1), scopes)
        for it in v:
            for ch in node.children: render(ch, scopes + [{a["as"]: it}], out)
        return
    if node.tag == "root":
        for ch in node.children: render(ch, scopes, out)
        return
    attrs = []
    val = None
    for k, v in node.attrs:
        if k.lower().startswith("on"): continue
        if v is None: attrs.append(k); continue
        fv = fill(v, scopes)
        if k == "value" and node.tag in ("select", "textarea"):
            val = fv; continue
        if k == "value" and node.tag == "option" and selectval is not None and fv == selectval:
            attrs.append("selected")
        attrs.append(f'{k}="{html.escape(fv)}"')
    out.append(f"<{node.tag}{(' ' + ' '.join(attrs)) if attrs else ''}>")
    if node.tag in VOID: return
    if node.tag == "textarea":
        out.append(html.escape(val or "")); out.append("</textarea>"); return
    for ch in node.children:
        render(ch, scopes, out, val if node.tag == "select" else selectval)
    out.append(f"</{node.tag}>")

class TP2(rc["TP"]):
    def handle_data(self, data):
        if self.stack[-1].tag in ("script", "style"):
            return
        if "{{" in data: self.stack[-1].children.append(("text", data, self.getpos()[0]))
        else: self.stack[-1].children.append(data)

def main():
    path = Path(sys.argv[1]); scen = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")); outdir = Path(sys.argv[3])
    src = path.read_text(encoding="utf-8")
    helmet = src[src.index("<helmet>") + 8: src.index("</helmet>")]
    tpl = src[src.index("</helmet>") + 9: src.index("</x-dc>")]
    m = re.search(r"<script type=\"text/x-dc\"[^>]*>(.*?)</script>", src, re.S)
    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / "s.js"; sp.write_text(m.group(1), encoding="utf-8")
        rp = Path(td) / "r.js"; rp.write_text(rc["RUNNER"], encoding="utf-8")
        scp = Path(td) / "sc.json"; scp.write_text(json.dumps(scen), encoding="utf-8")
        res = subprocess.run(["node", str(rp), str(sp), str(scp)], capture_output=True, text=True)
    out = json.loads(res.stdout)
    tp = TP2(); tp.feed(tpl)
    for o in out:
        buf = []
        render(tp.root, [o["vals"]], buf)
        doc = "<!doctype html><html lang=ru><head><meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'>" + helmet + "<style>sc-for,sc-if{display:contents}</style></head><body>" + "".join(buf) + "</body></html>"
        fn = outdir / f"{path.stem.replace('.dc','')}--{o['name']}.html"
        fn.write_text(doc, encoding="utf-8")
        print(fn.name)
main()
