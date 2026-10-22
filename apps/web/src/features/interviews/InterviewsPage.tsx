import {appResourceUrl} from '../../basePath';
import {useEffect,useRef,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {Button,Card,Dialog,Field,Textarea,Segmented,LoadingState,ErrorState,EmptyState,Icon,SectionTabs,cx} from '../../ui';
import {volunteersTabs} from '../../app/sectionTabs';
import {Booking,StaffBooking,meetingFormat,useInterviews,useInterviewCommand} from './api';
import {BookingPicker} from './BookingPicker';
import {StaffInterviewPanel,initials,isOnline,resultOf,resultWord,toneOf} from './StaffInterviewPanel';
import {addDays,capitalize,dateLabel,mskDay,timeLabel,today,weekdayName} from './date';
import './interviews.css';
const status:Record<string,string>={booked:'Назначена',completed:'Состоялась',cancelled:'Отменена',missed:'Не пришёл'};
/** Candidate dialog «Встреча с координатором»; staff open the side panel instead. */
export function InterviewDetails({booking,onClose}:{booking:Booking;onClose:()=>void}){
 const [action,setAction]=useState(''),[reason,setReason]=useState('');
 const command=useInterviewCommand();
 const send=(path:string,body:unknown)=>command.mutate({path:`/interviews/${booking.id}/${path}`,body},{onSuccess:onClose});
 return <Dialog open onClose={onClose} title="Встреча с координатором"><div className="iv-details"><p className="iv-kicker">{status[booking.status]}</p><h3>{dateLabel(booking.starts_at)}, {timeLabel(booking.starts_at)}–{timeLabel(booking.ends_at)}</h3><p>{meetingFormat}</p>{booking.join_url&&<a className="btn btn-secondary" href={appResourceUrl(booking.join_url)} target="_blank" rel="noreferrer">Открыть встречу</a>}
 {booking.cancel_reason&&<p>Причина отмены: {booking.cancel_reason}</p>}
 {booking.result&&<Card tone="soft"><h3>{booking.result.outcome as string}</h3><p>{booking.result.public_agreement as string}</p>{booking.result.next_contact_date!=null&&<p>Следующий контакт: {String(booking.result.next_contact_date)}</p>}</Card>}
 {booking.status==='booked'&&!action&&<div className="iv-actions"><Button variant="secondary" onClick={()=>setAction('move')}>Перенести</Button><Button variant="ghost" onClick={()=>setAction('cancel')}>Отменить встречу</Button></div>}
 {action==='move'&&<BookingPicker embedded booking={booking} applicationId={booking.application_id} onBooked={onClose} onClose={()=>setAction('')}/>}
 {action==='cancel'&&<><Field label="Причина отмены"><Textarea value={reason} onChange={e=>setReason(e.target.value)}/></Field><div className="iv-actions"><Button variant="danger" disabled={!reason.trim()||command.isPending} onClick={()=>send('cancel',{expected_version:booking.version,reason})}>Да, отменить запись</Button><Button variant="ghost" onClick={()=>setAction('')}>Оставить встречу</Button></div></>}
 {command.error&&<p role="alert" className="iv-error">{command.error.message}</p>}
 <details><summary>История встречи</summary>{(booking.events||[]).map((e,i)=><p key={i}>{({booked:'Встреча назначена',rescheduled:'Встреча перенесена',cancelled:'Встреча отменена',completed:'Встреча состоялась',missed:'Не пришёл',result_updated:'Итог встречи изменён'} as Record<string,string>)[String(e.kind)]||String(e.kind)}, {dateLabel(String(e.created_at))}</p>)}</details>
 </div></Dialog>;
}

const ROWS=4,GROUPS=5;
const dayTitle=(day:string)=>{const now=today();if(day===now)return 'Сегодня';if(day===addDays(now,1))return `Завтра, ${weekdayName(day)}`;return capitalize(new Intl.DateTimeFormat('ru-RU',{weekday:'long',day:'numeric',month:'long',timeZone:'UTC'}).format(new Date(`${day}T12:00:00Z`)));};
/** Past means finished, or a booking left from an earlier day; today's interviews stay upcoming until an outcome is saved. */
const isPast=(b:StaffBooking)=>b.status!=='booked'||mskDay(b.starts_at)<today();

function RowStatus({booking}:{booking:StaffBooking}){
 if(isPast(booking)){const code=resultOf(booking);return <span className={cx('dot',code==='fit'&&'dot-green',code==='more'&&'dot-yellow',!code&&'dot-orange')}>{resultWord(code)}</span>;}
 return booking.confirmed===false?<span className="dot dot-orange iv-wait">ждём ответа</span>:<span className="dot dot-green"><span className="sr-only">Кандидат подтвердил</span></span>;
}

/** Staff list of interviews by day with the selected one open in a side panel (?booking=). */
export function InterviewsPage(){
 const query=useInterviews(true),[search,setSearch]=useSearchParams(),[openGroups,setOpenGroups]=useState<string[]>([]),[allGroups,setAllGroups]=useState(false),panel=useRef<HTMLDivElement>(null);
 const bookings=(query.data??[]) as StaffBooking[],now=Date.now();
 const byCandidate=search.get('candidate')?bookings.filter(b=>b.application_id===search.get('candidate')):[];
 const selected=bookings.find(b=>b.id===search.get('booking'))??byCandidate.find(b=>b.status==='booked')??byCandidate.at(-1);
 const period=search.get('period')==='past'||(!search.get('period')&&selected&&isPast(selected))?'past':'up';
 // A cancelled future time is free again; it is not part of either list.
 const list=bookings.filter(b=>(b.status!=='cancelled'||new Date(b.starts_at).getTime()<now)&&(period==='past')===isPast(b));
 const days=new Map<string,StaffBooking[]>();
 [...list].sort((a,b)=>a.starts_at.localeCompare(b.starts_at)).forEach(b=>{const d=mskDay(b.starts_at);days.set(d,[...(days.get(d)??[]),b]);});
 const groups=[...days.entries()].sort(([a],[b])=>period==='past'?b.localeCompare(a):a.localeCompare(b)),shownGroups=allGroups?groups:groups.slice(0,GROUPS);
 const update=(change:(next:URLSearchParams)=>void)=>setSearch(old=>{const next=new URLSearchParams(old);change(next);return next;},{replace:true});
 const pick=(id:string)=>update(next=>{next.delete('candidate');if(selected?.id===id)next.delete('booking');else next.set('booking',id);});
 const close=()=>update(next=>{next.delete('booking');next.delete('candidate');});
 useEffect(()=>{if(selected)panel.current?.scrollIntoView?.({block:'nearest'});},[selected?.id]);
 return <div className="iv-staff">
  <SectionTabs label="Волонтёры" tabs={volunteersTabs} actions={<>
   <Segmented label="Период" value={period} onChange={v=>{update(next=>{next.set('period',v);next.delete('booking');next.delete('candidate');});setAllGroups(false);setOpenGroups([]);}} options={[{value:'up',label:'Предстоящие'},{value:'past',label:'Прошедшие'}]}/>
   <Link className="btn btn-secondary" to="/fund/interviews/availability"><Icon name="calendar"/>Свободные слоты</Link>
  </>}/>
  <div className="iv-split">
   <div className="iv-main">
    {query.isLoading?<LoadingState/>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:!groups.length?<EmptyState title={period==='past'?'Прошедших собеседований пока нет':'Предстоящих собеседований нет'} description={period==='past'?'Здесь появятся собеседования с итогами.':'Кандидаты выберут время из свободных слотов.'}/>:<>
     {shownGroups.map(([day,items])=>{const expanded=openGroups.includes(day),rows=expanded?items:items.slice(0,ROWS);return <section key={day} className="iv-day-group" aria-labelledby={`iv-day-${day}`}>
      <h2 className="iv-day-title" id={`iv-day-${day}`}>{dayTitle(day)}</h2>
      <div className="iv-rows">
       {rows.map(b=>{const on=selected?.id===b.id,online=isOnline(b);return <button key={b.id} type="button" className={cx('iv-row',on&&'is-on')} aria-pressed={on} onClick={()=>pick(b.id)}>
        <span className="iv-time">{timeLabel(b.starts_at)}</span>
        <span className="iv-person"><span className={cx('iv-ph iv-ph-sm',toneOf(b.application_id))} aria-hidden="true">{initials(b.candidate_name)}</span><span className="iv-person-name">{b.candidate_name}</span></span>
        <span className="iv-fmt"><Icon name={online?'video':'pin'}/>{online?'Онлайн':b.venue}</span>
        <RowStatus booking={b}/>
       </button>;})}
       {items.length>ROWS&&!expanded&&<button type="button" className="iv-more" onClick={()=>setOpenGroups(old=>[...old,day])}>Показать все</button>}
      </div>
     </section>;})}
     {groups.length>GROUPS&&!allGroups&&<Button variant="ghost" className="iv-more-days" onClick={()=>setAllGroups(true)}>Показать все</Button>}
    </>}
   </div>
   {selected&&<div ref={panel} className="iv-side"><StaffInterviewPanel key={selected.id} booking={selected} onClose={close}/></div>}
  </div>
 </div>;
}

export function CandidateInterviewsPage(){
 const query=useInterviews(),[picker,setPicker]=useState(false),[selected,setSelected]=useState<string|null>(null);
 const bookings=query.data||[],active=bookings.find(b=>b.status==='booked'),current=bookings.find(b=>b.id===selected);
 return <div className="iv-page"><h1>Встреча с координатором</h1>{query.isLoading?<LoadingState/>:query.error?<p role="alert">{query.error.message}</p>:<>
 <Card tone="hero" className="iv-hero"><div><p className="iv-kicker">Следующий шаг</p><h2>{active?`${dateLabel(active.starts_at)}, ${timeLabel(active.starts_at)}`:'Давайте познакомимся'}</h2><p>{active?meetingFormat:'Выберите удобное время для разговора. На встрече можно обсудить вопросы о волонтёрстве.'}</p><Button size="lg" onClick={()=>active?setSelected(active.id):setPicker(true)}>{active?'Открыть встречу':'Выбрать время'}</Button></div><div className="iv-calendar-art" aria-hidden="true"><Icon name="calendar"/></div></Card>
 {picker&&!active&&<BookingPicker onBooked={()=>setPicker(false)} onClose={()=>setPicker(false)}/>}
 <Card tone="soft" className="action-card"><h2>Познакомиться с фондом</h2><p>Знакомство и запись на встречу доступны параллельно.</p><div className="actions"><Link className="btn btn-secondary" to="/onboarding">Открыть знакомство</Link></div></Card>
 {bookings.some(b=>b.status!=='booked')&&<section><h2>История встреч</h2>{bookings.filter(b=>b.status!=='booked').map(b=><button className="iv-booking" key={b.id} onClick={()=>setSelected(b.id)}><span className="iv-grow">{dateLabel(b.starts_at)}, {timeLabel(b.starts_at)}</span><span>{status[b.status]}</span></button>)}</section>}
 {current&&<InterviewDetails key={current.id+current.version} booking={current} onClose={()=>setSelected(null)}/>}</>}
 </div>;
}
