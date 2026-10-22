import {useState,type ReactNode} from 'react';
import {Link,useParams,useSearchParams} from 'react-router-dom';
import {Button,Icon,type IconName} from '../../ui';
import {useActivityCommand} from './api';
import {EventsTabs} from './EventsTabs';
import {EventTile,PlacesDot,PointsPill} from './EventTile';
import {awaitingCoordinator,type AssignmentParticipation} from './participationApi';
import {bestNeed,eventDay,eventIcon,eventTime,eventUntil,eventWhen,eventWeekend,feedRange,needMultiplier,placesFor,toneFor,useEventFeed,useVolunteerEvent,type EventCard,type EventDetail,type EventNeed} from './eventsApi';
import {ReasonPick,reasonText} from './OwnAssignment';
import './events.css';
import {firstNameOf,initialsOf} from '../../ui/names';

const filters=[['all','Все'],['weekend','Выходные'],['weekday','Будни'],['online','Онлайн']] as const;
type Command=ReturnType<typeof useActivityCommand>;
type Done={card:EventCard;id:string;version:number;status:string};
const key=()=>crypto.randomUUID();

function matches(card:EventCard,filter:string){return filter==='all'||(filter==='online'?card.format==='online':card.format!=='online'&&(filter==='weekend')===eventWeekend(card))}
const active=(mine:EventCard['my_assignment'])=>mine&&['invited','confirmed'].includes(mine.status)?mine:undefined;

export {EventTile,PlacesDot,PointsPill};

function HeroCard({calm,eyebrow,title,sub,icon,children}:{calm?:boolean;eyebrow:string;title:string;sub:ReactNode;icon:IconName;children:ReactNode}){
 return <section className={`card-hero${calm?' calm':''}`}><div className="hero-grid"><div className="hero-copy">
  <p className="eyebrow">{eyebrow}</p><h2 className="hero-title">{title}</h2><p className="hero-sub">{sub}</p>{children}
 </div><span className="hero-art" aria-hidden="true"><Icon name={icon}/></span></div></section>;
}
const CommandError=({command}:{command:Command})=>command.isError?<p role="alert" className="event-error">{command.error.message}</p>:null;

function LockedHero({reason}:{reason?:string|null}){
 return reason==='volunteer_paused'
  ?<HeroCard calm eyebrow="Запись пока закрыта" title="Участие на паузе" sub="Возобнови участие в профиле, и запись снова откроется." icon="lock"><div className="actions"><Link className="btn btn-primary btn-lg" to="/profile">Открыть профиль</Link></div></HeroCard>
  :<HeroCard calm eyebrow="Запись откроется после знакомства" title="Одна встреча с координатором" sub="Она нужна один раз, а не перед каждым занятием. После неё можно записываться на любые мероприятия." icon="lock"><div className="actions"><Link className="btn btn-primary btn-lg" to="/interviews">Выбрать время встречи</Link></div></HeroCard>;
}

function FeedHero({card,command,onDone}:{card:EventCard;command:Command;onDone:(done:Done)=>void}){
 const need=bestNeed(card);
 const signUp=(need:EventNeed)=>void command.mutateAsync({path:`/staffing-needs/${need.id}/sign-up`,body:{expected_version:need.version,message:''},key:key()})
  .then(row=>{const item=row as AssignmentParticipation;onDone({card,id:item.id,version:item.version,status:item.status})}).catch(()=>{});
 return <HeroCard eyebrow="Лучше всего подходит тебе" title={card.title} sub={`${eventDay(card)}, ${eventTime(card)}${card.location?`, ${card.location}`:''}`} icon={eventIcon(card)}>
  <div className="actions">{need?.allowed_actions.includes('sign-up')&&<Button size="lg" loading={command.isPending} onClick={()=>signUp(need)}>Записаться</Button>}<Link className="btn btn-secondary btn-lg" to={`/events/${card.occurrence_id}`}>Подробнее</Link></div>
  <CommandError command={command}/>
 </HeroCard>;
}

function DoneHero({done,command,onCancelled}:{done:Done;command:Command;onCancelled:()=>void}){
 const confirmed=done.status==='confirmed';
 const cancel=()=>void command.mutateAsync({path:`/assignments/${done.id}/cancel`,body:{expected_version:done.version,reason:''},key:key()}).then(onCancelled).catch(()=>{});
 return <HeroCard eyebrow={confirmed?'Место за тобой':'Ждёт ответа координатора'} title={done.card.title} icon={confirmed?'check':'clock'}
  sub={`${eventWhen(done.card)}. Добавили в «Мои занятия».`}>
  <div className="actions">{confirmed?<Link className="btn btn-primary btn-lg" to={`/my/assignments/${done.id}/preparation`}>Подготовиться</Link>:<Link className="btn btn-secondary btn-lg" to={`/my/assignments/${done.id}`}>Открыть заявку</Link>}
   <Button variant="ghost" size="lg" loading={command.isPending} onClick={cancel}>{confirmed?'Отменить запись':'Отменить заявку'}</Button></div>
  <CommandError command={command}/>
 </HeroCard>;
}

