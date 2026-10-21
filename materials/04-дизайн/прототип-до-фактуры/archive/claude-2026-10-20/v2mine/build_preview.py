import re, sys, os
OUT = '/private/tmp/claude-501/-Users-iliapetri--claude-spares-spare-GxUBpt/91fc3645-2cae-45de-9eeb-32a080bb81c1/scratchpad/v2mine/preview'
SHIM = r'''
class DCLogic { constructor(props){ this.props = props || {}; this.state = {}; } setState(p){ Object.assign(this.state, p); __render(); } }
__CODE__
const __comp = new Component({});
function __lookup(scope, path){
  path = path.trim();
  if (path === 'true') return true; if (path === 'false') return false;
  if (/^\d+$/.test(path)) return +path;
  const parts = path.split('.'); let v = scope[parts[0]];
  for (let i = 1; i < parts.length; i++) v = (v == null) ? undefined : v[parts[i]];
  return v;
}
function __interp(str, scope){
  const m = str.match(/^\{\{([^}]*)\}\}$/);
  if (m) return __lookup(scope, m[1]);
  return str.replace(/\{\{([^}]*)\}\}/g, (_, p) => { const v = __lookup(scope, p); return v == null ? '' : String(v); });
}
function __walk(src, scope, parent){
  for (const n of src.childNodes){
    if (n.nodeType === 3){ parent.appendChild(document.createTextNode(__interp(n.nodeValue, scope))); continue; }
    if (n.nodeType !== 1) continue;
    const tag = n.localName;
    if (tag === 'sc-for'){
      const list = __lookup(scope, n.getAttribute('list').replace(/[{}]/g,'')) || [];
      const as = n.getAttribute('as');
      list.forEach((item) => { const s2 = Object.create(scope); s2[as] = item; __walk(n, s2, parent); });
      continue;
    }
    if (tag === 'sc-if'){
      if (__lookup(scope, n.getAttribute('value').replace(/[{}]/g,''))) __walk(n, scope, parent);
      continue;
    }
    const el = n.namespaceURI && n.namespaceURI !== 'http://www.w3.org/1999/xhtml' ? document.createElementNS(n.namespaceURI, tag) : document.createElement(tag);
    for (const a of n.attributes){
      if (/^on/i.test(a.name)){
        const fn = __interp(a.value, scope);
        let ev = a.name.slice(2).toLowerCase();
        if (ev === 'change' && (tag === 'input' || tag === 'textarea')) ev = 'input';
        if (typeof fn === 'function') el.addEventListener(ev, fn);
        continue;
      }
      if (a.name.startsWith('hint-')) continue;
      const v = __interp(a.value, scope);
      if (a.name === 'value' && (tag === 'input' || tag === 'textarea')) { el.value = v == null ? '' : v; continue; }
      el.setAttribute(a.name, v == null ? '' : String(v));
    }
    __walk(tag === 'template' ? n.content : n, scope, el);
    parent.appendChild(el);
  }
}
function __render(){
  const ae = document.activeElement; const aid = ae && ae.id; const sel = ae && ae.selectionStart;
  const vals = __comp.renderVals();
  const root = document.getElementById('__root'); root.innerHTML = '';
  __walk(document.getElementById('__tpl').content, vals, root);
  if (aid){ const e = document.getElementById(aid); if (e){ e.focus(); try { e.setSelectionRange(sel, sel); } catch(_){} } }
}
__render();
'''
def build(path):
    src = open(path, encoding='utf-8').read()
    xdc = src.split('<x-dc>')[1].split('</x-dc>')[0]
    helmet = re.search(r'<helmet>(.*?)</helmet>', xdc, re.S).group(1)
    body = xdc.replace(re.search(r'<helmet>.*?</helmet>', xdc, re.S).group(0), '')
    code = re.search(r'<script type="text/x-dc"[^>]*>(.*?)</script>', src, re.S).group(1)
    w = re.search(r'"width":(\d+)', src).group(1)
    html = '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=' + w + '">' + helmet + '</head><body><div id="__root"></div><template id="__tpl">' + body + '</template><script>' + SHIM.replace('__CODE__', code) + '</script></body></html>'
    out = os.path.join(OUT, os.path.basename(path).replace('.dc.html', '.preview.html'))
    open(out, 'w', encoding='utf-8').write(html)
    print(out)
for f in sys.argv[1:]: build(f)
