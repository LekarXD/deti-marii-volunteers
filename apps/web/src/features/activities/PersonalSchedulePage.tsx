import {useEffect,useState,type ReactNode} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {useQueries} from '@tanstack/react-query';
import {Button,Icon,Segmented,type IconName} from '../../ui';
import {keys} from '../../api/keys';
import {readReflection} from '../followups/api';
import {useActivityCommand} from './api';
import {useOwnReserves,usePersonalSchedule,type AssignmentParticipation,type OwnReserve} from './participationApi';
import {addDays,calendarDate,labelDate,labelTime,monday,monthRange,parseDate,today} from './calendarDates';
import {bestNeed,eventDay,feedRange,useEventFeed,type EventCard,type EventFeed} from './eventsApi';
import {EventTile,WhyCards} from './EventTile';
import {awaitingCoordinator} from './participationApi';
import {EventsTabs} from './EventsTabs';
import {Pts,ReasonPick,cap,dateOf,iconOf,isFundCancelled,low,needsAnswer,reasonText,timeRange,toneOf,whenLabel,type Tone} from './OwnAssignment';
import './schedule.css';

/** «Мероприятия → Мои занятия» from the canvas Mine.dc.html: the nearest занятие, what is ahead, open places on free days and the past. */
type Row={key:string;date:string;starts_at:string;ends_at:string;timezone:string;title:string;location:string;to:string;tone:Tone;multiplier:number;item?:AssignmentParticipation;reserve?:OwnReserve};
type Mark={label:string;cls:string};
type Done={card:EventCard;id:string;version:number;status:string};
const why='Выше то, что подходит тебе: навыки и направления из анкеты, удобное время и группы, где ты уже помогаешь.';
const weekdays=['пн','вт','ср','чт','пт','сб','вс'];

function hours(minutes:number){return `${(Math.round(minutes/6)/10).toLocaleString('ru-RU')} ч`}
function where(row:{starts_at:string;ends_at:string;timezone:string;location:string}){return `${timeRange(row)}${row.location?`, ${row.location}`:''}`}
/** Own declines, cancels and expired invitations leave the schedule; a занятие the fund cancelled stays, struck through. */
function kept(item:AssignmentParticipation){return ['invited','confirmed'].includes(item.status)||isFundCancelled(item)}
function fromAssignment(item:AssignmentParticipation,context:string,now:number):Row{
 const ready=item.status==='confirmed'&&item.occurrence_status==='scheduled'&&Date.parse(item.ends_at)>now;
 return {key:item.id,date:dateOf(item),starts_at:item.starts_at,ends_at:item.ends_at,timezone:item.timezone,title:item.title,location:item.location,tone:toneOf(item.title),multiplier:item.points_multiplier??1,item,
  to:ready?`/my/assignments/${item.id}/preparation`:`/my/assignments/${item.id}?schedule_return=${encodeURIComponent(context)}`};
}
/** Waiting reserve places from /me/reserves: a row marked «В резерве» that leads to the event. */
function reserveRows(reserves:OwnReserve[]|undefined):Row[]{return (reserves??[]).filter(row=>row.state==='waiting').map(row=>({key:`reserve:${row.reserve_id}`,date:dateOf(row),starts_at:row.starts_at,ends_at:row.ends_at,timezone:row.timezone,
 title:row.title,location:row.location,tone:toneOf(row.title),multiplier:1,to:`/events/${row.occurrence_id}`,reserve:row}))}
/** Only exceptions get a word; a confirmed занятие needs none. */
function markOf(row:Row):Mark|null{const item=row.item;if(row.reserve)return {label:'В резерве',cls:'m-res'};if(!item)return null;
 if(isFundCancelled(item))return {label:'Отменено фондом',cls:'m-off'};if(needsAnswer(item))return {label:'Ждёт ответа',cls:'m-ask'};
 if(item.status==='invited'&&awaitingCoordinator(item))return item.origin==='reserve'?{label:'Освободилось место из резерва',cls:'m-res'}:{label:'Ждёт ответа координатора',cls:'m-coord'};
 return null}
