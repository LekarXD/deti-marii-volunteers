import {useEffect, useState} from 'react';
import {Button,Card,DatePicker,Combobox,LoadingState} from '../../ui';
import {Booking,Slot,useSlots,useInterviewCommand} from './api';
import {addDays,dateLabel,monday,today,timeLabel,localDay} from './date';
import './interviews.css';
export type BookingPickerProps={applicationId?:string;booking?:Booking|null;onBooked?:()=>void;onClose?:()=>void};
export function BookingPicker({applicationId,booking,onBooked,onClose}:BookingPickerProps){
 const [focus,setFocus]=useState(today),[zone,setZone]=useState('Europe/Moscow'),[picked,setPicked]=useState<Slot|null>(null),[day,setDay]=useState(today);
 const from=monday(focus),to=addDays(from,6),query=useSlots(from,to,zone),command=useInterviewCommand<Booking>();
 useEffect(()=>{setPicked(null);setDay(focus);},[focus,zone]);
 const slots=query.data||[],daySlots=slots.filter(s=>localDay(s.starts_at,zone)===day);
 const confirm=()=>{if(!picked)return;command.mutate({path:booking?`/interviews/${booking.id}/reschedule`:'/interviews',body:{slot_id:picked.id,slot_version:picked.version,application_id:applicationId,...(booking?{expected_version:booking.version}:{})}},{onSuccess:()=>{setPicked(null);onBooked?.();},onError:()=>{setPicked(null);void query.refetch();}});};
 return <Card className="iv-picker"><div className="iv-heading"><h2>{booking?'Перенести встречу':'Выберите удобное время'}</h2>{onClose&&<Button variant="ghost" onClick={onClose}>Закрыть</Button>}</div>
 <p>Только свободные места. Записаться можно, пока вы знакомитесь с фондом.</p>
 <div className="iv-period"><Button variant="ghost" aria-label="Предыдущая неделя" onClick={()=>setFocus(addDays(focus,-7))}>←</Button><span>{dateLabel(from)} — {dateLabel(to)}</span><Button variant="ghost" aria-label="Следующая неделя" onClick={()=>setFocus(addDays(focus,7))}>→</Button><Button variant="ghost" onClick={()=>setFocus(today())}>Сегодня</Button></div>
 <div className="iv-grid"><DatePicker label="Перейти к дате" value={focus} onChange={setFocus}/><Combobox label="Часовой пояс" value={zone} onChange={setZone} options={[{value:'Europe/Moscow',label:'Москва (UTC+3)'},{value:'Asia/Yekaterinburg',label:'Екатеринбург (UTC+5)'},{value:'Asia/Novosibirsk',label:'Новосибирск (UTC+7)'},{value:'Europe/Berlin',label:'Берлин'}]}/></div>
 <div className="iv-days" role="group" aria-label="День встречи">{Array.from({length:7},(_,i)=>addDays(from,i)).map(d=><button key={d} className={`iv-day ${d===day?'is-on':''}`} aria-pressed={day===d} onClick={()=>{setDay(d);setPicked(null);}}><span>{dateLabel(d,zone)}</span><small>{slots.filter(s=>localDay(s.starts_at,zone)===d).length} свободно</small></button>)}</div>
 {query.isLoading?<LoadingState/>:query.error?<p role="alert">{query.error.message} <Button onClick={()=>void query.refetch()}>Повторить</Button></p>:!slots.length?<div className="iv-empty"><h3>Свободного времени пока нет</h3><p>Выберите другую неделю или напишите координатору.</p></div>:<div className="iv-slots" role="radiogroup" aria-label="Свободное время">{daySlots.map(s=><button key={s.id} role="radio" aria-checked={picked?.id===s.id} className={`iv-slot ${picked?.id===s.id?'is-on':''}`} onClick={()=>setPicked(s)}><strong>{timeLabel(s.starts_at,zone)}–{timeLabel(s.ends_at,zone)}</strong><span>{s.venue}</span></button>)}</div>}
 {picked&&<p className="iv-selected"><b>{dateLabel(picked.starts_at,zone)}, {timeLabel(picked.starts_at,zone)}</b><br/>{picked.venue}</p>}
 {command.error&&<p role="alert" className="iv-error">{command.error.message}</p>}
 {booking&&<p className="iv-hint">Прежняя запись сохранится до подтверждения переноса.</p>}
 <Button size="lg" disabled={!picked||command.isPending||query.isFetching} onClick={confirm}>{command.isPending?'Сохраняем…':booking?'Подтвердить перенос':'Записаться на встречу'}</Button>
 {!query.isLoading&&!query.error&&!!slots.length&&!daySlots.length&&<p className="iv-hint">В этот день свободного времени нет. Выберите другой день.</p>}
 </Card>;
}
