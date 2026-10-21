import {ApiError,readApiError} from '../../../api/errors';
export type RendererOperation='bootstrap'|'state'|'readiness'|'provider-grant';
export interface RendererRequest {body?:unknown;signal?:AbortSignal;afterRevision?:number;idempotencyKey?:string;timeoutMs?:number;}
export interface RendererAssetRequest {signal?:AbortSignal;timeoutMs?:number;maxBytes?:number;}
const operations:readonly RendererOperation[]=['bootstrap','state','readiness','provider-grant'];
const invalid=(code:string)=>new ApiError(0,code,'Состояние записи недоступно.');
/** Private bearer transport. A one-use bootstrap client is closed and replaced with
 * the returned in-memory access credential. Neither credential enters a URL/store. */
export function createRendererTransport(bearerCredential:string){
 if(!bearerCredential||bearerCredential.length>8192||/[\s\u0000-\u001f]/.test(bearerCredential))throw new ApiError(0,'renderer_ticket_required','Разрешение на запись недоступно.');
 let credential:string|null=bearerCredential;let generation=0;const active=new Set<AbortController>();
 const close=()=>{credential=null;generation++;active.forEach(controller=>controller.abort());active.clear();};
 async function send<T>(path:string,method:'GET'|'POST',options:RendererRequest,binaryLimit?:number):Promise<T>{
  if(!credential)throw new ApiError(0,'renderer_closed','Доступ к записи завершён.');
  const epoch=generation;const controller=new AbortController();active.add(controller);
  const externalAbort=()=>controller.abort();if(options.signal?.aborted)externalAbort();else options.signal?.addEventListener('abort',externalAbort,{once:true});
  const timer=setTimeout(()=>controller.abort('timeout'),Math.min(30000,Math.max(100,options.timeoutMs??12000)));
  try{
   const headers=new Headers({Authorization:`Bearer ${credential}`,Accept:binaryLimit?'image/png, image/jpeg, image/webp':'application/json'});
   if(method==='POST'){headers.set('Content-Type','application/json');headers.set('Idempotency-Key',options.idempotencyKey??crypto.randomUUID());}
   const response=await fetch(path,{method,headers,body:method==='POST'?JSON.stringify(options.body??{}):undefined,credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer',signal:controller.signal});
   if(epoch!==generation||!credential)throw new ApiError(0,'renderer_closed','Доступ к записи завершён.');
   if(!response.ok){const error=await readApiError(response);if(response.status===401||response.status===403)close();
    const code=/^[a-z0-9_]{1,80}$/.test(error.code)?error.code:'renderer_failed';
    throw new ApiError(error.status,code,response.status===401||response.status===403?'Доступ к записи истёк.':'Не удалось подготовить кадр записи.',{},undefined,error.retryable);
   }
   const limit=binaryLimit??1048576;const declared=Number(response.headers.get('Content-Length'));
   if(Number.isFinite(declared)&&declared>limit){await response.body?.cancel();throw invalid(binaryLimit?'renderer_asset_size':'renderer_response_invalid');}
   const reader=response.body?.getReader();if(!reader)throw invalid('renderer_response_invalid');
   const chunks:BlobPart[]=[];let length=0;
   try{while(true){const part=await reader.read();if(part.done)break;length+=part.value.byteLength;if(length>limit){await reader.cancel();throw invalid(binaryLimit?'renderer_asset_size':'renderer_response_invalid');}chunks.push(new Uint8Array(part.value).buffer);}}finally{reader.releaseLock();}
   if(epoch!==generation||!credential)throw new ApiError(0,'renderer_closed','Доступ к записи завершён.');
   const blob=new Blob(chunks,{type:binaryLimit?(response.headers.get('Content-Type')??'').split(';')[0]:'application/json'});
   if(binaryLimit)return blob as T;
   let value:T;try{value=JSON.parse(await blob.text()) as T;}catch{throw invalid('renderer_response_invalid');}
   if(epoch!==generation||!credential)throw new ApiError(0,'renderer_closed','Доступ к записи завершён.');return value;
  }catch(error){if(error instanceof ApiError)throw error;if(epoch!==generation||!credential)throw new ApiError(0,'renderer_closed','Доступ к записи завершён.');if(options.signal?.aborted)throw new ApiError(0,'aborted','Запрос отменён.');throw new ApiError(0,controller.signal.aborted?'timeout':'network','Не удалось связаться с сервисом записи.',{},undefined,true);
  }finally{clearTimeout(timer);active.delete(controller);options.signal?.removeEventListener('abort',externalAbort);}
 }
 return Object.freeze({
  close,
  request<T>(operation:RendererOperation,options:RendererRequest={}):Promise<T>{
   if(!operations.includes(operation))return Promise.reject(invalid('renderer_operation_invalid'));
   if(options.afterRevision!==undefined&&(!Number.isSafeInteger(options.afterRevision)||options.afterRevision<0))return Promise.reject(invalid('renderer_revision_invalid'));
   if(operation==='state'&&options.body!==undefined)return Promise.reject(invalid('renderer_operation_invalid'));
   const path=`/api/v1/recording-renderer/${operation}${operation==='state'&&options.afterRevision!==undefined?`?after_revision=${options.afterRevision}`:''}`;
   return send<T>(path,operation==='state'?'GET':'POST',options);
  },
  asset(assetId:string,options:RendererAssetRequest={}):Promise<Blob>{
   if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(assetId))return Promise.reject(invalid('renderer_asset_descriptor'));
   const limit=options.maxBytes??32*1024*1024;
   if(!Number.isSafeInteger(limit)||limit<1||limit>64*1024*1024)return Promise.reject(invalid('renderer_asset_limit'));
   return send<Blob>(`/api/v1/recording-renderer/assets/${assetId}`,'GET',options,limit);
  },
 });
}
export type RendererTransport=ReturnType<typeof createRendererTransport>;
