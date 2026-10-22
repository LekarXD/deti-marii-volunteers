import type {CalendarOccurrence} from './calendarApi';
import {labelDate,localParts,parseDate,today} from './calendarDates';
export function staffing(item:Pick<CalendarOccurrence,'staffing_needs'|'status'>){
 const required=item.staffing_needs.reduce((sum,n)=>sum+n.required,0),confirmed=item.staffing_needs.reduce((sum,n)=>sum+n.confirmed,0),invited=item.staffing_needs.reduce((sum,n)=>sum+n.invited,0),missing=Math.max(0,required-confirmed);
 return {required,confirmed,invited,missing,tone:item.status==='cancelled'||!required?'neutral':missing?'gap':'full',label:item.status==='cancelled'?'Отменено':!required?'Волонтёры не нужны':!missing?'Команда собрана':confirmed?`${confirmed} из ${required} подтвердили`:`${missing===1?'Нужен':'Нужны'} ${volunteers(missing)}`};
}
export function periodLabel(from:string,to:string){const a=parseDate(from),b=parseDate(to);return from.slice(0,7)===to.slice(0,7)?`${a.getUTCDate()}–${labelDate(to,{day:'numeric',month:'long',year:'numeric'})}`:a.getUTCFullYear()===b.getUTCFullYear()?`${labelDate(from)} — ${labelDate(to,{day:'numeric',month:'long',year:'numeric'})}`:`${labelDate(from,{day:'numeric',month:'long',year:'numeric'})} — ${labelDate(to,{day:'numeric',month:'long',year:'numeric'})}`;}
/** Selection is independent of range filtering: every day in the week remains visible. */
export function groupCalendarRows<T extends Pick<CalendarOccurrence,'starts_at'>>(rows:T[]){const groups=new Map<string,T[]>();for(const row of rows){const day=localParts(row.starts_at).date;groups.set(day,[...(groups.get(day)??[]),row]);}return Array.from(groups);}
const volunteerWord=(n:number)=>n%10===1&&n%100!==11?'волонтёр':n%10>=2&&n%10<=4&&(n%100<12||n%100>14)?'волонтёра':'волонтёров';
/** «1 волонтёр», «3 волонтёра», «12 волонтёров». */
export function volunteers(n:number){return `${n} ${volunteerWord(n)}`}
/** «2 из 3 волонтёров»: after «из» the noun agrees with the total. */
export function fillLabel(confirmed:number,required:number){return `${confirmed} из ${required} ${required%10===1&&required%100!==11?'волонтёра':'волонтёров'}`}
/** «Октябрь 2026». */
export function monthTitle(day:string){const month=labelDate(day,{month:'long'});return `${month.charAt(0).toUpperCase()}${month.slice(1)} ${day.slice(0,4)}`}
/** «Сегодня, чт, 22 октября» or «сб, 24 октября». */
export function dayTitle(day:string){return `${day===today()?'Сегодня, ':''}${labelDate(day,{weekday:'short'})}, ${labelDate(day)}`}
const tones=['d-o','d-y','d-g','d-b','d-v','d-p'];
/** Programmes shown in the period get distinct dot colours in alphabetical order; events without one get a quiet dot. */
export function programTones(programs:string[]){const names=Array.from(new Set(programs.filter(Boolean))).sort((a,b)=>a.localeCompare(b,'ru'));const map=new Map(names.map((name,index)=>[name,tones[index%tones.length]]));return {names,tone:(program:string)=>map.get(program)??'d-q'};}
/** The day itself when it has events, otherwise the closest day that has some (the later one on a tie). */
export function nearestDay(day:string,days:string[]){let best=day,distance=Infinity;for(const candidate of days){const gap=Math.abs(parseDate(candidate).getTime()-parseDate(day).getTime());if(gap<distance||(gap===distance&&candidate>best)){best=candidate;distance=gap;}}return best;}
