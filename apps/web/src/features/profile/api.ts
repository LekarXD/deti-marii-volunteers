import {useRef} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
type Schemas=components['schemas'];
export type Profile=Schemas['ProfileView'];
export type Asset=Schemas['AssetView'];
export type ProfileUpdate=Schemas['ProfileUpdateCommand'];
export type ProfileTag=Schemas['ProfileTagValue'];
export type Hours=Schemas['HoursView'];
export type ManualTime=Schemas['ManualTimeView'];
export type Document=Schemas['ProfileDocumentView'];
export type DataRequest=Schemas['ProfileDataView'];
export type Suggestion=Schemas['ProfileSuggestionView'];
export type Consent=Schemas['ProfileConsentView'];
export type RecognitionBasis=Schemas['RecognitionBasisView'];
export type Gratitude=Schemas['GratitudeView'];
export type OwnAvailability=Schemas['OwnAvailabilityView'];
export function useProfile(){return useQuery({queryKey:keys.self('profile'),queryFn:({signal})=>api<Profile>('/me/profile',{signal})});}
export function useHours(){return useQuery({queryKey:keys.self('profile-hours'),queryFn:({signal})=>api<Hours>('/me/hours',{signal}),refetchInterval:15000});}
export function useProfileList<T>(kind:string,path:string){return useQuery({queryKey:keys.self('profile-'+kind),queryFn:({signal})=>api<T[]>(path,{signal}),refetchInterval:15000});}
export function useOwnAvailability(){return useQuery({queryKey:keys.self('crm-availability'),queryFn:({signal})=>api<OwnAvailability>('/me/availability',{signal})});}
export function useProfileCommand<T>(path:string,method='POST',initialVersion?:number){
 const cache=useQueryClient(),logical=useRef({signature:'',key:''}),version=useRef(initialVersion);
 const invalidate=async()=>{await Promise.all(['profile','profile-hours','profile-documents','profile-data','profile-suggestions','profile-consents','notification-preferences','crm-availability','profile-review-hours','profile-review-documents','profile-review-data'].map(domain=>cache.invalidateQueries({queryKey:keys.all(domain)})));};
 const mutation=useMutation({mutationFn:(input:unknown)=>{const body=version.current!==undefined&&input&&typeof input==='object'?{...input,expected_version:version.current}:input,signature=JSON.stringify(body);if(signature!==logical.current.signature)logical.current={signature,key:crypto.randomUUID()};return api<T>(path,{method,body,idempotencyKey:logical.current.key,retries:0});},onSuccess:async result=>{if(version.current!==undefined&&result&&typeof result==='object'&&'version' in result)version.current=Number(result.version);await invalidate();},onError:async error=>{if(error instanceof ApiError&&error.status===409)await invalidate();}});
 return {...mutation,rebase:(next:number)=>{version.current=next;logical.current={signature:'',key:''};}};
}
export async function downloadAsset(id:string,name:string){const blob=await api<Blob>(`/assets/${id}/content`,{responseType:'blob'}),url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download=name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export const minutesLabel=(value:number)=>{const sign=value<0?'−':'',abs=Math.abs(value);return `${sign}${Math.floor(abs/60)} ч ${String(abs%60).padStart(2,'0')} мин`;};
export const dateLabel=(value:string)=>new Date(value+'T12:00:00+03:00').toLocaleDateString('ru',{day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Moscow'});
export const today=()=>new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Moscow'});
export const requestLabels:Record<string,string>={pending:'Ждёт проверки',approved:'Подтверждено',rejected:'Отклонено',cancelled:'Отменено',requested:'Запрос отправлен',in_review:'На рассмотрении',ready:'Готово',withdrawn:'Отозвано',completed:'Обработано'};
