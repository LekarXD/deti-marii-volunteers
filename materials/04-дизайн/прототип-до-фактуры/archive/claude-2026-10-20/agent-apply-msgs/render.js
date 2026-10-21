// Static preview of a .dc.html artboard: runs renderVals() for a given state patch and expands sc-if / sc-for.
// usage: node render.js <file.dc.html> <out.html> '<json state patch>'
const fs = require('fs');
const [file, out, patchJson] = process.argv.slice(2);
const src = fs.readFileSync(file, 'utf8');
const code = src.split('data-dc-script')[1].split('>').slice(1).join('>').split('</script>')[0];
class DCLogic { constructor(p) { this.props = p; } setState(p) { this.state = Object.assign({}, this.state, p); } }
const Component = new Function('DCLogic', code + '\nreturn Component;')(DCLogic);
const inst = new Component({});
if (patchJson) Object.assign(inst.state, JSON.parse(patchJson));
const vals = inst.renderVals();

const xdc = src.split('<x-dc>')[1].split('</x-dc>')[0];
const helmet = xdc.split('<helmet>')[1].split('</helmet>')[0];
const markup = xdc.split('</helmet>')[1];

const esc = (v) => String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
function lookup(path, scope) {
  const parts = path.split('.');
  let v;
  for (let i = scope.length - 1; i >= 0; i--) {
    if (parts[0] in scope[i]) { v = scope[i][parts[0]]; break; }
  }
  for (const k of parts.slice(1)) v = v == null ? undefined : v[k];
  return v;
}
function subst(str, scope) {
  // attributes first
  str = str.replace(/\s([\w-]+)="\{\{([\w.$]+)\}\}"/g, (m, attr, path) => {
    if (/^on[A-Z]/.test(attr)) return '';
    const v = path === 'true' ? true : path === 'false' ? false : lookup(path, scope);
    if (typeof v === 'boolean') {
      if (attr === 'checked' || attr === 'disabled') return v ? ' ' + attr : '';
      return ' ' + attr + '="' + v + '"';
    }
    if (v === undefined || typeof v === 'function') return '';
    return ' ' + attr + '="' + esc(v) + '"';
  });
  str = str.replace(/\{\{([\w.$]+)\}\}/g, (m, path) => {
    const v = lookup(path, scope);
    return v === undefined || typeof v === 'function' ? '' : esc(v);
  });
  return str;
}
function findClose(str, tag, from) {
  const re = new RegExp('<' + tag + '\\b[^>]*>|</' + tag + '>', 'g');
  re.lastIndex = from;
  let depth = 1;
  let m;
  while ((m = re.exec(str))) {
    if (m[0][1] === '/') { depth--; if (depth === 0) return [m.index, re.lastIndex]; } else depth++;
  }
  throw new Error('unclosed ' + tag);
}
function expand(str, scope) {
  let outStr = '';
  let pos = 0;
  const re = /<sc-(for|if)\b([^>]*)>/g;
  let m;
  while ((m = re.exec(str))) {
    outStr += subst(str.slice(pos, m.index), scope);
    const kind = m[1];
    const [ci, ce] = findClose(str, 'sc-' + kind, re.lastIndex);
    const body = str.slice(re.lastIndex, ci);
    if (kind === 'if') {
      const path = /value="\{\{([\w.$]+)\}\}"/.exec(m[2])[1];
      const v = path === 'true' ? true : path === 'false' ? false : lookup(path, scope);
      if (v) outStr += expand(body, scope);
    } else {
      const path = /list="\{\{([\w.$]+)\}\}"/.exec(m[2])[1];
      const as = /as="(\w+)"/.exec(m[2])[1];
      const list = lookup(path, scope) || [];
      for (const it of list) outStr += expand(body, scope.concat([{ [as]: it }]));
    }
    pos = ce;
    re.lastIndex = ce;
  }
  return outStr + subst(str.slice(pos), scope);
}
let html = expand(markup, [vals]);
html = html.replace(/<textarea([^>]*?)\svalue="([^"]*)"([^>]*)><\/textarea>/g, '<textarea$1$3>$2</textarea>');
fs.writeFileSync(out, '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' + helmet + '</head><body>' + html + '</body></html>');
console.log('wrote', out, html.length);
