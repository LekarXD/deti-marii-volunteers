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
export function useActivityCommand(){const client=useQueryClient();const attempts=useRef(new Map<string,string>());return useMutation({mutationFn:({path,body,method='POST',key}:{path:string;body:unknown;method?:'POST'|'PATCH';key:string})=>{const fingerprint=JSON.stringify([path,method,body]);const stableKey=attempts.current.get(fingerprint)??key;attempts.current.set(fingerprint,stableKey);return api<Role|Opportunity|CalendarOccurrence|CalendarSeries>(`/api/v1${path}`,{method,body,idempotencyKey:stableKey})},onSuccess:(_result,variables)=>{attempts.current.delete(JSON.stringify([variables.path,variables.method??'POST',variables.body]));return client.invalidateQueries({queryKey:keys.all('activities')})}});}
export function useRoleUsage(id:string|undefined){return useQuery({queryKey:keys.detail('activities',`role-usage:${id}`),enabled:!!id,queryFn:({signal})=>api<components['schemas']['RoleUsage']>(`/api/v1/coord/roles/${id}/usage`,{signal})});}
export function useActivityHistory(kind:'roles'|'opportunities',id:string|undefined){return useQuery({queryKey:keys.detail('activities',`history:${kind}:${id}`),enabled:!!id,queryFn:({signal})=>api<components['schemas']['ActivityRevisionView'][]>(`/api/v1/coord/${kind}/${id}/history`,{signal})});}
