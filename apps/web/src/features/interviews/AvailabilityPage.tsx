import {useState} from 'react';
import {Link} from 'react-router-dom';
import {Button,Icon,LoadingState,ErrorState,cx} from '../../ui';
import {Availability,CalendarSlot,WindowInput,useAvailability,useCalendar,useInterviewCommand} from './api';
import {initials} from './StaffInterviewPanel';
import {addDays,hhmm,monday,mskDay,mskInstant,mskMinute,shortDate,today,weekLabel,weekdayIndex} from './date';
import './interviews.css';

const weekdays=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'],weekdaysLower=['пн','вт','ср','чт','пт','сб','вс'];
const AHEAD=26,FIRST=600,LAST=1110;
const longDate=(day:string)=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',timeZone:'UTC'}).format(new Date(`${day}T12:00:00Z`));
const shortName=(name:string)=>{const [first,last]=name.split(/\s+/);return last?`${first} ${last[0]}.`:first;};
const slotsWord=(n:number)=>({one:'слот',few:'слота',many:'слотов',other:'слота'} as Record<string,string>)[new Intl.PluralRules('ru').select(n)];
const rank={booked:0,free:1,skipped:2};
type Command={path:string;body:unknown;method?:'POST'|'PATCH'};
const base=(venue:string,join_url:string|null):WindowInput=>({local_start_date:'',start_minute:0,end_minute:30,timezone:'Europe/Moscow',recurrence:'once',interval_weeks:1,weekdays:[],duration_minutes:30,buffer_after_minutes:0,venue,join_url,active:true,last_date:null});

/** What closes one free slot: a skipped date of a single-slot window, a paused one-off window, or a narrower day of a longer window. */
export function closeSlot(slot:CalendarSlot):Command[]{
 const id=slot.series_id!,version=slot.series_version!,day=slot.origin_date!,m=slot.origin_minute!,start=slot.window_start_minute!,end=slot.window_end_minute!,length=slot.duration_minutes!,step=length+slot.buffer_after_minutes!;
 const positions:number[]=[];for(let at=start;at+length<=end;at+=step)positions.push(at);
 const exception=(body:object)=>({path:`/coord/interview-availability/${id}/exceptions`,body:{expected_version:version,origin_date:day,...body}});
 if(positions.length<=1)return [slot.recurrence==='weekly'?exception({kind:'skip'}):{path:`/coord/interview-availability/${id}/pause`,body:{expected_version:version,active:false}}];
 if(m===positions[0])return [exception({kind:'override',start_minute:start+step,end_minute:end})];
 const narrowed=exception({kind:'override',start_minute:start,end_minute:m});
 if(m===positions.at(-1))return [narrowed];
 // A slot from the middle splits the day: the window keeps the first part, a one-off window takes the rest.
 return [narrowed,{path:'/coord/interview-availability',body:{...base(slot.venue??'Онлайн',slot.join_url??null),local_start_date:day,start_minute:m+step,end_minute:end,timezone:slot.timezone??'Europe/Moscow',duration_minutes:length,buffer_after_minutes:slot.buffer_after_minutes}}];
}

