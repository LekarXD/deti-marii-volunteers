import type {components} from '../../api/generated/schema';
export type TransferPeriod=components['schemas']['DobroTransferPeriodView'];
export type TransferGroup=TransferPeriod['groups'][number];
export type TransferRow=TransferGroup['rows'][number];
export interface SelectedTransfer {activity:TransferGroup['activity'];row:TransferRow;hours:string;}
export const validPeriod=(value:string)=>/^\d{4}-(0[1-9]|1[0-2])$/.test(value);
export function currentPeriod(){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit'}).format(new Date());}
export function movePeriod(value:string,offset:number){const [year,month]=value.split('-').map(Number),date=new Date(Date.UTC(year,month-1+offset,1));return `${date.getUTCFullYear()}-${String(date.getUTCMonth()+1).padStart(2,'0')}`;}
export function monthLabel(value:string){const [year,month]=value.split('-').map(Number);return new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(Date.UTC(year,month-1,1)));}
export function dateLabel(value:string|null){if(!value)return 'не указан';const date=new Date(value);return Number.isNaN(date.valueOf())?'не указан':new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Moscow'}).format(date);}
export const hoursLabel=(value:number)=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(value);
const dobroHosts=new Set(['dobro.ru',new URL('https://добро.рф').hostname]);
export function dobroUrl(value:string|null|undefined){try{const url=new URL(value??'');return url.protocol==='https:'&&!url.username&&!url.password&&!url.port&&!url.hash&&dobroHosts.has(url.hostname)?url.href:null;}catch{return null;}}
export function transferTsv(items:readonly SelectedTransfer[]){return ['ФИО\tЧасы',...items.map(({row,hours})=>{let name=row.display_name.replace(/[\t\r\n]+/g,' ').trim();if(/^[=+@-]/.test(name))name=`'${name}`;return `${name}\t${hours}`;})].join('\n');}
