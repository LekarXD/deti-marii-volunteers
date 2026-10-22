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
/** «Сб, 7 ноября, 14:00»: the tile and the big hero line show the start only. */
export function eventWhen(card:{starts_at:string;timezone:string}){return `${eventDay(card)}, ${labelTime(card.starts_at,card.timezone)}`}
/** «До 16:00, мастерская» under the big start line; an overnight event names its last day too. */
export function eventUntil(row:{starts_at:string;ends_at:string;timezone:string;location?:string|null}){
 const sameDay=localParts(row.starts_at,row.timezone).date===localParts(row.ends_at,row.timezone).date;
 return `До ${sameDay?'':`${eventDay({starts_at:row.ends_at,timezone:row.timezone})}, `}${labelTime(row.ends_at,row.timezone)}${row.location?`, ${row.location}`:''}`;
}
/** Tile date line: «Сб, 7 ноября, 14:00»; an online task that runs for days reads «До 12 ноября, онлайн». */
export function tileWhen(card:{starts_at:string;ends_at:string;timezone:string;format:string}){
 if(card.format!=='online')return eventWhen(card);
 const sameDay=localParts(card.starts_at,card.timezone).date===localParts(card.ends_at,card.timezone).date;
 return sameDay?`${eventWhen(card)}, онлайн`:`До ${labelDate(localParts(card.ends_at,card.timezone).date)}, онлайн`;
}
export function eventWeekend(card:{starts_at:string;timezone:string}){return [0,6].includes(parseDate(localParts(card.starts_at,card.timezone).date).getUTCDay())}
export function bestNeed(card:EventCard){return card.needs.find(need=>need.id===card.best_need_id)??card.needs[0]}

/** Places as a dot and a short phrase; a few places left turns the dot orange. The tile counts the role the volunteer would sign up for. */
export type Places={label:string;tone:''|'few'|'none'};
export function placesFor(missing:number):Places{
 if(missing<=0)return {label:'Мест нет',tone:'none'};
 if(missing===1)return {label:'Осталось одно место',tone:'few'};
 if(missing===2)return {label:'Осталось два места',tone:'few'};
 return {label:'Есть места',tone:''};
}
export function cardPlaces(card:EventCard):Places{
 if(card.conflict)return {label:'В это время у тебя другое занятие',tone:'none'};
 if(card.full)return {label:card.needs.some(need=>need.allowed_actions.includes('reserve'))?'Можно в резерв':'Мест нет',tone:'none'};
 return placesFor(bestNeed(card)?.missing??0);
}

/** Points multiplier of a role (1 or 1,5); the pill shows only above 1. */
export function needMultiplier(need:EventNeed){return need.points_multiplier||1}
/** The tile shows the multiplier of the role the volunteer would sign up for. */
export function cardMultiplier(card:EventCard){const need=bestNeed(card);return need?needMultiplier(need):1}

/** One colour per event title, so a tile, its detail page, the schedule row and the calendar chip always match. */
const tones=[{key:'y',art:'art-y',tint:'var(--yellow-tint)'},{key:'o',art:'art-o',tint:'var(--orange-tint)'},{key:'b',art:'art-b',tint:'var(--blue-tint)'},{key:'g',art:'art-g',tint:'var(--green-tint)'},{key:'v',art:'art-v',tint:'var(--violet-tint)'}] as const;
export function toneFor(seed:string){let hash=0;for(const char of seed)hash=(hash*31+char.charCodeAt(0))>>>0;return tones[hash%tones.length]}

export function eventIcon(card:{program:string;title:string;format:string}){
 const text=`${card.program} ${card.title}`.toLowerCase();
 if(card.format==='online')return 'globe' as const;
 if(text.includes('ярмар')||text.includes('базар'))return 'home' as const;
 if(text.includes('фото')||text.includes('съёмк')||text.includes('видео'))return 'camera' as const;
 if(text.includes('творч')||text.includes('мастер')||text.includes('живопис')||text.includes('арт'))return 'palette' as const;
 return 'users' as const;
}