export function EventsFeedPage(){
 const [params,setParams]=useSearchParams();const filter=filters.some(([value])=>value===params.get('when'))?params.get('when')!:'all';
 const {from,to}=feedRange();const feed=useEventFeed(from,to);const command=useActivityCommand();
 const [why,setWhy]=useState(false),[showFull,setShowFull]=useState(false),[done,setDone]=useState<Done|null>(null);
 const all=feed.data?.items??[];
 // The hero is the server's first open pick; the chips filter only the grid below it, as on the canvas.
 const hero=feed.data?.can_sign_up&&!done?all.find(card=>!card.full&&!card.conflict):undefined;
 const shown=all.filter(card=>card.occurrence_id!==hero?.occurrence_id&&card.occurrence_id!==done?.card.occurrence_id&&matches(card,filter));
 const rest=[...shown.filter(card=>!card.full&&!card.conflict),...shown.filter(card=>!card.full&&card.conflict)],closed=shown.filter(card=>card.full);
 const pick=(value:string)=>setParams(p=>{if(value==='all')p.delete('when');else p.set('when',value);return p});
 const withHero=!!(done||hero||(feed.data&&!feed.data.can_sign_up));
 return <div className="events-page">
  <div className="page-head"><h1 className="h1">Мероприятия</h1></div>
  <EventsTabs/>
  {feed.isPending?<section className="card-hero calm"><p className="hero-sub" role="status">Подбираем мероприятия…</p></section>
  :feed.isError?<div className="card action-card"><p role="alert">{feed.error.message}</p><div className="actions"><Button onClick={()=>void feed.refetch()}>Повторить</Button></div></div>:<>
   {done?<DoneHero done={done} command={command} onCancelled={()=>setDone(null)}/>:!feed.data.can_sign_up?<LockedHero reason={feed.data.locked_reason}/>:hero&&<FeedHero card={hero} command={command} onDone={setDone}/>}
   <section className="sec">
    <div className="sec-head"><h2 className="h2">{withHero?'Ещё подходят':'Ближайшие мероприятия'}</h2>
     <div className="ev-tools">
      <Button variant="ghost" size="sm" aria-expanded={why} onClick={()=>setWhy(!why)}>Почему так</Button>
      <div className="chips" role="group" aria-label="Когда">{filters.map(([value,label])=><button key={value} type="button" className={`chip${filter===value?' is-on':''}`} aria-pressed={filter===value} onClick={()=>pick(value)}>{label}</button>)}</div>
     </div>
    </div>
    {why&&<div className="card-soft ev-why"><p className="p">Выше то, что совпадает с твоей анкетой: интересы, удобные дни и группы, где ты уже помогаешь. Если места закончились, мероприятие опускается вниз. Интересы и время можно поменять в <Link to="/profile">профиле</Link>.</p></div>}
    {rest.length?<div className="grid-3">{rest.map(card=><EventTile key={card.occurrence_id} card={card} arrow={false}/>)}</div>
     :<div className="card action-card"><h3 className="h3">{filter!=='all'?'Здесь пока ничего нет':withHero?'Других мероприятий пока нет':'Пока нет подходящих мероприятий'}</h3>{filter!=='all'&&<div className="actions"><Button variant="secondary" onClick={()=>pick('all')}>Показать все</Button></div>}</div>}
   </section>
   {closed.length>0&&<section className="sec">
    <div className="sec-head"><h2 className="h2">Мест уже нет</h2><Button variant="secondary" size="sm" aria-expanded={showFull} onClick={()=>setShowFull(!showFull)}>{showFull?'Скрыть':`Показать (${closed.length})`}</Button></div>
    {showFull&&<div className="grid-3">{closed.map(card=><EventTile key={card.occurrence_id} card={card}/>)}</div>}
   </section>}
  </>}
 </div>;
}

