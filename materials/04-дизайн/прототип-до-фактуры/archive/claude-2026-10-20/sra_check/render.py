import sys, json, re, subprocess, html
from html.parser import HTMLParser
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','source','track','wbr'}
class Node:
    def __init__(s, tag, attrs, selfclose=False):
        s.tag, s.attrs, s.children, s.selfclose = tag, attrs, [], selfclose
class TB(HTMLParser):
    def __init__(s):
        super().__init__(convert_charrefs=False)
        s.root = Node('root', []); s.stack = [s.root]
    def handle_starttag(s, tag, attrs):
        n = Node(tag, attrs); s.stack[-1].children.append(n)
        if tag not in VOID: s.stack.append(n)
    def handle_startendtag(s, tag, attrs):
        s.stack[-1].children.append(Node(tag, attrs, True))
    def handle_endtag(s, tag):
        if tag in VOID: return
        for i in range(len(s.stack)-1, 0, -1):
            if s.stack[i].tag == tag:
                del s.stack[i:]; return
    def handle_data(s, d): s.stack[-1].children.append(d)
    def handle_entityref(s, n): s.stack[-1].children.append('&%s;' % n)
    def handle_charref(s, n): s.stack[-1].children.append('&#%s;' % n)
    def handle_comment(s, d): pass

def look(path, scopes):
    parts = path.split('.')
    for sc in reversed(scopes):
        if isinstance(sc, dict) and parts[0] in sc:
            v = sc[parts[0]]
            for p in parts[1:]:
                v = v.get(p) if isinstance(v, dict) else None
            return v
    if parts[0] in ('true',): return True
    if parts[0] in ('false',): return False
    return None
def sub(text, scopes):
    def r(m):
        v = look(m.group(1), scopes)
        if v is None: return ''
        if v is True: return 'true'
        if v is False: return 'false'
        return str(v)
    return re.sub(r'\{\{(.*?)\}\}', r, text)
def hole(attrval):
    m = re.fullmatch(r'\{\{(.*?)\}\}', attrval or '')
    return m.group(1) if m else None
def render(n, scopes, out):
    if isinstance(n, str):
        out.append(sub(n, scopes)); return
    if n.tag == 'root' or n.tag == 'helmet':
        for c in n.children: render(c, scopes, out)
        return
    a = dict(n.attrs)
    if n.tag == 'sc-if':
        if look(hole(a.get('value')), scopes):
            for c in n.children: render(c, scopes, out)
        return
    if n.tag == 'sc-for':
        lst = look(hole(a.get('list')), scopes) or []
        for it in lst:
            for c in n.children: render(c, scopes + [{a['as']: it}], out)
        return
    attrs = []
    for k, v in n.attrs:
        if k.lower().startswith('on'): continue
        if v is None: attrs.append(k); continue
        attrs.append('%s="%s"' % (k, html.escape(sub(v, scopes), quote=True)))
    out.append('<%s%s%s>' % (n.tag, (' ' + ' '.join(attrs)) if attrs else '', '/' if n.selfclose else ''))
    if n.tag == 'textarea' and 'value' in a:
        out.append(html.escape(sub(a['value'], scopes)))
    for c in n.children: render(c, scopes, out)
    if not n.selfclose and n.tag not in VOID:
        out.append('</%s>' % n.tag)

src_path, steps, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(src_path, encoding='utf-8').read()
vals = json.loads(subprocess.run(['node', __file__.replace('render.py', 'vals.js'), src_path, steps], capture_output=True, text=True, check=True).stdout)
body = src.split('<x-dc>')[1].split('</x-dc>')[0]
tb = TB(); tb.feed(body)
out = []
render(tb.root, [vals], out)
title = re.search(r'<title>(.*?)</title>', src).group(1)
open(out_path, 'w', encoding='utf-8').write('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>%s</title></head><body>%s</body></html>' % (title, ''.join(out)))
print('wrote', out_path)
