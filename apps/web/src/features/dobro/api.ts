import {useRef} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
type S=components['schemas'];
export type DobroOwn=S['DobroOwnView'];
export type DobroSettings=S['DobroSettingsView'];
export type DobroActivity=S['DobroActivityView'];
export type DobroActivityCommand=S['DobroActivityCommand'];
export type DobroOwnActivity=S['DobroOwnActivityView'];
export type DobroTeam=S['DobroTeamView'];
export type DobroSeries=S['DobroSeriesView'];
export type DobroPeriod=S['DobroTransferPeriodView'];
export function useDobroQuery<T>(kind:string,path:string,enabled=true){return useQuery({queryKey:keys.list('dobro',{kind,path}),queryFn:({signal})=>api<T>(path,{signal}),enabled,refetchInterval:30000});}
export function useDobroCommand<T>(path:string,method='POST'){
 const cache=useQueryClient(),attempts=useRef(new Map<string,string>());
 return useMutation({mutationFn:(body:unknown)=>{const signature=JSON.stringify([path,method,body]);const key=attempts.current.get(signature)??crypto.randomUUID();attempts.current.set(signature,key);return api<T>(path,{method,body,idempotencyKey:key,retries:0});},onSuccess:async(_result,body)=>{attempts.current.delete(JSON.stringify([path,method,body]));await cache.invalidateQueries({queryKey:keys.all('dobro')});},onError:async error=>{if(error instanceof ApiError&&error.status===409)await cache.invalidateQueries({queryKey:keys.all('dobro')});}});
}
export const dobroStates={none:'Нет отклика',applied:'Отклик отправлен',approved:'Отклик одобрен',not_needed:'Не нужно'};
export const dobroDate=(value:string)=>new Date(value+'T12:00:00+03:00').toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Moscow'});
export const monthNow=()=>new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Moscow'}).slice(0,7);
