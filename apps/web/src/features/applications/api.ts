import {useRef} from 'react';
import {keepPreviousData, useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
export type Draft = components['schemas']['DraftView'];
export type Application = components['schemas']['ApplicationSelfView'];
export type Candidate = components['schemas']['CandidateView'];
export type CandidateList = components['schemas']['CandidateListView'];
export type CandidateSummary = components['schemas']['CandidateSummaryView'];
export type CandidateStage = Candidate['stage'];
export type CandidateRequest = components['schemas']['RequestView'];
export type Note = components['schemas']['NoteView'];
export type Submission = components['schemas']['SubmissionCommand'];
export const applicationKeys = {all:()=>keys.all('application'), self:()=>keys.self('application'), draft:()=>keys.self('application-draft'),
  candidates:(query='')=>keys.list('application',{query}), candidate:(id:string)=>keys.detail('application',id), summary:()=>keys.list('application',{summary:true}),
  requests:(coord=false)=>keys.list('application',{requests:true,coord}), notes:(id:string)=>keys.detail('application-notes',id)};
export const useDraft = () => useQuery({queryKey:applicationKeys.draft(),queryFn:({signal})=>api<Draft>('/api/v1/registration/draft',{signal})});
export const useApplication = () => useQuery({queryKey:applicationKeys.self(),queryFn:({signal})=>api<Application>('/api/v1/me/application',{signal}),refetchInterval:15000,retry:false});
export const useCandidates = (query:string, keepPrevious=false) => useQuery({queryKey:applicationKeys.candidates(query),queryFn:({signal})=>api<CandidateList>(`/api/v1/coord/candidates?${query}`,{signal}),refetchInterval:15000,placeholderData:keepPrevious?keepPreviousData:undefined});
export const useCandidate = (id:string, placeholderData?:Candidate) => useQuery({queryKey:applicationKeys.candidate(id),queryFn:({signal})=>api<Candidate>(`/api/v1/coord/candidates/${id}`,{signal}),enabled:!!id,refetchInterval:15000,placeholderData});
export const useCandidateSummary = () => useQuery({queryKey:applicationKeys.summary(),queryFn:({signal})=>api<CandidateSummary>('/api/v1/coord/candidates/summary',{signal}),refetchInterval:15000});
export const useRequests = (coord=false) => useQuery({queryKey:applicationKeys.requests(coord),queryFn:({signal})=>api<CandidateRequest[]>(`/api/v1/${coord?'coord':'me'}/candidate-requests`,{signal}),refetchInterval:15000});
export const useNotes = (id:string, enabled=false) => useQuery({queryKey:applicationKeys.notes(id),queryFn:({signal})=>api<Note[]>(`/api/v1/coord/candidates/${id}/notes`,{signal}),enabled:!!id&&enabled,retry:false});
export function useCommand<T>(path:string, method='POST') {
  const client=useQueryClient();
  const last=useRef({signature:"",key:""});
  return useMutation({mutationFn:({body,key}:{body:unknown;key?:string})=>{const signature=JSON.stringify(body);if(last.current.signature!==signature)last.current={signature,key:commandKey()};return api<T>(path,{method,body,idempotencyKey:key||last.current.key,retries:0});},
    onError:async(error)=>{if(error instanceof ApiError&&error.status===409)await client.invalidateQueries({queryKey:applicationKeys.all()});},
    onSuccess:async()=>{await Promise.all(['application','application-draft','application-notes','candidates'].map(domain=>client.invalidateQueries({queryKey:keys.all(domain)})));}});
}
export const commandKey=()=>crypto.randomUUID();
