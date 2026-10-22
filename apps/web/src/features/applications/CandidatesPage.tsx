import {useEffect,useRef,useState} from 'react';
import {Link, useLocation, useParams, useSearchParams} from 'react-router-dom';
import {Button, Card, Combobox, ErrorState, Field, Input, LoadingState, Segmented, SectionTabs, Textarea, Icon, cx} from '../../ui';
import {getSession} from '../../api/transport';
import {volunteersTabs} from '../../app/sectionTabs';
import {Candidate, CandidateStage, Note, useCandidate, useCandidateSummary, useCandidates, useCommand, useDraft, useNotes, useRequests} from './api';
import {CoordinatorRequest} from './Requests';
import {formatAnswer} from './ApplicationPage';
import type {FormContent} from './form';
import './applications.css';
const states:Record<string,string>={new:'Новая анкета',reviewing:'На рассмотрении',discussed:'Обсудили',paused:'На паузе',closed:'Закрыта'};
const meetingLabels:Record<string,string>={unavailable:'Встречи недоступны',none:'Встреча не назначена',booked:'Встреча назначена',completed:'Встреча состоялась',cancelled:'Встреча отменена',missed:'Не пришёл на встречу'};
function preparationLabel(candidate:Candidate){const progress=candidate.progress.introduction;return progress.status==='unavailable'?'Знакомство недоступно':progress.status==='completed'?'Знакомство завершено':`${progress.completed_lessons} из ${progress.total_lessons} шагов`;}
function name(candidate:Candidate){return [candidate.revision.answers.firstName,candidate.revision.answers.lastName].filter(Boolean).join(' ');}

/* «Кандидаты»: four funnel stages stacked, a side panel opens on a click. */
type FunnelStage=Exclude<CandidateStage,'done'>;
const stageTitles:Record<FunnelStage,string>={new:'Новые анкеты',intro:'Знакомятся с фондом',interview:'Собеседование',ready:'Готовы к первому выходу',closed:'Отказы и пауза'};
const funnel:FunnelStage[]=['new','intro','interview','ready'];
const order:Record<string,number>={new:0,intro:1,interview:2,ready:3};
const tones=['tone-v','tone-b','tone-o','tone-p','tone-g'];
const msk='Europe/Moscow',day=86400000,lateAfter=2;
const toneOf=(id:string)=>tones[[...id].reduce((sum,char)=>sum+char.charCodeAt(0),0)%tones.length];
const initials=(person:Candidate)=>name(person).split(' ').map(word=>word[0]).slice(0,2).join('');
const plural=(n:number,one:string,few:string,many:string)=>{const a=n%10,b=n%100;return a===1&&b!==11?one:a>=2&&a<=4&&(b<12||b>14)?few:many;};
const shortDate=(value:string)=>new Date(value).toLocaleDateString('ru-RU',{day:'numeric',month:'short',timeZone:msk}).replace('.','');
function longDate(value:string){const date=new Date(value);return date.toLocaleDateString('ru-RU',{day:'numeric',month:'long',...(date.getFullYear()!==new Date().getFullYear()&&{year:'numeric'}),timeZone:msk});}
function slotLabel(value:string){const date=new Date(value),part=(options:Intl.DateTimeFormatOptions)=>date.toLocaleString('ru-RU',{...options,timeZone:msk});return `${part({weekday:'short'})} ${shortDate(value)}, ${part({hour:'2-digit',minute:'2-digit'})}`;}
const waitingDays=(person:Candidate)=>Math.floor((Date.now()-new Date(person.submitted_at).getTime())/day);
const lessons=(done:number,total:number)=>`${done} из ${total} ${plural(total,'урока','уроков','уроков')}`;
const interest=(person:Candidate)=>formatAnswer(person.revision.answers.directions)||formatAnswer(person.revision.answers.skills)||'Пока не знает';
function rowValue(person:Candidate):[string,boolean]{
  const intro=person.progress.introduction,meeting=person.progress.interview;
  if(person.stage==='new'){const days=waitingDays(person);return days>=lateAfter?[`ждёт ${days} ${plural(days,'день','дня','дней')}`,true]:[days<1?'сегодня':days<2?'вчера':shortDate(person.submitted_at),false];}
  if(person.stage==='intro')return [lessons(intro.completed_lessons,intro.total_lessons),false];
  if(person.stage==='interview')return [meeting.status==='booked'&&meeting.starts_at?slotLabel(meeting.starts_at):'без даты',false];
  if(person.stage==='ready')return [person.stage_since?`с ${shortDate(person.stage_since)}`:'',false];
  return [person.stage_since?shortDate(person.stage_since):'',false];
}
const remindedRecently=(person:Candidate)=>person.history.some(event=>event.kind==='reminded'&&Date.now()-new Date(event.created_at).getTime()<20*3600000);
function contact(person:Candidate){
  const answers=person.revision.answers,telegram=String(answers.telegram||'').trim().replace(/^@/,''),phone=String(answers.phone||'').trim(),email=String(answers.email||'').trim();
  if(telegram)return <a href={`https://t.me/${encodeURIComponent(telegram)}`} target="_blank" rel="noreferrer">Telegram @{telegram}</a>;
  if(phone)return <a href={`tel:${phone.replace(/[^\d+]/g,'')}`}>{phone}</a>;
  return email?<a href={`mailto:${email}`}>{email}</a>:'Не указана';
}
function experience(person:Candidate){
  const answers=person.revision.answers,text=[answers.volExpText,answers.specialExpText].map(value=>String(value||'').trim()).filter(Boolean).join('. ');
  return text||formatAnswer(answers.skills)||(answers.volExp==='Да'?'Был волонтёром':'Без опыта волонтёрства');
}
const when=(person:Candidate)=>[formatAnswer(person.revision.answers.participation),person.revision.answers.online===true&&'можно онлайн'].filter(Boolean).join(', ')||'Не указано';

