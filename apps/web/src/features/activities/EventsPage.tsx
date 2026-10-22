import {useState} from 'react';
import {Link,useParams,useSearchParams} from 'react-router-dom';
import {Button,Card,Icon,Segmented} from '../../ui';
import {useActivityCommand} from './api';
import {bestNeed,eventDay,eventIcon,eventTime,eventWeekend,feedRange,placesLabel,useEventFeed,useVolunteerEvent,type EventCard,type EventDetail,type EventNeed} from './eventsApi';
import './activities.css';
import './events.css';
const arts=['art-y','art-o','art-b','art-g','art-v','art-p'];
const filters=[{value:'all',label:'Все'},{value:'weekend',label:'Выходные'},{value:'weekday',label:'Будни'},{value:'online',label:'Онлайн'}];
type Done={card:EventCard;status:string;id:string};

function matches(card:EventCard,filter:string){return filter==='all'||(filter==='online'?card.format==='online':card.format!=='online'&&(filter==='weekend')===eventWeekend(card))}

export function EventTile({card,index}:{card:EventCard;index:number}){
 return <Link className="card match home-invitation event-tile" to={`/events/${card.occurrence_id}`}>
  <span className={`art ${arts[index%arts.length]}`} aria-hidden="true"><Icon name={eventIcon(card)}/></span>
  <span><span className="h3">{card.title}</span><span className="p home-line">{eventDay(card)}, {eventTime(card)}</span>{card.location&&<span className="meta home-line">{card.location}</span>}</span>
  <span className="match-foot"><span className="event-places">{placesLabel(card)}</span><Icon name="arrow-right"/></span>
 </Link>;
}

export function WhyRanking(){return <Card className="events-why"><p className="p">Сверху то, что ближе тебе:</p><ul><li>роль подходит к твоей анкете;</li><li>группы, где ты уже помогаешь;</li><li>время, когда тебе удобно.</li></ul><p className="p">Если все места заняты, мероприятие уходит в конец.</p></Card>}

function signUp(command:ReturnType<typeof useActivityCommand>,need:EventNeed){
 return command.mutateAsync({path:`/staffing-needs/${need.id}/sign-up`,body:{expected_version:need.version,message:''},key:crypto.randomUUID()});
}

function LockedHero({reason,message}:{reason?:string|null;message?:string|null}){
 return <Card tone="hero"><div className="hero-grid"><div className="hero-copy"><p className="eyebrow">Запись пока закрыта</p><h2 className="hero-title">{message??'Записаться пока нельзя'}</h2>
  <div className="actions">{reason==='volunteer_paused'?<Link className="btn btn-primary btn-lg" to="/profile">Открыть профиль</Link>:<Link className="btn btn-primary btn-lg" to="/interviews">Встреча с координатором</Link>}</div>
 </div><span className="hero-art" aria-hidden="true"><Icon name="calendar"/></span></div></Card>;
}

function FeedHero({card,command,onDone}:{card:EventCard;command:ReturnType<typeof useActivityCommand>;onDone:(done:Done)=>void}){
 const need=bestNeed(card);const can=need?.allowed_actions.includes('sign-up');
 return <Card tone="hero"><div className="hero-grid"><div className="hero-copy">
  <p className="eyebrow">Лучше всего подходит тебе</p><h2 className="hero-title">{card.title}</h2>
  <p className="lead">{eventDay(card)}, {eventTime(card)}{card.location?`, ${card.location}`:''}</p>
  {need&&<p className="event-hero-places">{need.role_title}: записались {need.confirmed} из {need.required}</p>}
  <div className="actions">{can&&need&&<Button size="lg" loading={command.isPending} onClick={()=>void signUp(command,need).then(row=>onDone({card,status:'status' in row?String(row.status):'',id:row.id})).catch(()=>{})}>Записаться</Button>}<Link className="btn btn-secondary btn-lg" to={`/events/${card.occurrence_id}`}>Подробнее</Link></div>
  {command.isError&&<p role="alert" className="event-error">{command.error.message}</p>}
 </div><span className="hero-art" aria-hidden="true"><Icon name={eventIcon(card)}/></span></div></Card>;
}

