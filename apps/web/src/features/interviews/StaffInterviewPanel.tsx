import {appResourceUrl} from '../../basePath';
import {useState} from 'react';
import {Link} from 'react-router-dom';
import {Button,Icon,LoadingState,Textarea,cx} from '../../ui';
import {useCandidate} from '../applications/api';
import {StaffBooking,Slot,useInterviewCommand,useSlots} from './api';
import {addDays,dateLabel,dayShort,mskDay,timeLabel,today} from './date';

/** Outcomes a coordinator records; `stored` is the result text the API keeps, `agreement` is what the candidate reads. */
export const outcomes=[
 {id:'fit',label:'Подходит, зовём на первый выход',stored:'Подходит',short:'подходит',color:'var(--green)',agreement:'Координатор подберёт первое мероприятие и напишет вам.'},
 {id:'more',label:'Нужна ещё одна встреча',stored:'Нужна ещё одна встреча',short:'нужна ещё встреча',color:'var(--yellow)',agreement:'Договоримся о ещё одной встрече.'},
 {id:'no',label:'Не подходит',stored:'Не подходит',short:'не подходит',color:'var(--red)',agreement:'Спасибо за разговор. Координатор напишет вам.'},
 {id:'noshow',label:'Не пришёл',stored:'Не пришёл',short:'не пришёл',color:'var(--quiet)',agreement:'Встреча не состоялась. Можно выбрать другое время.'},
] as const;
// Results recorded before the redesign used these texts.
const legacy:Record<string,string>={'Подобрать первое занятие':'fit','Обсудить подходящую роль':'more','Вернуться к разговору позже':'more'};
export const resultOf=(b:StaffBooking)=>{if(b.status==='missed')return 'noshow';if(b.status==='cancelled')return 'cancelled';if(b.status!=='completed')return null;const text=String(b.result?.outcome??'');return outcomes.find(o=>o.stored===text)?.id??legacy[text]??'done';};
export const resultWord=(code:string|null)=>outcomes.find(o=>o.id===code)?.short??({cancelled:'отменено',done:'состоялось'} as Record<string,string>)[code??'']??'нет итога';
export const isOnline=(b:{venue:string;join_url?:string|null})=>!!b.join_url||/онлайн|online|телемост|zoom/i.test(b.venue);
export const initials=(name:string)=>name.split(/\s+/).filter(Boolean).map(p=>p[0]).slice(0,2).join('').toUpperCase();
const tones=['ph-b','ph-p','ph-g','ph-o','ph-v'];
export const toneOf=(id:string)=>`iv-${tones[[...id].reduce((sum,c)=>sum+c.charCodeAt(0),0)%tones.length]}`;
export const endLabel=(b:StaffBooking)=>`${timeLabel(b.starts_at)}–${timeLabel(b.ends_at)}`;
export const whenLabel=(instant:string)=>{const day=mskDay(instant);return day===today()?'Сегодня':dayShort(day);};
const answer=(v:unknown)=>Array.isArray(v)?v.join(', '):typeof v==='string'?v.trim():'';
const eventLabels:Record<string,string>={booked:'Кандидат записался',rescheduled:'Собеседование перенесли',cancelled:'Собеседование отменили',completed:'Записан итог',missed:'Отмечено, что кандидат не пришёл',result_updated:'Итог изменён'};

