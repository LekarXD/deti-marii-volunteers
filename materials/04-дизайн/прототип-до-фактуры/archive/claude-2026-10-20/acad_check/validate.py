#!/usr/bin/env python3
"""Validate .dc.html artboards: helmet verbatim, tag balance, holes, JS sanity (acad agent)."""
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / 'dm-canvas'
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
SVG_SELF = {'path', 'circle', 'rect', 'ellipse', 'line', 'polyline', 'polygon'}


class Balance(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.aliases = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'sc-for':
            for k, v in attrs:
                if k == 'as':
                    self.aliases.add(v)
        if tag in VOID:
            return
        self.stack.append((tag, self.getpos()))

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID and tag not in SVG_SELF:
            self.errors.append(f'self-closed non-void <{tag}/> at {self.getpos()}')

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f'stray </{tag}> at {self.getpos()}')
            return
        top, pos = self.stack[-1]
        if top == tag:
            self.stack.pop()
            return
        self.errors.append(f'</{tag}> at {self.getpos()} closes <{top}> opened at {pos}')
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return


JS_TMPL = r"""
class DCLogic { constructor(props){ this.props = props; this.state = {}; } setState(p){ this.state = Object.assign({}, this.state, p); } }
__SCRIPT__
const c = new Component({});
const roots = __ROOTS__;
const seen = new Set();
function mark(vals){ for (const r of roots) { if (vals[r] !== undefined) seen.add(r); } }
function fire(vals, label){
  for (const [fk, fv] of Object.entries(vals)) {
    if (typeof fv === 'function') {
      try { fv({ target: { value: 'тест' } }); mark(c.renderVals()); } catch (e) { console.log('ERR ' + label + '.' + fk + ': ' + e.message); }
    }
    if (Array.isArray(fv)) {
      for (const it of fv) {
        if (it && typeof it === 'object') {
          for (const [ik, iv] of Object.entries(it)) {
            if (typeof iv === 'function') {
              try { iv(); mark(c.renderVals()); } catch (e) { console.log('ERR ' + label + '.' + fk + '[].' + ik + ': ' + e.message); }
            }
          }
        }
      }
    }
  }
}
let v0 = c.renderVals();
mark(v0);
const modeKey = Object.keys(v0).find(k => /^(modes|views|demo)$/.test(k));
const modes = modeKey ? v0[modeKey] : [null];
for (let i = 0; i < modes.length; i++) {
  const cur = c.renderVals();
  if (modeKey) { cur[modeKey][i].pick(); }
  const v = c.renderVals();
  mark(v);
  fire(v, 'mode' + i);
  mark(c.renderVals());
}
console.log(JSON.stringify({ missing: roots.filter(r => !seen.has(r)) }));
"""


def check(path: Path):
    src = path.read_text(encoding='utf-8')
    errs, notes = [], []
    if '<script src="./support.js"></script>' not in src:
        errs.append('support.js line missing')
    kit = (ROOT / 'kit' / 'helmet.html').read_text(encoding='utf-8')
    kit_prefix = kit.split('</style>')[0]
    m = re.search(r'<helmet>.*?</helmet>', src, re.S)
    if not m:
        errs.append('no helmet')
    else:
        h = m.group(0)
        if not h.startswith(kit_prefix):
            for i, (a, b) in enumerate(zip(h, kit_prefix)):
                if a != b:
                    errs.append(f'helmet differs at char {i}: file={h[max(0, i-30):i+30]!r} kit={kit_prefix[max(0, i-30):i+30]!r}')
                    break
            else:
                errs.append('helmet shorter than kit prefix')
        if not h.endswith('</style>\n</helmet>'):
            errs.append('helmet tail not </style></helmet>')
    body = re.sub(r'(<script[^>]*>).*?(</script>)', r'\1\2', src, flags=re.S)
    body = re.sub(r'(<style[^>]*>).*?(</style>)', r'\1\2', body, flags=re.S)
    p = Balance()
    p.feed(body)
    p.close()
    errs += p.errors
    if p.stack:
        errs.append('unclosed: ' + ', '.join(f'<{t}>@{pos}' for t, pos in p.stack))
    holes = re.findall(r'\{\{(.*?)\}\}', body)
    bad = [x for x in holes if not re.fullmatch(r'[A-Za-z_$][\w$]*(\.[\w$]+)*', x)]
    if bad:
        errs.append('expression holes: ' + repr(bad))
    for pat, label in [('<table', '<table>'), ('·', 'middle dot'), ('innerHTML', 'innerHTML'), ('<iframe', 'iframe'), ('Cinzel', 'Cinzel')]:
        if pat in src:
            errs.append(f'forbidden: {label}')
    emoji = re.findall('[\U0001F300-\U0001FAFF☀-➿⭐✅❌]', src)
    if emoji:
        errs.append('emoji: ' + repr(set(emoji)))
    dp = re.search(r"data-props='([^']*)'", src)
    if not dp:
        errs.append('no data-props')
    else:
        try:
            props = json.loads(dp.group(1))
            notes.append(f"preview {props['$preview']}")
        except Exception as e:  # noqa: BLE001
            errs.append(f'data-props JSON: {e}')
    notes.append(f'btn-primary occurrences in markup: {body.count("btn-primary")}')
    script = re.search(r'<script type="text/x-dc"[^>]*>(.*?)</script>', src, re.S).group(1)
    roots = sorted({x.split('.')[0] for x in holes if re.fullmatch(r'[A-Za-z_$][\w$]*(\.[\w$]+)*', x)} - p.aliases - {'true', 'false'})
    js = JS_TMPL.replace('__SCRIPT__', script).replace('__ROOTS__', json.dumps(roots))
    tmp = HERE / ('_run_' + path.stem.replace('.', '_') + '.js')
    tmp.write_text(js, encoding='utf-8')
    out = subprocess.run(['node', str(tmp)], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        errs.append('node error: ' + out.stderr.strip()[:800])
    else:
        for line in out.stdout.strip().splitlines():
            if line.startswith('ERR'):
                errs.append(line)
            elif line.startswith('{'):
                miss = json.loads(line)['missing']
                if miss:
                    notes.append('holes never defined (check!): ' + ', '.join(miss))
    return errs, notes


if __name__ == '__main__':
    ok = True
    for name in sys.argv[1:]:
        errs, notes = check(ROOT / 'project' / name)
        print(f'== {name}: {"OK" if not errs else "FAIL"}')
        for e in errs:
            print('  ERROR', e)
        for n in notes:
            print('  note ', n)
        ok = ok and not errs
    sys.exit(0 if ok else 1)
