// Renders a DC component through many states and checks every template hole resolves.
const fs = require('fs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

class DCLogic {
  constructor(props) { this.props = props || {}; this.state = {}; }
  setState(p) { this.state = Object.assign({}, this.state, typeof p === 'function' ? p(this.state) : p); }
}
const Component = new Function('DCLogic', data.js + '\nreturn Component;')(DCLogic);

const get = (env, vals, expr) => {
  const parts = expr.split('.');
  let cur = Object.prototype.hasOwnProperty.call(env, parts[0]) ? env[parts[0]] : vals[parts[0]];
  if (!Object.prototype.hasOwnProperty.call(env, parts[0]) && !(parts[0] in vals)) return { missing: parts[0] };
  for (let i = 1; i < parts.length; i++) {
    if (cur == null) return { missing: parts.slice(0, i + 1).join('.') };
    if (!(parts[i] in Object(cur))) return { missing: parts.slice(0, i + 1).join('.') };
    cur = cur[parts[i]];
  }
  return { value: cur };
};

const checked = new Map(); // key -> count resolved
const problems = new Set();

function checkHoles(vals, tag) {
  for (const h of data.holes) {
    let envs = [{}];
    let ok = true;
    for (const [alias, listExpr] of h.scopes) {
      const next = [];
      for (const env of envs) {
        const r = get(env, vals, listExpr);
        if (r.missing) { problems.add(`[${tag}] list ${listExpr} missing (${r.missing}) line ${h.line}`); ok = false; break; }
        if (!Array.isArray(r.value)) { problems.add(`[${tag}] list ${listExpr} not array line ${h.line}`); ok = false; break; }
        for (const item of r.value) next.push(Object.assign({}, env, { [alias]: item }));
      }
      if (!ok) break;
      envs = next;
    }
    if (!ok) continue;
    const key = h.expr + '@' + h.line;
    for (const env of envs) {
      const r = get(env, vals, h.expr);
      if (r.missing) problems.add(`[${tag}] hole {{${h.expr}}} line ${h.line} missing ${r.missing}`);
      else if (r.value === undefined) problems.add(`[${tag}] hole {{${h.expr}}} line ${h.line} is undefined`);
      else checked.set(key, (checked.get(key) || 0) + 1);
    }
  }
}

function collectFns(obj, prefix, out, depth) {
  if (depth > 4 || obj == null) return;
  if (Array.isArray(obj)) { obj.forEach((x, i) => collectFns(x, prefix + '[' + i + ']', out, depth + 1)); return; }
  if (typeof obj === 'object') {
    for (const k of Object.keys(obj)) {
      const v = obj[k];
      if (typeof v === 'function') out.push([prefix + '.' + k, v]);
      else collectFns(v, prefix + '.' + k, out, depth + 1);
    }
  }
}

const fakeEvent = { target: { value: 'Тест' }, preventDefault() {}, stopPropagation() {} };
let renders = 0;
const seen = new Set();
function explore(comp, depth, path) {
  let vals;
  try { vals = comp.renderVals(); renders++; } catch (e) { problems.add(`render threw after ${path}: ${e.message}`); return; }
  checkHoles(vals, path);
  const sig = JSON.stringify(comp.state, (k, v) => (typeof v === 'function' ? undefined : v));
  if (seen.has(sig)) return;
  seen.add(sig);
  if (depth <= 0) return;
  const fns = [];
  collectFns(vals, '', fns, 0);
  for (const [name, fn] of fns) {
    const c2 = new Component({});
    c2.state = JSON.parse(JSON.stringify(comp.state));
    // re-render to bind closures to c2
    let v2;
    try { v2 = c2.renderVals(); } catch (e) { problems.add('rerender threw ' + e.message); continue; }
    const fns2 = [];
    collectFns(v2, '', fns2, 0);
    const match = fns2.find((f) => f[0] === name);
    if (!match) continue;
    try { match[1](fakeEvent); } catch (e) { problems.add(`handler ${name} threw after ${path}: ${e.message}`); continue; }
    explore(c2, depth - 1, path + ' > ' + name);
    if (renders > 6000) return;
  }
}

const c = new Component({});
explore(c, 4, 'init');
const never = data.holes.filter((h) => !checked.has(h.expr + '@' + h.line)).map((h) => `{{${h.expr}}} line ${h.line}`);
console.log('renders:', renders, 'states:', seen.size);
if (problems.size) { console.log('PROBLEMS:'); [...problems].slice(0, 40).forEach((p) => console.log('  ' + p)); if (problems.size > 40) console.log('  ...' + (problems.size - 40) + ' more'); }
else console.log('no hole/handler problems');
if (never.length) console.log('never rendered holes (' + never.length + '):', never.slice(0, 30).join(', '));
