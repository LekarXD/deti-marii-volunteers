import {useEffect,useId,useRef,useState,type FormEvent,type ReactNode} from 'react';
import {Link,useParams} from 'react-router-dom';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {Button,EmptyState,ErrorState,Icon,Input,LoadingState,Textarea,useToast,type IconName} from '../../ui';
import {command,decisionLabels,moodLabels,readPreparation,readReflection,type Reflection,type ReflectionDraft} from './api';
import {ReflectionRecorder} from './ReflectionRecorder';
import {coordinatorContact,creditAmount,dateBadge,dayMonth,errorText,firstName,initials,isFirstExit,leadContact,ledgerMinutes,stamp,timeOnly,useNarrow,useOwnAssignment,useOwnDay,useOwnHours,useOwnProfile,type OwnAssignment,type OwnHours} from './volunteerApi';
import './followups.css';

type Mood=NonNullable<ReflectionDraft['mood']>;
const moods:Array<{value:Mood;icon:IconName}>=[{value:'great',icon:'heart'},{value:'good',icon:'smile'},{value:'ok',icon:'meh'},{value:'hard',icon:'frown'},{value:'awful',icon:'alert'}];
const helpOptions:Array<[ReflectionDraft['help'],string]>=[['later','Пока не знаю'],['yes','Хочу поговорить'],['no','Сейчас справляюсь']];
const continuationOptions:Array<[ReflectionDraft['continuation'],string]>=[['yes','Да, в этой группе'],['other','Хочу другую роль'],['pause','Нужна пауза'],['discuss','Сначала обсудить'],['finish','Не планирую']];
const AUTOSAVE_MS=1500;

export function ReflectionPage(){
 const {id=''}=useParams();
 const data=useQuery({queryKey:keys.detail('own-reflection',id),queryFn:({signal})=>readReflection(id,signal),enabled:!!id,staleTime:0});
 const assignment=useOwnAssignment(id),hours=useOwnHours(),profile=useOwnProfile();
 const preparation=useQuery({queryKey:keys.detail('assignment-preparation',id),queryFn:({signal})=>readPreparation(id,signal),enabled:!!id,staleTime:0});
 if(!id)return <EmptyState title="Выбери своё занятие"/>;
 if(data.isPending)return <LoadingState/>;
 if(data.error)return <ErrorState error={data.error} retry={()=>data.refetch()}/>;
 const value=data.data,a=assignment.data,contacts=preparation.data?.contacts;
 const eyebrow=[value.title,a?dayMonth(a.starts_at,a.timezone):''].filter(Boolean).join(', ');
 const people={lead:firstName(leadContact(contacts)?.display_name),coordinator:firstName(coordinatorContact(contacts)?.display_name),me:firstName(profile.data?.display_name)};
 return <div className="refl-page">
  <Link className="back" to="/my/schedule"><Icon name="chevron-left"/>Мои занятия</Link>
  {value.submitted_at?<ReflectionSent id={id} value={value} eyebrow={eyebrow} assignment={a} hours={hours.data} people={people}/>
  :value.can_submit?<ReflectionForm key={id} id={id} value={value} eyebrow={eyebrow} first={isFirstExit(hours.data,id)}/>
  :<section className="card-hero calm"><div className="hero-grid"><div className="hero-copy">
    {eyebrow&&<p className="eyebrow">{eyebrow}</p>}
    <h1 className="hero-title">Как прошло занятие?</h1>
    <p className="hero-sub">Рассказать, как прошло, можно после занятия.</p>
    <div className="actions"><Link className="btn btn-primary btn-lg" to={`/my/assignments/${id}/preparation`}>К занятию</Link></div>
   </div><span className="hero-art" aria-hidden="true"><Icon name="message"/></span></div></section>}
 </div>;
}

function draftOf(value:Reflection):ReflectionDraft{return {expected_version:value.version,mood:value.mood as ReflectionDraft['mood'],text:value.text,unexpected:value.unexpected,help:value.help as ReflectionDraft['help'],help_text:value.help_text,continuation:value.continuation as ReflectionDraft['continuation'],restricted:value.restricted};}
const isEmpty=(draft:ReflectionDraft)=>!draft.mood&&!draft.text?.trim()&&!draft.unexpected?.trim()&&draft.help!=='yes'&&draft.continuation==='discuss';

