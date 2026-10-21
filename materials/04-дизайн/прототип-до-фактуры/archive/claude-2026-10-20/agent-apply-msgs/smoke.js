// Smoke-run a .dc.html logic class: render, call every handler two levels deep, re-render; report exceptions
// and top-level holes that renderVals never provides, plus sc-if values that are not booleans.
const fs = require('fs');
const file = process.argv[2];
const src = fs.readFileSync(file, 'utf8');
const code = src.split('data-dc-script')[1].split('>').slice(1).join('>').split('</script>')[0];
class DCLogic {
  constructor(props) { this.props = props; }
  setState(patch) { this.state = Object.assign({}, this.state, patch); }
}
const Component = new Function('DCLogic', code + '\nreturn Component;')(DCLogic);
const inst = new Component({});
const markup = src.split('</helmet>')[1].split('<script type="text/x-dc"')[0];
const holes = new Set([...markup.matchAll(/\{\{([\w.$]+)\}\}/g)].map((m) => m[1]).filter((h) => h !== 'true' && h !== 'false'));
const loopVars = new Set([...markup.matchAll(/as="(\w+)"/g)].map((m) => m[1]));
const ifHoles = new Set([...markup.matchAll(/<sc-if value="\{\{([\w.]+)\}\}"/g)].map((m) => m[1]).filter((h) => !loopVars.has(h.split('.')[0])));
let errors = 0;
let calls = 0;
function collectFns(obj, path, out, depth) {
  if (depth > 4 || obj == null) return;
  if (typeof obj === 'function') { out.push([path, obj]); return; }
  if (Array.isArray(obj)) { obj.forEach((x, i) => collectFns(x, path + '[' + i + ']', out, depth + 1)); return; }
  if (typeof obj === 'object') Object.keys(obj).forEach((k) => collectFns(obj[k], path + '.' + k, out, depth + 1));
}
var check = function (vals, where) {
  for (const h of holes) {
    const root = h.split('.')[0];
    if (loopVars.has(root)) continue;
    let v = vals;
    for (const k of h.split('.')) v = v == null ? undefined : v[k];
    if (v === undefined) { console.log('  undefined hole', h, 'at', where); errors++; }
  }
  for (const h of ifHoles) {
    if (typeof vals[h] !== 'boolean') { console.log('  sc-if not boolean', h, typeof vals[h], 'at', where); errors++; }
  }
}
// sc-for field check: map each alias to its list expression and the alias.field holes used inside it
const loops = [];
{
  const re = /<sc-for\s+list="\{\{([\w.]+)\}\}"\s+as="(\w+)"[^>]*>|<\/sc-for>/g;
  const stack = [];
  let m;
  while ((m = re.exec(markup))) {
    if (m[0].startsWith('</')) {
      const top = stack.pop();
      top.body = markup.slice(top.start, m.index);
      loops.push(top);
    } else {
      stack.push({ list: m[1], as: m[2], start: re.lastIndex });
    }
  }
}
const aliasList = {};
loops.forEach((l) => { aliasList[l.as] = l.list; });
function itemsOf(vals, listExpr) {
  const parts = listExpr.split('.');
  if (parts.length === 1) return vals[parts[0]] || [];
  const parent = itemsOf(vals, aliasList[parts[0]]);
  let out = [];
  parent.forEach((it) => { let v = it; for (const k of parts.slice(1)) v = v == null ? undefined : v[k]; out = out.concat(v || []); });
  return out;
}
function checkLoops(vals, where) {
  for (const l of loops) {
    const items = itemsOf(vals, l.list);
    if (!Array.isArray(items)) { console.log('  list not array', l.list, where); errors++; continue; }
    const fields = new Set([...l.body.matchAll(new RegExp('\\{\\{' + l.as + '\\.([\\w.]+)\\}\\}', 'g'))].map((x) => x[1]));
    items.forEach((it, i) => {
      for (const f of fields) {
        let v = it;
        for (const k of f.split('.')) v = v == null ? undefined : v[k];
        if (v === undefined) { console.log('  item field missing', l.as + '.' + f, '#' + i, 'list', l.list, 'at', where); errors++; }
      }
    });
  }
}
const _check = check;
check = function (vals, where) { _check(vals, where); checkLoops(vals, where); };
const ev = { target: { value: 'тест@почта.рф', checked: true } };
const initial = JSON.parse(JSON.stringify(inst.state));
const v0 = inst.renderVals();
check(v0, 'initial');
const fns = [];
collectFns(v0, 'v', fns, 0);
for (const [path] of fns) {
  inst.state = JSON.parse(JSON.stringify(initial));
  try {
    const v = inst.renderVals();
    const again = [];
    collectFns(v, 'v', again, 0);
    const f = (again.find((x) => x[0] === path) || [])[1];
    if (!f) continue;
    f(ev); calls++;
    const v2 = inst.renderVals();
    check(v2, path);
    const more = [];
    collectFns(v2, 'v', more, 0);
    for (const [p2] of more) {
      const snap = JSON.parse(JSON.stringify(inst.state));
      try {
        const v3 = inst.renderVals();
        const m3 = [];
        collectFns(v3, 'v', m3, 0);
        const f2 = (m3.find((x) => x[0] === p2) || [])[1];
        if (f2) { f2(ev); calls++; check(inst.renderVals(), path + ' -> ' + p2); }
      } catch (e) { console.log('  error at', path, '->', p2, e.message); errors++; }
      inst.state = snap;
    }
  } catch (e) { console.log('  error at', path, e.message); errors++; }
}
console.log(file.split('/').pop() + ': handlers=' + fns.length + ', calls=' + calls + ', errors=' + errors);
process.exit(errors ? 1 : 0);