function openCards(feed:EventFeed|undefined){return (feed?.items??[]).filter(card=>!card.full&&!card.conflict&&!card.my_assignment&&!card.my_reserve)}
function useWholePeriod(query:ReturnType<typeof usePersonalSchedule>){useEffect(()=>{if(query.hasNextPage&&!query.isFetchingNextPage)void query.fetchNextPage()},[query.hasNextPage,query.isFetchingNextPage])}
function ownRows(query:ReturnType<typeof usePersonalSchedule>,context:string,now:number){return (query.data?.pages.flatMap(page=>page.items)??[]).filter(kept).map(item=>fromAssignment(item,context,now))}

function Hero({eyebrow,title,sub,big,calm,icon='calendar',children}:{eyebrow:string;title:string;sub?:string;big?:boolean;calm?:boolean;icon?:IconName;children?:ReactNode}){
 return <section className={`card-hero sch-hero${calm?' calm':''}`}><div className="hero-grid"><div className="hero-copy">
  <p className="eyebrow">{eyebrow}</p><h2 className={big?'hero-when':'hero-title'}>{title}</h2>{sub&&<p className="hero-sub">{sub}</p>}{children}
 </div><span className="hero-art" aria-hidden="true"><Icon name={icon}/></span></div></section>;
}
function CommandError({command}:{command:ReturnType<typeof useActivityCommand>}){return command.isError?<p role="alert" className="own-error">{command.error.message}</p>:null}

/** The nearest own занятие: answer the invitation, or say you cannot come and why. */
function ShiftHero({item,asking,onAsk,onSent}:{item:AssignmentParticipation;asking:boolean;onAsk:(asking:boolean)=>void;onSent:(sent:{when:string;icon:IconName})=>void}){
 const command=useActivityCommand(),[reason,setReason]=useState('');
 const answer=needsAnswer(item),when=whenLabel(item),icon=iconOf(item.title);
 const sub=`${item.location?`${item.title}, ${item.location}`:item.title}${item.role_title?`. ${item.role_title}`:''}`;
 function confirm(){void command.mutateAsync({path:`/assignments/${item.id}/confirm`,body:{expected_version:item.version},key:crypto.randomUUID()}).then(()=>onAsk(false)).catch(()=>{})}
 function send(){if(!reason)return;void command.mutateAsync({path:`/assignments/${item.id}/${item.status==='confirmed'?'cancel':'decline'}`,body:{expected_version:item.version,reason:reasonText(reason)},key:crypto.randomUUID()}).then(()=>{setReason('');onSent({when,icon})}).catch(()=>{})}
 if(asking)return <Hero big eyebrow={when} title="Не сможешь прийти?" sub="Выбери причину — координатор поймёт, искать ли замену" icon={icon}>
  <ReasonPick value={reason} onChange={setReason}/>
  <div className="actions"><Button size="lg" aria-disabled={!reason} loading={command.isPending} onClick={send}>Сообщить координатору</Button><Button variant="ghost" size="lg" disabled={command.isPending} onClick={answer?confirm:()=>onAsk(false)}>Я приду</Button></div>
  <CommandError command={command}/>
 </Hero>;
 return <Hero big eyebrow={answer?(item.origin==='invitation'?'Тебя приглашают':'Координатор согласовал участие'):'Ближайшее занятие'} title={when} sub={sub} icon={icon}>
  <div className="actions">{answer?<><Button size="lg" loading={command.isPending} onClick={confirm}>Я приду</Button>{item.allowed_actions.includes('decline')&&<Button variant="secondary" size="lg" onClick={()=>onAsk(true)}>Не смогу</Button>}</>
   :<><Link className="btn btn-primary btn-lg" to={`/my/assignments/${item.id}/preparation`}>Подготовиться</Link>{item.allowed_actions.includes('cancel')&&<Button variant="ghost" size="lg" onClick={()=>onAsk(true)}>Не смогу</Button>}</>}</div>
  <CommandError command={command}/>
 </Hero>;
}