function ReflectionForm({id,value,eyebrow,first}:{id:string;value:Reflection;eyebrow:string;first:boolean}){
 const client=useQueryClient(),{toast}=useToast(),uid=useId(),narrow=useNarrow();
 const [draft,setDraft]=useState<ReflectionDraft>(()=>draftOf(value));
 const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null),[invalid,setInvalid]=useState(false),[voice,setVoice]=useState(false),[open,setOpen]=useState<boolean|null>(null),[typing,setTyping]=useState(()=>!!value.text.trim());
 // Drafts save themselves a moment after the last change; saves run one at a time on the latest version.
 const latest=useRef(draft),version=useRef(value.version),dirty=useRef(false),pending=useRef<Promise<void>|null>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 latest.current=draft;
 async function persist(){
  while(pending.current)await pending.current;
  if(!dirty.current)return;
  dirty.current=false;
  const run=(async()=>{try{const saved=await command<Reflection>(`/me/assignments/${id}/reflection`,{...latest.current,expected_version:version.current},'PUT');version.current=saved.version;client.setQueryData(keys.detail('own-reflection',id),saved);}catch(e){dirty.current=true;throw e;}})();
  pending.current=run.catch(()=>undefined).then(()=>{pending.current=null;});
  await run;
 }
 function schedule(){if(timer.current)clearTimeout(timer.current);timer.current=setTimeout(()=>{timer.current=null;persist().then(()=>setError(null),setError);},AUTOSAVE_MS);}
 useEffect(()=>()=>{if(timer.current){clearTimeout(timer.current);void persist().catch(()=>undefined);}},[]);// eslint-disable-line react-hooks/exhaustive-deps
 function change<K extends keyof ReflectionDraft>(field:K,next:ReflectionDraft[K]){setDraft(current=>{const updated={...current,[field]:next};latest.current=updated;return updated;});dirty.current=true;setInvalid(false);schedule();}
 async function submit(event:FormEvent){
  event.preventDefault();if(timer.current){clearTimeout(timer.current);timer.current=null;}
  if(isEmpty(latest.current)){setInvalid(true);return;}
  setBusy(true);setError(null);
  try{dirty.current=true;await persist();const sent=await command<Reflection>(`/me/assignments/${id}/reflection/submit`,{expected_version:version.current});client.setQueryData(keys.detail('own-reflection',id),sent);toast('Отправлено');}
  catch(e){setError(e);}finally{setBusy(false);}
 }
 // On a phone the extra questions start folded so «Отправить» stays close (canvas Phone, screen 3).
 const expanded=open??(first&&!narrow);
 const moodRow=<div className="moods" role="group" aria-label="Настроение">{moods.map(mood=><button type="button" key={mood.value} className={`mood${draft.mood===mood.value?' is-on':''}`} aria-pressed={draft.mood===mood.value} disabled={busy} onClick={()=>change('mood',mood.value)}><Icon name={mood.icon}/><span>{moodLabels[mood.value]}</span></button>)}</div>;
 const textField=<label className="field refl-say"><span className={narrow?'refl-voice-title':'sr-only'}>Расскажи своими словами</span><Textarea placeholder="Что получилось, что было трудно" value={draft.text??''} onChange={e=>change('text',e.target.value)} maxLength={12000} disabled={busy}/></label>;
 const recorder=voice&&value.voice_available&&<ReflectionRecorder id={id} available text={draft.text??''} disabled={busy} onApply={text=>{setTyping(true);change('text',[latest.current.text?.trim(),text].filter(Boolean).join('\n\n'));}}/>;
 const more=<div className="card refl-more">
  <button type="button" className="refl-toggle" aria-expanded={expanded} aria-controls={`${uid}-more`} onClick={()=>setOpen(!expanded)}><span className="h3">{first?'После первого выхода':'Подробнее о занятии'}</span><Icon name="chevron-down"/></button>
  {expanded&&<div className="stack refl-fields" id={`${uid}-more`}>
   <label className="field"><span className="label">Что оказалось неожиданным?</span><Input placeholder="Например, сколько ребята хотят общаться" value={draft.unexpected??''} onChange={e=>change('unexpected',e.target.value)} maxLength={6000} disabled={busy}/></label>
   <div className="field"><span className="label" id={`${uid}-help`}>Нужна ли помощь?</span><div className="pick" role="group" aria-labelledby={`${uid}-help`}>{helpOptions.map(([key,label])=><button type="button" key={key} className={draft.help===key?'is-on':''} aria-pressed={draft.help===key} disabled={busy} onClick={()=>change('help',key)}>{label}</button>)}</div></div>
   {draft.help==='yes'&&<>
    <label className="field"><span className="label">Что хочется обсудить?</span><Textarea className="refl-help" value={draft.help_text??''} onChange={e=>change('help_text',e.target.value)} maxLength={6000} disabled={busy}/></label>
    <label className="check"><input type="checkbox" checked={draft.restricted??false} disabled={busy} onChange={e=>change('restricted',e.target.checked)}/><span>Личный или тревожный вопрос, только для специалиста</span></label>
   </>}
   <div className="field"><span className="label" id={`${uid}-cont`}>Хочешь продолжать?</span><div className="pick" role="group" aria-labelledby={`${uid}-cont`}>{continuationOptions.map(([key,label])=><button type="button" key={key} className={draft.continuation===key?'is-on':''} aria-pressed={draft.continuation===key} disabled={busy} onClick={()=>change('continuation',key)}>{label}</button>)}</div></div>
  </div>}
 </div>;
 const alerts=<>{invalid&&<p className="followup-error" role="alert">Выбери настроение или напиши пару слов.</p>}{error?<p className="followup-error" role="alert">{errorText(error)}</p>:null}</>;
 if(narrow){
  // Phone: title and moods on the page, one yellow card that asks for a voice note first, then a full-width «Отправить».
  const speak=value.voice_available&&!typing;
  return <form className="refl-form refl-phone" onSubmit={submit} noValidate>
   {eyebrow&&<p className="eyebrow">{eyebrow}</p>}
   <h1 className="refl-phone-title">Как прошло занятие?</h1>
   {moodRow}
   <section className={`card-hero refl-voice${speak?' is-voice':''}`} aria-label={speak?'Голосом':'Своими словами'}>
    {speak?<>
     <button type="button" className="refl-mic" aria-expanded={voice} disabled={busy} onClick={()=>setVoice(!voice)}><span className="mic" aria-hidden="true"><Icon name="mic"/></span><b>Расскажи голосом</b></button>
     <button type="button" className="quiet-link refl-switch" disabled={busy} onClick={()=>{setVoice(false);setTyping(true);}}>Написать текстом</button>
    </>:<>
     {textField}
     {value.voice_available&&<button type="button" className="quiet-link refl-switch" disabled={busy} onClick={()=>setTyping(false)}>Сказать голосом</button>}
    </>}
    {speak&&recorder}
   </section>
   {more}
   {alerts}
   <Button type="submit" size="lg" className="btn-block" loading={busy}>Отправить</Button>
  </form>;
 }
 return <form className="card-hero refl-form" onSubmit={submit} noValidate>
  {eyebrow&&<p className="eyebrow">{eyebrow}</p>}
  <h1 className="hero-title">Как прошло занятие?</h1>
  {moodRow}
  {textField}
  {more}
  {alerts}
  <div className="actions">
   <Button type="submit" size="lg" loading={busy}>Отправить</Button>
   {value.voice_available&&<Button size="lg" variant="secondary" aria-expanded={voice} disabled={busy} onClick={()=>setVoice(!voice)}><Icon name="mic"/>Сказать голосом</Button>}
  </div>
  {recorder}
 </form>;
}

