import {appPath} from '../../../basePath';
import {mountPrivateRenderer} from './mount';
import {mountRendererView} from './RendererView';

type BridgeRequest={protocol_version:1;phase:'challenge'}|{protocol_version:1;phase:'consume';nonce:string};
type PrivateBridge=(request:BridgeRequest)=>Promise<unknown>;
declare global {interface Window {__oporaTakeRendererBootstrap?:PrivateBridge;}}
const unavailable=()=>new Error('private_renderer_unavailable');
function field(value:unknown,key:'nonce'|'ticket') {
 if(!value||typeof value!=='object'||Array.isArray(value))throw unavailable();
 const reply=value as Record<string,unknown>;
 if(reply.protocol_version!==1||Object.keys(reply).length!==2||typeof reply[key]!=='string')throw unavailable();
 const result=reply[key] as string;
 if(key==='nonce'?!/^[A-Za-z0-9_-]{32,256}$/.test(result):!/^[A-Za-z0-9_-]{40,192}$/.test(result))throw unavailable();
 return result;
}
async function bounded<T>(promise:Promise<T>) {
 let timer:ReturnType<typeof setTimeout>|undefined;
 try{return await Promise.race([promise,new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(unavailable()),12000);})]);}
 finally{clearTimeout(timer);}
}
/** Private top-frame entry only. The orchestrator independently validates exact
 * Page/mainFrame/origin/path on BOTH bridge calls; browser checks are not authority. */
export async function startPrivateRendererEntry(root:HTMLElement|null=document.getElementById('renderer-root')) {
 if(!root)return;
 let active=true,nonce:string|undefined,ticket:string|undefined,reply:unknown;
 let mounted:ReturnType<typeof mountPrivateRenderer>|undefined;
 let idle:ReturnType<typeof mountRendererView>|undefined;
 const close=()=>{if(!active)return;active=false;nonce=undefined;ticket=undefined;reply=undefined;mounted?.close();idle?.close();window.removeEventListener('pagehide',close);};
 const showUnavailable=()=>{mounted?.close();mounted=undefined;if(active)idle=mountRendererView(root,{phase:'failed',isCurrent:()=>false});};
 window.addEventListener('pagehide',close,{once:true});
 try{
  // Guard only the route/frame shape. Never extract a credential from location.
  if(window.top!==window||location.pathname!==appPath('/recorder.html')||location.search!==''||location.hash!=='')throw unavailable();
  const bridge=window.__oporaTakeRendererBootstrap;
  if(typeof bridge!=='function')throw unavailable();
  mounted=mountPrivateRenderer(root);
  reply=await bounded(bridge({protocol_version:1,phase:'challenge'}));if(!active)return {close};
  nonce=field(reply,'nonce');reply=undefined;
  const consuming=bridge({protocol_version:1,phase:'consume',nonce});nonce=undefined;
  reply=await bounded(consuming);if(!active)return {close};
  ticket=field(reply,'ticket');reply=undefined;
  const starting=mounted.start(ticket);ticket=undefined;
  await starting;
 }catch{showUnavailable();}
 finally{nonce=undefined;ticket=undefined;reply=undefined;}
 return Object.freeze({close});
}

// Importing this dedicated module elsewhere has no effect without its owned root.
void startPrivateRendererEntry();