function StageBlock({stage,q,selected,onPick}:{stage:FunnelStage;q:string;selected:string;onPick:(person:Candidate)=>void}){
  const [all,setAll]=useState(false);
  const query=new URLSearchParams({stage,limit:all?'100':'5',...(q&&{q})}).toString(),list=useCandidates(query,true),summary=useCandidateSummary();
  const items=list.data?.items??[],shown=all?items:items.slice(0,4),count=summary.data?.[stage]??list.data?.total;
  return <section className="cand-stage" aria-label={stageTitles[stage]}>
    <div className="cand-stage-head"><h2 className="h3">{stageTitles[stage]}</h2>{count!==undefined&&<span className={cx('cand-n',stage==='new'&&count>0&&'is-hot')}>{count}</span>}</div>
    {list.isPending?<LoadingState/>:list.error?<ErrorState error={list.error} retry={()=>void list.refetch()}/>:!shown.length?<p className="p cand-empty">Никого</p>:<>
      {shown.map(person=>{const [value,late]=rowValue(person);return <button type="button" key={person.id} className={cx('cand-row',selected===person.id&&'is-on')} aria-pressed={selected===person.id} onClick={()=>onPick(person)}>
        <span className="cand-person"><span className={cx('cand-ph',toneOf(person.id))} aria-hidden="true">{initials(person)}</span><span className="cand-name">{name(person)}</span></span>
        <span className="p">{interest(person)}</span>
        <span className={late?'cand-late':'meta'}>{value}</span>
        <Icon name="chevron-right"/>
      </button>;})}
      {!all&&(list.data?.total??0)>4&&<button type="button" className="cand-more" onClick={()=>setAll(true)}>Показать все</button>}
    </>}
  </section>;
}

