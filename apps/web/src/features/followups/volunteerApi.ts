import {useEffect,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import {hoursLabel,pointsLabel} from '../profile/api';
import {firstNameOf,initialsOf} from '../../ui/names';
type Schemas=components['schemas'];
export type OwnHours=Schemas['HoursView'];
export type OwnProfile=Schemas['ProfileView'];
export type OwnAssignment=Schemas['AssignmentParticipationView'];
export type Contact=Schemas['PreparationContact'];

/** Volunteer reads shared by the adaptation screens; keys match the profile and participation caches. */
export const readOwnHours=(signal?:AbortSignal)=>api<OwnHours>('/me/hours',{signal});
export const readOwnProfile=(signal?:AbortSignal)=>api<OwnProfile>('/me/profile',{signal});
export const readOwnAssignment=(id:string,signal?:AbortSignal)=>api<OwnAssignment>(`/assignments/${id}`,{signal});
export function useOwnHours(){return useQuery({queryKey:keys.self('profile-hours'),queryFn:({signal})=>readOwnHours(signal)});}
export function useOwnProfile(){return useQuery({queryKey:keys.self('profile'),queryFn:({signal})=>readOwnProfile(signal)});}
export function useOwnAssignment(id:string){return useQuery({queryKey:keys.detail('activities',`assignment:${id}`),enabled:!!id,queryFn:({signal})=>readOwnAssignment(id,signal)});}
/** Own invited or confirmed занятия on one calendar day (YYYY-MM-DD, Moscow), e.g. the date a coordinator suggested after a reflection. */
export function useOwnDay(day:string|null|undefined){return useQuery({queryKey:keys.list('activities',{kind:'own-day',day}),enabled:!!day,queryFn:({signal})=>api<Schemas['AssignmentParticipationPage']>(`/me/schedule?from=${day}&to=${day}&timezone=Europe/Moscow&state=active&limit=20`,{signal}).then(page=>page.items??[])});}

const NARROW='(max-width: 720px)';
const narrowQuery=()=>typeof window!=='undefined'&&typeof window.matchMedia==='function'?window.matchMedia(NARROW):null;
/** Phone width, the breakpoint of the volunteer CSS; without matchMedia (tests, old browsers) the wide layout is used. */
export function useNarrow(){
 const [narrow,setNarrow]=useState(()=>narrowQuery()?.matches??false);
 useEffect(()=>{const query=narrowQuery();if(!query)return;const update=()=>setNarrow(query.matches);update();query.addEventListener?.('change',update);return ()=>query.removeEventListener?.('change',update);},[]);
 return narrow;
}

/** The first exit is the one before any занятие with confirmed minutes (this one may already be marked). */
export function isFirstExit(hours:OwnHours|undefined,assignmentId:string){
 if(!hours)return false;
 const own=hours.entries.filter(entry=>entry.assignment_id===assignmentId).reduce((sum,entry)=>sum+entry.delta_minutes,0)>0;
 return hours.confirmed_assignments===(own?1:0);
}

const format=(value:string|Date,timeZone:string,options:Intl.DateTimeFormatOptions)=>new Intl.DateTimeFormat('ru-RU',{timeZone,...options}).format(typeof value==='string'?new Date(value):value);
export const cap=(value:string)=>value.charAt(0).toUpperCase()+value.slice(1);
/** «Сб, 24 октября, 14:00» in the event's own time zone. */
export const whenLong=(value:string,timeZone='Europe/Moscow')=>`${cap(format(value,timeZone,{weekday:'short'}))}, ${format(value,timeZone,{day:'numeric',month:'long'})}, ${format(value,timeZone,{hour:'2-digit',minute:'2-digit'})}`;
export const timeOnly=(value:string,timeZone='Europe/Moscow')=>format(value,timeZone,{hour:'2-digit',minute:'2-digit'});
export const dayMonth=(value:string,timeZone='Europe/Moscow')=>format(value,timeZone,{day:'numeric',month:'long'});
/** A calendar date (YYYY-MM-DD) without time: day number and short weekday for the `.day` badge. */
export const dateBadge=(date:string)=>{const noon=new Date(`${date}T12:00:00Z`);return {day:format(noon,'UTC',{day:'numeric'}),weekday:format(noon,'UTC',{weekday:'short'})};};
/** «сегодня, 19:10», «вчера, 19:10» or «24 октября, 19:10» in Moscow time. */
export function stamp(value:string,now=new Date()){
 const zone='Europe/Moscow',day=(d:Date)=>format(d,zone,{year:'numeric',month:'2-digit',day:'2-digit'});
 const at=new Date(value),time=format(at,zone,{hour:'2-digit',minute:'2-digit'});
 if(day(at)===day(now))return `сегодня, ${time}`;
 if(day(at)===day(new Date(now.getTime()-86400000)))return `вчера, ${time}`;
 return `${format(at,zone,{day:'numeric',month:'long'})}, ${time}`;
}
export const firstName=(name?:string|null)=>firstNameOf(name);
export const initials=(name:string)=>initialsOf(name);
/** The group leader is the person who meets the volunteer and marks the занятие. */
export const leadContact=(contacts:Contact[]|undefined)=>contacts?.find(contact=>contact.role==='Ведущий');
export const coordinatorContact=(contacts:Contact[]|undefined)=>contacts?.find(contact=>contact.role==='Координатор');
/** Confirmed minutes of one занятие in the hours ledger, or null while the ledger has nothing for it. */
export function ledgerMinutes(hours:OwnHours|undefined,assignmentId:string){
 const rows=hours?.entries.filter(entry=>entry.assignment_id===assignmentId)??[];
 return rows.length?rows.reduce((sum,entry)=>sum+entry.delta_minutes,0):null;
}
export const errorText=(error:unknown)=>error instanceof Error&&error.message?error.message:'Не получилось. Попробуй ещё раз.';

/** 10 points per hour, half-up on the whole assignment — the same rule as the server ledger. */
export const estimatePoints=(minutes:number,multiplier=1)=>Math.floor((minutes*10*Math.round(multiplier*100)+3000)/6000);
export const hoursText=(minutes:number)=>minutes%60===0?hoursLabel(minutes):`${(Math.round(minutes/6)/10).toLocaleString('ru')} часа`;
export function creditAmount(minutes:number,multiplier=1){const points=estimatePoints(minutes,multiplier);return points>0?`${hoursText(minutes)} и ${pointsLabel(points)}`:hoursText(minutes);}
