import {api,getPrincipalKey} from '../../api/transport';
import type {components} from '../../api/generated/schema';
export type Conversation=components['schemas']['ConversationView'];
export type ConversationPage=components['schemas']['ConversationPage'];
export type Message=components['schemas']['MessageView'];
export type MessagePage=components['schemas']['MessagePage'];
export type ContactPage=components['schemas']['ContactPage'];
export type SendBody=components['schemas']['MessageCreate'];
export const conversations=(cursor:string|null,signal?:AbortSignal)=>api<ConversationPage>(`/conversations?limit=30${cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`,{signal});
export const messages=(id:string,before:number|undefined,signal?:AbortSignal)=>api<MessagePage>(`/conversations/${id}/messages?limit=50${before?`&before_seq=${before}`:''}`,{signal});
export const contacts=(query:string,signal?:AbortSignal)=>api<ContactPage>(`/conversations/contacts?query=${encodeURIComponent(query)}&limit=50`,{signal});
export const send=(id:string,body:SendBody,key:string)=>api<Message>(`/conversations/${id}/messages`,{method:'POST',body,idempotencyKey:key});
export const markRead=(id:string,seq:number)=>api<components['schemas']['ReadCursorView']>(`/conversations/${id}/read-cursor`,{method:'PUT',body:{last_read_seq:seq},idempotencyKey:crypto.randomUUID()});
export const direct=(recipient_id:string,key=crypto.randomUUID())=>api<Conversation>('/conversations/direct',{method:'POST',body:{recipient_id},idempotencyKey:key});
export const group=(title:string,member_ids:string[],key=crypto.randomUUID())=>api<Conversation>('/conversations',{method:'POST',body:{title,member_ids},idempotencyKey:key});
export async function upload(file:File,signal:AbortSignal):Promise<string>{
 if(!['image/png','image/jpeg','image/webp','application/pdf'].includes(file.type)||file.size>10*1024*1024||file.size===0)throw new Error('Выберите PNG, JPEG, WebP или PDF до 10 МБ.');
 const principal=getPrincipalKey();
 const pin=()=>{if(signal.aborted||getPrincipalKey()!==principal)throw new Error('Сессия изменилась. Выберите файл ещё раз.');};
 const checksum=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer())),v=>v.toString(16).padStart(2,'0')).join('');
 pin();
 const asset=await api<components['schemas']['AssetView']>('/assets/upload-intents',{method:'POST',body:{content_type:file.type,expected_size:file.size,checksum},signal,idempotencyKey:crypto.randomUUID()});
 for(let offset=0;offset<file.size;offset+=1024*1024){pin();await api(`/assets/${asset.id}/upload`,{method:'PATCH',body:file.slice(offset,offset+1024*1024),headers:{'X-Upload-Offset':String(offset),'Content-Type':'application/octet-stream'},signal});}
 pin();
 await api(`/assets/${asset.id}/complete-upload`,{method:'POST',body:{},signal,idempotencyKey:crypto.randomUUID()});
 return asset.id;
}
