export const calendarZone='Europe/Moscow';
export function calendarDate(value:Date){return `${value.getUTCFullYear()}-${String(value.getUTCMonth()+1).padStart(2,'0')}-${String(value.getUTCDate()).padStart(2,'0')}`}
export function parseDate(value:string){return new Date(`${value}T12:00:00Z`)}
export function addDays(value:string,days:number){const date=parseDate(value);date.setUTCDate(date.getUTCDate()+days);return calendarDate(date)}
export function monday(value:string){const date=parseDate(value);return addDays(value,-((date.getUTCDay()+6)%7))}
export function monthRange(value:string){const date=parseDate(value);return {from:calendarDate(new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth(),1))),to:calendarDate(new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)))}}
export function localParts(instant:string,zone=calendarZone){const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(instant)).map(p=>[p.type,p.value]));return {date:`${parts.year}-${parts.month}-${parts.day}`,time:`${parts.hour}:${parts.minute}`}}
export function today(){return localParts(new Date().toISOString()).date}
export function labelDate(value:string,options:Intl.DateTimeFormatOptions={day:'numeric',month:'long'}){return new Intl.DateTimeFormat('ru-RU',{...options,timeZone:'UTC'}).format(parseDate(value))}
export function labelTime(instant:string,zone=calendarZone){return new Intl.DateTimeFormat('ru-RU',{timeZone:zone,hour:'2-digit',minute:'2-digit'}).format(new Date(instant))}
