import type {components} from '../../api/generated/schema';
import {useSession} from '../../app/layouts/AppProviders';
import type {EventResponsesSummary,Opportunity} from './api';
import type {CalendarOccurrence} from './calendarApi';
import {labelDate,labelTime,localParts} from './calendarDates';
type RecurrenceRule=components['schemas']['RecurrenceRule'];

export const plural=(n:number,one:string,few:string,many:string)=>{const a=n%10,b=n%100;return a===1&&b!==11?one:a>=2&&a<=4&&(b<12||b>14)?few:many;};
export const responsesLabel=(n:number)=>`${n} ${plural(n,'отклик','отклика','откликов')}`;
export const firstName=(name:string)=>name.trim().split(/\s+/)[0]||name;
const initials=(name:string)=>name.trim().split(/\s+/).slice(0,2).map(part=>part[0]??'').join('').toUpperCase();
const tones=['ph-o','ph-g','ph-b','ph-v','ph-p'];
export function Avatar({id,name}:{id:string;name:string}){return <span className={`cev-ph ${tones[[...id].reduce((sum,char)=>sum+char.charCodeAt(0),0)%tones.length]}`} aria-hidden="true">{initials(name)}</span>;}
export function RepeatIcon(){return <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9a8 8 0 0 1 14-3l2 2M20 4v4h-4M20 15a8 8 0 0 1-14 3l-2-2M4 20v-4h4"/></svg>;}

/** What the coordinator may see and do on the events pages; the API stays authoritative. */
export function useCoordAccess(){const {session}=useSession();const has=(name:string)=>!!session?.permissions.includes(name);return {assign:has('assignments.manage'),schedule:has('schedule.read')||has('schedule.manage'),opportunities:has('opportunities.manage'),roles:has('roles.manage')};}

const months=['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
const cap=(value:string)=>value.charAt(0).toUpperCase()+value.slice(1);
export const weekdayShort=(date:string)=>cap(labelDate(date,{weekday:'short'}).replace('.',''));
export function dateChip(item:Pick<CalendarOccurrence,'starts_at'|'timezone'>){const date=localParts(item.starts_at,item.timezone).date;return {day:String(Number(date.slice(8))),mon:months[Number(date.slice(5,7))-1]};}
export const timeRange=(item:Pick<CalendarOccurrence,'starts_at'|'ends_at'|'timezone'>)=>`${labelTime(item.starts_at,item.timezone)}–${labelTime(item.ends_at,item.timezone)}`;
/** «Сб, 14:00–18:00, место»; with the date for the event page: «Сб, 31 октября, 14:00–18:00, место». */
export function eventWhen(item:Pick<CalendarOccurrence,'starts_at'|'ends_at'|'timezone'|'location'>,withDate=false){
 const start=localParts(item.starts_at,item.timezone).date,end=localParts(item.ends_at,item.timezone).date;
 if(start!==end)return [start.slice(0,7)===end.slice(0,7)?`${labelDate(start,{day:'numeric'})}–${labelDate(end)}`:`${labelDate(start)} – ${labelDate(end)}`,item.location].filter(Boolean).join(', ');
 return [weekdayShort(start),withDate?labelDate(start):'',timeRange(item),item.location].filter(Boolean).join(', ');
}
const every=['Каждый понедельник','Каждый вторник','Каждую среду','Каждый четверг','Каждую пятницу','Каждую субботу','Каждое воскресенье'];
const byDays=['понедельникам','вторникам','средам','четвергам','пятницам','субботам','воскресеньям'];
const joinAnd=(items:string[])=>items.length>1?`${items.slice(0,-1).join(', ')} и ${items[items.length-1]}`:items[0]??'';
export function recurrenceText(rule?:RecurrenceRule){
 const days=rule?.weekdays??[];
 if(rule?.frequency==='weekly'&&days.length===1)return every[days[0]];
 if(rule?.frequency==='weekly'&&days.length)return `По ${joinAnd(days.map(day=>byDays[day]))}`;
 if(rule?.frequency==='biweekly')return `Раз в две недели${days.length?`, по ${joinAnd(days.map(day=>byDays[day]))}`:''}`;
 if(rule?.frequency==='monthly')return 'Раз в месяц';
 return 'Регулярно';
}
export function titlesLine(titles:string[]){const shown=titles.slice(0,3),rest=titles.length-shown.length;return rest>0?`${shown.join(', ')} и ещё ${rest}`:joinAnd(shown);}

export type EventsTab='open'|'draft'|'past';
export interface EventRow{key:string;title:string;when:string;chip:'date'|'repeat'|'undated';day?:string;mon?:string;roles:{name:string;fill?:string;low?:boolean}[];responses:number;tab:EventsTab;section:'once'|'regular';sort:string;to?:string;opportunityId?:string}
/**
 * Coordinator «Мероприятия»: dated occurrences with staffing needs (what volunteers sign up for),
 * a recurring series as one row, and opportunities (directions without dates) as regular programmes or drafts.
 */
export function buildEventRows({occurrences,opportunities,summary,rules={},roleTitles={},now=Date.now()}:{occurrences:CalendarOccurrence[];opportunities:Opportunity[];summary?:EventResponsesSummary;rules?:Record<string,RecurrenceRule|undefined>;roleTitles?:Record<string,string>;now?:number}):EventRow[]{
 const waiting=new Map((summary?.sign_ups??[]).map(row=>[row.staffing_need_id,row.count]));
 const answers=new Map((summary?.responses??[]).map(row=>[row.opportunity_id,row.count]));
 const pending=(item:CalendarOccurrence)=>item.staffing_needs.reduce((sum,need)=>sum+(waiting.get(need.id)??0),0);
 const roles=(item:CalendarOccurrence,open:boolean)=>item.staffing_needs.filter(need=>need.required>0).map(need=>{const people=need.confirmed+Math.max(0,need.invited-(waiting.get(need.id)??0));return {name:need.role_title,fill:`${people} из ${need.required}`,low:open&&people/need.required<.5};});
 const dated=(item:CalendarOccurrence,tab:EventsTab):EventRow=>({key:item.id,title:item.title,when:eventWhen(item),chip:'date',...dateChip(item),roles:roles(item,tab==='open'),responses:tab==='open'?pending(item):0,tab,section:'once',sort:item.starts_at,to:`/fund/events/${item.id}`});
 const live=occurrences.filter(item=>item.status!=='cancelled'&&item.staffing_needs.some(need=>need.required>0)).sort((a,b)=>a.starts_at.localeCompare(b.starts_at));
 const upcoming=live.filter(item=>Date.parse(item.ends_at)>now),series=new Map<string,CalendarOccurrence[]>();
 for(const item of upcoming)series.set(item.series_id,[...(series.get(item.series_id)??[]),item]);
 const rows:EventRow[]=[];
 for(const [id,items] of series){
  if(items.length===1){rows.push(dated(items[0],'open'));continue;}
  const next=items[0];
  rows.push({key:`series:${id}`,title:next.title,when:[recurrenceText(rules[id]),timeRange(next),next.location].filter(Boolean).join(', '),chip:'repeat',roles:roles(next,true),responses:items.reduce((sum,item)=>sum+pending(item),0),tab:'open',section:'regular',sort:next.starts_at,to:`/fund/events/${next.id}`});
 }
 for(const item of live.filter(item=>Date.parse(item.ends_at)<=now).reverse())rows.push(dated(item,'past'));
 for(const item of [...opportunities].sort((a,b)=>a.title.localeCompare(b.title,'ru'))){
  const tab:EventsTab=item.state==='published'?'open':item.state==='closed'?'past':'draft';
  rows.push({key:`opportunity:${item.id}`,title:item.title,when:[item.schedule,item.location].filter(Boolean).join(', '),chip:['regular','periodic'].includes(item.regularity??'')?'repeat':'undated',
   roles:item.role_ids.map(id=>roleTitles[id]).filter(Boolean).map(name=>({name})),responses:tab==='open'?answers.get(item.id)??0:0,tab,section:['regular','periodic'].includes(item.regularity??'')?'regular':'once',sort:`~${item.title}`,opportunityId:item.id});
 }
 return rows;
}