function DoneHero({done}:{done:Done}){
 const confirmed=done.status==='confirmed';
 return <Card tone="hero"><div className="hero-grid"><div className="hero-copy">
  <p className="eyebrow">{confirmed?'Место за тобой':'Заявка у координатора'}</p><h2 className="hero-title">{done.card.title}</h2>
  <p className="lead">{eventDay(done.card)}, {eventTime(done.card)}{done.card.location?`, ${done.card.location}`:''}</p>
  {!confirmed&&<p className="event-hero-places">Координатор подтвердит участие, ответ придёт в сообщения.</p>}
  <div className="actions">{confirmed?<Link className="btn btn-primary btn-lg" to={`/my/assignments/${done.id}/preparation`}>Подготовиться к выходу</Link>:<Link className="btn btn-primary btn-lg" to={`/my/assignments/${done.id}`}>Открыть участие</Link>}</div>
 </div><span className="hero-art" aria-hidden="true"><Icon name="check"/></span></div></Card>;
}

export function EventsFeedPage(){
 const [params,setParams]=useSearchParams();const filter=filters.some(f=>f.value===params.get('when'))?params.get('when')!:'all';
 const {from,to}=feedRange();const feed=useEventFeed(from,to);const command=useActivityCommand();
 const [why,setWhy]=useState(false),[showFull,setShowFull]=useState(false),[done,setDone]=useState<Done|null>(null);
 const items=(feed.data?.items??[]).filter(card=>matches(card,filter));
 const open=items.filter(card=>!card.full&&!card.conflict),closed=items.filter(card=>card.full||card.conflict);
 const hero=feed.data?.can_sign_up&&!done?open[0]:undefined;const rest=hero?open.slice(1):open;
 return <div className="activities events-feed">
  <div className="head"><h1 className="h1">Мероприятия</h1><Link to="/opportunities">Направления фонда</Link></div>
  {feed.isPending?<Card tone="hero"><p role="status">Подбираем мероприятия…</p></Card>:feed.isError?<Card className="action-card"><p role="alert">{feed.error.message}</p><div className="actions"><Button onClick={()=>void feed.refetch()}>Повторить</Button></div></Card>:<>
   {done?<DoneHero done={done}/>:!feed.data.can_sign_up?<LockedHero reason={feed.data.locked_reason} message={feed.data.locked_message}/>:hero&&<FeedHero card={hero} command={command} onDone={setDone}/>}
   <section className="section">
    <div className="section-head"><h2 className="h2">{hero||done?'Ещё подходят':'Ближайшие мероприятия'}</h2><Button variant="ghost" size="sm" aria-expanded={why} onClick={()=>setWhy(!why)}>Почему так</Button></div>
    {why&&<WhyRanking/>}
    <div className="events-tools"><Segmented label="Когда" value={filter} onChange={value=>setParams(p=>{if(value==='all')p.delete('when');else p.set('when',value);return p})} options={filters}/></div>
    {rest.length?<div className="activity-catalog events-grid">{rest.map((card,index)=><EventTile key={card.occurrence_id} card={card} index={index+1}/>)}</div>
     :<Card className="action-card"><h3 className="h3">{items.length?'Остальное уже в списке выше':'Пока нет подходящих мероприятий'}</h3>{filter!=='all'&&<div className="actions"><Button variant="secondary" onClick={()=>setParams({})}>Показать все</Button></div>}</Card>}
   </section>
   {closed.length>0&&<section className="section">
    <div className="section-head"><h2 className="h2">Места уже заняты</h2><Button variant="secondary" size="sm" aria-expanded={showFull} onClick={()=>setShowFull(!showFull)}>{showFull?'Скрыть':`Показать (${closed.length})`}</Button></div>
    {showFull&&<div className="activity-catalog events-grid">{closed.map((card,index)=><EventTile key={card.occurrence_id} card={card} index={index}/>)}</div>}
   </section>}
  </>}
 </div>;
}

