#!/usr/bin/env python3
"""Build preview_<Name>.html: artboard + a tiny emulation of the DC runtime (sc-if, sc-for, holes, onClick/onChange)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / 'dm-canvas' / 'project'

RUNTIME = r"""
<script>
(function () {
  const HOLE = /\{\{([\w$.]+)\}\}/g;
  function get(scope, path) { return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), scope); }
  function single(str) { const m = (str || '').match(/^\{\{([\w$.]+)\}\}$/); return m ? m[1] : null; }
  function lit(scope, p) { if (p === 'true') return true; if (p === 'false') return false; return get(scope, p); }
  function subst(str, scope) { return str.replace(HOLE, (m, p) => { const v = lit(scope, p); return v == null ? '' : String(v); }); }
  let inst, tplNodes, mount, pending = false;
  window.__dcErrors = [];
  function renderNode(node, scope, out) {
    if (node.nodeType === 3) { out.appendChild(document.createTextNode(subst(node.textContent, scope))); return; }
    if (node.nodeType !== 1) return;
    const tag = node.tagName.toLowerCase();
    if (tag === 'sc-if') { if (lit(scope, single(node.getAttribute('value')))) node.childNodes.forEach((c) => renderNode(c, scope, out)); return; }
    if (tag === 'sc-for') {
      const arr = get(scope, single(node.getAttribute('list'))) || [];
      const as = node.getAttribute('as');
      arr.forEach((item) => { const sc = Object.create(scope); sc[as] = item; node.childNodes.forEach((c) => renderNode(c, sc, out)); });
      return;
    }
    const el = node.namespaceURI === 'http://www.w3.org/2000/svg' ? document.createElementNS(node.namespaceURI, node.tagName) : document.createElement(node.tagName);
    for (const a of Array.from(node.attributes)) {
      const n = a.name.toLowerCase();
      if (n === 'onclick' || n === 'onchange') {
        const fn = get(scope, single(a.value));
        if (typeof fn !== 'function') { window.__dcErrors.push('no fn ' + a.value); continue; }
        el.addEventListener(n === 'onclick' ? 'click' : 'input', (e) => { fn(e); schedule(); });
        continue;
      }
      const v = subst(a.value, scope);
      if (n === 'value' && (tag === 'input' || tag === 'textarea')) { el.value = v; continue; }
      el.setAttribute(a.name, v);
    }
    node.childNodes.forEach((c) => renderNode(c, scope, el));
    if (tag === 'textarea') { const vv = node.getAttribute('value'); if (vv) el.value = subst(vv, scope); }
    out.appendChild(el);
  }
  function rerender() {
    pending = false;
    const vals = inst.renderVals();
    const frag = document.createDocumentFragment();
    tplNodes.forEach((n) => renderNode(n, vals, frag));
    mount.replaceChildren(frag);
  }
  function schedule() { if (!pending) { pending = true; Promise.resolve().then(rerender); } }
  window.DCLogic = class { constructor(p) { this.props = p; this.state = {}; } setState(p) { this.state = Object.assign({}, this.state, p); schedule(); } };
  document.addEventListener('DOMContentLoaded', () => {
    const xdc = document.querySelector('x-dc');
    const code = document.querySelector('script[data-dc-script]').textContent;
    const Comp = new Function('DCLogic', code + '\nreturn Component;')(window.DCLogic);
    inst = new Comp({});
    const root = xdc.querySelector('.dm');
    tplNodes = [root.cloneNode(true)];
    mount = document.createElement('div');
    root.replaceWith(mount);
    rerender();
    window.__dc = inst;
  });
})();
</script>
"""

for name in sys.argv[1:]:
    src = (ROOT / name).read_text(encoding='utf-8')
    out = src.replace('<script src="./support.js"></script>', RUNTIME)
    (HERE / ('preview_' + name.replace('.dc.html', '') + '.html')).write_text(out, encoding='utf-8')
    print('ok', name)
