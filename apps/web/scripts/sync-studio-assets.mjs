import {createRequire} from 'node:module';
import {cp,mkdir,readFile,writeFile} from 'node:fs/promises';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const webRoot=resolve(dirname(fileURLToPath(import.meta.url)),'..');
let packageRoot=dirname(require.resolve('@excalidraw/excalidraw'));
for(let i=0;i<5;i++){
 try{const info=JSON.parse(await readFile(join(packageRoot,'package.json'),'utf8'));if(info.name==='@excalidraw/excalidraw')break;}catch{}
 packageRoot=dirname(packageRoot);
}
const info=JSON.parse(await readFile(join(packageRoot,'package.json'),'utf8'));
if(info.name!=='@excalidraw/excalidraw'||info.version!=='0.17.6')throw new Error('Expected pinned Excalidraw 0.17.6');
const target=join(webRoot,'public/studio-board-assets');
await mkdir(target,{recursive:true});
await cp(join(packageRoot,'dist/excalidraw-assets'),target,{recursive:true});
await cp(join(packageRoot,'dist/excalidraw.production.min.js.LICENSE.txt'),join(target,'LICENSE-bundle.txt'));
await writeFile(join(target,'source.json'),JSON.stringify({package:info.name,version:info.version,origin:'npm package pinned by pnpm-lock.yaml'},null,2)+'\n');
console.log('Copied pinned local Excalidraw assets');
