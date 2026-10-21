// Runs a .dc.html Component's renderVals() across modes and one level of interactions,
// printing every string value produced (JSON array).
const fs = require('fs');
const file = process.argv[2];
const html = fs.readFileSync(file, 'utf8');
const m = html.match(/<script[^>]*data-dc-script[^>]*>([\s\S]*?)<\/script>/);
if (!m) { console.log('[]'); process.exit(0); }
class DCLogic {
  constructor(props) { this.props = props || {}; this.state = {}; }
  setState(p, cb) { const v = typeof p === 'function' ? p(this.state, this.props) : p; this.state = Object.assign({}, this.state, v); if (cb) cb(); }
  forceUpdate() {}
}
let Component;
try { Component = new Function('DCLogic', m[1] + '\n;return Component;')(DCLogic); }
catch (e) { console.error('EVAL FAIL', file, e.message); process.exit(2); }
const out = new Set();
const fns = [];
function walk(v, path, collectFns) {
  if (v == null) return;
  if (typeof v === 'string') { out.add(v); return; }
  if (typeof v === 'number') return;
  if (typeof v === 'function') { if (collectFns) fns.push(path); return; }
  if (Array.isArray(v)) { v.forEach((x, i) => walk(x, path.concat([i]), collectFns)); return; }
  if (typeof v === 'object') { for (const k of Object.keys(v)) walk(v[k], path.concat([k]), collectFns); }
}
function get(obj, path) { return path.reduce((o, k) => (o == null ? o : o[k]), obj); }
const ev = { target: { value: 'тест', checked: true }, preventDefault() {}, stopPropagation() {}, key: 'Enter' };
let errs = 0;
function render(c) { try { return c.renderVals(); } catch (e) { errs++; return null; } }
const base = new Component({});
const init = JSON.parse(JSON.stringify(base.state));
const r0 = render(base);
walk(r0, [], true);
const level1 = fns.slice();
const states = [];
for (const p of level1) {
  const c = new Component({}); c.state = JSON.parse(JSON.stringify(init));
  const r = render(c); const f = get(r, p);
  if (typeof f !== 'function') continue;
  try { f(ev); } catch (e) { continue; }
  const r2 = render(c); walk(r2, [], false);
  states.push(JSON.parse(JSON.stringify(c.state)));
}
// level 2: from each level-1 state, try every handler once more
for (const st of states) {
  const c0 = new Component({}); c0.state = JSON.parse(JSON.stringify(st));
  const r = render(c0); const local = []; 
  (function w(v, path) { if (v == null) return; if (typeof v === 'function') { local.push(path); return; }
    if (Array.isArray(v)) v.forEach((x, i) => w(x, path.concat([i]))); else if (typeof v === 'object') for (const k of Object.keys(v)) w(v[k], path.concat([k])); })(r, []);
  for (const p of local) {
    const c = new Component({}); c.state = JSON.parse(JSON.stringify(st));
    const rr = render(c); const f = get(rr, p);
    if (typeof f !== 'function') continue;
    try { f(ev); } catch (e) { continue; }
    walk(render(c), [], false);
  }
}
// calendar-style components: enumerate every month/day selection
if ('month' in init && 'sel' in init && typeof init.sel === 'string' && /-\d+$/.test(init.sel)) {
  const DIM = { sep: 30, oct: 31, nov: 30, dec: 31 };
  for (const mo of Object.keys(DIM)) for (let d = 1; d <= DIM[mo]; d++) {
    const c = new Component({}); c.state = Object.assign(JSON.parse(JSON.stringify(init)), { view: 'cal', month: mo, sel: mo + '-' + d });
    const r = render(c); if (r) walk(r, [], false);
  }
}
console.log(JSON.stringify({ strings: Array.from(out), errors: errs, handlers: level1.length, states: states.length }));
