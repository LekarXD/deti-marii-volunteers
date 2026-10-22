/** Webinar times are planned and shown in Moscow time, like the webinar form. */
const zone='Europe/Moscow';
const months=['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
const calendar=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'numeric',day:'numeric'});
const weekdayFormat=new Intl.DateTimeFormat('ru-RU',{timeZone:zone,weekday:'short'});
const dayMonthFormat=new Intl.DateTimeFormat('ru-RU',{timeZone:zone,day:'numeric',month:'long'});
const clockFormat=new Intl.DateTimeFormat('ru-RU',{timeZone:zone,hour:'2-digit',minute:'2-digit'});
function day(value:string|Date){const parts=Object.fromEntries(calendar.formatToParts(new Date(value)).map(part=>[part.type,Number(part.value)]));return {year:parts.year,month:parts.month,day:parts.day};}
export const plural=(count:number,one:string,few:string,many:string)=>{const form=new Intl.PluralRules('ru-RU').select(count);return form==='one'?one:form==='few'?few:many;};
/** Whole Moscow calendar days from today to the date. */
export function daysUntil(value:string,now=new Date()){const a=day(value),b=day(now);return Math.round((Date.UTC(a.year,a.month-1,a.day)-Date.UTC(b.year,b.month-1,b.day))/86400000);}
const weekday=(value:string)=>{const text=weekdayFormat.format(new Date(value));return text.charAt(0).toUpperCase()+text.slice(1);};
export const dayMonth=(value:string)=>dayMonthFormat.format(new Date(value));
/** «Чт, 29 октября, 19:00» */
export const fullWhen=(value:string)=>`${weekday(value)}, ${dayMonth(value)}, ${clockFormat.format(new Date(value))}`;
/** «Чт, 19:00» */
export const shortWhen=(value:string)=>`${weekday(value)}, ${clockFormat.format(new Date(value))}`;
export function dateChip(value:string){const parts=day(value);return {day:parts.day,month:months[parts.month-1]};}
export function nextLabel(value:string,now=new Date()){
 if(Date.parse(value)<=now.getTime())return 'Эфир идёт';
 const days=daysUntil(value,now);
 return days<=0?'Ближайший эфир, сегодня':days===1?'Ближайший эфир, завтра':`Ближайший эфир, через ${days} ${plural(days,'день','дня','дней')}`;
}
export const enrolledLabel=(count:number)=>count>0?`${count} ${plural(count,'записался','записались','записались')}`:'Нет записавшихся';
/** «4:12», «1:02:05»; null when the server reported no length. */
export function videoLength(ms:number|null|undefined){
 if(ms==null||!Number.isFinite(ms)||ms<0)return null;
 const total=Math.round(ms/1000),hours=Math.floor(total/3600),minutes=Math.floor(total%3600/60),seconds=String(total%60).padStart(2,'0');
 return hours?`${hours}:${String(minutes).padStart(2,'0')}:${seconds}`:`${minutes}:${seconds}`;
}
