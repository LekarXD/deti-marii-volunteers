// Smoke-run a .dc.html logic class: render, click every handler (depth-limited), re-render; report errors
// and holes in markup that renderVals never provides.
const fs = require('fs');
const ROOT = '/private/tmp/claude-501/-Users-iliapetri--claude-spares-spare-GxUBpt/91fc3645-2cae-45de-9eeb-32a080bb81c1/scratchpad/dm-canvas/project/';
const name = process.argv[2];
const src = fs.readFileSync(ROOT + name, 'utf8');
const code = src.split('data-dc-script')[1].split('>').slice(1).join('>').split('</script>')[0];
class DCLogic {
  constructor(props) { this.props = props; }
  setState(patch) { this.state = Object.assign({}, this.state, patch); }
}
const Component = new Function('DCLogic', code + '\nreturn Component;')(DCLogic);
const inst = new Component({});
const markup = src.split('</helmet>')[1].split('<script type="text/x-dc"')[0];
const holes = new Set([...markup.matchAll(/\{\{([\w.]+)\}\}/g)].map((m) => m[1]).filter((h) => h !== 'true' && h !== 'false'));
// loop variable names declared via as="x"
const loopVars = new Set([...markup.matchAll(/as="(\w+)"/g)].map((m) => m[1]));
let errors = 0;
let clicks = 0;
function collectFns(obj, path, out, depth) {
  if (depth > 3 || obj == null) return;
  if (typeof obj === 'function') { out.push([path, obj]); return; }
  if (Array.isArray(obj)) { obj.forEach((x, i) => collectFns(x, path + '[' + i + ']', out, depth + 1)); return; }
  if (typeof obj === 'object') Object.keys(obj).forEach((k) => collectFns(obj[k], path + '.' + k, out, depth + 1));
}
function checkHoles(vals) {
  for (const h of holes) {
    const root = h.split('.')[0];
    if (loopVars.has(root)) continue;
    if (!(root in vals)) { console.log('  missing top-level hole:', h); errors++; }
  }
}
const initial = JSON.parse(JSON.stringify(inst.state));
let vals = inst.renderVals();
checkHoles(vals);
const fns = [];
collectFns(vals, 'vals', fns, 0);
for (const [path, fn] of fns) {
  // reset to initial state, re-render, find same fn path, call it, re-render
  inst.state = JSON.parse(JSON.stringify(initial));
  try {
    const v = inst.renderVals();
    const again = [];
    collectFns(v, 'vals', again, 0);
    const f = (again.find((x) => x[0] === path) || [])[1];
    if (!f) continue;
    f({ target: { value: 'тест' } });
    clicks++;
    const v2 = inst.renderVals();
    const more = [];
    collectFns(v2, 'vals', more, 0);
    for (const [p2, f2] of more) {
      const snap = JSON.parse(JSON.stringify(inst.state));
      try { f2({ target: { value: 'тест' } }); inst.renderVals(); clicks++; } catch (e) { console.log('  error at', path, '->', p2, e.message); errors++; }
      inst.state = snap;
    }
  } catch (e) {
    console.log('  error at', path, e.message);
    errors++;
  }
}
console.log(name + ': handlers top-level=' + fns.length + ', clicks simulated=' + clicks + ', errors=' + errors);
