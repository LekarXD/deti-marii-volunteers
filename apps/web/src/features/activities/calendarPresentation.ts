import type {CalendarOccurrence} from './calendarApi';
import {labelDate,localParts,parseDate} from './calendarDates';
export function staffing(item:Pick<CalendarOccurrence,'staffing_needs'|'status'>){
 const required=item.staffing_needs.reduce((sum,n)=>sum+n.required,0),confirmed=item.staffing_needs.reduce((sum,n)=>sum+n.confirmed,0),invited=item.staffing_needs.reduce((sum,n)=>sum+n.invited,0),missing=Math.max(0,required-confirmed);
 const count=(n:number)=>n%10===1&&n%100!==11?'волонтёр':n%10>=2&&n%10<=4&&(n%100<12||n%100>14)?'волонтёра':'волонтёров';
 return {required,confirmed,invited,missing,tone:item.status==='cancelled'||!required?'neutral':missing?'gap':'full',label:item.status==='cancelled'?'Отменено':!required?'Волонтёры не нужны':!missing?'Команда собрана':confirmed?`${confirmed} из ${required} подтвердили`:`${missing===1?'Нужен':'Нужны'} ${missing} ${count(missing)}`};
}
export function periodLabel(from:string,to:string){const a=parseDate(from),b=parseDate(to);return from.slice(0,7)===to.slice(0,7)?`${a.getUTCDate()}–${labelDate(to,{day:'numeric',month:'long',year:'numeric'})}`:a.getUTCFullYear()===b.getUTCFullYear()?`${labelDate(from)} — ${labelDate(to,{day:'numeric',month:'long',year:'numeric'})}`:`${labelDate(from,{day:'numeric',month:'long',year:'numeric'})} — ${labelDate(to,{day:'numeric',month:'long',year:'numeric'})}`;}
/** Selection is independent of range filtering: every day in the week remains visible. */
export function groupCalendarRows<T extends Pick<CalendarOccurrence,'starts_at'>>(rows:T[]){const groups=new Map<string,T[]>();for(const row of rows){const day=localParts(row.starts_at).date;groups.set(day,[...(groups.get(day)??[]),row]);}return Array.from(groups);}