function heroState(event:EventDetail,need:EventNeed|undefined){
 const mine=event.my_assignment;
 if(mine?.status==='confirmed')return {eyebrow:'Место за тобой',kind:'confirmed'} as const;
 if(mine?.status==='invited')return mine.origin==='self'&&!mine.approved_at&&need?.approval_policy==='coordinator'?{eyebrow:'Заявка у координатора',kind:'requested'} as const:{eyebrow:mine.origin==='reserve'?'Освободилось место':'Тебя приглашают',kind:'invited'} as const;
 if(event.status!=='scheduled'||Date.parse(event.starts_at)<=Date.now())return {eyebrow:event.status==='cancelled'?'Занятие отменено':'Занятие уже прошло',kind:'closed'} as const;
 if(!event.can_sign_up)return {eyebrow:event.locked_message??'Запись пока закрыта',kind:'locked'} as const;
 if(event.conflict)return {eyebrow:'В это время у тебя другое занятие',kind:'conflict'} as const;
 if(event.my_reserve?.state==='waiting')return {eyebrow:'Ты в резерве',kind:'reserve'} as const;
 if(need&&need.missing===0)return {eyebrow:'Все места заняты',kind:'full'} as const;
 return {eyebrow:'Есть места',kind:'open'} as const;
}

export function VolunteerEventPage(){
 const {id}=useParams();const detail=useVolunteerEvent(id);const command=useActivityCommand();const [selected,setSelected]=useState<string>();
 if(detail.isPending)return <div className="activities"><p role="status">Загружаем мероприятие…</p></div>;
 if(detail.isError)return <div className="activities"><Link className="event-back" to="/events"><Icon name="chevron-left"/>Все мероприятия</Link><Card className="action-card"><p role="alert">{detail.error.message}</p><div className="actions"><Button onClick={()=>void detail.refetch()}>Повторить</Button></div></Card></div>;
 const event=detail.data;const mine=event.my_assignment;
 const need=event.needs.find(row=>row.id===(mine?.staffing_need_id??selected??event.best_need_id))??event.needs[0];
 const state=heroState(event,need);
 const run=(path:string,body:object)=>void command.mutateAsync({path,body,key:crypto.randomUUID()}).catch(()=>{});
 return <div className="activities event-page">
  <Link className="event-back" to="/events"><Icon name="chevron-left"/>Все мероприятия</Link>
  <div className="head"><h1 className="h1">{event.title}</h1></div>
  <Card tone="hero"><div className="hero-grid"><div className="hero-copy">
   <p className="eyebrow">{state.eyebrow}</p>
   <p className="hero-when">{eventDay(event)}, {eventTime(event).split('–')[0]}</p>
   <p className="lead">До {eventTime(event).split('–')[1]}{event.location?`, ${event.location}`:''}</p>
   {need&&<p className="event-hero-places">{state.kind==='reserve'&&event.my_reserve?.position?`Ты ${event.my_reserve.position}-й в резерве. Напишем, если место освободится.`:`${need.role_title}: записались ${need.confirmed} из ${need.required}`}</p>}
   <div className="actions">
    {state.kind==='open'&&need?.allowed_actions.includes('sign-up')&&<Button size="lg" loading={command.isPending} onClick={()=>run(`/staffing-needs/${need.id}/sign-up`,{expected_version:need.version,message:''})}>Записаться</Button>}
    {state.kind==='full'&&need?.allowed_actions.includes('reserve')&&<Button size="lg" loading={command.isPending} onClick={()=>run(`/staffing-needs/${need.id}/reserve`,{expected_version:need.version})}>Встать в резерв</Button>}
    {state.kind==='reserve'&&event.my_reserve&&<Button variant="ghost" size="lg" loading={command.isPending} onClick={()=>run(`/reserves/${event.my_reserve!.id}/leave`,{expected_version:event.my_reserve!.version})}>Выйти из резерва</Button>}
    {state.kind==='confirmed'&&mine&&<><Link className="btn btn-primary btn-lg" to={`/my/assignments/${mine.id}/preparation`}>Подготовиться к выходу</Link><Link className="btn btn-ghost btn-lg" to={`/my/assignments/${mine.id}`}>Открыть участие</Link></>}
    {state.kind==='invited'&&mine&&<Link className="btn btn-primary btn-lg" to={`/my/assignments/${mine.id}`}>Ответить на приглашение</Link>}
    {state.kind==='requested'&&mine&&<Link className="btn btn-secondary btn-lg" to={`/my/assignments/${mine.id}`}>Открыть участие</Link>}
    {state.kind==='locked'&&<Link className="btn btn-primary btn-lg" to={event.locked_reason==='volunteer_paused'?'/profile':'/interviews'}>{event.locked_reason==='volunteer_paused'?'Открыть профиль':'Встреча с координатором'}</Link>}
    {state.kind==='conflict'&&<Link className="btn btn-secondary btn-lg" to="/my/schedule">Мои смены</Link>}
    {['open','full'].includes(state.kind)&&event.other_dates.length>0&&<a className="btn btn-secondary btn-lg" href="#event-dates">Другая дата</a>}
   </div>
   {command.isError&&<p role="alert" className="event-error">{command.error.message}</p>}
  </div><span className="hero-art" aria-hidden="true"><Icon name={eventIcon(event)}/></span></div></Card>

  {event.needs.length>1&&<section className="section"><div className="section-head"><h2 className="h2">Чем помочь</h2></div><div className="grid-2">
   {event.needs.map(row=><button key={row.id} type="button" className={`card event-role${row.id===need?.id?' is-on':''}`} aria-pressed={row.id===need?.id} aria-disabled={mine?true:undefined} onClick={()=>{if(!mine)setSelected(row.id)}}>
    <span className="event-role-top"><span className="h3">{row.role_title}</span><span className="event-role-mark" aria-hidden="true"><Icon name="check"/></span></span>
    {row.task&&<span className="p">{row.task}{row.approval_policy==='coordinator'?' Участие подтверждает координатор.':''}</span>}
    <span className="meta">Записались {row.confirmed} из {row.required}</span>
   </button>)}
  </div></section>}

  {event.other_dates.length>0&&<section className="section" id="event-dates"><div className="section-head"><h2 className="h2">Другие даты</h2></div><div className="chips">
   {event.other_dates.map(date=><Link key={date.occurrence_id} className="chip" to={`/events/${date.occurrence_id}`}>{eventDay({...date,timezone:event.timezone})}{date.mine?', ты идёшь':date.full?', мест нет':''}</Link>)}
  </div></section>}

  <section className="section"><div className="grid-3">
   <Card className="event-info"><h2 className="h3">Кого ждём</h2><p className="p">{event.audience||event.program||'Участники и команда фонда'}</p></Card>
   <Card className="event-info"><h2 className="h3">Перед выходом</h2>{need?.preparation_requirements.length?<ul className="event-checks">{need.preparation_requirements.map(req=><li key={req.key}><Icon name={req.level==='mandatory'?'alert':'check-circle'}/><span>{req.title}{req.level==='mandatory'?', обязательно':''}</span></li>)}</ul>:<p className="p">Дополнительная подготовка не нужна.</p>}</Card>
   {event.reasons.length>0&&<Card className="event-info"><h2 className="h3">Почему тебе подходит</h2><ul className="event-checks">{event.reasons.map(reason=><li key={reason}><Icon name="check"/><span>{reason}</span></li>)}</ul></Card>}
  </div></section>
 </div>;
}
