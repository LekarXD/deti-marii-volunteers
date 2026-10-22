import {useRef} from 'react';
import {useInfiniteQuery, useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {CalendarOccurrence,CalendarSeries} from './calendarApi';
import type {components} from '../../api/generated/schema';
export type Role = components['schemas']['RoleView'];
export type Opportunity = components['schemas']['OpportunityView'];
export type Requirement = components['schemas']['PreparationRequirement'];
export type RoleCreate = components['schemas']['RoleCreate'];
export type OpportunityCreate = components['schemas']['OpportunityCreate'];
type RolePage = components['schemas']['RolePage'];
type OpportunityPage = components['schemas']['OpportunityPage'];
export const activityKeys = {roles:(archived:boolean,q:string)=>keys.list('activities',{kind:'roles',archived,q}), opportunities:(staff:boolean,q:string,state:string,regularity:string,format:string)=>keys.list('activities',{kind:'opportunities',staff,q,state,regularity,format})};
export function useRoles(archived=false,q='') {
 return useInfiniteQuery({queryKey:activityKeys.roles(archived,q),initialPageParam:'',queryFn:({signal,pageParam})=>api<RolePage>(`/api/v1/coord/roles?archived=${archived}&q=${encodeURIComponent(q)}&limit=100${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:last=>last.next_cursor || undefined});
}
export function useOpportunityList(staff:boolean,q='',state='',regularity='',format='') {
 const query=new URLSearchParams({q,limit:'30'}); if(state)query.set('state',state);if(regularity)query.set('regularity',regularity);if(format)query.set('format',format);
 return useInfiniteQuery({queryKey:activityKeys.opportunities(staff,q,state,regularity,format),initialPageParam:'',queryFn:({signal,pageParam})=>api<OpportunityPage>(`/api/v1/${staff?'coord/':''}opportunities?${query}${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:last=>last.next_cursor || undefined});
}
export function useOpportunity(id:string|undefined,staff:boolean){return useQuery({queryKey:keys.detail('activities',`${staff?'staff':'public'}:opportunity:${id}`),enabled:!!id,queryFn:({signal})=>api<Opportunity>(`/api/v1/${staff?'coord/':''}opportunities/${id}`,{signal})});}
export function useActivityCommand(){const client=useQueryClient();const attempts=useRef(new Map<string,string>());return useMutation({mutationFn:({path,body,method='POST',key}:{path:string;body:unknown;method?:'POST'|'PATCH';key:string})=>{const fingerprint=JSON.stringify([path,method,body]);const stableKey=attempts.current.get(fingerprint)??key;attempts.current.set(fingerprint,stableKey);return api<Role|Opportunity|CalendarOccurrence|CalendarSeries|components['schemas']['AssignmentParticipationView']|components['schemas']['ParticipationResponseView']>(`/api/v1${path}`,{method,body,idempotencyKey:stableKey})},onSuccess:(_result,variables)=>{attempts.current.delete(JSON.stringify([variables.path,variables.method??'POST',variables.body]));return client.invalidateQueries({queryKey:keys.all('activities')})}});}
export function useRoleUsage(id:string|undefined){return useQuery({queryKey:keys.detail('activities',`role-usage:${id}`),enabled:!!id,queryFn:({signal})=>api<components['schemas']['RoleUsage']>(`/api/v1/coord/roles/${id}/usage`,{signal})});}
export function useActivityHistory(kind:'roles'|'opportunities',id:string|undefined){return useQuery({queryKey:keys.detail('activities',`history:${kind}:${id}`),enabled:!!id,queryFn:({signal})=>api<components['schemas']['ActivityRevisionView'][]>(`/api/v1/coord/${kind}/${id}/history`,{signal})});}
export type EventResponsesSummary=components['schemas']['EventResponsesSummary'];
export type StaffReserve=components['schemas']['StaffReserveView'];
type TeamRow=components['schemas']['AssignmentParticipationView'];
type ResponseRow=components['schemas']['ParticipationResponseView'];
/** Reads every page of a cursor list: the coordinator events list and event page need whole sets, not a feed. */
async function allPages<T>(path:string,signal:AbortSignal){const items:T[]=[];let cursor='';do{const page=await api<{items:T[];next_cursor?:string|null}>(`${path}${path.includes('?')?'&':'?'}limit=100${cursor?`&cursor=${cursor}`:''}`,{signal});items.push(...page.items);cursor=page.next_cursor??'';}while(cursor);return items;}
export function useStaffOpportunities(enabled=true){return useQuery({queryKey:keys.list('activities',{kind:'staff-opportunities'}),enabled,queryFn:({signal})=>allPages<Opportunity>('/api/v1/coord/opportunities',signal)});}
export function useRoleTitles(enabled=true){return useQuery({queryKey:keys.list('activities',{kind:'role-titles'}),enabled,queryFn:async({signal})=>Object.fromEntries([...await allPages<Role>('/api/v1/coord/roles?archived=false',signal),...await allPages<Role>('/api/v1/coord/roles?archived=true',signal)].map(role=>[role.id,role.title])) as Record<string,string>});}
export function useEventResponsesSummary(enabled=true){return useQuery({queryKey:keys.list('activities',{kind:'event-responses'}),enabled,queryFn:({signal})=>api<EventResponsesSummary>('/api/v1/coord/event-responses',{signal})});}
export function useEventTeam(occurrenceId:string|undefined,enabled=true){return useQuery({queryKey:keys.list('activities',{kind:'event-team',occurrenceId}),enabled:enabled&&!!occurrenceId,queryFn:({signal})=>allPages<TeamRow>(`/api/v1/coord/assignments?occurrence_id=${occurrenceId}`,signal)});}
export function useEventReserve(occurrenceId:string|undefined,enabled=true){return useQuery({queryKey:keys.list('activities',{kind:'event-reserve',occurrenceId}),enabled:enabled&&!!occurrenceId,queryFn:({signal})=>api<StaffReserve[]>(`/api/v1/coord/event-occurrences/${occurrenceId}/reserve`,{signal})});}
export function useAwaitingResponses(opportunityId:string|undefined,enabled=true){return useQuery({queryKey:keys.list('activities',{kind:'awaiting-responses',opportunityId}),enabled:enabled&&!!opportunityId,queryFn:({signal})=>allPages<ResponseRow>(`/api/v1/coord/responses?opportunity_id=${opportunityId}&awaiting=true`,signal)});}
