const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const script = src.match(/<script type="text\/x-dc"[^>]*>([\s\S]*?)<\/script>/)[1];
class DCLogic { constructor(p){ this.props = p; } setState(u){ this.state = Object.assign({}, this.state, typeof u === 'function' ? u(this.state) : u); } }
const Component = new Function('DCLogic', script + '\nreturn Component;')(DCLogic);
global.C = new Component({});
global.V = () => C.renderVals();
const steps = require(process.argv[3]);
steps(C, V);
