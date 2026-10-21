"""Validate .dc.html artboards: tag balance, helmet verbatim, lookup-only holes, misc brief rules."""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(sys.argv[1])
FILES = sys.argv[2:]
KIT = (ROOT / "kit" / "helmet.html").read_text(encoding="utf-8")
MEDIA_LINE = "@media (max-width:720px){.shell{padding:12px 16px 56px}"
kit_prefix = KIT[: KIT.index(MEDIA_LINE)]
kit_media = KIT[KIT.index(MEDIA_LINE):].split("\n", 1)[0]

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SVG_SELF = {"path", "circle", "rect", "ellipse", "line", "polyline", "polygon"}
HOLE = re.compile(r"\{\{(.*?)\}\}", re.S)
LOOKUP = re.compile(r"^[A-Za-z_$][\w$]*(\.[\w$]+)*$")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅]")


class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.aliases = []  # stack of (depth, alias)
        self.roots = set()
        self.loop_root_refs = []

    def _holes(self, text, where):
        for m in HOLE.finditer(text):
            expr = m.group(1)
            if expr in ("true", "false"):
                continue
            if expr != expr.strip() or not LOOKUP.match(expr):
                self.errors.append(f"non-lookup hole {{{{{expr}}}}} at {where}")
                continue
            root = expr.split(".")[0]
            alias_names = [a for _, a in self.aliases]
            if root in alias_names:
                continue
            self.roots.add(root)
            if self.aliases:
                self.loop_root_refs.append((expr, where))

    def handle_starttag(self, tag, attrs):
        pos = self.getpos()
        for k, v in attrs:
            if v is not None:
                self._holes(v, f"{tag}[{k}] line {pos[0]}")
        if tag == "sc-for":
            d = dict(attrs)
            self._holes(d.get("list", ""), f"sc-for list line {pos[0]}")
        BLOCK = {"div", "p", "h1", "h2", "h3", "h4", "section", "aside", "ol", "ul", "nav", "header", "hr", "textarea" if False else "_"}
        INLINE = {"span", "button", "label", "a"}
        if tag in BLOCK:
            open_tags = [t for t, _ in self.stack]
            bad = [t for t in open_tags if t in INLINE]
            if bad:
                self.errors.append(f"nesting: <{tag}> inside <{bad[-1]}> line {pos[0]}")
            if "p" in open_tags:
                self.errors.append(f"nesting: <{tag}> inside <p> line {pos[0]}")
        if tag in VOID:
            return
        self.stack.append((tag, pos[0]))
        if tag == "sc-for":
            self.aliases.append((len(self.stack), dict(attrs).get("as")))

    def handle_startendtag(self, tag, attrs):
        pos = self.getpos()
        for k, v in attrs:
            if v is not None:
                self._holes(v, f"{tag}[{k}] line {pos[0]}")
        if tag not in VOID and tag not in SVG_SELF:
            self.errors.append(f"self-closing non-void <{tag}/> line {pos[0]}")

    def handle_endtag(self, tag):
        pos = self.getpos()
        if tag in VOID:
            self.errors.append(f"closing void </{tag}> line {pos[0]}")
            return
        if not self.stack:
            self.errors.append(f"stray </{tag}> line {pos[0]}")
            return
        top, line = self.stack[-1]
        if top != tag:
            self.errors.append(f"mismatch: </{tag}> line {pos[0]} closes <{top}> from line {line}")
            # try recover
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break
        else:
            self.stack.pop()
        while self.aliases and self.aliases[-1][0] > len(self.stack):
            self.aliases.pop()

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] in ("script", "style"):
            return
        self._holes(data, f"text line {self.getpos()[0]}")


ok_all = True
for name in FILES:
    path = ROOT / "project" / name
    src = path.read_text(encoding="utf-8")
    errs = []
    # helmet verbatim
    h0 = src.index("<helmet>")
    h1 = src.index("</helmet>") + len("</helmet>")
    helmet = src[h0:h1]
    if not helmet.startswith(kit_prefix):
        for i, (a, b) in enumerate(zip(helmet, kit_prefix)):
            if a != b:
                errs.append(f"helmet differs from kit at char {i}: {helmet[i-40:i+40]!r}")
                break
        else:
            errs.append("helmet shorter than kit prefix")
    if kit_media not in helmet:
        errs.append("kit @media line missing/changed")
    if '<script src="./support.js"></script>' not in src:
        errs.append("support.js line missing")
    # parse
    p = P()
    p.feed(src)
    p.close()
    errs += p.errors
    if p.stack:
        errs.append(f"unclosed: {p.stack}")
    # data-props
    m = re.search(r"data-props='([^']*)'", src)
    props = json.loads(m.group(1)) if m else None
    if not props or set(props) != {"$preview"}:
        errs.append(f"bad data-props {props}")
    # script roots
    script = src[src.index("data-dc-script"):]
    missing = []
    for r in sorted(p.roots):
        if not re.search(r"(?<![\w$.])" + re.escape(r) + r"\s*[:,\n}]", script):
            missing.append(r)
    if missing:
        errs.append(f"holes not found as keys in renderVals: {missing}")
    if p.loop_root_refs:
        errs.append(f"root-level holes used inside sc-for: {p.loop_root_refs[:6]}")
    # brief rules
    body = src[h1:]
    if "<table" in body:
        errs.append("<table> used")
    if "·" in body:
        errs.append("middle dot used")
    if EMOJI.search(src):
        errs.append(f"emoji found: {EMOJI.findall(src)[:5]}")
    if "<a" in body and re.search(r"<a\b[^>]*>(?:(?!</a>).)*<button", body, re.S):
        errs.append("button inside <a>")
    for fs in re.findall(r"font-size:(\d+)px", body):
        if int(fs) < 15 and int(fs) != 13:
            errs.append(f"inline font-size {fs}px")
    n_primary = len(re.findall(r"btn-primary", body))
    status = "OK" if not errs else "FAIL"
    ok_all &= not errs
    print(f"== {name}: {status}  (tags ok={not p.stack}, holes roots={len(p.roots)}, btn-primary occurrences={n_primary}, preview={props})")
    for e in errs:
        print("   -", e)
sys.exit(0 if ok_all else 1)