type People={lead:string;coordinator:string;me:string};
/** What the volunteer gets for this занятие: the minutes in the hours ledger once it is marked, or its planned length until then. Points follow the server rule. */
function creditLine(id:string,assignment:OwnAssignment|undefined,hours:OwnHours|undefined,lead:string){
 if(!assignment)return '';
 const attendance=assignment.attendance,counted=ledgerMinutes(hours,id)??(attendance?(attendance.outcome==='attended'?attendance.minutes:0):null);
 if(counted!=null)return counted>0?`Засчитали ${creditAmount(counted,assignment.points_multiplier)}.`:'';
 const minutes=Math.round((Date.parse(assignment.ends_at)-Date.parse(assignment.starts_at))/60000);
 return minutes>0?`${creditAmount(minutes,assignment.points_multiplier)} засчитаем, когда ${lead||'координатор'} отметит занятие.`:'';
}

function ReflectionSent({id,value,eyebrow,assignment,hours,people}:{id:string;value:Reflection;eyebrow:string;assignment?:OwnAssignment;hours?:OwnHours;people:People}){
 const hard=value.mood==='hard'||value.mood==='awful'||value.help==='yes';
 const credit=creditLine(id,assignment,hours,people.lead);
 const review=value.review;
 return <>
  {hard?<section className="card-hero calm"><div className="hero-grid"><div className="hero-copy">
   <p className="eyebrow">Спасибо, что делишься</p>
   <h1 className="hero-title">Так бывает у многих</h1>
   <p className="hero-sub">{value.follow_up_registered?`${people.coordinator||'Координатор'} скоро напишет тебе. `:''}Часы засчитаем как обычно.</p>
   <div className="actions"><Link className="btn btn-primary btn-lg" to="/messages">Написать координатору</Link></div>
  </div><span className="hero-art" aria-hidden="true"><Icon name="message"/></span></div></section>
  :<section className="card-hero"><div className="hero-grid"><div className="hero-copy">
   {eyebrow&&<p className="eyebrow">{eyebrow}</p>}
   <h1 className="hero-title">{people.me?`Спасибо, ${people.me}!`:'Спасибо!'}</h1>
   {credit&&<p className="hero-sub">{credit}</p>}
   <div className="actions"><Link className="btn btn-primary btn-lg" to="/hours">Мой путь</Link></div>
  </div><span className="hero-art" aria-hidden="true"><Icon name="heart"/></span></div></section>}

  {review&&<section className="sec" aria-labelledby="refl-next">
   <div className="sec-head"><h2 className="h2" id="refl-next">Что дальше</h2></div>
   <div className="grid-2">
    <div className="card action-card">
     <div className="who"><span className="ph ph-sm ph-b" aria-hidden="true">{initials(review.assigned_staff_name)}</span><div><b>{firstName(review.assigned_staff_name)||review.assigned_staff_name}</b><span className="meta">{stamp(review.created_at)}</span></div></div>
     {review.public_message&&<p className="p refl-review">{review.public_message}</p>}
    </div>
    {review.next_date&&<NextDate date={review.next_date} fallback={`${review.decision==='next_date'?value.title:decisionLabels[review.decision]??value.title}, ${dayMonth(`${review.next_date}T12:00:00Z`,'UTC')}`}/>}
   </div>
  </section>}

  {hard&&<section className="sec" aria-labelledby="refl-help">
   <div className="sec-head"><h2 className="h2" id="refl-help">Что может помочь</h2></div>
   <div className="grid-3">
    <div className="card action-card"><span className="art art-v" aria-hidden="true"><Icon name="users"/></span><h3 className="h3">Супервизия с психологом</h3><div className="actions"><Link className="btn btn-secondary" to="/webinars">Записаться</Link></div></div>
    <div className="card action-card"><span className="art art-g" aria-hidden="true"><Icon name="message"/></span><h3 className="h3">Разговор с опытным волонтёром</h3><div className="actions"><Link className="btn btn-secondary" to="/messages">Написать</Link></div></div>
    <div className="card action-card"><span className="art art-y" aria-hidden="true"><svg className="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/></svg></span><h3 className="h3">Пауза без потери места</h3><p className="p">Группа подождёт, приглашать не будем</p><div className="actions"><Link className="btn btn-secondary" to="/profile?tab=pause">Поставить паузу</Link></div></div>
   </div>
  </section>}
 </>;
}

