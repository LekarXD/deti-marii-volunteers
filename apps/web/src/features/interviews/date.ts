export const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
export const addDays=(date:string,n:number)=>{const d=new Date(`${date}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
export const monday=(date:string)=>{const day=new Date(`${date}T12:00:00Z`).getUTCDay();return addDays(date,-((day+6)%7));};
export const dateLabel=(date:string,zone='Europe/Moscow')=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',weekday:'short',timeZone:zone}).format(new Date(date.length===10?`${date}T12:00:00Z`:date));
export const timeLabel=(date:string,zone='Europe/Moscow')=>new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:zone}).format(new Date(date));
export const minutes=(s:string)=>Number(s.slice(0,2))*60+Number(s.slice(3));
export const hhmm=(n:number)=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;
export const localDay=(instant:string,zone:string)=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:zone}).format(new Date(instant));
