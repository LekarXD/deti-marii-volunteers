// Explicit local protocol client; no browser automation or physical media.
import fs from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const Y=await import(pathToFileURL(resolve(process.argv[3],'yjs/dist/yjs.mjs')));
const {WebsocketProvider}=await import(pathToFileURL(resolve(process.argv[3],'y-websocket/src/y-websocket.js')));
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const wait=async predicate=>{for(let n=0;n<100;n++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,30));}throw new Error('protocol_state_timeout');};
const host=new Y.Doc(),viewer=new Y.Doc();const a=new WebsocketProvider(fixture.url,fixture.room,host,{params:{token:fixture.host},disableBc:true});const b=new WebsocketProvider(fixture.url,fixture.room,viewer,{params:{token:fixture.viewer},disableBc:true});
try{await wait(()=>a.synced&&b.synced);host.getArray('elements').push([new Y.Map([['shape','approved-host']])]);await wait(()=>viewer.getArray('elements').length===1);viewer.getArray('elements').push([new Y.Map([['shape','forged-viewer']])]);host.getMap('assets').set('barrier','host');await wait(()=>viewer.getMap('assets').get('barrier')==='host');await new Promise(resolve=>setTimeout(resolve,100));if(host.getArray('elements').length!==1)throw new Error('viewer_write_accepted');console.log(JSON.stringify({actual_js_y_websocket:true,host_draw_sync:true,viewer_update_denied:true,physical_media_requested:false}));}finally{a.destroy();b.destroy();host.destroy();viewer.destroy();}
