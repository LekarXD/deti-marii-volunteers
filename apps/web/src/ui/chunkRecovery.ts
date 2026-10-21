/** Adapted OD chunkReload.js: one recovery per bundle, no reload loop. */
const patterns=[/chunkloaderror/i,/loading chunk [\w-]+ failed/i,/failed to fetch dynamically imported module/i,/error loading dynamically imported module/i,/importing a module script failed/i,/failed to load module script/i,/unable to preload css/i];
export function isChunkLoadFailure(value:unknown):boolean {
 if(!value)return false;
 if(typeof value==='object'){const data=value as {name?:string;message?:unknown;reason?:unknown;error?:unknown;payload?:unknown};if(data.name==='ChunkLoadError')return true;for(const nested of [data.message,data.reason,data.error,data.payload]){if(nested&&nested!==value&&isChunkLoadFailure(nested))return true;}}
 return patterns.some(pattern=>pattern.test(String(value)));
}
let recoveredInMemory=false;
export function installChunkRecovery({reload=()=>location.reload(),storage,buildId=import.meta.url}:{reload?:()=>void;storage?:Storage|null;buildId?:string}={}){
 let storageRef=storage;if(storageRef===undefined){try{storageRef=window.sessionStorage;}catch{storageRef=null;}}
 const key=`opora:chunk-reload:${buildId}`;let timer:ReturnType<typeof setTimeout>|undefined;
 const handle=(event:Event)=>{if(!isChunkLoadFailure(event)||!storageRef)return;let recovered=recoveredInMemory;try{recovered=recovered||storageRef?.getItem(key)==='1';}catch{/* memory fallback */}if(recovered)return;recoveredInMemory=true;try{storageRef?.setItem(key,'1');}catch{/* memory fallback */}event.preventDefault();timer=setTimeout(reload,0);};
 window.addEventListener('vite:preloadError',handle);window.addEventListener('error',handle);window.addEventListener('unhandledrejection',handle);
 return()=>{if(timer)clearTimeout(timer);window.removeEventListener('vite:preloadError',handle);window.removeEventListener('error',handle);window.removeEventListener('unhandledrejection',handle);};
}