function MoveForm({booking,onDone,onBack}:{booking:StaffBooking;onDone:()=>void;onBack:()=>void}){
 const from=today(),slots=useSlots(from,addDays(from,27),'Europe/Moscow'),command=useInterviewCommand(),[picked,setPicked]=useState<Slot|null>(null),[all,setAll]=useState(false);
 // One chip per time: the booking's own coordinator wins when two people are free at once.
 const byTime=new Map<string,Slot>();
 for(const s of slots.data??[]){if(new Date(s.starts_at).getTime()<=Date.now())continue;const seen=byTime.get(s.starts_at);if(!seen||(s.coordinator_id===booking.coordinator_id&&seen.coordinator_id!==booking.coordinator_id))byTime.set(s.starts_at,s);}
 const days=new Map<string,Slot[]>();
 [...byTime.values()].sort((a,b)=>a.starts_at.localeCompare(b.starts_at)).forEach(s=>{const d=mskDay(s.starts_at);days.set(d,[...(days.get(d)??[]),s]);});
 const list=[...days.entries()],shown=all?list:list.slice(0,4);
 const move=()=>{if(!picked)return;command.mutate({path:`/interviews/${booking.id}/reschedule`,body:{slot_id:picked.id,slot_version:picked.version,expected_version:booking.version}},{onSuccess:onDone,onError:()=>{setPicked(null);void slots.refetch();}});};
 return <div className="iv-block">
  <h3 className="h3">Новое время</h3>
  {slots.isLoading?<LoadingState/>:!list.length?<p className="p">Свободных слотов нет. <Link to="/fund/interviews/availability">Открыть слоты</Link></p>:<>
   {shown.map(([day,items])=><div key={day} className="iv-move-day"><span className="label">{dayShort(day)}</span><div className="iv-chips">{items.map(s=><button key={s.id} type="button" aria-pressed={picked?.id===s.id} className={cx(picked?.id===s.id&&'is-on')} onClick={()=>setPicked(s)}>{timeLabel(s.starts_at)}</button>)}</div></div>)}
   {list.length>4&&!all&&<button type="button" className="iv-more" onClick={()=>setAll(true)}>Показать все</button>}
  </>}
  {command.error&&<p role="alert" className="iv-error">{command.error.message}</p>}
  <div className="iv-actions-row"><Button disabled={!picked||command.isPending} onClick={move}>Перенести</Button><Button variant="ghost" onClick={onBack}>Назад</Button></div>
 </div>;
}