function heroState(event:EventDetail,need:EventNeed|undefined){
 const mine=active(event.my_assignment);
 if(mine?.status==='confirmed')return {eyebrow:'Место за тобой',kind:'confirmed'} as const;
 // Self sign-ups and reserve places always wait for the coordinator; only an invitation is answered by the volunteer.
 if(mine?.status==='invited'){
  if(awaitingCoordinator(mine))return mine.origin==='reserve'?{eyebrow:'Освободилось место из резерва',kind:'requested',note:'Координатор подтвердит участие.'} as const:{eyebrow:'Ждёт ответа координатора',kind:'requested'} as const;
  return {eyebrow:'Тебя приглашают',kind:'invited'} as const;}
 if(event.status!=='scheduled'||Date.parse(event.starts_at)<=Date.now())return {eyebrow:event.status==='cancelled'?'Занятие отменено':'Занятие уже прошло',kind:'closed'} as const;
 if(!event.can_sign_up)return {eyebrow:event.locked_reason==='volunteer_paused'?'Запись пока закрыта':'Запись откроется после знакомства',kind:'locked'} as const;
 if(event.conflict)return {eyebrow:'В это время у тебя другое занятие',kind:'conflict'} as const;
 if(event.my_reserve?.state==='waiting')return {eyebrow:'Ты в резерве',kind:'reserve'} as const;
 if(need&&need.missing===0)return {eyebrow:'Все места заняты',kind:'full'} as const;
 return {eyebrow:'Есть места',kind:'open'} as const;
}
const personTones=['','ph-b','ph-g','ph-v'];
const initials=(name:string)=>initialsOf(name);
/** «Записаться: ассистент педагога» keeps abbreviations such as «SMM» as they are. */
const roleName=(title:string)=>title.length>1&&title[1]===title[1].toLowerCase()?title[0].toLowerCase()+title.slice(1):title;