/** No own занятия yet: the best-fitting event from the feed takes the top block. */
function PickHero({card,first,onDone}:{card:EventCard;first:boolean;onDone:(done:Done)=>void}){
 const command=useActivityCommand(),need=bestNeed(card);
 function signUp(){if(!need)return;void command.mutateAsync({path:`/staffing-needs/${need.id}/sign-up`,body:{expected_version:need.version,message:''},key:crypto.randomUUID()}).then(row=>onDone({card,id:row.id,version:row.version,status:'status' in row?String(row.status):''})).catch(()=>{})}
 return <Hero eyebrow={first?'Занятий пока нет. Лучше всего подходит тебе':'Лучше всего подходит тебе'} title={card.title} sub={`${eventDay(card)}, ${where(card)}${need?`. Нужен ${low(need.role_title)}.`:''}`} icon="search">
  <div className="actions">{need?.allowed_actions.includes('sign-up')&&<Button size="lg" loading={command.isPending} onClick={signUp}>Записаться</Button>}<Link className="btn btn-secondary btn-lg" to={`/events/${card.occurrence_id}`}>Подробнее</Link></div>
  <CommandError command={command}/>
 </Hero>;
}

function DoneHero({done,onUndo}:{done:Done;onUndo:()=>void}){
 const command=useActivityCommand(),confirmed=done.status==='confirmed';
 function undo(){void command.mutateAsync({path:`/assignments/${done.id}/${confirmed?'cancel':'decline'}`,body:{expected_version:done.version},key:crypto.randomUUID()}).then(onUndo).catch(()=>{})}
 return <Hero eyebrow={confirmed?'Место за тобой':'Ждёт ответа координатора'} title={done.card.title} sub={`${eventDay(done.card)}, ${where(done.card)}`} icon={confirmed?'check':'clock'}>
  <div className="actions">{confirmed?<Link className="btn btn-primary btn-lg" to={`/my/assignments/${done.id}/preparation`}>Подготовиться</Link>:<Link className="btn btn-secondary btn-lg" to={`/my/assignments/${done.id}`}>Подробнее</Link>}<Button variant="ghost" size="lg" loading={command.isPending} onClick={undo}>{confirmed?'Отменить запись':'Отменить заявку'}</Button></div>
  <CommandError command={command}/>
 </Hero>;
}

function LockedHero({reason}:{reason?:string|null}){const paused=reason==='volunteer_paused';
 return <Hero eyebrow="Запись пока закрыта" title={paused?'Участие на паузе':'Сначала встреча с координатором'} sub={paused?'Сними паузу в профиле, чтобы записываться на занятия.':'После встречи откроется запись на занятия.'} icon={paused?'clock':'users'}>
  <div className="actions">{paused?<Link className="btn btn-primary btn-lg" to="/profile?tab=pause">Открыть профиль</Link>:<Link className="btn btn-primary btn-lg" to="/interviews">Выбрать время встречи</Link>}</div>
 </Hero>;
}

function DayTile({date,tone}:{date:string;tone?:Tone}){return <span className={`day${tone?` ${tone}`:''}`}><b>{parseDate(date).getUTCDate()}</b><span>{labelDate(date,{weekday:'short'})}</span></span>}

function AheadRow({row}:{row:Row}){const mark=markOf(row),off=!!row.item&&isFundCancelled(row.item);
 return <Link className={`rowi${off?' is-off':''}`} to={row.to}>
  <DayTile date={row.date} tone={off?undefined:row.tone}/>
  <span className="grow"><span className="rowi-title">{row.title}</span><span className="meta">{where(row)}</span></span>
  <span className="rowi-end"><Pts value={row.multiplier}/>{mark&&<span className={`st-mark ${mark.cls}`}>{mark.label}</span>}<Icon name="chevron-right"/></span>
 </Link>;
}

function PastRow({row,canReflect}:{row:Row;canReflect:boolean}){
 const done=row.item?.attendance,minutes=done?.minutes??Math.round((Date.parse(row.ends_at)-Date.parse(row.starts_at))/60000);
 const state=done?.outcome==='absent'?'off':done?.ledger_state==='posted'?'ok':'wait';
 return <div className="rowi">
  <DayTile date={row.date}/>
  <span className="grow"><span className="rowi-title">{row.title}</span><span className="meta">{where(row)}</span></span>
  <span className="rowi-end">
   {state==='off'?<span className="hours-st"><span className="st st-off" role="img" aria-label="Отмечено неучастие"><Icon name="x"/></span>Не засчитано</span>
    :<span className="hours-st"><span className={`st st-${state}`} role="img" aria-label={state==='ok'?'Засчитано':done?'Ждёт подтверждения':'Ждёт отметки'}><Icon name={state==='ok'?'check':'clock'}/></span>{hours(minutes)}</span>}
   {canReflect&&state!=='off'&&<Link className="btn btn-secondary btn-sm" to={`/my/assignments/${row.item!.id}/reflection`}>Как прошло?</Link>}
  </span>
 </div>;
}

