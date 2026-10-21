"""Run a .dc.html Component in node with a mock DCLogic, replay scenarios, and check every hole resolves."""
import json
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

RUNNER = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const scen = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
class DCLogic { constructor(props) { this.props = props || {}; } setState(p) { this.state = Object.assign({}, this.state, typeof p === 'function' ? p(this.state) : p); } }
const Component = new Function('DCLogic', src + '\nreturn Component;')(DCLogic);
function snap(v, depth) {
  if (typeof v === 'function') return '__fn__';
  if (v === undefined) return '__undef__';
  if (Array.isArray(v)) return v.map((x) => snap(x, depth + 1));
  if (v && typeof v === 'object') { const o = {}; for (const k of Object.keys(v)) o[k] = snap(v[k], depth + 1); return o; }
  return v;
}
function get(obj, path) { return path.split('.').reduce((a, k) => (a == null ? undefined : a[k]), obj); }
const out = [];
for (const sc of scen) {
  const c = new Component({});
  const steps = [];
  try {
    for (const st of sc.steps) {
      const vals = c.renderVals();
      const fn = get(vals, st.fn);
      if (typeof fn !== 'function') throw new Error('not a function: ' + st.fn);
      fn(st.value !== undefined ? { target: { value: st.value } } : undefined);
    }
    out.push({ name: sc.name, vals: snap(c.renderVals(), 0) });
  } catch (e) { out.push({ name: sc.name, error: String(e && e.stack || e) }); }
}
process.stdout.write(JSON.stringify(out));
"""


class Node:
    def __init__(self, tag, attrs, line):
        self.tag, self.attrs, self.line, self.children = tag, attrs, line, []


class TP(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", [], 0)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.getpos()[0])
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.stack[-1].tag in ("script", "style"):
            return
        if "{{" in data:
            self.stack[-1].children.append(("text", data, self.getpos()[0]))


HOLE = re.compile(r"\{\{(.*?)\}\}")
MISSING = object()


def lookup(expr, scopes):
    if expr in ("true", "false"):
        return expr == "true"
    parts = expr.split(".")
    for sc in reversed(scopes):
        if parts[0] in sc:
            v = sc[parts[0]]
            for p in parts[1:]:
                if isinstance(v, dict) and p in v:
                    v = v[p]
                else:
                    return MISSING
            return v
    return MISSING


def walk(node, scopes, errs, counts):
    if isinstance(node, tuple):
        for m in HOLE.finditer(node[1]):
            v = lookup(m.group(1), scopes)
            if v is MISSING or v == "__undef__" or v is None:
                errs.append(f"text hole {{{{{m.group(1)}}}}} unresolved (line {node[2]})")
            elif isinstance(v, (dict, list)):
                errs.append(f"text hole {{{{{m.group(1)}}}}} is object (line {node[2]})")
        return
    attrs = dict(node.attrs)
    if node.tag == "sc-if":
        m = HOLE.fullmatch(attrs.get("value", ""))
        v = lookup(m.group(1), scopes) if m else MISSING
        if v is MISSING or v == "__undef__":
            errs.append(f"sc-if {attrs.get('value')} unresolved (line {node.line})")
            return
        if not isinstance(v, bool):
            errs.append(f"sc-if {attrs.get('value')} not boolean: {v!r} (line {node.line})")
        if not v:
            return
        counts["if_on"] += 1
        for ch in node.children:
            walk(ch, scopes, errs, counts)
        return
    if node.tag == "sc-for":
        m = HOLE.fullmatch(attrs.get("list", ""))
        v = lookup(m.group(1), scopes) if m else MISSING
        if not isinstance(v, list):
            errs.append(f"sc-for {attrs.get('list')} not a list: {v!r:.60} (line {node.line})")
            return
        alias = attrs.get("as")
        counts["for_items"] += len(v)
        for item in v:
            for ch in node.children:
                walk(ch, scopes + [{alias: item}], errs, counts)
        return
    for k, val in node.attrs:
        if val is None:
            continue
        for m in HOLE.finditer(val):
            v = lookup(m.group(1), scopes)
            if v is MISSING or v == "__undef__":
                errs.append(f"attr {node.tag}[{k}] {{{{{m.group(1)}}}}} unresolved (line {node.line})")
            elif k.lower().startswith("on") and v != "__fn__":
                errs.append(f"handler {node.tag}[{k}] {{{{{m.group(1)}}}}} not a function (line {node.line})")
            elif not k.lower().startswith("on") and v == "__fn__":
                errs.append(f"attr {node.tag}[{k}] got a function (line {node.line})")
    counts["elems"] += 1
    for ch in node.children:
        walk(ch, scopes, errs, counts)


def main():
    path = Path(sys.argv[1])
    scen = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    src = path.read_text(encoding="utf-8")
    tpl = src[src.index("<x-dc>"): src.index("</x-dc>")]
    tpl = tpl[tpl.index("</helmet>") + len("</helmet>"):]
    m = re.search(r"<script type=\"text/x-dc\"[^>]*>(.*?)</script>", src, re.S)
    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / "s.js"
        sp.write_text(m.group(1), encoding="utf-8")
        rp = Path(td) / "r.js"
        rp.write_text(RUNNER, encoding="utf-8")
        scp = Path(td) / "sc.json"
        scp.write_text(json.dumps(scen), encoding="utf-8")
        res = subprocess.run(["node", str(rp), str(sp), str(scp)], capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr)
        sys.exit(1)
    out = json.loads(res.stdout)
    tp = TP()
    tp.feed(tpl)
    bad = False
    for o in out:
        if "error" in o:
            print(f"  [{o['name']}] ERROR {o['error'][:400]}")
            bad = True
            continue
        errs, counts = [], {"if_on": 0, "for_items": 0, "elems": 0}
        walk(tp.root, [o["vals"]], errs, counts)
        status = "ok" if not errs else "FAIL"
        bad |= bool(errs)
        print(f"  [{o['name']}] {status} elems={counts['elems']} ifs_on={counts['if_on']} loop_items={counts['for_items']}")
        for e in errs[:12]:
            print("     -", e)
        if len(sys.argv) > 3 and sys.argv[3] == "dump":
            print(json.dumps(o["vals"], ensure_ascii=False)[:3000])
    sys.exit(1 if bad else 0)


main()
