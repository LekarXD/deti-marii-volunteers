// usage: node vals.js file.dc.html '[["call","path.to.fn",arg?],...]'
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const script = src.match(/<script type="text\/x-dc"[^>]*>([\s\S]*?)<\/script>/)[1];
class DCLogic { constructor(p){ this.props = p; } setState(u){ this.state = Object.assign({}, this.state, u); } }
const Component = new Function('DCLogic', script + '\nreturn Component;')(DCLogic);
const c = new Component({});
const steps = JSON.parse(process.argv[3] || '[]');
for (const st of steps) {
  const v = c.renderVals();
  let fn = v; for (const k of st[0].split('.')) fn = fn[k];
  fn(st[1] !== undefined ? { target: { value: st[1] } } : undefined);
}
process.stdout.write(JSON.stringify(c.renderVals()));
