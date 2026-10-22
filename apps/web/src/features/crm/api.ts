import {useRef} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
export type Volunteer=components['schemas']['CrmVolunteerView'];
export type VolunteerSummary=components['schemas']['CrmVolunteerSummary'];
export type VolunteerList=components['schemas']['CrmVolunteerListView'];
export type Task=components['schemas']['FollowUpTaskView'];
export type StaffOption=components['schemas']['StaffOptionView'];
export type ApplicationOption=components['schemas']['CrmApplicationOptionView'];
export const useVolunteers=(query='')=>useQuery({queryKey:keys.list('crm',{query}),queryFn:({signal})=>api<VolunteerList>(`/coord/volunteers?${query}`,{signal}),refetchInterval:15000});
export const useVolunteer=(id:string)=>useQuery({queryKey:keys.detail('crm',id),enabled:!!id,queryFn:({signal})=>api<Volunteer>(`/coord/volunteers/${id}`,{signal}),refetchInterval:15000});
export const useStaff=()=>useQuery({queryKey:keys.list('crm-staff'),queryFn:({signal})=>api<StaffOption[]>('/coord/crm/staff',{signal})});
export const useApplicationOptions=(q:string,enabled:boolean)=>useQuery({queryKey:keys.list('crm-application-options',{q}),queryFn:({signal})=>api<ApplicationOption[]>(`/coord/volunteers/application-options?q=${encodeURIComponent(q)}`,{signal}),enabled});
export function useCrmCommand<T>(path:string,method='POST',baseVersion?:number){
  const client=useQueryClient(),logical=useRef({signature:'',key:''}),version=useRef(baseVersion);
  const refresh=async()=>{await client.invalidateQueries({queryKey:keys.all('crm')});};
  const mutation=useMutation({mutationFn:(input:unknown)=>{const body=version.current!==undefined&&typeof input==='object'&&input!==null?{...input,expected_version:version.current}:input;const signature=JSON.stringify(body);if(signature!==logical.current.signature)logical.current={signature,key:crypto.randomUUID()};return api<T>(path,{method,body,idempotencyKey:logical.current.key,retries:0});},onSuccess:async result=>{if(version.current!==undefined&&result&&typeof result==='object'&&'version' in result)version.current=Number(result.version);await refresh();},
    onError:async error=>{if(error instanceof ApiError&&error.status===409)await refresh();}});
  return {...mutation,rebase:(next:number)=>{version.current=next;}};
}
export const stateLabels:Record<string,string>={unverified:'Актуальность не проверена',contacted:'Связались',awaiting_reply:'Ждём ответа',ready:'Готов помогать',active:'Регулярно участвует',paused:'Сейчас на паузе',unavailable:'Сейчас не готов помогать',unreachable:'Не удалось связаться',closed:'Участие завершено'};
export const channels=[{value:'telegram',label:'Telegram'},{value:'phone',label:'Телефонный звонок'},{value:'email',label:'Электронная почта'},{value:'max',label:'Max'},{value:'whatsapp',label:'WhatsApp'},{value:'other',label:'Другой канал'}];
export const dateLabel=(value:string)=>new Date(value+'T12:00:00+03:00').toLocaleDateString('ru',{day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Moscow'});
export const initials=(value:string)=>value.split(/\s+/).map(word=>word[0]).slice(0,2).join('');
