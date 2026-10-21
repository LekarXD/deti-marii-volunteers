import re, sys, os, glob
from html.parser import HTMLParser
O, N = sys.argv[1], sys.argv[2]
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr',
        # SVG self-closing shapes are handled via startendtag; these are void only when written as <x/>
        }
class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []; self.errs = []; self.seq = []
    def handle_starttag(self, tag, attrs):
        self.seq.append('<' + tag)
        if tag not in VOID: self.stack.append((tag, self.getpos()))
    def handle_startendtag(self, tag, attrs):
        self.seq.append('<' + tag + '/')
    def handle_endtag(self, tag):
        self.seq.append('</' + tag)
        if tag in VOID: return
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop(); return
        names = [t for t, _ in self.stack]
        if tag in names:
            while self.stack and self.stack[-1][0] != tag:
                t, pos = self.stack.pop(); self.errs.append(f'unclosed <{t}> at {pos}')
            self.stack.pop()
        else:
            self.errs.append(f'stray </{tag}> at {self.getpos()}')
def analyse(path):
    src = open(path, encoding='utf-8').read()
    p = P(); p.feed(src); p.close()
    errs = p.errs + [f'unclosed <{t}> at {pos}' for t, pos in p.stack]
    markup = re.sub(r'<script\b[^>]*>.*?</script>', '', src, flags=re.S)
    holes = re.findall(r'\{\{(.*?)\}\}', markup, flags=re.S)
    badholes = [h for h in holes if not re.fullmatch(r'\s*([A-Za-z_$][\w$]*(\.[\w$]+)*|true|false|-?\d+(\.\d+)?)\s*', h)]
    cnt = {k: len(re.findall(k, src)) for k in (r'<sc-if\b', r'</sc-if>', r'<sc-for\b', r'</sc-for>')}
    return errs, badholes, cnt, p.seq, len(holes)
allok = True
for f in sorted(glob.glob(os.path.join(N, '*.dc.html'))):
    b = os.path.basename(f)
    e1, h1, c1, s1, nh1 = analyse(os.path.join(O, b))
    e2, h2, c2, s2, nh2 = analyse(f)
    scok = c2[r'<sc-if\b'] == c2[r'</sc-if>'] and c2[r'<sc-for\b'] == c2[r'</sc-for>']
    same = s1 == s2 and c1 == c2 and nh1 == nh2
    status = 'OK' if (not e2 and not h2 and scok and same) else 'CHECK'
    if status != 'OK': allok = False
    v = list(c2.values())
    print(f'{b:28s} tags-unbalanced:{len(e2)} (orig {len(e1)})  bad-holes:{len(h2)}  holes:{nh2}  sc-if {v[0]}/{v[1]}  sc-for {v[2]}/{v[3]}  tag-seq-identical:{s1 == s2}  -> {status}')
    for x in e2[:5]: print('    ', x)
    for x in h2[:5]: print('     hole:', x)
print('ALL OK' if allok else 'SOME CHECKS FAILED')