function CandidatePanel({id,seed,onClose,back}:{id:string;seed?:Candidate;onClose:()=>void;back:string}){
  const candidate=useCandidate(id,seed),heading=useRef<HTMLHeadingElement>(null),panel=useRef<HTMLElement>(null);
  const [declining,setDeclining]=useState(false),[reminded,setReminded]=useState(false);
  const review=useCommand<Candidate>(`/api/v1/coord/candidates/${id}/review`),reopen=useCommand<Candidate>(`/api/v1/coord/candidates/${id}/reopen`),remind=useCommand<Candidate>(`/api/v1/coord/candidates/${id}/remind`);
  const canReview=!!getSession()?.permissions.includes('candidates.review'),me=getSession()?.user_id;
  useEffect(()=>{panel.current?.scrollIntoView?.({block:'nearest'});heading.current?.focus();},[]);
  if(candidate.isPending)return <aside className="cand-panel" ref={panel}><LoadingState/></aside>;
  if(candidate.error||!candidate.data)return <aside className="cand-panel" ref={panel}><ErrorState error={candidate.error} retry={()=>void candidate.refetch()}/></aside>;
  const person=candidate.data,intro=person.progress.introduction,meeting=person.progress.interview,at=order[person.stage]??-1,busy=review.isPending||reopen.isPending||remind.isPending;
  const error=review.error||reopen.error||remind.error;
  const path=[
    {title:'Анкета',note:longDate(person.submitted_at),done:at>0},
    {title:'Знакомство с фондом',note:intro.status==='completed'?'пройдено':intro.status==='in_progress'||(intro.status==='not_started'&&at===1)?lessons(intro.completed_lessons,intro.total_lessons):'',done:intro.status==='completed'||(intro.status==='unavailable'&&at>1)},
    {title:'Собеседование',note:meeting.status==='booked'&&meeting.starts_at?slotLabel(meeting.starts_at):meeting.status==='completed'?'пройдено':meeting.status==='missed'?'не состоялось':meeting.status==='cancelled'?'отменено':'',done:meeting.status==='completed'||at>2},
    {title:'Первый выход',note:'',done:false},
  ];
  const decide=(state:'reviewing'|'closed',public_message:string)=>review.mutateAsync({body:{expected_version:person.version,state,public_message,assigned_coordinator_id:person.assigned_coordinator_id??(state==='reviewing'?me:null)}});
  const nudged=reminded||remindedRecently(person);
  return <aside className="cand-panel" aria-labelledby="cand-name" ref={panel}>
    <div className="cand-panel-head">
      <div className="cand-person"><span className={cx('cand-ph is-lg',toneOf(person.id))} aria-hidden="true">{initials(person)}</span><div className="cand-who"><h2 className="h3" id="cand-name" tabIndex={-1} ref={heading}>{name(person)}</h2><span className="meta">Анкета от {longDate(person.submitted_at)}</span></div></div>
      <button type="button" className="cand-close" aria-label="Закрыть" onClick={onClose}><Icon name="x"/></button>
    </div>
    <dl className="cand-dl">
      <dt>Интересно</dt><dd>{interest(person)}</dd>
      <dt>Когда удобно</dt><dd>{when(person)}</dd>
      <dt>Опыт</dt><dd>{experience(person)}</dd>
      <dt>Связь</dt><dd>{contact(person)}</dd>
    </dl>
    <Link className="btn btn-ghost btn-sm cand-full" to={`/fund/candidates/${person.id}`} state={{back}}>Вся анкета</Link>
    <div className="cand-block"><ol className="cand-path" aria-label="Путь кандидата">{path.map((step,index)=>{const now=!step.done&&index===at;return <li key={step.title} className={cx('cand-step',step.done&&'is-done',now&&'is-now')} aria-current={now?'step':undefined}>
      <span className="cand-mark">{step.done?<Icon name="check"/>:index+1}</span><span><b>{step.title}</b>{step.note&&<span className="meta">{step.note}</span>}</span>
    </li>;})}</ol></div>
    {person.stage==='closed'&&<p className="meta cand-state">{person.submission_state==='withdrawn'?'Кандидат отозвал анкету':person.review_state==='paused'?'Анкета на паузе':'Кандидату отказали'}</p>}
    {declining?<div className="cand-block"><h3 className="h3">Отказать кандидату?</h3><p className="p">Анкета закроется, кандидат увидит это в кабинете. Вернуть её можно из полной анкеты.</p><div className="cand-actions"><Button variant="danger" loading={review.isPending} onClick={()=>void decide('closed','').then(onClose).catch(()=>{})}>Отказать</Button><Button variant="ghost" disabled={busy} onClick={()=>setDeclining(false)}>Не отказывать</Button></div></div>:
    <div className="cand-actions">
      {person.stage==='new'&&canReview&&<><Button loading={review.isPending} disabled={busy} onClick={()=>void decide('reviewing','Анкета принята. Следующий шаг: знакомство с фондом.').catch(()=>{})}>Принять анкету</Button><Button variant="ghost" disabled={busy} onClick={()=>setDeclining(true)}>Отказать</Button></>}
      {person.stage==='intro'&&<>{canReview&&<Button variant="secondary" loading={remind.isPending} disabled={busy||nudged} onClick={()=>void remind.mutateAsync({body:{expected_version:person.version}}).then(()=>setReminded(true)).catch(()=>{})}>{nudged?'Напоминание отправлено':'Напомнить про знакомство'}</Button>}<Link className="btn btn-ghost" to="/fund/messages">Написать</Link></>}
      {person.stage==='interview'&&(meeting.status==='booked'&&meeting.booking_id?<Link className="btn btn-primary" to={`/fund/interviews?booking=${meeting.booking_id}`}>Открыть собеседование</Link>:<><Link className="btn btn-primary" to="/fund/interviews/availability">Предложить время</Link><Link className="btn btn-ghost" to="/fund/messages">Написать</Link></>)}
      {person.stage==='ready'&&<Link className="btn btn-primary" to="/fund/opportunities">Подобрать первое мероприятие</Link>}
      {person.stage==='closed'&&canReview&&person.submission_state==='submitted'&&<Button variant="secondary" loading={reopen.isPending} onClick={()=>void reopen.mutateAsync({body:{expected_version:person.version}}).catch(()=>{})}>Вернуться к рассмотрению</Button>}
    </div>}
    {error&&<p role="alert" className="cand-error">{error.message}</p>}
  </aside>;
}