export function VolunteerEventPage(){
 const {id}=useParams();const detail=useVolunteerEvent(id);const command=useActivityCommand();const [selected,setSelected]=useState<string>();const [asking,setAsking]=useState(false),[reason,setReason]=useState('');
 const mine=active(detail.data?.my_assignment);
 if(detail.isPending)return <div className="event-page"><p role="status">Загружаем мероприятие…</p></div>;
 if(detail.isError)return <div className="event-page"><Link className="back" to="/events"><Icon name="chevron-left"/>Все мероприятия</Link><div className="card action-card"><p role="alert">{detail.error.message}</p><div className="actions"><Button onClick={()=>void detail.refetch()}>Повторить</Button></div></div></div>;
 const event=detail.data;
 const need=event.needs.find(row=>row.id===(mine?.staffing_need_id??selected??event.best_need_id))??event.needs[0];
 const state=heroState(event,need);const reserve=event.my_reserve;
 const run=(path:string,body:object)=>void command.mutateAsync({path,body,key:key()}).then(()=>{setAsking(false);setReason('')}).catch(()=>{});
 const otherDate=event.other_dates.length>0&&<a className="btn btn-secondary btn-lg" href="#event-dates">Другая дата</a>;
 // The volunteer's own readiness per requirement; without it every item is still to do.
 const prep=need?.readiness?.length?need.readiness:(need?.preparation_requirements??[]).map(req=>({...req,state:'pending' as const}));
 const contacts=event.contacts??[];
 return <div className="event-page">
  <Link className="back" to="/events"><Icon name="chevron-left"/>Все мероприятия</Link>
  <div className="page-head"><h1 className="h1">{event.title}</h1></div>
  <section className="card-hero" style={{background:toneFor(event.title).tint}}><div className="hero-grid"><div className="hero-copy">
   <p className="eyebrow">{asking&&state.kind==='invited'?'Не сможешь прийти?':state.eyebrow}</p>
   <h2 className="hero-when">{eventWhen(event)}</h2>
   <p className="hero-sub">{asking?'Выбери причину — координатор поймёт, искать ли замену':eventUntil(event)}</p>
   {'note' in state&&<p className="hero-sub">{state.note}</p>}
   {state.kind==='open'&&<div className="actions">{need?.allowed_actions.includes('sign-up')&&<Button size="lg" loading={command.isPending} onClick={()=>run(`/staffing-needs/${need.id}/sign-up`,{expected_version:need.version,message:''})}>Записаться: {roleName(need.role_title)}</Button>}{otherDate}</div>}
   {state.kind==='full'&&<div className="actions">{need?.allowed_actions.includes('reserve')&&<Button size="lg" loading={command.isPending} onClick={()=>run(`/staffing-needs/${need.id}/reserve`,{expected_version:need.version})}>Встать в резерв</Button>}{otherDate}</div>}
   {state.kind==='reserve'&&reserve&&<div className="hero-note"><span className="strong">{reserve.position?`Место в резерве: ${reserve.position}.`:'Ты в резерве.'} Если освободится, напишем, а участие подтвердит координатор.</span>{reserve.allowed_actions.includes('leave')&&<Button variant="ghost" size="sm" loading={command.isPending} onClick={()=>run(`/reserves/${reserve.id}/leave`,{expected_version:reserve.version})}>Выйти из резерва</Button>}</div>}
   {state.kind==='confirmed'&&mine&&<div className="actions"><Link className="btn btn-primary btn-lg" to={`/my/assignments/${mine.id}/preparation`}>Подготовиться</Link><Button variant="ghost" size="lg" loading={command.isPending} onClick={()=>run(`/assignments/${mine.id}/cancel`,{expected_version:mine.version,reason:''})}>Отменить запись</Button></div>}
   {state.kind==='invited'&&mine&&(asking?<><ReasonPick value={reason} onChange={setReason}/><div className="actions"><Button size="lg" aria-disabled={!reason} loading={command.isPending} onClick={()=>{if(reason)run(`/assignments/${mine.id}/decline`,{expected_version:mine.version,reason:reasonText(reason)})}}>Сообщить координатору</Button><Button variant="ghost" size="lg" disabled={command.isPending} onClick={()=>run(`/assignments/${mine.id}/confirm`,{expected_version:mine.version})}>Я приду</Button></div></>
    :<div className="actions"><Button size="lg" loading={command.isPending} onClick={()=>run(`/assignments/${mine.id}/confirm`,{expected_version:mine.version})}>Я приду</Button><Button variant="secondary" size="lg" disabled={command.isPending} onClick={()=>setAsking(true)}>Не смогу</Button></div>)}
   {state.kind==='requested'&&mine&&<div className="actions"><Link className="btn btn-secondary btn-lg" to={`/my/assignments/${mine.id}`}>Открыть заявку</Link><Button variant="ghost" size="lg" loading={command.isPending} onClick={()=>run(`/assignments/${mine.id}/cancel`,{expected_version:mine.version,reason:''})}>{mine.origin==='reserve'?'Не смогу':'Отменить заявку'}</Button></div>}
   {state.kind==='locked'&&<div className="actions">{event.locked_reason==='volunteer_paused'?<Link className="btn btn-primary btn-lg" to="/profile">Открыть профиль</Link>:<Link className="btn btn-primary btn-lg" to="/interviews">Выбрать время встречи</Link>}</div>}
   {state.kind==='conflict'&&<div className="actions"><Link className="btn btn-secondary btn-lg" to="/my/schedule">Мои занятия</Link></div>}
   <CommandError command={command}/>
  </div><span className="hero-art" aria-hidden="true"><Icon name={eventIcon(event)}/></span></div></section>

  {event.needs.length>0&&<section className="sec"><div className="sec-head"><h2 className="h2">Чем помочь</h2></div><div className="grid-2">
   {event.needs.map(row=>{const on=row.id===need?.id;const task=row.task;
    return <button key={row.id} type="button" className={`role-pick${on?' is-on':''}`} aria-pressed={on} aria-disabled={mine?true:undefined} onClick={()=>{if(!mine)setSelected(row.id)}}>
     <span className="role-top"><span className="h3">{row.role_title}</span><span className="role-mark" aria-hidden="true"><Icon name="check"/></span></span>
     {task&&<span className="p">{task}</span>}
     <span className="role-foot"><PlacesDot places={placesFor(row.missing)}/><PointsPill value={needMultiplier(row)}/></span>
    </button>;})}
  </div></section>}

  {event.other_dates.length>0&&<section className="sec" id="event-dates"><div className="sec-head"><h2 className="h2">Другие даты</h2></div><div className="chips">
   {event.other_dates.map(date=><Link key={date.occurrence_id} className={`chip${date.full&&!date.mine?' is-off':''}`} to={`/events/${date.occurrence_id}`}>{eventDay({...date,timezone:event.timezone})}{date.mine?', ты идёшь':date.full?', мест нет':''}</Link>)}
  </div></section>}

  <section className="sec"><div className="grid-3">
   {event.audience&&<div className="card action-card"><h2 className="h3">Кого ждём</h2><p className="p">{event.audience}</p></div>}
   <div className="card action-card ev-info"><h2 className="h3">Перед выходом</h2>{prep.length?<div className="rows">{prep.map(req=>{const ok=req.state==='fulfilled';return <div className="rowi" key={req.key}>
    <span className={`st ${ok?'st-ok':'st-off'}`} aria-hidden="true"><Icon name="check"/></span><span>{ok&&<span className="sr-only">Готово: </span>}{req.title}{req.level==='recommended'?', по желанию':''}</span>
   </div>;})}</div>:<p className="p">Дополнительная подготовка не нужна.</p>}</div>
   {contacts.length>0&&<div className="card action-card ev-info"><h2 className="h3">Команда</h2><div className="rows">{contacts.map((person,index)=><div className="rowi" key={`${person.role}:${person.display_name}`}>
    <span className={`ph ph-sm ${personTones[index%personTones.length]}`} aria-hidden="true">{initials(person.display_name)}</span><span>{firstNameOf(person.display_name)||person.display_name}, {person.role.toLowerCase()}</span>
   </div>)}</div></div>}
  </div></section>
 </div>;
}
