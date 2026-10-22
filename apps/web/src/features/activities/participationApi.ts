import {useInfiniteQuery,useQuery} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
export type AssignmentParticipation=components['schemas']['AssignmentParticipationView'];
export type OpportunityResponse=components['schemas']['ParticipationResponseView'];
/** A self sign-up or a freed reserve place the coordinator has not approved yet: nothing to answer.
 * The server flag wins when the view carries it; a coordinator's invitation is always answered by the volunteer. */
export function awaitingCoordinator(item:{status:string;origin?:string|null;approved_at?:string|null;awaiting_coordinator?:boolean}){
 if(typeof item.awaiting_coordinator==='boolean')return item.awaiting_coordinator;
 return item.status==='invited'&&(item.origin==='self'||item.origin==='reserve')&&!item.approved_at;
}
export function useAssignments(staff=false,occurrenceId?:string){return useInfiniteQuery({queryKey:keys.list('activities',{kind:'assignments',staff,occurrenceId}),initialPageParam:'',queryFn:({signal,pageParam})=>api<components['schemas']['AssignmentParticipationPage']>(`${staff?'/coord':'/me'}/assignments?limit=100${occurrenceId?`&occurrence_id=${occurrenceId}`:''}${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:last=>last.next_cursor??undefined})}
export function useAssignment(id:string|undefined){return useQuery({queryKey:keys.detail('activities',`assignment:${id}`),enabled:!!id,queryFn:({signal})=>api<AssignmentParticipation>(`/assignments/${id}`,{signal})})}
export function useResponses(staff=false,opportunityId?:string){return useInfiniteQuery({queryKey:keys.list('activities',{kind:'responses',staff,opportunityId}),initialPageParam:'',queryFn:({signal,pageParam})=>api<components['schemas']['ParticipationResponsePage']>(`${staff?'/coord':'/me'}/responses?limit=100${opportunityId?`&opportunity_id=${opportunityId}`:''}${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:last=>last.next_cursor??undefined})}
export function useAssignmentSuggestions(needId:string|undefined,q=''){return useQuery({queryKey:keys.list('activities',{kind:'assignment-suggestions',needId,q}),enabled:!!needId,queryFn:({signal})=>api<components['schemas']['AssignmentSuggestion'][]>(`/coord/staffing-needs/${needId}/suggestions?q=${encodeURIComponent(q)}`,{signal})})}
export function usePersonalSchedule(from:string,to:string,state='all'){return useInfiniteQuery({queryKey:keys.list('activities',{kind:'personal-schedule',from,to,state}),initialPageParam:'',queryFn:({signal,pageParam})=>api<components['schemas']['AssignmentParticipationPage']>(`/me/schedule?from=${from}&to=${to}&timezone=Europe/Moscow&state=${state}&limit=100${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:last=>last.next_cursor??undefined})}
export const multiplierLabel=(value:number)=>`Баллы ×${String(value).replace('.',',')}`;
export type OwnReserve=components['schemas']['VolunteerReserveItem'];
/** Waiting reserve places of the volunteer, upcoming only. */
export function useOwnReserves(){return useQuery({queryKey:keys.list('activities',{kind:'own-reserves'}),queryFn:({signal})=>api<components['schemas']['VolunteerReservePage']>('/me/reserves',{signal})})}
