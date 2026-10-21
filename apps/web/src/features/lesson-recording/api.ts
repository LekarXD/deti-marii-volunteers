import {useRef} from 'react';
import {useInfiniteQuery,useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
export type RecordingProject=components['schemas']['RecordingProjectView'];
export type RecordingTake=components['schemas']['RecordingTakeView'];
export type RecordingRender=components['schemas']['RecordingRenderView'];
export const useRecordingProjects=()=>useInfiniteQuery({queryKey:keys.list('recordings'),initialPageParam:'',queryFn:({signal,pageParam})=>api<components['schemas']['RecordingProjectPage']>(`/recording-projects?limit=20${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:page=>page.next_cursor??undefined});
export const useRecordingProject=(id:string|undefined)=>useQuery({queryKey:keys.detail('recordings',id??''),queryFn:({signal})=>api<RecordingProject>(`/recording-projects/${id}`,{signal}),enabled:!!id,refetchInterval:3000});
export const useRecordingTakes=(id:string)=>useInfiniteQuery({queryKey:keys.list('recording-takes',{projectId:id}),initialPageParam:0,queryFn:({signal,pageParam})=>api<components['schemas']['RecordingTakePage']>(`/recording-projects/${id}/takes?limit=20${pageParam?`&before=${pageParam}`:''}`,{signal}),getNextPageParam:page=>page.next_cursor??undefined,refetchInterval:query=>query.state.data?.pages[0]?.items.some(take=>['created','starting','capturing','stopping'].includes(take.state))?2000:false});
/** Stable logical command key survives uncertain network/server failures. No unsafe retries. */
export function useRecordingCommand<T=unknown>() {
 const client=useQueryClient(),pending=useRef(new Map<string,string>());
 return useMutation({mutationFn:async({path,body,method='POST'}:{path:string;body:unknown;method?:'POST'|'PATCH'})=>{
  const signature=JSON.stringify([path,method,body]),key=pending.current.get(signature)??crypto.randomUUID();pending.current.set(signature,key);
  try{const value=await api<T>(path,{method,body,idempotencyKey:key,retries:0});pending.current.delete(signature);return value;}
  catch(error){if(error instanceof ApiError&&error.status>=400&&error.status<500&&![408,429].includes(error.status))pending.current.delete(signature);throw error;}
 },onSuccess:async()=>{await Promise.all(['recordings','recording-takes','recording-renders','studio-sessions'].map(domain=>client.invalidateQueries({queryKey:keys.all(domain)})));}});
}
export const useRecordingRenders=(projectId:string)=>useInfiniteQuery({queryKey:keys.list('recording-renders',{projectId}),initialPageParam:'',queryFn:({signal,pageParam})=>api<components['schemas']['RecordingRenderPage']>(`/recording-projects/${projectId}/renders?limit=20${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:page=>page.next_cursor??undefined,refetchInterval:3000});