function PauseCard(){
 return <section className="sec"><div className="card-soft row wrap sch-pause">
  <div className="row"><span className="art art-y" aria-hidden="true"><svg className="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/></svg></span><div><h2 className="h3">Нужна пауза?</h2><p className="p">Новых приглашений не будет, место в группе сохранится</p></div></div>
  <Link className="btn btn-secondary" to="/profile?tab=pause">Поставить паузу</Link>
 </div></section>;
}

function pastMeta(item:AssignmentParticipation){const done=item.attendance;return done?.outcome==='absent'?'Прошло, без участия':done?.ledger_state==='posted'?'Прошло, часы засчитаны':'Прошло, часы ждут отметки'}

function MonthView({month,picked,onMonth,onPick,feed,reserves,context,now}:{month:string;picked:string;onMonth:(month:string)=>void;onPick:(day:string)=>void;feed:EventFeed|undefined;reserves:OwnReserve[]|undefined;context:string;now:number}){
 const range=monthRange(`${month}-01`),from=monday(range.from),to=addDays(monday(range.to),6),query=usePersonalSchedule(from,to);useWholePeriod(query);
 const todayDate=today(),rows=[...ownRows(query,context,now),...reserveRows(reserves)].sort((a,b)=>a.starts_at.localeCompare(b.starts_at));
 const days:string[]=[];for(let day=from;day<=to;day=addDays(day,1))days.push(day);
 const mine=rows.filter(row=>row.date===picked),open=picked>=todayDate?openCards(feed).filter(card=>dateOf(card)===picked):[];
 const shift=(step:number)=>{const value=parseDate(`${month}-01`);onMonth(calendarDate(new Date(Date.UTC(value.getUTCFullYear(),value.getUTCMonth()+step,1))).slice(0,7))};
 return <>
  <div className="row sch-monthnav">
   <button type="button" className="iconbtn-soft" aria-label="Предыдущий месяц" onClick={()=>shift(-1)}><Icon name="chevron-left"/></button>
   <h2 className="h2">{cap(labelDate(`${month}-01`,{month:'long',year:'numeric'}).replace(' г.',''))}</h2>
   <button type="button" className="iconbtn-soft" aria-label="Следующий месяц" onClick={()=>shift(1)}><Icon name="chevron-right"/></button>
  </div>
  {query.isError?<div className="card"><p role="alert" className="p">{query.error.message}</p><div className="actions"><Button onClick={()=>void query.refetch()}>Повторить</Button></div></div>:
  <div className="cal-wrap">
   <div>
    <div className="mcal">
     {weekdays.map(day=><span key={day} className="mcal-wd">{day}</span>)}
     {days.map(day=>{const n=parseDate(day).getUTCDate();if(day.slice(0,7)!==month)return <span key={day} className="mcal-cell out" aria-hidden="true"><span className="mcal-n">{n}</span></span>;
      const items=rows.filter(row=>row.date===day);
      return <button key={day} type="button" className={`mcal-cell${day===todayDate?' today':''}${day===picked?' picked':''}`} aria-pressed={day===picked} aria-current={day===todayDate?'date':undefined} aria-label={`${labelDate(day)}${items.length?`, занятий: ${items.length}`:''}`} onClick={()=>onPick(day)}>
       <span className="mcal-n">{n}</span>
       {items.map(row=>{const item=row.item;return <span key={row.key} className={`mcal-ev ev-${row.tone}${item&&needsAnswer(item)?' ev-ask':''}${Date.parse(row.ends_at)<=now?' ev-past':''}${item&&isFundCancelled(item)?' ev-off':''}`}>{labelTime(row.starts_at,row.timezone)} {row.title.split(':')[0]}</span>})}
      </button>})}
    </div>
    <div className="legend"><span><i/>Твои занятия</span><span><i className="l-ask"/>Ждут ответа</span><span><i className="l-past"/>Прошедшие</span></div>
   </div>
   <div className="card day-card">
    <h2 className="h3">{cap(labelDate(picked,{weekday:'long',day:'numeric',month:'long'}))}</h2>
    {query.isPending?<p className="p" role="status">Загружаем занятия…</p>:mine.length?<div className="rows">{mine.map(row=>{const item=row.item,mark=markOf(row),past=!!item&&Date.parse(row.ends_at)<=now&&!isFundCancelled(item);
     return <Link key={row.key} className={`rowi${item&&isFundCancelled(item)?' is-off':''}`} to={row.to}><span className="grow"><span className="rowi-title">{row.title}</span><span className="meta">{past?pastMeta(item!):where(row)}</span>{mark&&!past&&<span className={`st-mark ${mark.cls}`}>{mark.label}</span>}</span><Icon name="chevron-right"/></Link>})}</div>
     :<p className="p">В этот день занятий нет.</p>}
    {open.length>0&&<><h3 className="h3">Можно записаться</h3><div className="rows">{open.map(card=><Link key={card.occurrence_id} className="rowi" to={`/events/${card.occurrence_id}`}><span className="grow"><span className="rowi-title">{card.title}</span><span className="meta">{where(card)}</span></span><Icon name="chevron-right"/></Link>)}</div></>}
   </div>
  </div>}
 </>;
}

