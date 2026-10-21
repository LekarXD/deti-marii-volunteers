import {useRef} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import type {components} from '../../api/generated/schema';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
export type Webinar=components['schemas']['WebinarView'];
export type WebinarInput=components['schemas']['WebinarInput'];
export type StudioSession=components['schemas']['StudioSessionView'];
export type SlideDeck=components['schemas']['SlideDeckView'];
export type SlidePage=components['schemas']['SlidePageView'];
export type BoardPass=components['schemas']['StudioBoardPass'];
export type StudioParticipant=components['schemas']['StudioParticipantView'];
export const useStudioParticipants=(webinarId:string|undefined)=>useQuery({queryKey:keys.detail('studio-roster',webinarId??''),queryFn:({signal})=>api<StudioParticipant[]>(`/webinars/${webinarId}/enrollments`,{signal}),enabled:!!webinarId,refetchInterval:5000});
export const useWebinars=()=>useQuery({queryKey:keys.all('webinars'),queryFn:({signal})=>api<Webinar[]>('/webinars',{signal}),refetchInterval:15000});
export const useStudioSession=(id:string|undefined)=>useQuery({queryKey:keys.detail('studio-sessions',id??''),queryFn:({signal})=>api<StudioSession>(`/studio-sessions/${id}`,{signal}),enabled:!!id,refetchInterval:3000});
export const useSlideDeck=(id:string|undefined)=>useQuery({queryKey:keys.detail('slide-decks',id??''),queryFn:({signal})=>api<SlideDeck>(`/slide-decks/${id}/status`,{signal}),enabled:!!id,refetchInterval:query=>query.state.data?.state==='ready'||query.state.data?.state==='failed'?false:2000});
export function useStudioCommand<T>(){const client=useQueryClient(),pending=useRef(new Map<string,string>());return useMutation({mutationFn:async({path,body,method='POST'}:{path:string;body?:unknown;method?:'POST'|'PATCH'})=>{const signature=JSON.stringify([path,method,body]),key=pending.current.get(signature)??crypto.randomUUID();pending.current.set(signature,key);try{const result=await api<T>(path,{method,body,idempotencyKey:key});pending.current.delete(signature);return result;}catch(error){if(error instanceof ApiError&&error.status>=400&&error.status<500&&![408,429].includes(error.status))pending.current.delete(signature);throw error;}},onSuccess:()=>Promise.all(['webinars','studio-sessions','slide-decks','studio-roster'].map(domain=>client.invalidateQueries({queryKey:keys.all(domain)})))});}

export async function uploadAsset(file:Blob,grant:components['schemas']['AssetView']){
 const current=await api<components['schemas']['AssetView']>(`/assets/${grant.id}/status`);if(current.state==='ready'||current.state==='processing')return current;
 let offset=current.received_size;
 while(offset<file.size){const chunk=file.slice(offset,offset+1024*1024);const next=await api<components['schemas']['AssetView']>(grant.upload_url,{method:'PATCH',body:chunk,headers:{'X-Upload-Offset':String(offset)}});if(next.received_size<=offset)throw new Error('upload_no_progress');offset=next.received_size;}
 return api<components['schemas']['AssetView']>(`/assets/${grant.id}/complete-upload`,{method:'POST'});
}
export async function checksum(file:Blob){const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());return Array.from(new Uint8Array(digest)).map(value=>value.toString(16).padStart(2,'0')).join('');}
export interface SlideUploadAttempt {key:string;deck?:SlideDeck;}
export async function uploadSlides(file:File,session:StudioSession,attempt:SlideUploadAttempt={key:crypto.randomUUID()}){
 const content_type=file.type||(file.name.toLowerCase().endsWith('.pptx')?'application/vnd.openxmlformats-officedocument.presentationml.presentation':'application/pdf');
 const deck=attempt.deck??await api<SlideDeck>('/slide-decks/upload-intents',{method:'POST',body:{resource_kind:session.resource_kind,resource_id:session.resource_id,title:file.name,content_type,expected_size:file.size,checksum:await checksum(file)},idempotencyKey:attempt.key});
 attempt.deck=deck;
 if(!deck.upload)throw new Error('upload_intent_missing');await uploadAsset(file,deck.upload as components['schemas']['AssetView']);return deck;
}