/** Staff side of one interview: who, when, where, and the next action. The candidate keeps the «Встреча с координатором» dialog. */
export function StaffInterviewPanel({booking,onClose}:{booking:StaffBooking;onClose:()=>void}){
 const [mode,setMode]=useState<'view'|'outcome'|'move'|'cancel'>('view'),[choice,setChoice]=useState(''),[note,setNote]=useState(booking.private_note??''),[flash,setFlash]=useState('');
 const candidate=useCandidate(booking.application_id),command=useInterviewCommand();
 const answers=(candidate.data?.revision.answers??{}) as Record<string,unknown>,result=resultOf(booking),open=booking.status==='booked',started=new Date(booking.starts_at).getTime()<=Date.now();
 const telegram=answer(answers.telegram),contact=telegram?`Telegram ${telegram.startsWith('@')?telegram:'@'+telegram}`:answer(answers.phone)||answer(answers.email);
 const experience=answer(answers.volExpText)||answer(answers.specialExpText)||({'Да':'Уже был волонтёром','Нет':'Пока без опыта'} as Record<string,string>)[answer(answers.volExp)]||'';
 const facts=[['Когда удобно',answer(answers.participation)],['Опыт',experience],['Связь',contact]].filter(([,v])=>v);
 const go=(next:typeof mode)=>{setMode(next);setFlash('');command.reset();};
 const save=()=>{const o=outcomes.find(x=>x.id===choice);if(!o)return;command.mutate({path:`/interviews/${booking.id}/${o.id==='noshow'?'mark-missed':'complete'}`,body:{expected_version:booking.version,outcome:o.stored,public_agreement:o.agreement,private_note:note,next_contact_date:booking.result?.next_contact_date??null}},{onSuccess:()=>setMode('view')});};
 const cancel=()=>command.mutate({path:`/interviews/${booking.id}/cancel`,body:{expected_version:booking.version,reason:'Координатор отменил встречу'}},{onSuccess:onClose});
 return <aside className="iv-panel" aria-labelledby="iv-panel-name">
  <div className="iv-panel-head">
   <div className="iv-person"><span className={cx('iv-ph iv-ph-lg',toneOf(booking.application_id))} aria-hidden="true">{initials(booking.candidate_name)}</span><div className="iv-min"><h2 className="h3 iv-panel-name" id="iv-panel-name">{booking.candidate_name}</h2>{answer(answers.directions)&&<span className="meta">{answer(answers.directions)}</span>}</div></div>
   <button type="button" className="iv-close" aria-label="Закрыть" onClick={onClose}><Icon name="x"/></button>
  </div>
  <p className="iv-when-big">{whenLabel(booking.starts_at)}, {timeLabel(booking.starts_at)}</p>
  <p className="p iv-place">{isOnline(booking)?<>Онлайн{booking.join_url?<>, <a href={appResourceUrl(booking.join_url)} target="_blank" rel="noreferrer">ссылка на встречу</a></>:', ссылка придёт обоим'}</>:booking.venue}</p>
  {mode==='view'&&<>
   {flash&&<div className="iv-done" role="status"><Icon name="check"/>{flash}</div>}
   {result&&result!=='cancelled'&&<div className="iv-done"><Icon name="check"/><span>Итог: {resultWord(result)}{booking.private_note&&<span className="iv-done-note">{booking.private_note}</span>}</span></div>}
   {booking.status==='cancelled'&&<p className="p iv-gap">Собеседование отменено{booking.cancel_reason?`: ${booking.cancel_reason}`:''}</p>}
   <div className="iv-actions-row">
    {open&&started&&<Button onClick={()=>go('outcome')}>Записать итог</Button>}
    {open&&<Button variant="secondary" onClick={()=>go('move')}>Перенести</Button>}
    {result==='fit'&&<Link className="btn btn-primary" to="/fund/opportunities">Подобрать первое мероприятие</Link>}
   </div>
   {candidate.isLoading?<div className="iv-block"><LoadingState/></div>:facts.length>0&&<div className="iv-block"><h3 className="h3">Из анкеты</h3><dl className="iv-dl">{facts.map(([k,v])=><div key={k} className="iv-dl-row"><dt>{k}</dt><dd>{v}</dd></div>)}</dl></div>}
   {(booking.events??[]).length>0&&<details className="iv-block iv-history"><summary>История</summary><ul>{(booking.events??[]).map((e,i)=><li key={i}><span>{eventLabels[String(e.kind)]??String(e.kind)}</span><span className="meta">{dateLabel(String(e.created_at))}, {timeLabel(String(e.created_at))}</span></li>)}</ul></details>}
   <div className="iv-block iv-foot"><Link className="btn btn-ghost btn-sm iv-flush" to={`/fund/candidates/${booking.application_id}`}>Вся анкета</Link>{open&&<Button variant="ghost" size="sm" onClick={()=>go('cancel')}>Отменить собеседование</Button>}</div>
  </>}
  {mode==='outcome'&&<div className="iv-block">
   <h3 className="h3">Итог</h3>
   <div className="iv-outcome" role="radiogroup" aria-label="Итог">{outcomes.map(o=><button key={o.id} type="button" role="radio" aria-checked={choice===o.id} className={cx(choice===o.id&&'is-on')} onClick={()=>setChoice(o.id)}><i style={{background:o.color}}/>{o.label}</button>)}</div>
   <label className="field iv-gap"><span className="label">Заметка для команды</span><Textarea className="iv-note" value={note} onChange={e=>setNote(e.target.value)}/></label>
   {command.error&&<p role="alert" className="iv-error">{command.error.message}</p>}
   <div className="iv-actions-row"><Button disabled={!choice||command.isPending} onClick={save}>Сохранить итог</Button><Button variant="ghost" onClick={()=>go('view')}>Назад</Button></div>
  </div>}
  {mode==='move'&&<MoveForm booking={booking} onBack={()=>go('view')} onDone={()=>{setMode('view');setFlash('Перенесли, кандидат получит сообщение');}}/>}
  {mode==='cancel'&&<div className="iv-block">
   <h3 className="h3">Отменить собеседование?</h3>
   <p className="p">Кандидат получит сообщение и выберет другое время.</p>
   {command.error&&<p role="alert" className="iv-error">{command.error.message}</p>}
   <div className="iv-actions-row"><Button variant="danger" disabled={command.isPending} onClick={cancel}>Отменить</Button><Button variant="ghost" onClick={()=>go('view')}>Не отменять</Button></div>
  </div>}
 </aside>;
}