export function PersonalSchedulePage(){
 const [params,setParams]=useSearchParams(),todayDate=today(),now=Date.now(),context=params.toString();
 const view=['calendar','month','week'].includes(params.get('view')??'')?'calendar':'list';
 const month=/^\d{4}-\d{2}$/.test(params.get('month')??'')?params.get('month')!:todayDate.slice(0,7);
 // The list covers the recent past and the months ahead; the calendar asks for its own visible weeks.
 const query=usePersonalSchedule(addDays(todayDate,-120),addDays(todayDate,240));useWholePeriod(query);
 const feedWindow=feedRange(),feed=useEventFeed(feedWindow.from,feedWindow.to),reserves=useOwnReserves();
 const [showAll,setShowAll]=useState(false),[showPast,setShowPast]=useState(false),[showWhy,setShowWhy]=useState(false);
 const [focus,setFocus]=useState<{id:string;asking:boolean}|null>(null),[sent,setSent]=useState<{when:string;icon:IconName}|null>(null),[done,setDone]=useState<Done|null>(null);
 const rows=ownRows(query,context,now);
 const ahead=[...rows.filter(row=>Date.parse(row.ends_at)>now),...reserveRows(reserves.data?.items)].sort((a,b)=>a.starts_at.localeCompare(b.starts_at)||a.key.localeCompare(b.key));
 const past=rows.filter(row=>row.item!.status==='confirmed'&&row.item!.occurrence_status!=='cancelled'&&Date.parse(row.ends_at)<=now).sort((a,b)=>b.starts_at.localeCompare(a.starts_at));
 const candidates=ahead.flatMap(row=>row.item&&row.item.occurrence_status==='scheduled'&&(row.item.status==='confirmed'||needsAnswer(row.item))?[row.item]:[]);
 const heroItem=candidates.find(item=>item.id===focus?.id)??candidates[0];
 // Open places only on days without an own занятие.
 const busy=new Set(ahead.filter(row=>row.item&&!isFundCancelled(row.item)).map(row=>row.date));
 const cards=openCards(feed.data).filter(card=>!busy.has(dateOf(card)));
 const canSignUp=!!feed.data?.can_sign_up,paused=feed.data?.locked_reason==='volunteer_paused';
 const pick=!heroItem&&!done&&!sent&&canSignUp?cards[0]:undefined,tiles=pick?cards.slice(1,4):cards.slice(0,3);
 const reflections=useQueries({queries:(showPast?past:[]).map(row=>({queryKey:keys.detail('own-reflection',row.key),queryFn:({signal}:{signal:AbortSignal})=>readReflection(row.key,signal),staleTime:60_000}))});
 const heroDate=heroItem?dateOf(heroItem):'';
 const pickedParam=params.get('day')??'';
 const picked=/^\d{4}-\d{2}-\d{2}$/.test(pickedParam)&&pickedParam.startsWith(month)?pickedParam:heroDate.startsWith(month)?heroDate:todayDate.startsWith(month)?todayDate:`${month}-01`;
 function set(changes:Record<string,string|null>){setParams(current=>{for(const [key,value] of Object.entries(changes)){if(value===null)current.delete(key);else current.set(key,value)}return current})}

 const hero=sent?<Hero big calm eyebrow={sent.when} icon={sent.icon} title="Ищем замену" sub="Координатор видит причину. Место предложим тем, кто в резерве."/>
  :done?<DoneHero done={done} onUndo={()=>setDone(null)}/>
  :query.isPending?<Hero calm eyebrow="Мои занятия" title="Загружаем занятия…"/>
  :heroItem?<ShiftHero key={heroItem.id} item={heroItem} asking={focus?.id===heroItem.id&&focus.asking} onAsk={asking=>setFocus({id:heroItem.id,asking})} onSent={value=>{setFocus(null);setSent(value)}}/>
  :feed.isPending?<Hero calm eyebrow="Мои занятия" title="Подбираем мероприятия…"/>
  :feed.data&&!canSignUp?<LockedHero reason={feed.data.locked_reason}/>
  :pick?<PickHero card={pick} first={!ahead.length} onDone={setDone}/>
  :<Hero calm eyebrow={ahead.length?'Новых мест пока нет':'Занятий пока нет'} title="Мероприятия скоро появятся" sub="Координаторы готовят расписание. Напишем, когда откроется запись."><div className="actions"><Link className="btn btn-primary btn-lg" to="/opportunities">Направления фонда</Link></div></Hero>;

 return <div className="sch-page">
  <div className="page-head"><h1 className="h1">Мероприятия</h1><Segmented label="Вид" value={view} onChange={value=>set({view:value==='list'?null:value})} options={[{value:'list',label:'Список'},{value:'calendar',label:'Календарь'}]}/></div>
  <EventsTabs/>
  {view==='calendar'?<MonthView month={month} picked={picked} onMonth={value=>set({month:value,day:null})} onPick={day=>set({day})} feed={feed.data} reserves={reserves.data?.items} context={context} now={now}/>:<>
   {query.isError?<section className="card-hero calm"><p role="alert" className="hero-sub">{query.error.message}</p><div className="actions"><Button onClick={()=>void query.refetch()}>Повторить</Button></div></section>:hero}
   {ahead.length>0&&<section className="sec"><div className="sec-head"><h2 className="h2">Впереди</h2></div><div className="card">
    <div className="rows">{(showAll?ahead:ahead.slice(0,4)).map(row=><AheadRow key={row.key} row={row}/>)}</div>
    {ahead.length>4&&<Button variant="ghost" className="sch-more" aria-expanded={showAll} onClick={()=>setShowAll(!showAll)}>{showAll?'Свернуть':`Показать все (${ahead.length})`}</Button>}
   </div></section>}
   {tiles.length>0&&<section className="sec">
    <div className="sec-head"><h2 className="h2">{canSignUp?'Можно записаться':'Что будет в ближайшие недели'}</h2>
     <div className="row wrap sch-head-actions">{canSignUp&&<Button variant="ghost" size="sm" aria-expanded={showWhy} onClick={()=>setShowWhy(!showWhy)}>Почему так</Button>}<Link className="btn btn-secondary btn-sm" to="/events">Все мероприятия</Link></div>
    </div>
    {showWhy&&canSignUp&&<div className="card-soft sch-why"><p className="p">Здесь только то, что не пересекается с твоими занятиями.</p><WhyCards cards={pick?[pick,...tiles]:tiles} fallback={why}/></div>}
    <div className="grid-3">{tiles.map(card=><EventTile key={card.occurrence_id} card={card}/>)}</div>
   </section>}
   {past.length>0&&<section className="sec">
    <div className="sec-head"><h2 className="h2">Прошедшие</h2><Button variant="secondary" size="sm" aria-expanded={showPast} onClick={()=>setShowPast(!showPast)}>{showPast?'Скрыть':`Показать (${past.length})`}</Button></div>
    {showPast&&<div className="card"><div className="rows">{past.map((row,index)=><PastRow key={row.key} row={row} canReflect={!!reflections[index]?.data?.can_submit}/>)}</div></div>}
   </section>}
  </>}
  {!paused&&<PauseCard/>}
 </div>;
}
