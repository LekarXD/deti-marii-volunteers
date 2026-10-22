export const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
export const addDays=(date:string,n:number)=>{const d=new Date(`${date}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
export const monday=(date:string)=>{const day=new Date(`${date}T12:00:00Z`).getUTCDay();return addDays(date,-((day+6)%7));};
export const dateLabel=(date:string,zone='Europe/Moscow')=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',weekday:'short',timeZone:zone}).format(new Date(date.length===10?`${date}T12:00:00Z`:date));
export const timeLabel=(date:string,zone='Europe/Moscow')=>new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:zone}).format(new Date(date));
export const minutes=(s:string)=>Number(s.slice(0,2))*60+Number(s.slice(3));
export const hhmm=(n:number)=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;
export const localDay=(instant:string,zone:string)=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:zone}).format(new Date(instant));
const calendarDay=(date:string,options:Intl.DateTimeFormatOptions)=>new Intl.DateTimeFormat('ru-RU',{...options,timeZone:'UTC'}).format(new Date(`${date}T12:00:00Z`));
const capitalize=(text:string)=>text.charAt(0).toUpperCase()+text.slice(1);
export const dayNumber=(date:string)=>calendarDay(date,{day:'numeric'});
export const dayTitle=(date:string)=>capitalize(calendarDay(date,{weekday:'long',day:'numeric',month:'long'}));
export const monthStart=(date:string)=>`${date.slice(0,7)}-01`;
export const addMonths=(month:string,n:number)=>{const d=new Date(`${month}T12:00:00Z`);d.setUTCMonth(d.getUTCMonth()+n,1);return d.toISOString().slice(0,10);};
export const monthEnd=(month:string)=>addDays(addMonths(month,1),-1);
export const monthLabel=(month:string)=>`${capitalize(calendarDay(month,{month:'long'}))} ${month.slice(0,4)}`;
const months=['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
/** Moscow calendar day and minute of an instant; the interviews grid is always МСК (UTC+3, no DST). */
export const mskDay=(instant:string)=>localDay(instant,'Europe/Moscow');
export const mskMinute=(instant:string)=>{const d=new Date(new Date(instant).getTime()+3*3600000);return d.getUTCHours()*60+d.getUTCMinutes();};
export const mskInstant=(date:string,minute:number)=>new Date(`${date}T${hhmm(minute)}:00+03:00`);
export const weekdayIndex=(date:string)=>(new Date(`${date}T12:00:00Z`).getUTCDay()+6)%7;
export const shortDate=(date:string)=>`${Number(date.slice(8))} ${months[Number(date.slice(5,7))-1]}`;
/** «Пт, 23 октября». */
export const dayShort=(date:string)=>capitalize(calendarDay(date,{weekday:'short',day:'numeric',month:'long'}));
/** «пятница». */
export const weekdayName=(date:string)=>calendarDay(date,{weekday:'long'});
/** «19 – 25 октября» or «26 октября – 1 ноября». */
export const weekLabel=(first:string)=>{const last=addDays(first,6),a=calendarDay(first,{day:'numeric',month:'long'}),b=calendarDay(last,{day:'numeric',month:'long'});return first.slice(5,7)===last.slice(5,7)?`${Number(first.slice(8))} – ${b}`:`${a} – ${b}`;};
export {capitalize};
