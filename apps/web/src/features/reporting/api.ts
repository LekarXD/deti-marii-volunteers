import {useRef} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
type S=components['schemas'];
export type Report=S['ReportView'];
export type ReportSummary=S['ReportSummaryView'];
export type Scope=S['ReportScopeView'];
export type Metrics=S['ReportMetricsView'];
export type Export=S['ReportExportView'];
export type Dobro=S['DobroPreviewView'];
export type Digest=S['ReportDigestView'];
export type Recipient=S['ReportDigestRecipientView'];
export function useReportQuery<T>(name:string,path:string,enabled=true){return useQuery({queryKey:keys.list('reporting',{name,path}),queryFn:({signal})=>api<T>(path,{signal}),enabled,refetchInterval:30000});}
export function useReportCommand(){const cache=useQueryClient(),receipt=useRef({signature:'',key:''});return useMutation({mutationFn:({path,body,method='POST'}:{path:string;body:unknown;method?:string})=>{const signature=JSON.stringify([path,body,method]);if(signature!==receipt.current.signature)receipt.current={signature,key:crypto.randomUUID()};return api<unknown>(path,{method,body,idempotencyKey:receipt.current.key,retries:0});},onSuccess:async()=>{await cache.invalidateQueries({queryKey:keys.all('reporting')});},onError:async error=>{if(error instanceof ApiError&&error.status===409)await cache.invalidateQueries({queryKey:keys.all('reporting')});}});}
export const scopeQuery=(scope:Scope)=>`scope_type=${scope.scope_type}${scope.scope_id?'&scope_id='+scope.scope_id:''}`;
export const reportDate=(date:string)=>new Date(date+'T12:00:00+03:00').toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Moscow'});
export const dateTime=(date:string)=>new Date(date).toLocaleString('ru-RU',{timeZone:'Europe/Moscow'});
export const valueLabel=(metric:Metrics['metrics'][number])=>metric.value===null?'Нет данных':metric.key==='volunteer_minutes'?`${Math.floor(metric.value/60)} ч ${metric.value%60} мин`:`${metric.value}${metric.unit==='%'?' %':''}`;