/** One week of the coordinator's interview slots in Moscow time; a click opens or closes a half-hour slot. */
export function AvailabilityPage(){
 const current=monday(today()),[week,setWeek]=useState(current),[repeat,setRepeat]=useState(true),[flash,setFlash]=useState(''),[focus,setFocus]=useState<string|null>(null),[busy,setBusy]=useState(false);
 const calendar=useCalendar(week,addDays(week,13)),windows=useAvailability(),command=useInterviewCommand(),now=Date.now();
 const cells=new Map<string,CalendarSlot>();
 for(const slot of calendar.data??[]){const key=`${mskDay(slot.starts_at)} ${Math.floor(mskMinute(slot.starts_at)/30)*30}`,seen=cells.get(key);if(!seen||rank[slot.state]<rank[seen.state])cells.set(key,slot);}
 const days=Array.from({length:7},(_,i)=>addDays(week,i)),inWeek=(calendar.data??[]).filter(s=>days.includes(mskDay(s.starts_at)));
 const lo=Math.min(FIRST,...inWeek.map(s=>Math.floor(mskMinute(s.starts_at)/30)*30)),hi=Math.max(LAST,...inWeek.map(s=>Math.floor(mskMinute(s.starts_at)/30)*30));
 const times=Array.from({length:(hi-lo)/30+1},(_,i)=>lo+i*30);
 // Venue and link follow the coordinator's latest window; interviews are online by default.
 const latest=[...(windows.data??[])].filter(w=>w.active).at(-1),venue=latest?.venue??'Онлайн',link=latest?.join_url??null;
 const run=async(commands:Command[])=>{for(const c of commands)await command.mutateAsync(c);};
 const act=async(work:()=>Promise<string|void>)=>{if(busy)return;setBusy(true);setFlash('');setFocus(null);command.reset();try{const message=await work();if(message)setFlash(message);}catch{/* the command error is shown below the grid */}finally{setBusy(false);}};
 const open=(day:string,minute:number,slot?:CalendarSlot)=>act(async()=>{
  if(slot?.state==='skipped'&&slot.series_id)return void await run([{path:`/coord/interview-availability/${slot.series_id}/exceptions`,body:{expected_version:slot.series_version,origin_date:slot.origin_date,kind:'restore'}}]);
  const paused=(windows.data??[]).find((w:Availability)=>!w.active&&w.recurrence==='once'&&w.local_start_date===day&&w.start_minute===minute&&w.end_minute===minute+30&&w.timezone==='Europe/Moscow');
  if(paused)return void await run([{path:`/coord/interview-availability/${paused.id}/pause`,body:{expected_version:paused.version,active:true}}]);
  await run([{path:'/coord/interview-availability',body:{...base(venue,link),local_start_date:day,start_minute:minute,end_minute:minute+30,...(repeat?{recurrence:'weekly',weekdays:[weekdayIndex(day)]}:{})}}]);
 });
 const copy=()=>act(async()=>{
  let count=0;
  for(const slot of inWeek.filter(s=>s.state==='free')){
   const day=addDays(mskDay(slot.starts_at),7),minute=mskMinute(slot.starts_at),target=cells.get(`${day} ${Math.floor(minute/30)*30}`);
   if(target&&target.state!=='skipped')continue;
   await run(target?.series_id?[{path:`/coord/interview-availability/${target.series_id}/exceptions`,body:{expected_version:target.series_version,origin_date:target.origin_date,kind:'restore'}}]:[{path:'/coord/interview-availability',body:{...base(slot.venue??venue,slot.join_url??link),local_start_date:day,start_minute:minute,end_minute:minute+(slot.duration_minutes??30),duration_minutes:slot.duration_minutes??30}}]);
   count++;
  }
  setWeek(addDays(week,7));
  return count?`Скопировали ${count} ${slotsWord(count)}`:'Это время на следующей неделе уже открыто';
 });
 const focused=focus?cells.get(focus):undefined;
 return <div className="iv-slots">
  <Link className="iv-back" to="/fund/interviews"><Icon name="chevron-left"/>Собеседования</Link>
  <div className="page-head"><h1 className="h1 iv-h1">Свободные слоты для собеседований</h1></div>
  <section className="iv-wk" aria-label="Неделя">
   <div className="iv-wk-bar">
    <div className="iv-wk-nav">
     <div className="iv-week-switch">
      <button type="button" className="iconbtn" aria-label="Предыдущая неделя" disabled={week<=current} onClick={()=>{setWeek(addDays(week,-7));setFocus(null);setFlash('');}}><Icon name="chevron-left"/></button>
      <b aria-live="polite">{weekLabel(week)}</b>
      <button type="button" className="iconbtn" aria-label="Следующая неделя" disabled={week>=addDays(current,AHEAD*7)} onClick={()=>{setWeek(addDays(week,7));setFocus(null);setFlash('');}}><Icon name="chevron-right"/></button>
     </div>
     {week!==current&&<Button variant="ghost" size="sm" onClick={()=>{setWeek(current);setFocus(null);setFlash('');}}>Эта неделя</Button>}
    </div>
    <div className="iv-wk-tools">
     <label className="iv-toggle-line"><button type="button" className={cx('toggle',repeat&&'is-on')} role="switch" aria-checked={repeat} aria-label="Повторять каждую неделю" onClick={()=>setRepeat(!repeat)}/>Повторять каждую неделю</label>
     <Button variant="secondary" size="sm" disabled={busy||calendar.isLoading} onClick={()=>void copy()}>Скопировать на следующую</Button>
    </div>
   </div>
   {flash&&<div className="iv-done iv-wk-note" role="status"><Icon name="check"/>{flash}</div>}
   {command.error&&<p role="alert" className="iv-error iv-wk-note">{command.error.message}</p>}
   {focused?.booking_id&&<div className="iv-focus">
    <span className="iv-person"><span className="iv-ph iv-ph-sm iv-ph-b" aria-hidden="true">{initials(focused.candidate_name??'')}</span><span><span className="iv-person-name">{focused.candidate_name}</span><span className="meta">{weekdaysLower[weekdayIndex(mskDay(focused.starts_at))]}, {longDate(mskDay(focused.starts_at))}, {hhmm(mskMinute(focused.starts_at))}</span></span></span>
    <Link className="btn btn-secondary btn-sm" to={`/fund/interviews?booking=${focused.booking_id}`}>Открыть собеседование</Link>
   </div>}
   {calendar.isLoading?<LoadingState/>:calendar.error?<ErrorState error={calendar.error} retry={()=>void calendar.refetch()}/>:<div className="iv-wk-scroll"><div className="iv-wk-grid" aria-busy={busy||undefined}>
    <span className="iv-wk-corner">МСК</span>
    {days.map((day,i)=><span key={day} className={cx('iv-wk-day',day===today()&&'is-today')}><b>{weekdays[i]}</b><span>{shortDate(day)}</span></span>)}
    {times.map(minute=>[<span key={`t${minute}`} className="iv-wk-time">{hhmm(minute)}</span>,...days.map((day,i)=>{
     const key=`${day} ${minute}`,slot=cells.get(key),past=mskInstant(day,minute).getTime()<=now,state=slot?.state==='skipped'?undefined:slot?.state;
     const where=`${weekdaysLower[i]}, ${longDate(day)}, ${hhmm(minute)}`;
     const cls=cx('iv-cell',state==='free'&&'free',state==='booked'&&'booked',past&&'past',!state&&!past&&'add');
     if(state==='booked')return <button key={key} type="button" className={cls} aria-label={`${where}, занято: ${slot!.candidate_name}`} onClick={()=>{setFocus(key);setFlash('');}}>{shortName(slot!.candidate_name??'')}</button>;
     if(past)return <span key={key} className={cls}>{state==='free'?'Свободно':''}</span>;
     if(state==='free')return <button key={key} type="button" className={cls} aria-label={`${where}, свободно, убрать`} onClick={()=>void act(async()=>run(closeSlot(slot!)))}>Свободно</button>;
     return <button key={key} type="button" className={cls} aria-label={`${where}, открыть время`} onClick={()=>void open(day,minute,slot)}/>;
    })])}
   </div></div>}
  </section>
 </div>;
}
