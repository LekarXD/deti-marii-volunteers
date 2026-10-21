import re, sys, subprocess, os, tempfile
from html.parser import HTMLParser

ROOT = '/private/tmp/claude-501/-Users-iliapetri--claude-spares-spare-GxUBpt/91fc3645-2cae-45de-9eeb-32a080bb81c1/scratchpad/dm-canvas'
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','source','track','wbr'}

class P(HTMLParser):
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
        pass
    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append('stray </%s> at %s' % (tag, self.getpos()))
            return
        top, pos = self.stack[-1]
        if top == tag:
            self.stack.pop()
        else:
            self.errors.append('mismatch: </%s> at %s but open <%s> from %s' % (tag, self.getpos(), top, pos))
            # try recover
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break

def check(path):
    src = open(path, encoding='utf-8').read()
    out = []
    # helmet
    kit = open(os.path.join(ROOT, 'kit/helmet.html'), encoding='utf-8').read()
    kit_body = kit.split('</style>')[0]
    h0 = src.find('<helmet>')
    h1 = src.find('</helmet>')
    helm = src[h0:h1 + len('</helmet>')]
    if not helm.startswith(kit_body):
        # find first diff
        n = min(len(helm), len(kit_body))
        i = next((k for k in range(n) if helm[k] != kit_body[k]), n)
        out.append('HELMET differs from kit at char %d: kit=%r file=%r' % (i, kit_body[i:i+60], helm[i:i+60]))
    else:
        extra = helm[len(kit_body):]
        out.append('helmet: verbatim kit + %d extra css lines' % (extra.count('\n') - 2))
    if '<script src="./support.js"></script>' not in src:
        out.append('MISSING support.js line')
    # tags (body only, skip script content handled by parser as cdata)
    p = P()
    p.feed(src)
    p.close()
    if p.errors:
        out.extend('TAG ' + e for e in p.errors[:20])
    if p.stack:
        out.append('UNCLOSED: ' + ', '.join('%s@%s' % (t, pos) for t, pos in p.stack))
    # holes
    holes = re.findall(r'\{\{(.*?)\}\}', src)
    bad = [h for h in holes if not re.fullmatch(r'(true|false|[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*)', h)]
    if bad:
        out.append('BAD HOLES: %r' % bad)
    # top-level keys exist in script
    script = re.search(r'<script type="text/x-dc"[^>]*>(.*?)</script>', src, re.S).group(1)
    tops = sorted({h.split('.')[0] for h in holes if h not in ('true', 'false')} - p.aliases)
    missing = [t for t in tops if not re.search(r'(^|[\s,{])' + re.escape(t) + r'\s*[:,}\n]', script)]
    if missing:
        out.append('KEYS maybe missing in renderVals: %r' % missing)
    # forbidden
    if re.search(r'<table', src, re.I):
        out.append('HAS <table>')
    if '·' in src:
        out.append('HAS middot')
    emo = re.findall(r'[\U0001F300-\U0001FAFF☀-➿]', src)
    if emo:
        out.append('EMOJI-ish chars: %r' % emo)
    if re.search(r'font-weight:\s*[89]00', src):
        out.append('weight 800+')
    out.append('btn-primary occurrences: %d' % len(re.findall(r'btn-primary', src.split('</helmet>')[1])))
    m = re.search(r"data-props='([^']*)'", src)
    out.append('data-props: ' + (m.group(1) if m else 'MISSING'))
    # js syntax
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, dir=os.path.dirname(__file__)) as tf:
        tf.write('class DCLogic { constructor(p){} setState(){} }\n' + script + '\nconst c = new Component({}); const v = c.renderVals(); console.log(Object.keys(v).length + " keys");\n')
        tfn = tf.name
    r = subprocess.run(['node', tfn], capture_output=True, text=True)
    os.unlink(tfn)
    out.append('node: ' + (r.stdout.strip() or '') + (' ERR ' + r.stderr.strip()[:400] if r.returncode else ''))
    return out

for f in sys.argv[1:]:
    print('==', os.path.basename(f))
    for line in check(f):
        print('  ' + line)
