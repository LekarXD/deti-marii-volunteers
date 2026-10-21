import sys, re, json, subprocess, os
from html.parser import HTMLParser

VOID = {'area','base','br','col','embed','hr','img','input','link','meta','source','track','wbr','path','circle','rect','ellipse','line','polyline','polygon'}
BLOCK = {'div','section','aside','nav','header','footer','h1','h2','h3','h4','h5','h6','ul','ol','p','form','table','main'}
HOLE_OK = re.compile(r'^[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*$')
KIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dm-canvas', 'kit', 'helmet.html')


class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errs = []
        self.scopes = []  # (alias, listExpr)
        self.holes = []   # {expr, scopes}
        self.in_xdc = False
        self.ids = {}

    def _hole_scan(self, text):
        for m in re.finditer(r'\{\{(.*?)\}\}', text):
            raw = m.group(1).strip()
            if raw in ('true', 'false'):
                continue
            if not HOLE_OK.match(raw):
                self.errs.append('bad hole expression: {{%s}} at line %d' % (raw, self.getpos()[0]))
                continue
            self.holes.append({'expr': raw, 'scopes': list(self.scopes), 'line': self.getpos()[0]})

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        if tag == 'x-dc':
            self.in_xdc = True
        if tag == 'p' or tag == 'span' or tag == 'button' or tag == 'a':
            pass
        # block inside p / span
        if tag in BLOCK:
            for t, l in reversed(self.stack):
                if t in ('sc-if', 'sc-for'):
                    continue
                if t == 'p':
                    self.errs.append('block <%s> inside <p> (line %d, p at %d)' % (tag, line, l))
                if t in ('span', 'button', 'a') and tag in ('div', 'section', 'p', 'h1', 'h2', 'h3', 'h4', 'ul', 'ol'):
                    self.errs.append('block <%s> inside <%s> (line %d)' % (tag, t, line))
                break
        d = dict(attrs)
        if 'id' in d and '{{' not in (d['id'] or ''):
            if d['id'] in self.ids:
                self.errs.append('duplicate id %s (lines %d, %d)' % (d['id'], self.ids[d['id']], line))
            self.ids[d['id']] = line
        if self.in_xdc:
            for k, v in attrs:
                if v and '{{' in v:
                    if k in ('style', 'class') and not re.fullmatch(r'\{\{[^}]*\}\}', v.strip()):
                        self.errs.append('partial hole in %s="%s" line %d' % (k, v, line))
                    self._hole_scan(v)
        if tag == 'table':
            self.errs.append('<table> used at line %d' % line)
        if tag == 'sc-for':
            lst = d.get('list', '')
            m = re.fullmatch(r'\{\{\s*([\w$.]+)\s*\}\}', lst or '')
            if not m or not d.get('as'):
                self.errs.append('bad sc-for at line %d' % line)
            self.scopes.append((d.get('as'), m.group(1) if m else ''))
            # list hole was scanned above with outer scopes: pop that duplicate? keep (it's valid in outer scope)
        if tag == 'sc-if':
            if 'hint-placeholder-val' not in d:
                self.errs.append('sc-if without hint at line %d' % line)
        if tag == 'button' and self.in_xdc and d.get('type') != 'button':
            self.errs.append('<button> without type=button at line %d' % line)
        if tag in VOID:
            return
        self.stack.append((tag, line))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
            if tag == 'sc-for':
                self.scopes.pop()

    def handle_endtag(self, tag):
        line = self.getpos()[0]
        if tag in VOID:
            return
        if not self.stack:
            self.errs.append('stray </%s> at line %d' % (tag, line))
            return
        t, l = self.stack[-1]
        if t != tag:
            self.errs.append('mismatch: </%s> at line %d closes <%s> from line %d' % (tag, line, t, l))
            # try recover
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    for tt, _ in self.stack[i + 1:]:
                        if tt == 'sc-for':
                            self.scopes.pop()
                    del self.stack[i:]
                    break
            return
        self.stack.pop()
        if tag == 'sc-for':
            self.scopes.pop()
        if tag == 'x-dc':
            self.in_xdc = False

    def handle_data(self, data):
        if self.in_xdc and '{{' in data:
            self._hole_scan(data)


def main(path):
    src = open(path, encoding='utf-8').read()
    errs = []
    if '<script src="./support.js"></script>' not in src:
        errs.append('support.js line missing')
    # helmet verbatim
    kit = open(KIT, encoding='utf-8').read().strip()
    kit_head = kit[:kit.rindex('</style>')]
    hm = re.search(r'<helmet>.*?</helmet>', src, re.S)
    if not hm:
        errs.append('no helmet')
    else:
        h = hm.group(0)
        if not h.startswith(kit_head):
            # find first diff
            for i, (a, b) in enumerate(zip(h, kit_head)):
                if a != b:
                    errs.append('helmet differs from kit at char %d: %r vs %r' % (i, h[max(0, i - 40):i + 40], kit_head[max(0, i - 40):i + 40]))
                    break
            else:
                errs.append('helmet shorter than kit')
        if not h.endswith('</style>\n</helmet>'):
            errs.append('helmet tail unexpected')
    # emoji check
    if re.search('[\U0001F300-\U0001FAFF☀-➿]', src):
        errs.append('emoji-like char found')
    if '·' in src:
        errs.append('middle dot found')
    body = src[src.index('<x-dc>'):src.index('</x-dc>') + len('</x-dc>')]
    p = P()
    p.feed(src[:src.index('<script type="text/x-dc"')])
    rest = [(t, l) for t, l in p.stack if t not in ('html', 'body')]
    if rest:
        errs.append('unclosed: %s' % rest)
    errs += p.errs
    # font sizes below 15 in custom css / inline styles (report)
    small = []
    for m in re.finditer(r'font-size:(\d+)px', src):
        if int(m.group(1)) < 15:
            small.append(m.group(1))
    sm = re.search(r"<script type=\"text/x-dc\" data-dc-script data-props='(.*?)'>(.*?)</script>", src, re.S)
    if not sm:
        errs.append('dc script not found')
        print('\n'.join(errs)); return 1
    props = json.loads(sm.group(1))
    js = sm.group(2)
    tmp = path + '.holes.json'
    json.dump({'holes': p.holes, 'js': js}, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    r = subprocess.run(['node', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harness.js'), tmp], capture_output=True, text=True)
    os.remove(tmp)
    print('== %s' % os.path.basename(path))
    print('props:', props)
    print('holes:', len(p.holes))
    for e in errs:
        print('ERR', e)
    print(r.stdout.strip())
    if r.stderr.strip():
        print('NODE STDERR', r.stderr.strip()[:3000])
    return 0


if __name__ == '__main__':
    for f in sys.argv[1:]:
        main(f)
