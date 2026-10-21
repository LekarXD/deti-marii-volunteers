// Static preview of a .dc.html: run renderVals (optionally after clicking handler paths), expand sc-for/sc-if/holes.
// usage: node expand_dc_cosr.js <File.dc.html> <outName> [handlerPath ...]   e.g. modes.1.pick
const fs = require('fs');
const path = require('path');
const ROOT = '/private/tmp/claude-501/-Users-iliapetri--claude-spares-spare-GxUBpt/91fc3645-2cae-45de-9eeb-32a080bb81c1/scratchpad/';
const [file, outName, ...clicks] = process.argv.slice(2);
const src = fs.readFileSync(ROOT + 'dm-canvas/project/' + file, 'utf8');
const code = src.split('data-dc-script')[1].split('>').slice(1).join('>').split('</script>')[0];
class DCLogic { constructor(p) { this.props = p; } setState(x) { this.state = Object.assign({}, this.state, x); } }
const Component = new Function('DCLogic', code + '\nreturn Component;')(DCLogic);
const inst = new Component({});
for (const c of clicks) {
  const v = inst.renderVals();
  const fn = c.split('.').reduce((o, k) => (o == null ? o : o[k]), v);
  if (typeof fn !== 'function') { console.error('no handler', c); process.exit(1); }
  fn({ target: { value: 'тест' } });
}
const vals = inst.renderVals();
const helmet = src.split('<helmet>')[1].split('</helmet>')[0];
const markup = src.split('</helmet>')[1].split('</x-dc>')[0];
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
function look(scope, p) {
  if (p === 'true') return true;
  if (p === 'false') return false;
  return p.split('.').reduce((o, k) => (o == null ? undefined : o[k]), scope);
}
function holes(str, scope) {
  return str
    .replace(/\s(on[A-Z]\w*)="\{\{[\w.]+\}\}"/g, '')
    .replace(/\{\{([\w.]+)\}\}/g, (m, p) => {
      const v = look(scope, p);
      if (v === undefined) console.error('undefined hole', p);
      return esc(v === undefined ? '' : v);
    });
}
function findClose(str, tag, from) {
  const re = new RegExp('<(/?)' + tag + '\\b[^>]*>', 'g');
  re.lastIndex = from;
  let depth = 1, m;
  while ((m = re.exec(str))) {
    depth += m[1] ? -1 : 1;
    if (depth === 0) return { start: m.index, end: re.lastIndex };
  }
  throw new Error('unclosed ' + tag);
}
function expand(str, scope) {
  let out = '';
  let i = 0;
  const re = /<(sc-for|sc-if)\b([^>]*)>/g;
  let m;
  while ((m = re.exec(str))) {
    out += holes(str.slice(i, m.index), scope);
    const tag = m[1];
    const attrs = m[2];
    const close = findClose(str, tag, re.lastIndex);
    const inner = str.slice(re.lastIndex, close.start);
    if (tag === 'sc-for') {
      const listP = /list="\{\{([\w.]+)\}\}"/.exec(attrs)[1];
      const alias = /as="(\w+)"/.exec(attrs)[1];
      const list = look(scope, listP) || [];
      for (const item of list) out += expand(inner, Object.assign({}, scope, { [alias]: item }));
    } else {
      const valP = /value="\{\{([\w.]+)\}\}"/.exec(attrs)[1];
      if (look(scope, valP)) out += expand(inner, scope);
    }
    i = close.end;
    re.lastIndex = close.end;
  }
  out += holes(str.slice(i), scope);
  return out;
}
const body = expand(markup, vals);
const html = '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' + helmet + '</head><body>' + body + '</body></html>';
fs.mkdirSync(ROOT + 'preview_cosr', { recursive: true });
fs.writeFileSync(ROOT + 'preview_cosr/' + outName + '.html', html);
console.log('wrote', outName);
