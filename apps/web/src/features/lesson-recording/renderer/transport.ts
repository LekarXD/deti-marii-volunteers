import {ApiError,readApiError} from '../../../api/errors';
export type RendererOperation='bootstrap'|'state'|'readiness';
export interface RendererRequest {body?:unknown;signal?:AbortSignal;afterRevision?:number;idempotencyKey?:string;timeoutMs?:number;}
const operations:readonly RendererOperation[]=['bootstrap','state','readiness'];
/** Purpose-ticket client, separate from cookie auth. Construct only after the private launch channel is verified.
 * No automatic command retries; no ticket/URL/storage/normal-session accessor is exposed. */
export function createRendererTransport(purposeTicket:string){
 if(!purposeTicket||purposeTicket.length>8192||/[\s\u0000-\u001f]/.test(purposeTicket))throw new ApiError(0,'renderer_ticket_required','Разрешение на запись недоступно.');
 let ticket:string|null=purposeTicket;let generation=0;const active=new Set<AbortController>();
 return Object.freeze({
  close(){ticket=null;generation++;active.forEach(controller=>controller.abort());active.clear();},
  async request<T>(operation:RendererOperation,options:RendererRequest={}):Promise<T>{
   if(!operations.includes(operation))throw new ApiError(0,'renderer_operation_invalid','Операция записи недоступна.');
   if(!ticket)throw new ApiError(0,'renderer_closed','Доступ к записи завершён.');
   if(options.afterRevision!==undefined&&(!Number.isSafeInteger(options.afterRevision)||options.afterRevision<0))throw new ApiError(0,'renderer_revision_invalid','Версия кадра недоступна.');
   if(operation==='state'&&options.body!==undefined)throw new ApiError(0,'renderer_operation_invalid','Операция записи недоступна.');
   const epoch=generation;const controller=new AbortController();active.add(controller);const externalAbort=()=>controller.abort();
   if(options.signal?.aborted)externalAbort();else options.signal?.addEventListener('abort',externalAbort,{once:true});
   const timer=setTimeout(()=>controller.abort('timeout'),Math.min(30000,Math.max(100,options.timeoutMs??12000)));
   const path=`/api/v1/recording-renderer/${operation}${operation==='state'&&options.afterRevision!==undefined?`?after_revision=${options.afterRevision}`:''}`;
   try{
    const headers=new Headers({Authorization:`Bearer ${ticket}`,Accept:'application/json'});if(operation!=='state'){headers.set('Content-Type','application/json');headers.set('Idempotency-Key',options.idempotencyKey??crypto.randomUUID());}
    const response=await fetch(path,{method:operation==='state'?'GET':'POST',headers,body:operation==='state'?undefined:JSON.stringify(options.body??{}),credentials:'omit',cache:'no-store',referrerPolicy:'no-referrer',signal:controller.signal});
    if(epoch!==generation||!ticket)throw new ApiError(0,'renderer_closed','Доступ к записи завершён.');
    if(!response.ok){const error=await readApiError(response);if(response.status===401||response.status===403){ticket=null;generation++;active.forEach(item=>item.abort());}
     const code=/^[a-z0-9_]{1,80}$/.test(error.code)?error.code:'renderer_failed';
     throw new ApiError(error.status,code,response.status===401||response.status===403?'Доступ к записи истёк.':'Не удалось подготовить кадр записи.',{},undefined,error.retryable);
    }
    const reader=response.body?.getReader();if(!reader)throw new ApiError(0,'renderer_response_invalid','Состояние записи недоступно.');
    const decoder=new TextDecoder();let length=0;let content='';try{while(true){const part=await reader.read();if(part.done)break;length+=part.value.byteLength;if(length>1048576){await reader.cancel();throw new ApiError(0,'renderer_response_invalid','Состояние записи недоступно.');}content+=decoder.decode(part.value,{stream:true});}content+=decoder.decode();}finally{reader.releaseLock();}
    const value=JSON.parse(content) as T;if(epoch!==generation||!ticket)throw new ApiError(0,'renderer_closed','Доступ к записи завершён.');return value;
   }catch(error){if(error instanceof ApiError)throw error;if(epoch!==generation||!ticket)throw new ApiError(0,'renderer_closed','Доступ к записи завершён.');if(options.signal?.aborted)throw new ApiError(0,'aborted','Запрос отменён.');throw new ApiError(0,controller.signal.aborted?'timeout':'network','Не удалось связаться с сервисом записи.',{},undefined,true);
   }finally{clearTimeout(timer);active.delete(controller);options.signal?.removeEventListener('abort',externalAbort);}
  },
 });
}
export type RendererTransport=ReturnType<typeof createRendererTransport>;
