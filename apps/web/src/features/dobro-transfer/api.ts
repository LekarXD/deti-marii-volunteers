import {useRef} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import type {TransferPeriod} from './model';
export const transferKey=(period:string)=>keys.list('dobro',{kind:'transfers',period});
export function useDobroTransfers(period:string){return useQuery({queryKey:transferKey(period),queryFn:({signal})=>api<TransferPeriod>(`/fund/integrations/dobro/transfers?period=${encodeURIComponent(period)}`,{signal})});}
/** Command keys survive uncertain outcomes in memory; no external CRM request exists. */
function useDobroCommand<T>(receipt?:(value:T)=>void) {
 const pending=useRef(new Map<string,string>()),client=useQueryClient();
 return useMutation({mutationFn:async({path,body,method='POST'}:{path:string;body:unknown;method?:'POST'|'PUT'})=>{
  const signature=JSON.stringify([path,method,body]),key=pending.current.get(signature)??crypto.randomUUID();pending.current.set(signature,key);
  try{const value=await api<T>(path,{method,body,retries:0,idempotencyKey:key});pending.current.delete(signature);return value;}
  catch(error){if(error instanceof ApiError&&error.status>=400&&error.status<500&&![408,429].includes(error.status))pending.current.delete(signature);throw error;}
 },onSuccess:async(value)=>{
  receipt?.(value);
  await client.invalidateQueries({queryKey:keys.all('dobro')});
 }});
}
export function useMarkDobroEntered(){const client=useQueryClient(),command=useDobroCommand<TransferPeriod>(value=>client.setQueryData(transferKey(value.period),value));return {...command,mark:(body:components['schemas']['DobroMarkCommand'])=>command.mutateAsync({path:'/fund/integrations/dobro/transfers/mark-entered',body})};}
export function useDobroEnrollment(){const command=useDobroCommand<components['schemas']['DobroEnrollmentView']>();return {...command,change:(activityId:string,userId:string,body:components['schemas']['DobroEnrollmentCommand'])=>command.mutateAsync({path:`/fund/integrations/dobro/enrollments/${encodeURIComponent(activityId)}/${encodeURIComponent(userId)}`,method:'PUT',body})};}
