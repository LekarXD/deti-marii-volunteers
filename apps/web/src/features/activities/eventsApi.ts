import {useQuery} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import {addDays,labelDate,labelTime,localParts,parseDate,today} from './calendarDates';
export type EventFeed=components['schemas']['VolunteerEventFeed'];
export type EventCard=components['schemas']['VolunteerEventCard'];
export type EventDetail=components['schemas']['VolunteerEventDetail'];
export type EventNeed=components['schemas']['VolunteerEventNeed'];
export type MatchingOptions=components['schemas']['MatchingOptionsView'];

/** The feed is ordered by the server; the score itself never reaches the client. */
export function useEventFeed(from:string,to:string,enabled=true){return useQuery({queryKey:keys.list('activities',{kind:'event-feed',from,to}),enabled:enabled&&from<=to,
 queryFn:({signal})=>api<EventFeed>(`/me/events?from=${from}&to=${to}&timezone=Europe/Moscow`,{signal})})}
export function useVolunteerEvent(id:string|undefined){return useQuery({queryKey:keys.detail('activities',`volunteer-event:${id}`),enabled:!!id,queryFn:({signal})=>api<EventDetail>(`/me/events/${id}`,{signal})})}
export function useMatchingOptions(){return useQuery({queryKey:keys.detail('activities','role-matching-options'),staleTime:Infinity,queryFn:({signal})=>api<MatchingOptions>('/coord/role-matching-options',{signal})})}

export const FEED_DAYS=60;
export function feedRange(){const from=today();return {from,to:addDays(from,FEED_DAYS)}}
export function eventDay(card:{starts_at:string;timezone:string}){const date=localParts(card.starts_at,card.timezone).date;const label=labelDate(date,{weekday:'short',day:'numeric',month:'long'});return label.charAt(0).toUpperCase()+label.slice(1)}
export function eventTime(card:{starts_at:string;ends_at:string;timezone:string}){return `${labelTime(card.starts_at,card.timezone)}–${labelTime(card.ends_at,card.timezone)}`}
export function eventWeekend(card:{starts_at:string;timezone:string}){return [0,6].includes(parseDate(localParts(card.starts_at,card.timezone).date).getUTCDay())}
export function bestNeed(card:EventCard){return card.needs.find(need=>need.id===card.best_need_id)??card.needs[0]}
export function placesLabel(card:EventCard){
 if(card.conflict)return 'В это время у тебя другое занятие';
 const need=bestNeed(card);if(!need)return '';
 return card.full?`Записались ${need.confirmed} из ${need.required}, можно в резерв`:`Записались ${need.confirmed} из ${need.required}`;
}
export function eventIcon(card:EventCard){
 const text=`${card.program} ${card.title}`.toLowerCase();
 if(card.format==='online')return 'globe' as const;
 if(text.includes('ярмар')||text.includes('базар'))return 'home' as const;
 if(text.includes('фото')||text.includes('съёмк')||text.includes('видео'))return 'camera' as const;
 if(text.includes('творч')||text.includes('мастер')||text.includes('живопис')||text.includes('арт'))return 'palette' as const;
 return 'users' as const;
}
