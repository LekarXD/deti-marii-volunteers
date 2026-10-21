import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import type {components} from '../../api/generated/schema';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
export type Source=components['schemas']['SourceView'];
export type Fragment=components['schemas']['FragmentView'];
export type MentorRun=components['schemas']['MentorView'];
export type Question=components['schemas']['app__modules__knowledge__schemas__QuestionView'];
export type AIRun=components['schemas']['AIRunView'];
export function useSources(){return useQuery({queryKey:keys.list('knowledge-sources'),queryFn:({signal})=>api<Source[]>('/coord/knowledge/sources',{signal}),refetchInterval:query=>query.state.data?.some(source=>source.index_state==='queued'||source.ingest_state==='queued')?3000:false});}
export function useQuestions(){return useQuery({queryKey:keys.list('knowledge-questions'),queryFn:({signal})=>api<Question[]>('/coord/knowledge/questions',{signal}),refetchInterval:10000});}
export function useHistory(){return useQuery({queryKey:keys.list('mentor-history'),queryFn:({signal})=>api<MentorRun[]>('/mentor/runs',{signal})});}
export function useMentorRun(id?:string|null){return useQuery({queryKey:keys.detail('mentor-run',id??''),enabled:Boolean(id),queryFn:({signal})=>api<MentorRun>(`/mentor/runs/${id}`,{signal}),refetchInterval:query=>['queued','calling'].includes(query.state.data?.state??'')?2000:10000});}
export function useKnowledgeCommand(){const client=useQueryClient();return useMutation({mutationFn:({path,body,method='POST'}:{path:string;body:unknown;method?:'POST'|'PUT'})=>api<unknown>(path,{method,body,idempotencyKey:crypto.randomUUID()}),onSuccess:async()=>{await Promise.all(['knowledge-sources','knowledge-questions','mentor-history','mentor-run','learning-author'].map(domain=>client.invalidateQueries({queryKey:keys.all(domain)})));}});}
export async function uploadPdf(file:File){
 const buffer=await file.arrayBuffer();const checksum=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer))).map(n=>n.toString(16).padStart(2,'0')).join('');
 const intent=await api<{id:string;upload_url:string}>('/assets/upload-intents',{method:'POST',body:{content_type:file.type,expected_size:file.size,checksum}});
 for(let offset=0;offset<buffer.byteLength;offset+=1048576)await api(intent.upload_url,{method:'PATCH',headers:{'X-Upload-Offset':String(offset)},body:buffer.slice(offset,offset+1048576)});
 await api(`/assets/${intent.id}/complete-upload`,{method:'POST'});return intent.id;
}
