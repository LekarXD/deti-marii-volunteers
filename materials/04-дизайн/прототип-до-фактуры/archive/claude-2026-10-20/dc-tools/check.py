import re, sys
from html.parser import HTMLParser

VOID = {'area','base','br','col','embed','hr','img','input','link','meta','source','track','wbr','param'}
KIT = '/private/tmp/claude-501/-Users-iliapetri--claude-spares-spare-GxUBpt/91fc3645-2cae-45de-9eeb-32a080bb81c1/scratchpad/dm-canvas/kit/helmet.html'

class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []; self.errors = []
    def handle_starttag(self, tag, attrs):
        if tag in VOID: return
        self.stack.append((tag, self.getpos()))
    def handle_startendtag(self, tag, attrs):
        pass
    def handle_endtag(self, tag):
        if tag in VOID:
            self.errors.append(f'void end tag </{tag}> at {self.getpos()}'); return
        if not self.stack:
            self.errors.append(f'stray </{tag}> at {self.getpos()}'); return
        t, pos = self.stack.pop()
        if t != tag:
            self.errors.append(f'mismatch: <{t}> opened at {pos} closed by </{tag}> at {self.getpos()}')

def check(path):
    src = open(path, encoding='utf-8').read()
    p = P(); p.feed(src); p.close()
    errs = list(p.errors)
    for t, pos in p.stack:
        errs.append(f'unclosed <{t}> at {pos}')
    ok_hole = re.compile(r'^([A-Za-z_$][\w$]*(\.[\w$]+)*|true|false|\d+)$')
    holes = re.findall(r'\{\{(.*?)\}\}', src)
    bad = [h for h in holes if not ok_hole.match(h)]
    if bad: errs.append(f'bad holes: {bad}')
    if '<table' in src: errs.append('<table> used')
    if '·' in src: errs.append('middle dot used')
    emoji = re.findall('[\U0001F300-\U0001FAFF☀-➿]', src)
    if emoji: errs.append(f'emoji-like chars: {set(emoji)}')
    if '<script src="./support.js"></script>' not in src: errs.append('support.js line missing')
    kit = open(KIT, encoding='utf-8').read()
    head = kit.split('</style>')[0]
    if head not in src: errs.append('helmet is not verbatim kit prefix')
    if src.count('<sc-for') != src.count('</sc-for>'): errs.append('sc-for count mismatch')
    if src.count('<sc-if') != src.count('</sc-if>'): errs.append('sc-if count mismatch')
    m = re.search(r"data-props='(\{.*?\})'", src)
    import json
    try: props = json.loads(m.group(1)); 
    except Exception as e: errs.append(f'data-props invalid: {e}'); props=None
    # custom css font sizes < 13
    custom = src.split(head)[-1].split('</style>')[0] if head in src else ''
    small = re.findall(r'font-size:(\d+)px', custom)
    small = [s for s in small if int(s) < 13]
    if small: errs.append(f'custom font-size <13: {small}')
    print(path.split('/')[-1], 'OK' if not errs else 'ERRORS', props, f'holes={len(holes)}')
    for e in errs: print('  -', e)

for f in sys.argv[1:]: check(f)
