import {useState,type FormEvent} from 'react';
import {Link,useParams} from 'react-router-dom';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {Button,EmptyState,ErrorState,Icon,LoadingState,Textarea,useToast} from '../../ui';
import {command,readPreparation,type Preparation} from './api';
import {cap,coordinatorContact,dayMonth,errorText,firstName,initials,isFirstExit,leadContact,stamp,timeOnly,useOwnHours,useOwnProfile,whenLong} from './volunteerApi';
import './followups.css';

export function FirstShiftPage(){const {id=''}=useParams();return <FirstShiftWorkspace key={id} id={id}/>;}

function FirstShiftWorkspace({id}:{id:string}){
 const client=useQueryClient(),{toast}=useToast();
 const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null),[confirmNo,setConfirmNo]=useState(false);
 const [question,setQuestion]=useState(''),[restricted,setRestricted]=useState(false),[asking,setAsking]=useState(false),[askError,setAskError]=useState<unknown>(null);
 const data=useQuery({queryKey:keys.detail('assignment-preparation',id),queryFn:({signal})=>readPreparation(id,signal),enabled:!!id,staleTime:0,refetchInterval:15000});
 const hours=useOwnHours(),profile=useOwnProfile();
 async function refresh(){await Promise.all([client.invalidateQueries({queryKey:keys.detail('assignment-preparation',id)}),client.invalidateQueries({queryKey:keys.all('activities')})]);}
 async function answer(action:'confirm'|'decline'|'cancel'){
  if(!data.data)return;setBusy(true);setError(null);
  try{await command(`/assignments/${id}/${action}`,{expected_version:data.data.assignment_version});setConfirmNo(false);await refresh();toast(action==='confirm'?'Участие подтверждено':'Координатор увидит, что ты не сможешь');}
  catch(e){setError(e);}finally{setBusy(false);}
 }
 async function toggle(key:string){
  if(!data.data)return;setBusy(true);setError(null);const value=data.data;
  const checked=value.checklist.filter(item=>item.checked?item.key!==key:item.key===key).map(item=>item.key);
  try{const saved=await command<Preparation>(`/me/assignments/${id}/checklist`,{expected_version:value.version,checklist_version:value.checklist_version,checked_keys:checked},'PUT');client.setQueryData(keys.detail('assignment-preparation',id),saved);}
  catch(e){setError(e);}finally{setBusy(false);}
 }
 async function ask(event:FormEvent,kind:string){
  event.preventDefault();if(!question.trim())return;setAsking(true);setAskError(null);
  try{await command(`/me/assignments/${id}/questions`,{kind,text:question,restricted});setQuestion('');setRestricted(false);await refresh();toast('Вопрос отправлен');}
  catch(e){setAskError(e);}finally{setAsking(false);}
 }
 if(!id)return <EmptyState title="Открой памятку из своего занятия"/>;
 if(data.isPending)return <LoadingState/>;
 if(data.error)return <ErrorState error={data.error} retry={()=>data.refetch()}/>;
 const p=data.data;
 const invited=p.status==='invited'&&p.allowed_actions.includes('confirm');
 const confirmed=p.status==='confirmed'&&p.group_briefing_available;
 const off=!invited&&!confirmed;
 const first=isFirstExit(hours.data,id),name=firstName(profile.data?.display_name);
 const title=off?(first?'Первый выход':'Перед занятием'):name?`${name}, тебя ждут`:'Тебя ждут';
 const done=p.checklist.filter(item=>item.checked).length;
 const tasks=p.tasks.split(/\n+/).map(line=>line.replace(/^[\s•\-–—]+/,'').trim()).filter(Boolean);
 const place=p.location.trim();
 // The card shows the one person who meets the volunteer: the group leader, else the coordinator.
 const host=leadContact(p.contacts)??coordinatorContact(p.contacts)??p.contacts[0];
 return <div className="prep-page">
  <Link className="back" to="/my/schedule"><Icon name="chevron-left"/>Мои занятия</Link>
  <div className="page-head"><h1 className="h1">{title}</h1></div>
  {off?<section className="card-hero calm"><div className="hero-grid"><div className="hero-copy">
   <p className="eyebrow">Планы изменились</p>
   <h2 className="hero-title">Подберём другую дату</h2>
   <p className="hero-sub">{['cancelled','declined'].includes(p.status)?`Координатор уже знает, что ${dayMonth(p.starts_at,p.timezone)} ты не сможешь.`:`${p.title}, ${dayMonth(p.starts_at,p.timezone)}.`}</p>
   <div className="actions"><Link className="btn btn-primary btn-lg" to="/messages">Написать координатору</Link></div>
  </div><span className="hero-art" aria-hidden="true"><Icon name="calendar"/></span></div></section>
  :<section className="card-hero"><div className="hero-grid"><div className="hero-copy">
   <p className="eyebrow">{first?'Твой первый выход':'Ближайшее занятие'}</p>
   <h2 className="hero-when">{whenLong(p.starts_at,p.timezone)}</h2>
   <p className="hero-sub">{[p.title,place].filter(Boolean).join(', ')}. До {timeOnly(p.ends_at,p.timezone)}.</p>
   {confirmNo?<div className="hero-note" role="group" aria-label="Отказ от занятия"><span className="strong">Предупредить координатора, что не сможешь?</span><Button size="sm" loading={busy} onClick={()=>void answer(invited?'decline':'cancel')}>Да, не смогу</Button><Button size="sm" variant="ghost" disabled={busy} onClick={()=>invited?void answer('confirm'):setConfirmNo(false)}>Я приду</Button></div>
   :invited?<div className="actions"><Button size="lg" loading={busy} onClick={()=>void answer('confirm')}>Я приду</Button><Button size="lg" variant="secondary" disabled={busy} onClick={()=>setConfirmNo(true)}>Не смогу</Button></div>
   :<div className="actions"><Link className="btn btn-primary btn-lg" to={`/me/group?assignment_id=${id}`}>Познакомиться с группой</Link>{p.allowed_actions.includes('cancel')&&<Button size="lg" variant="ghost" disabled={busy} onClick={()=>setConfirmNo(true)}>Не смогу прийти</Button>}</div>}
  </div><span className="hero-art" aria-hidden="true"><Icon name="palette"/></span></div></section>}
  {error?<p className="followup-error" role="alert">{errorText(error)}</p>:null}

  {!off&&<section className="sec" aria-labelledby="prep-who">
   <div className="sec-head"><h2 className="h2" id="prep-who">Кто встретит и что делать</h2></div>
   <div className="grid-3">
    {host&&<div className="card action-card">
     <div className="who"><span className="ph ph-lg ph-o" aria-hidden="true">{initials(host.display_name)}</span><div><b>{host.display_name}</b><span className="meta">{host.role}</span></div></div>
     <div className="actions"><Link className="btn btn-secondary" to="/messages">Написать</Link></div>
    </div>}
    <div className="card action-card">
     <div className="row"><span className="art art-y" aria-hidden="true"><Icon name="hand"/></span><h3 className="h3">{p.role_title}</h3></div>
     {tasks.length>0&&<div className="rows">{tasks.map((task,index)=><div className="rowi" key={index}><span>{task}</span></div>)}</div>}
    </div>
    {place&&<div className="card action-card">
     <div className="row"><span className="art art-b" aria-hidden="true"><Icon name="pin"/></span><h3 className="h3">{cap(place)}</h3></div>
     <div className="actions"><a className="btn btn-secondary" href={`https://yandex.ru/maps/?text=${encodeURIComponent(place)}`} target="_blank" rel="noreferrer">Маршрут</a></div>
    </div>}
   </div>
  </section>}

  {!off&&<section className="sec" aria-labelledby="prep-check">
   <div className="sec-head"><h2 className="h2" id="prep-check">Перед выходом</h2><b className="num prep-count">{done} из {p.checklist.length}</b></div>
   <div className="card">{p.checklist.map(item=><div className={`tick${item.checked?' done':''}`} key={item.key}>
    <button type="button" className={`box${item.checked?' on':''}`} aria-pressed={item.checked} aria-label={item.title} aria-disabled={!confirmed||undefined} disabled={busy} onClick={()=>{if(confirmed)void toggle(item.key);}}><Icon name="check"/></button>
    <span className="grow">{item.title}</span>
    {item.href&&confirmed&&<Link className="quiet-link" to={item.href}>Открыть</Link>}
   </div>)}</div>
   {!confirmed&&<p className="p prep-locked">Отметить пункты можно после ответа «Я приду».</p>}
  </section>}

  <section className="sec" id="question" aria-labelledby="prep-ask">
   <div className="sec-head"><h2 className="h2" id="prep-ask">Есть вопрос?</h2></div>
   <div className="grid-2 prep-ask-grid">
    <form className="card stack prep-ask" onSubmit={event=>void ask(event,off?'alternate_date':'question')}>
     <label className="field"><span className="label">Вопрос координатору</span><Textarea className="prep-question" disabled={asking} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Что хочется уточнить до занятия" required maxLength={6000}/></label>
     <label className="check"><input type="checkbox" disabled={asking} checked={restricted} onChange={e=>setRestricted(e.target.checked)}/><span>Личный вопрос, только для специалиста</span></label>
     {askError?<p className="followup-error" role="alert">{errorText(askError)}</p>:null}
     <div className="row"><Button type="submit" variant="secondary" loading={asking}>Отправить</Button></div>
    </form>
    {p.questions.length>0&&<div className="card stack prep-thread" aria-label="Твои вопросы">{p.questions.map(item=><div className="stack prep-qa" key={item.id}>
     <div className="bubble bubble-me">{item.text}</div>
     {item.public_answer&&<><div className="bubble bubble-them">{item.public_answer}</div>{item.answered_at&&<span className="meta">{stamp(item.answered_at)}</span>}</>}
    </div>)}</div>}
   </div>
  </section>

  {!off&&<section className="sec">
   <Link className="card-soft row prep-after" to={`/my/assignments/${id}/reflection`}>
    <span className="row"><span className="art art-v" aria-hidden="true"><Icon name="message"/></span><span className="h3">После занятия расскажи, как прошло</span></span>
    <Icon name="chevron-right"/>
   </Link>
  </section>}
 </div>;
}
