import {useState,type KeyboardEvent,type ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {Button,Icon,type IconName} from '../../ui';
import {firstNameOf,initialsOf} from '../../ui/names';
import {useActivityCommand} from './api';
import {awaitingCoordinator,multiplierLabel,type AssignmentParticipation} from './participationApi';
import {labelDate,labelTime,localParts} from './calendarDates';
import {eventDay,eventUntil,placesFor,toneFor,useVolunteerEvent} from './eventsApi';
import './schedule.css';
import './events.css';

/** The volunteer's own занятие: helpers shared by «Мои занятия» and the занятие page (canvas Mine.dc.html, Event.dc.html). */
export type Tone='y'|'o'|'b'|'g'|'v';
/** Gender-neutral words, so the same list fits everyone. */
export const reasons=['Болезнь','Работа','Семейные дела','Другое'];

export function cap(text:string){return text.charAt(0).toUpperCase()+text.slice(1)}
export function low(text:string){return text.charAt(0).toLowerCase()+text.slice(1)}
export function dateOf(row:{starts_at:string;timezone:string}){return localParts(row.starts_at,row.timezone).date}
/** «Сб, 24 октября, 14:00» */
export function whenLabel(row:{starts_at:string;timezone:string}){const date=dateOf(row);return `${cap(labelDate(date,{weekday:'short'}))}, ${labelDate(date)}, ${labelTime(row.starts_at,row.timezone)}`}
export function timeRange(row:{starts_at:string;ends_at:string;timezone:string}){return `${labelTime(row.starts_at,row.timezone)}–${labelTime(row.ends_at,row.timezone)}`}
export function reasonText(reason:string){return `Не смогу прийти: ${low(reason)}`}
/** One event keeps one colour on every screen: the tint follows the title, not the place in a list. */
export function toneOf(title:string):Tone{return toneFor(title).key}
export function tintOf(title:string){return toneFor(title).tint}
export function iconOf(title:string,format=''):IconName{
 const text=title.toLowerCase();
 if(format==='online')return 'globe';
 if(text.includes('ярмар')||text.includes('базар'))return 'home';
 if(text.includes('фото')||text.includes('съёмк')||text.includes('видео'))return 'camera';
 if(text.includes('творч')||text.includes('мастер')||text.includes('живопис')||text.includes('арт'))return 'palette';
 return 'users';
}

/** Only a self sign-up or a freed reserve place waits for the coordinator; an invitation is always answered by the volunteer. */
export function waitsForCoordinator(item:AssignmentParticipation){return awaitingCoordinator(item)}
/** An invitation the volunteer can answer right now. */
export function needsAnswer(item:AssignmentParticipation){return item.status==='invited'&&item.occurrence_status==='scheduled'&&item.allowed_actions.includes('confirm')&&!awaitingCoordinator(item)}
/** The fund cancelled the занятие itself; own declines and cancels leave the schedule instead. */
export function isFundCancelled(item:AssignmentParticipation){return item.occurrence_status==='cancelled'&&['invited','confirmed','cancelled'].includes(item.status)}

export function Pts({value}:{value:number}){return value>1?<span className="pts"><Icon name="star"/>{multiplierLabel(value)}</span>:null}

export function ReasonPick({value,onChange}:{value:string;onChange:(value:string)=>void}){
 function move(event:KeyboardEvent<HTMLButtonElement>,index:number){
  const step=['ArrowRight','ArrowDown'].includes(event.key)?1:['ArrowLeft','ArrowUp'].includes(event.key)?-1:0;if(!step)return;
  event.preventDefault();const next=(index+step+reasons.length)%reasons.length;onChange(reasons[next]);(event.currentTarget.parentElement?.children[next] as HTMLElement|undefined)?.focus();
 }
 return <div className="pick own-reasons" role="radiogroup" aria-label="Почему не получится">{reasons.map((label,index)=><button key={label} type="button" role="radio" aria-checked={value===label} tabIndex={value===label||(!value&&index===0)?0:-1} className={value===label?'is-on':undefined} onClick={()=>onChange(label)} onKeyDown={event=>move(event,index)}>{label}</button>)}</div>;
}

type Step={title:string;meta?:string;state:'done'|'now'|''};
function hours(minutes:number){return `${(Math.round(minutes/6)/10).toLocaleString('ru-RU')} ч`}
/** The way to the занятие depends on how it started: an own request or a reserve place goes through the coordinator, an invitation through the volunteer. */
function steps(item:AssignmentParticipation,answer:boolean,ended:boolean):Step[]{
 const confirmed=item.status==='confirmed',done=item.attendance,attended=done?.outcome==='attended',posted=attended&&done?.ledger_state==='posted';
 const own=item.origin==='self'||item.origin==='reserve';
 const rows:Step[]=[{title:item.origin==='self'?'Заявка':item.origin==='reserve'?'Место из резерва':'Приглашение',state:'done'}];
 if(own)rows.push({title:'Согласование координатора',state:confirmed||item.approved_at?'done':'now'});
 else rows.push({title:'Твоё подтверждение',state:confirmed?'done':answer?'now':''});
 rows.push({title:'Занятие',state:attended?'done':confirmed&&(!ended||!done)?'now':''});
 if(done?.outcome==='absent')rows.push({title:'Отмечено неучастие',state:''});
 else rows.push({title:posted?'Часы засчитаны':'Часы',meta:attended?(posted?hours(done.minutes):`${hours(done.minutes)}, ждут подтверждения`):undefined,state:posted?'done':attended?'now':''});
 return rows;
}
const personTones=['','ph-b','ph-g','ph-v'];

/** The volunteer's own занятие (/my/assignments/:id) laid out like Event.dc.html: a hero in the pale tint of its event,
 * «Чем помочь» with the volunteer's role, other dates and the info cards. The event detail adds audience, team, task and dates. */
export function VolunteerAssignment({item}:{item:AssignmentParticipation}){
 const command=useActivityCommand(),[mode,setMode]=useState<'idle'|'asking'|'sent'>('idle'),[reason,setReason]=useState('');
 const event=useVolunteerEvent(item.occurrence_id).data;
 const ended=Date.parse(item.ends_at)<=Date.now(),attendance=item.attendance??null,confirmed=item.status==='confirmed';
 const answer=needsAnswer(item),waiting=awaitingCoordinator(item)&&item.status==='invited',fund=isFundCancelled(item);
 const leave=confirmed?'cancel':'decline',canLeave=item.allowed_actions.includes(leave);
 function run(action:string,body:Record<string,unknown>={}){return command.mutateAsync({path:`/assignments/${item.id}/${action}`,body:{expected_version:item.version,...body},key:crypto.randomUUID()})}
 function confirm(){void run('confirm').then(()=>setMode('idle')).catch(()=>{})}
 function send(){if(!reason)return;void run(leave,{reason:reasonText(reason)}).then(()=>{setReason('');setMode('sent')}).catch(()=>{})}
 const eyebrow=mode==='sent'?'Ищем замену':mode==='asking'?'Не сможешь прийти?':fund?'Отменено фондом'
  :attendance?(attendance.outcome==='absent'?'Отмечено неучастие':'Занятие прошло'):confirmed?(ended?'Занятие прошло':'Место за тобой')
  :waiting?(item.origin==='reserve'?'Освободилось место из резерва':'Ждёт ответа координатора')
  :item.status==='invited'?(item.origin==='invitation'?'Тебя приглашают':'Координатор согласовал участие')
  :({declined:'Приглашение отклонено',cancelled:'Участие отменено',expired:'Срок приглашения истёк'} as Record<string,string>)[item.status]??'Занятие';
 const sub=mode==='sent'?'Координатор видит причину. Место предложим тем, кто в резерве.':mode==='asking'?'Выбери причину — координатор поймёт, искать ли замену':eventUntil(item);
 const note=mode==='idle'&&waiting&&item.origin==='reserve'?'Координатор подтвердит участие.':'';
 const active=!fund&&mode!=='sent'&&(confirmed||item.status==='invited');
 const coordinatorNote=[...item.history].reverse().find(entry=>entry.command==='approve'&&String(entry.reason??'').trim());
 const need=event?.needs.find(row=>row.id===item.staffing_need_id);
 const contacts=event?.contacts??[];
 const dates=event?.other_dates??[];
 const group=confirmed&&!fund;
 let actions:ReactNode=null;
 if(mode==='asking')actions=<><ReasonPick value={reason} onChange={setReason}/><div className="actions"><Button size="lg" aria-disabled={!reason} loading={command.isPending} onClick={send}>Сообщить координатору</Button><Button variant="ghost" size="lg" disabled={command.isPending} onClick={answer?confirm:()=>setMode('idle')}>Я приду</Button></div></>;
 else if(mode==='sent'||fund)actions=null;
 else if(answer)actions=<div className="actions"><Button size="lg" loading={command.isPending} onClick={confirm}>Я приду</Button>{canLeave&&<Button variant="secondary" size="lg" onClick={()=>setMode('asking')}>Не смогу</Button>}</div>;
 else if(confirmed&&!ended)actions=<div className="actions"><Link className="btn btn-primary btn-lg" to={`/my/assignments/${item.id}/preparation`}>Подготовиться</Link>{canLeave&&<Button variant="ghost" size="lg" onClick={()=>setMode('asking')}>Не смогу</Button>}</div>;
 else if(confirmed&&attendance?.outcome!=='absent')actions=<div className="actions"><Link className="btn btn-primary btn-lg" to={`/my/assignments/${item.id}/reflection`}>Как прошло?</Link></div>;
 else if(waiting&&canLeave)actions=<div className="actions"><Button variant="secondary" size="lg" loading={command.isPending} onClick={()=>void run('decline').catch(()=>{})}>{item.origin==='reserve'?'Не смогу':'Отменить заявку'}</Button></div>;
 return <>
  <div className="page-head"><h1 className="h1">{item.title}</h1></div>
  <section className={mode==='sent'?'card-hero calm':'card-hero'} style={mode==='sent'?undefined:{background:tintOf(item.title)}}>
   <div className="hero-grid"><div className="hero-copy">
    <p className="eyebrow">{eyebrow}</p>
    <h2 className="hero-when">{whenLabel(item)}</h2>
    <p className="hero-sub">{sub}</p>
    {note&&<p className="hero-sub">{note}</p>}
    {actions}
    {command.isError&&<p role="alert" className="own-error">{command.error.message}</p>}
   </div><span className="hero-art" aria-hidden="true"><Icon name={iconOf(item.title,event?.format)}/></span></div>
  </section>

  {item.role_title&&<section className="sec"><div className="sec-head"><h2 className="h2">Чем помочь</h2></div><div className="grid-2">
   <div className="role-pick is-on">
    <span className="role-top"><span className="h3">{item.role_title}</span><span className="role-mark" aria-hidden="true"><Icon name="check"/></span></span>
    {need?.task&&<span className="p">{need.task}</span>}
    {(need||item.points_multiplier>1)&&<span className="role-foot">{need&&!ended&&!fund&&<span className={`places${placesFor(need.missing).tone?` ${placesFor(need.missing).tone}`:''}`}><i aria-hidden="true"/>{placesFor(need.missing).label}</span>}<Pts value={item.points_multiplier}/></span>}
   </div>
  </div></section>}

  {!ended&&!fund&&dates.length>0&&<section className="sec"><div className="sec-head"><h2 className="h2">Другие даты</h2></div><div className="chips">
   {dates.map(date=><Link key={date.occurrence_id} className={`chip${date.full&&!date.mine?' is-off':''}`} to={`/events/${date.occurrence_id}`}>{eventDay({...date,timezone:item.timezone})}{date.mine?', ты идёшь':date.full?', мест нет':''}</Link>)}
  </div></section>}

  <section className="sec"><div className="grid-3">
   {event?.audience&&<div className="card action-card"><h2 className="h3">Кого ждём</h2><p className="p">{event.audience}</p></div>}
   <div className="card action-card"><h2 className="h3">Перед выходом</h2>{item.readiness.length?<div className="rows">{item.readiness.map(req=>{const ok=req.state!=='pending';
    return <div key={req.key} className="rowi"><span className={`st ${ok?'st-ok':'st-off'}`} role="img" aria-label={ok?'Готово':'Предстоит'}><Icon name="check"/></span><span>{req.title}{req.level==='recommended'?', по желанию':''}</span></div>})}</div>:<p className="p">Дополнительная подготовка не нужна.</p>}</div>
   {(contacts.length>0||group)&&<div className="card action-card"><h2 className="h3">Команда</h2>
    {contacts.length>0&&<div className="rows">{contacts.map((person,index)=><div className="rowi" key={`${person.role}:${person.display_name}`}>
     <span className={`ph ph-sm ${personTones[index%personTones.length]}`} aria-hidden="true">{initialsOf(person.display_name)}</span><span>{firstNameOf(person.display_name)||person.display_name}, {person.role.toLowerCase()}</span>
    </div>)}</div>}
    {group&&<div className="actions"><Link className="btn btn-secondary" to={`/me/group?assignment_id=${item.id}`}>Кто будет в группе</Link></div>}
   </div>}
   {active&&<div className="card action-card"><h2 className="h3">Как идёт участие</h2><div className="timeline">{steps(item,answer,ended).map((step,index)=><div key={step.title} className={`tl${step.state?` ${step.state}`:''}`}>
    <span className="tl-mark" aria-hidden="true">{step.state==='done'?<Icon name="check"/>:index+1}</span>
    <span><b>{step.title}</b>{step.meta&&<span className="meta">{step.meta}</span>}</span>
   </div>)}</div></div>}
   {coordinatorNote&&<div className="card action-card"><h2 className="h3">От координатора</h2><p className="p">{String(coordinatorNote.reason)}</p></div>}
  </div></section>
 </>;
}