export function CandidatesPage() {
  const [search,setSearch]=useSearchParams(),q=search.get('q')||'',selected=search.get('candidate')||'';
  const [picked,setPicked]=useState<Candidate>(),[archive,setArchive]=useState(false);
  const summary=useCandidateSummary(),fresh=useCandidates('stage=new&limit=5');
  const query=search.toString(),back='/fund/candidates'+(query?'?'+query:'');
  const change=(key:string,value:string,replace=true)=>setSearch(previous=>{const next=new URLSearchParams(previous);value?next.set(key,value):next.delete(key);return next;},{replace});
  const pick=(person:Candidate)=>{setPicked(person);change('candidate',selected===person.id?'':person.id,false);};
  const waiting=summary.data?.new??0,first=fresh.data?.items[0];
  return <div className="cand-page">
    <SectionTabs className="cand-head" label="Волонтёры" tabs={volunteersTabs} actions={<label className="cand-search"><span className="sr-only">Найти кандидата</span><Icon name="search"/><Input type="search" placeholder="Имя или навык" value={q} onChange={event=>change('q',event.target.value)}/></label>}/>
    {waiting>0&&<section className="card-hero cand-hero" aria-labelledby="cand-hero">
      <div className="hero-grid"><div className="hero-copy">
        <h2 className="hero-title" id="cand-hero">{waiting} {plural(waiting,'новая анкета ждёт','новые анкеты ждут','новых анкет ждут')} ответа</h2>
        <p className="cand-hero-line">Ответьте в течение двух дней, пока человек не остыл</p>
        <div className="actions"><Button size="lg" disabled={!first} onClick={()=>first&&pick(first)}>Разобрать</Button></div>
      </div><span className="hero-art" aria-hidden="true"><Icon name="inbox"/></span></div>
    </section>}
    <div className="cand-split">
      <div className="cand-main">
        {funnel.map(stage=><StageBlock key={stage} stage={stage} q={q} selected={selected} onPick={pick}/>)}
        {!!summary.data?.closed&&(archive?<StageBlock stage="closed" q={q} selected={selected} onPick={pick}/>:<button type="button" className="cand-archive" onClick={()=>setArchive(true)}>{stageTitles.closed}<span className="cand-n">{summary.data.closed}</span></button>)}
      </div>
      {selected&&<CandidatePanel key={selected} id={selected} seed={picked?.id===selected?picked:undefined} back={back} onClose={()=>change('candidate','',false)}/>}
    </div>
  </div>;
}
export function CandidateDetailPage() {
  const {id=''}=useParams(), location=useLocation(), candidate=useCandidate(id),formQuery=useDraft(),requests=useRequests(true);
  const [tab,setTab]=useState('overview'),[message,setMessage]=useState(''),[note,setNote]=useState(''),[reviewState,setReviewState]=useState('reviewing');
  const canNote=!!getSession()?.permissions.includes('candidates.notes'),canReview=!!getSession()?.permissions.includes('candidates.review');
  const notes=useNotes(id,canNote),review=useCommand<Candidate>(`/api/v1/coord/candidates/${id}/review`),reopen=useCommand<Candidate>(`/api/v1/coord/candidates/${id}/reopen`),addNote=useCommand<Note>(`/api/v1/coord/candidates/${id}/notes`);
  if(candidate.isPending)return <LoadingState/>;
  if(candidate.error||!candidate.data)return <ErrorState error={candidate.error} retry={()=>void candidate.refetch()}/>;
  const person=candidate.data,form=formQuery.data?.form.content as unknown as FormContent|undefined;
  const back=location.state?.back||'/fund/candidates';
  return <div className="ap-page"><Link className="ap-back" to={back} onClick={()=>{if(location.state?.scroll)setTimeout(()=>window.scrollTo(0,location.state.scroll),0);}}><Icon name="chevron-left"/>К кандидатам</Link><Card><div className="ap-profile-head"><span className="ap-avatar ap-avatar-lg">{name(person).split(' ').map(word=>word[0]).slice(0,2).join('')}</span><div><p className="ap-eyebrow">Анкета волонтёра</p><h1 className="h1">{name(person)}</h1><span className="ap-tag">{states[person.review_state]}</span></div></div><Segmented label="Раздел карточки" value={tab} onChange={setTab} options={[{value:'overview',label:'Обзор'},{value:'answers',label:'Анкета'},{value:'history',label:'История'}]}/></Card>
    {tab==='overview'&&<><div className="ap-two-cols ap-section"><Card><h2 className="h2">Контакты и интересы</h2><dl className="ap-details">{['phone','email','telegram','directions','skills','participation'].filter(key=>person.revision.answers[key]).map(key=><div key={key}><dt>{({phone:'Телефон',email:'Почта',telegram:'Telegram',directions:'Направления',skills:'Навыки',participation:'Как часто'})[key]}</dt><dd>{formatAnswer(person.revision.answers[key])}</dd></div>)}</dl><div className="ap-progress-stat"><strong>{preparationLabel(person)}</strong><p>{meetingLabels[person.progress.interview.status]}{person.progress.interview.starts_at&&<>, {new Date(person.progress.interview.starts_at).toLocaleString('ru',{timeZone:'Europe/Moscow'})} МСК</>}</p></div><p className="ap-muted">Рассмотрение анкеты, знакомство и запись на встречу идут независимо.</p><Link className="btn btn-secondary" to={`/fund/interviews?candidate=${person.id}`}>Встречи кандидата</Link></Card>
      <Card><h2 className="h2">Рассмотрение анкеты</h2><p className="ap-muted">Координатор: {person.assigned_coordinator_id===getSession()?.user_id?'Вы':person.assigned_coordinator_id?'Назначен':'Пока не назначен'}</p>{canReview&&(person.review_state==='closed'||person.review_state==='paused')?<Button disabled={reopen.isPending} onClick={()=>reopen.mutate({body:{expected_version:person.version}})}>Вернуться к рассмотрению</Button>:canReview?<><Combobox label="Решение" value={reviewState} onChange={setReviewState} options={Object.entries(states).filter(([value])=>value!=='new').map(([value,label])=>({value,label}))}/><Field label="Сообщение кандидату" htmlFor="review-message" hint="Этот текст будет виден в личном кабинете."><Textarea id="review-message" value={message} onChange={event=>setMessage(event.target.value)} maxLength={4000}/></Field><div className="ap-actions"><Button disabled={review.isPending} onClick={()=>review.mutate({body:{expected_version:person.version,state:reviewState,public_message:message,assigned_coordinator_id:person.assigned_coordinator_id}})}>Сохранить решение</Button><Button variant="ghost" disabled={review.isPending} onClick={()=>review.mutate({body:{expected_version:person.version,state:'reviewing',public_message:'',assigned_coordinator_id:getSession()?.user_id}})}>Взять в работу</Button></div></>:<p>Для изменения решения нужны права координатора.</p>}{(review.error||reopen.error)&&<p role="alert" className="ap-error">{(review.error||reopen.error)?.message}</p>}</Card></div>
      <section className="ap-section"><h2 className="h2">Вопросы и просьбы</h2>{requests.isPending?<LoadingState/>:requests.error?<ErrorState error={requests.error} retry={()=>void requests.refetch()}/>:requests.data?.filter(request=>request.application_id===person.id).length?requests.data.filter(request=>request.application_id===person.id).map(request=><CoordinatorRequest key={request.id} request={request}/>):<p className="ap-muted">Пока нет обращений.</p>}</section>
      {canNote&&<section className="ap-section"><Card><h2 className="h2">Внутренние заметки</h2><p className="ap-muted">Доступны только сотрудникам с разрешением на заметки.</p>{notes.isPending?<LoadingState/>:notes.error?<ErrorState error={notes.error} retry={()=>void notes.refetch()}/>:notes.data?.map(item=><div className="ap-request" key={item.id}><small>{new Date(item.created_at).toLocaleString('ru')}</small><p>{item.text}</p></div>)}<Field label="Новая заметка" htmlFor="private-note"><Textarea id="private-note" value={note} onChange={event=>setNote(event.target.value)} maxLength={8000}/></Field><Button disabled={!note.trim()||addNote.isPending} onClick={()=>void addNote.mutateAsync({body:{text:note}}).then(()=>setNote('')).catch(()=>{})}>Добавить заметку</Button>{addNote.error&&<p role="alert" className="ap-error">{addNote.error.message}</p>}</Card></section>}</>}
    {tab==='answers'&&<Card className="ap-section"><h2 className="h2">Анкета, версия {person.revision.number}</h2>{form?.steps.map(section=><div key={section.id}><h3 className="h3">{section.title}</h3><dl className="ap-details">{section.fields.filter(field=>person.revision.answers[field.id]!==undefined).map(field=><div key={field.id}><dt>{field.label}</dt><dd>{formatAnswer(person.revision.answers[field.id])}</dd></div>)}</dl></div>)}</Card>}
    {tab==='history'&&<Card className="ap-section"><h2 className="h2">История</h2>{person.history.map(event=><div className="ap-timeline" key={event.id}><small>{new Date(event.created_at).toLocaleString('ru')}</small><p>{event.kind==='reminded'?'Напомнили про знакомство с фондом':event.public_message||states[event.state]}</p></div>)}<h3 className="h3">Ревизии анкеты</h3>{person.revisions.map(revision=><details className="ap-request" key={revision.id}><summary>Версия {revision.number}, {new Date(revision.created_at).toLocaleString('ru')}</summary><dl className="ap-details">{Object.entries(revision.answers).map(([key,value])=><div key={key}><dt>{form?.steps.flatMap(part=>part.fields).find(field=>field.id===key)?.label||key}</dt><dd>{formatAnswer(value)}</dd></div>)}</dl></details>)}</Card>}
  </div>;
}