/** The date the coordinator suggested: the own занятие on that day when there is one (answer it right here), otherwise the date itself. */
function NextDate({date,fallback}:{date:string;fallback:string}){
 const day=useOwnDay(date),client=useQueryClient(),{toast}=useToast();
 const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null);
 const item=(day.data??[]).filter(row=>row.status==='invited'||row.status==='confirmed').sort((a,b)=>Date.parse(a.starts_at)-Date.parse(b.starts_at))[0];
 const badge=dateBadge(date),canConfirm=!!item&&item.status==='invited'&&item.allowed_actions.includes('confirm');
 async function confirm(){
  if(!item)return;setBusy(true);setError(null);
  try{await command(`/assignments/${item.id}/confirm`,{expected_version:item.version});await client.invalidateQueries({queryKey:keys.all('activities')});toast('Участие подтверждено');}
  catch(e){setError(e);}finally{setBusy(false);}
 }
 let main:ReactNode=null;
 if(canConfirm)main=<Button variant="secondary" loading={busy} onClick={()=>void confirm()}>Я приду</Button>;
 else if(item?.status==='confirmed')main=<Link className="btn btn-secondary" to={`/my/assignments/${item.id}/preparation`}>Подготовиться</Link>;
 return <div className="card action-card">
  <span className="day y" aria-hidden="true"><b>{badge.day}</b><span>{badge.weekday}</span></span>
  <h3 className="h3">{item?`${item.title}, ${timeOnly(item.starts_at,item.timezone)}`:fallback}</h3>
  <div className="actions">{main}<Link className={`btn ${main?'btn-ghost':'btn-secondary'}`} to="/messages">Обсудить</Link></div>
  {error?<p className="followup-error" role="alert">{errorText(error)}</p>:null}
 </div>;
}
