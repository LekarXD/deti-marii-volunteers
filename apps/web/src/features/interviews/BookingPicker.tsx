import {useState} from 'react';
import {Button,Card,Combobox,ErrorState,Icon,LoadingState} from '../../ui';
import {Booking,Slot,useSlots,useInterviewCommand} from './api';
import {addDays,addMonths,dateLabel,dayNumber,dayTitle,localDay,monthEnd,monthLabel,monthStart,timeLabel} from './date';
import './interviews.css';
export type BookingPickerProps={applicationId?:string;booking?:Booking|null;onBooked?:()=>void;onClose?:()=>void;embedded?:boolean};
const zones=[{value:'Europe/Moscow',label:'Москва (UTC+3)',time:'Московское время'},{value:'Asia/Yekaterinburg',label:'Екатеринбург (UTC+5)',time:'Время Екатеринбурга'},{value:'Asia/Novosibirsk',label:'Новосибирск (UTC+7)',time:'Время Новосибирска'},{value:'Europe/Berlin',label:'Берлин',time:'Время Берлина'}];
const weekdays=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
/** Month calendar with the chosen day's free times; past days and days without free time are not selectable. */
export function BookingPicker({applicationId,booking,onBooked,onClose,embedded=false}:BookingPickerProps){
 const [zone,setZone]=useState('Europe/Moscow'),[zoneOpen,setZoneOpen]=useState(false),now=localDay(new Date().toISOString(),zone),current=monthStart(now),last=addMonths(current,6);
 const [month,setMonth]=useState(current),[day,setDay]=useState<string|null>(null),[picked,setPicked]=useState<Slot|null>(null);
 const shown=month<current?current:month,query=useSlots(shown===current?now:shown,monthEnd(shown),zone),command=useInterviewCommand<Booking>();
 const future=(query.data||[]).filter(s=>new Date(s.starts_at)>new Date()),slotsOf=(d:string)=>future.filter(s=>localDay(s.starts_at,zone)===d);
 const days=Array.from({length:Number(monthEnd(shown).slice(8))},(_,i)=>addDays(shown,i)),offset=(new Date(`${shown}T12:00:00Z`).getUTCDay()+6)%7;
 const active=day&&slotsOf(day).length?day:days.find(d=>slotsOf(d).length)??null,daySlots=active?slotsOf(active):[],chosen=daySlots.find(s=>s.id===picked?.id)??null;
 const goMonth=(next:string)=>{setMonth(next);setDay(null);setPicked(null);};
 const confirm=()=>{if(!chosen)return;command.mutate({path:booking?`/interviews/${booking.id}/reschedule`:'/interviews',body:{slot_id:chosen.id,slot_version:chosen.version,application_id:applicationId,...(booking?{expected_version:booking.version}:{})}},{onSuccess:()=>{setPicked(null);onBooked?.();},onError:()=>{setPicked(null);void query.refetch();}});};
 const body=<>
  <div className="iv-pick-head"><h3 className="h3">{booking?'Новое время':'Выберите время'}</h3>{zoneOpen?<Combobox className="iv-pick-zone" label="Часовой пояс" value={zone} onChange={value=>{setZone(value);setZoneOpen(false);setDay(null);setPicked(null);}} options={zones}/>:<p className="iv-pick-tz">{zones.find(z=>z.value===zone)?.time}<button type="button" className="iv-pick-link" onClick={()=>setZoneOpen(true)}>Изменить</button></p>}</div>
  <div className="iv-pick-layout">
   <div>
    <div className="iv-pick-mhead"><span aria-live="polite">{monthLabel(shown)}</span><div><Button variant="ghost" size="sm" aria-label="Предыдущий месяц" disabled={shown<=current} onClick={()=>goMonth(addMonths(shown,-1))}><Icon name="chevron-left"/></Button><Button variant="ghost" size="sm" aria-label="Следующий месяц" disabled={shown>=last} onClick={()=>goMonth(addMonths(shown,1))}><Icon name="chevron-right"/></Button></div></div>
    <div className="iv-pick-weekdays" aria-hidden="true">{weekdays.map(w=><span key={w}>{w}</span>)}</div>
    <div className="iv-pick-grid" role="group" aria-label={monthLabel(shown)}>{Array.from({length:offset},(_,i)=><span key={`blank-${i}`}/>)}{days.map(d=>{const n=slotsOf(d).length,on=d===active;return <button key={d} type="button" className={`iv-pick-cell${n?' is-open':''}${on?' is-on':''}`} disabled={!n} aria-pressed={on} aria-label={`${dayTitle(d)}: ${n?`свободно ${n}`:'нет свободного времени'}`} onClick={()=>{setDay(d);setPicked(null);}}>{dayNumber(d)}</button>;})}</div>
   </div>
   <div className="iv-pick-col">{query.isLoading?<LoadingState/>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:!active?<div className="iv-pick-empty"><p>В этом месяце свободного времени нет</p>{shown<last&&<Button variant="secondary" size="sm" onClick={()=>goMonth(addMonths(shown,1))}>Следующий месяц</Button>}</div>:<>
    <p className="iv-pick-day">{dayTitle(active)}</p>
    <div className="iv-pick-times" role="radiogroup" aria-label={`Свободное время: ${dayTitle(active)}`}>{daySlots.map(s=><button key={s.id} type="button" role="radio" aria-checked={chosen?.id===s.id} className={`iv-pick-time${chosen?.id===s.id?' is-on':''}`} onClick={()=>setPicked(s)}>{timeLabel(s.starts_at,zone)}</button>)}</div>
   </>}</div>
  </div>
  {command.error&&<p role="alert" className="iv-error">{command.error.message}</p>}
  <div className="iv-pick-actions"><Button size="lg" disabled={!chosen||command.isPending||query.isFetching} onClick={confirm}>{command.isPending?'Сохраняем…':chosen?`${booking?'Перенести на':'Записаться на'} ${dateLabel(chosen.starts_at,zone)}, ${timeLabel(chosen.starts_at,zone)}`:booking?'Перенести встречу':'Записаться на встречу'}</Button>{onClose&&<Button variant="ghost" onClick={onClose}>Отмена</Button>}</div>
 </>;
 return embedded?<section className="iv-pick is-embedded">{body}</section>:<Card className="iv-pick">{body}</Card>;
}
