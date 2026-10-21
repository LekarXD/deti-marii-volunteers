import {useInfiniteQuery, useQuery} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
export type CalendarOccurrence=components['schemas']['EventOccurrenceView'];
export type CalendarSeries=components['schemas']['EventSeriesView'];
export type CalendarSeriesCreate=components['schemas']['EventSeriesCreate'];
export type CalendarNeedInput=components['schemas']['StaffingNeedInput'];
export type CalendarPreview=components['schemas']['SeriesChangePreview'];
export function useCalendarRange(from:string,to:string){return useInfiniteQuery({queryKey:keys.list('activities',{kind:'calendar',from,to}),initialPageParam:'',queryFn:({signal,pageParam})=>api<components['schemas']['EventOccurrencePage']>(`/event-occurrences?from=${from}&to=${to}&limit=500${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:last=>last.next_cursor??undefined})}
export function useCalendarOccurrence(id:string|undefined){return useQuery({queryKey:keys.detail('activities',`occurrence:${id}`),enabled:!!id,queryFn:({signal})=>api<CalendarOccurrence>(`/event-occurrences/${id}`,{signal})})}
export function useCalendarSeries(id:string|undefined){return useQuery({queryKey:keys.detail('activities',`series:${id}`),enabled:!!id,queryFn:({signal})=>api<CalendarSeries>(`/coord/event-series/${id}`,{signal})})}
export function useCalendarGroups(){return useInfiniteQuery({queryKey:keys.list('activities',{kind:'groups'}),initialPageParam:'',queryFn:({signal,pageParam})=>api<components['schemas']['GroupList']>(`/coord/groups?limit=100${pageParam?`&cursor=${pageParam}`:''}`,{signal}),getNextPageParam:()=>undefined})}
