import {useEffect,useState,type FormEvent} from 'react';
import {Link,useNavigate,useParams,useSearchParams} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {Button,Dialog,EmptyState,ErrorState,Field,Icon,LoadingState,Textarea,cx} from '../../ui';
import {nameWords} from '../../ui/names';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import {useLearningCommand,useLesson,usePreparation,type Assignment} from './api';
import {useLibrary,useLibraryText,type LibraryItem,type LibraryKind} from './libraryApi';
import {AssessmentPlayer} from './OnboardingPage';
import {ContentBlock,type Block} from './Blocks';
import {useScenarios,useSimulationHistory,type ScenarioPublic} from '../simulator/api';
import {useStudioCommand,useWebinars,type Webinar} from '../studio/api';
import {SummaryPublishedDialog} from '../studio/SummaryPublishedDialog';
import './learning.css';
import './builder.css';
type Submission=components['schemas']['TaskSubmissionView'];

/** One place in a track: a lesson or the closing test. */
type Step={id:string;title:string;done:boolean;href:string};
const lessonHref=(lessonId:string,assignmentId:string)=>`/academy/lessons/${encodeURIComponent(lessonId)}?assignment=${encodeURIComponent(assignmentId)}`;
export function trackSteps(item:Assignment):Step[]{
 const steps=item.lessons.map(lesson=>({id:lesson.id,title:lesson.title,done:lesson.completed,href:lessonHref(lesson.id,item.id)}));
 if(item.assessment_version_id)steps.push({id:'assessment',title:'Тест по материалам',done:item.latest_attempt_state==='submitted',href:lessonHref('assessment',item.id)});
 return steps;
}
const nextStep=(item:Assignment)=>{const steps=trackSteps(item);return steps.find(step=>!step.done)??steps[0];};

const moscow='Europe/Moscow';
const fmt=(value:string,options:Intl.DateTimeFormatOptions)=>new Intl.DateTimeFormat('ru-RU',{...options,timeZone:moscow}).format(new Date(value));
const endsAt=(item:Webinar)=>new Date(item.starts_at).getTime()+item.duration_minutes*60_000;
const inMonth=['январе','феврале','марте','апреле','мае','июне','июле','августе','сентябре','октябре','ноябре','декабре'];
const yearMonth=(value:Date)=>{const parts=new Intl.DateTimeFormat('en-US',{year:'numeric',month:'numeric',timeZone:moscow}).formatToParts(value);const part=(type:string)=>Number(parts.find(item=>item.type===type)?.value);return {year:part('year'),month:part('month')};};
/** «Пройдено в октябре», with the year only when it is not this year. */
export function completedLabel(completedAt?:string|null,now=new Date()){
 if(!completedAt)return 'Пройдено';
 const done=yearMonth(new Date(completedAt)),today=yearMonth(now);
 return `Пройдено в ${inMonth[done.month-1]}${done.year===today.year?'':` ${done.year}`}`;
}
/** «19:00, онлайн, ведёт Ирина Власова»; the host name comes only for staff hosts. */
export function webinarMeta(item:Webinar){
 const host=nameWords(item.host_name).join(' ');
 return [fmt(item.starts_at,{hour:'2-digit',minute:'2-digit'}),'онлайн',host&&`ведёт ${host}`].filter(Boolean).join(', ');
}
const suggestions=['просит мой телефон','не хочет рисовать','рассказал что-то тревожное'];
/** The question goes in router state, not the address bar: it may describe a child. */
const mentorState=(text:string)=>({question:text});

function TaskAnswer({block,lessonId,assignmentId}:{block:Block;lessonId:string;assignmentId:string}){
 const query=useQuery({queryKey:keys.detail('learning-tasks',assignmentId),queryFn:({signal})=>api<Submission[]>(`/learning/assignments/${assignmentId}/tasks`,{signal})});
 const command=useLearningCommand(),[text,setText]=useState(''),[saved,setSaved]=useState(false),[version,setVersion]=useState(0),[dirty,setDirty]=useState(false);
 const value=query.data?.find(item=>item.block_id===block.id);
 useEffect(()=>{if(!dirty){setText(value?.answer_text??'');setVersion(value?.version??0);}},[value,dirty]);
 async function save(){try{const result=await command.mutateAsync({path:`/learning/lessons/${lessonId}/tasks/${block.id}`,body:{assignment_id:assignmentId,answer_text:text,expected_version:version}}) as Submission;setVersion(result.version);setSaved(true);setDirty(false);}catch{/* command.error is rendered below */}}
 return <section className="card learn-task">
  <h2 className="h3">{block.title||'Задание'}</h2>
  {block.text&&<p className="p">{block.text}</p>}
  {block.required===true&&<p className="tag">Обязательное задание</p>}
  <Field label="Твой ответ"><Textarea rows={4} value={text} disabled={query.isPending} onChange={e=>{setText(e.target.value);setDirty(true);setSaved(false);}}/></Field>
  <div className="row wrap"><Button variant="secondary" disabled={command.isPending||!text.trim()} onClick={()=>void save()}>Сохранить ответ</Button>{saved&&<span className="st st-ok" role="img" aria-label="Ответ сохранён"><Icon name="check"/></span>}</div>
  {query.error&&<ErrorState error={query.error} retry={()=>void query.refetch()}/>}
  {command.error&&<ErrorState error={command.error}/>}
 </section>;
}

/** Lesson blocks inside the canvas `.lesson-body`; the shared renderer keeps quizzes, video and files. */
function LessonBlock({block,lessonId,assignmentId}:{block:Block;lessonId:string;assignmentId:string}){
 if(block.type==='task')return <TaskAnswer block={block} lessonId={lessonId} assignmentId={assignmentId}/>;
 if(block.type==='callout'){const warning=block.tone==='warn';return <div className={cx('callout',!warning&&'is-note')}><span className="art" aria-hidden="true"><Icon name={warning?'alert':'heart'}/></span><span>{block.text}</span></div>;}
 if(block.type==='phrases')return <section>{block.title&&<h2>{block.title}</h2>}{((block.items??[]) as string[][]).map(([say,avoid],i)=><div className="swap-row" key={i}><div><span>Вместо</span>{avoid}</div><div className="better"><span>Лучше</span>{say}</div></div>)}</section>;
 return <ContentBlock block={block} lessonId={lessonId}/>;
}

function SimulatorCourse(){
 const scenarios=useScenarios(),history=useSimulationHistory();
 const items=(scenarios.data?.pages.flatMap(page=>page.items)??[]) as ScenarioPublic[];
 if(scenarios.isPending||scenarios.isError||!items.length)return null;
 const finished=new Set((history.data?.pages.flatMap(page=>page.items)??[]).filter(item=>item.state==='finished').map(item=>item.scenario.id));
 const done=items.filter(item=>finished.has(item.id)).length,next=items.find(item=>!finished.has(item.id));
 return <div className="course">
  <div className="course-top"><span className="art art-o" aria-hidden="true"><Icon name="message"/></span><h3 className="h3">Тренажёр трудных ситуаций</h3></div>
  <div className="row"><div className="bar bar-ink grow" aria-hidden="true"><i style={{width:`${Math.round(done/items.length*100)}%`}}/></div><b className="num">{done} из {items.length}</b></div>
  <div className="course-foot"><Link className="btn btn-secondary btn-sm" to={next?`/simulator/${next.id}`:'/simulator'}>{next?'Следующая ситуация':'Открыть тренажёр'}</Link></div>
 </div>;
}

function TrackCourse({item,current}:{item:Assignment;current:boolean}){
 const total=item.lessons.length,done=item.lessons.filter(lesson=>lesson.completed).length;
 if(item.completed)return <div className="course">
  <div className="course-top"><span className="art art-g" aria-hidden="true"><Icon name="check"/></span><h3 className="h3">{item.title}</h3></div>
  <p className="p">{completedLabel(item.completed_at)}</p>
  <div className="course-foot"><Link className="btn btn-ghost btn-sm learn-pull" to={trackSteps(item)[0]?.href??'/academy'}>Открыть материалы</Link></div>
 </div>;
 return <div className={cx('course',current&&'is-now')}>
  <div className="course-top"><span className={cx('art',current?'art-y':'art-b')} aria-hidden="true"><Icon name="book"/></span><h3 className="h3">{item.title}</h3></div>
  {total>0&&<div className="row"><div className="bar bar-ink grow" aria-hidden="true"><i style={{width:`${Math.round(done/total*100)}%`}}/></div><b className="num">{done} из {total}</b></div>}
  <div className="course-foot"><Link className="btn btn-secondary btn-sm" to={nextStep(item)?.href??'/academy'}>Уроки</Link></div>
 </div>;
}

function Broadcasts(){
 const query=useWebinars(),command=useStudioCommand<unknown>(),[summary,setSummary]=useState<Webinar|null>(null);
 const now=Date.now(),rows=query.data??[];
 const upcoming=rows.filter(item=>item.state==='published'&&(item.session_id||endsAt(item)>now)).sort((a,b)=>a.starts_at.localeCompare(b.starts_at)).slice(0,3);
 const summaries=rows.filter(item=>item.state==='ended'&&item.summary_available&&item.enrollment_state==='enrolled').sort((a,b)=>b.starts_at.localeCompare(a.starts_at)).slice(0,2);
 const enroll=(item:Webinar)=>command.mutate({path:`/webinars/${item.id}/enroll`,body:item.enrollment_version?{expected_version:item.enrollment_version}:undefined});
 const withdraw=(item:Webinar)=>command.mutate({path:`/webinars/${item.id}/withdraw`,body:{expected_version:item.enrollment_version}});
 function end(item:Webinar){
  const described=`webinar-${item.id}`;
  if(item.enrollment_state==='revoked')return <span className="meta">Доступ закрыт</span>;
  if(item.enrollment_state==='enrolled')return <><span className="st st-ok" role="img" aria-label="Ты в списке"><Icon name="check"/></span>{item.session_id
   ?<Link className="btn btn-secondary btn-sm" to={`/studio/${item.session_id}`} aria-describedby={described}>Войти</Link>
   :<Button variant="ghost" size="sm" disabled={command.isPending} aria-describedby={described} onClick={()=>withdraw(item)}>Отменить</Button>}</>;
  return <Button variant="secondary" size="sm" disabled={command.isPending} aria-describedby={described} onClick={()=>enroll(item)}>Записаться</Button>;
 }
 return <section className="sec">
  <div className="sec-head"><h2 className="h2">Эфиры и записи</h2></div>
  <div className="card">
   {query.isPending?<LoadingState/>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:upcoming.length||summaries.length?<div className="rows">
    {upcoming.map(item=><div className="rowi" key={item.id}>
     <span className="day v"><b>{fmt(item.starts_at,{day:'numeric'})}</b><span>{fmt(item.starts_at,{weekday:'short'})}</span></span>
     <div className="grow"><span className="rowi-title" id={`webinar-${item.id}`}>{item.title}</span><span className="meta">{webinarMeta(item)}</span></div>
     <span className="rowi-end">{end(item)}</span>
    </div>)}
    {summaries.map(item=><div className="rowi" key={item.id}>
     <span className="art art-v learn-rec" aria-hidden="true"><Icon name="file"/></span>
     <div className="grow"><span className="rowi-title" id={`webinar-${item.id}`}>Итоги: {item.title}</span><span className="meta">{fmt(item.starts_at,{day:'numeric',month:'long'})}</span></div>
     <span className="rowi-end"><Button variant="secondary" size="sm" aria-describedby={`webinar-${item.id}`} onClick={()=>setSummary(item)}>Смотреть</Button></span>
    </div>)}
   </div>:<p className="p">Новые эфиры появятся здесь.</p>}
   {command.error&&<ErrorState error={command.error}/>}
   <Link className="btn btn-ghost learn-all" to="/webinars">Все записи</Link>
  </div>
  {summary&&<SummaryPublishedDialog webinarId={summary.id} onClose={()=>setSummary(null)}/>}
 </section>;
}

const kindLabels:Record<LibraryKind,string>={article:'Статьи',memo:'Памятки'};
const kindArt:Record<LibraryKind,{art:string;icon:'book'|'file'}>={article:{art:'art-b',icon:'book'},memo:{art:'art-g',icon:'file'}};
type LessonLink={key:string;title:string;href:string};

function LibraryReader({item,onClose}:{item:LibraryItem;onClose:()=>void}){
 const query=useLibraryText(item.id);
 return <Dialog open onClose={onClose} title={item.title} className="learn-reader">
  {query.isPending?<LoadingState/>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>
   :<div className="learn-reader-text">{query.data.text.split(/\n\s*\n/).map(part=>part.trim()).filter(Boolean).map((part,i)=><p key={i}>{part}</p>)}</div>}
 </Dialog>;
}

/** «Статьи и памятки»: the fund's published materials; lessons of my courses only while the library is empty. */
function Library({lessons}:{lessons:LessonLink[]}){
 const query=useLibrary(),[kind,setKind]=useState<'all'|LibraryKind>('all'),[open,setOpen]=useState<LibraryItem|null>(null);
 if(query.isPending)return null;
 const items=query.data??[];
 if(!items.length){
  if(!lessons.length)return null;
  return <section className="sec">
   <div className="sec-head"><h2 className="h2">Статьи и памятки</h2></div>
   <div className="grid-3">{lessons.map(item=><Link key={item.key} className="lib" to={item.href}><span className="art art-b" aria-hidden="true"><Icon name="book"/></span><span>{item.title}</span></Link>)}</div>
  </section>;
 }
 const kinds=(Object.keys(kindLabels) as LibraryKind[]).filter(value=>items.some(item=>item.kind===value));
 const shown=items.filter(item=>kind==='all'||item.kind===kind);
 const chips:[typeof kind,string][]=[['all','Все'],...kinds.map(value=>[value,kindLabels[value]] as [LibraryKind,string])];
 return <section className="sec">
  <div className="sec-head"><h2 className="h2">Статьи и памятки</h2>
   {kinds.length>1&&<div className="chips" role="group" aria-label="Тип">{chips.map(([value,label])=><button type="button" key={value} className={cx('chip',kind===value&&'is-on')} aria-pressed={kind===value} onClick={()=>setKind(value)}>{label}</button>)}</div>}
  </div>
  <div className="grid-3">{shown.map(item=><button type="button" key={item.id} className="lib" aria-haspopup="dialog" onClick={()=>setOpen(item)}><span className={cx('art',kindArt[item.kind].art)} aria-hidden="true"><Icon name={kindArt[item.kind].icon}/></span><span>{item.title}</span></button>)}</div>
  {open&&<LibraryReader item={open} onClose={()=>setOpen(null)}/>}
 </section>;
}

function AskBox(){
 const navigate=useNavigate(),[text,setText]=useState('');
 function submit(event:FormEvent){event.preventDefault();const value=text.trim();navigate('/mentor',value?{state:mentorState(value)}:undefined);}
 return <section className="sec">
  <form className="ai-box" onSubmit={submit}>
   <h2 className="h3">Не знаешь, как поступить на занятии?</h2>
   <div className="ask"><label className="sr-only" htmlFor="learn-ask">Вопрос</label><input id="learn-ask" className="input" placeholder="Что делать, если ребёнок…" maxLength={3000} value={text} onChange={event=>setText(event.target.value)}/><button type="submit" className="btn btn-ai">Спросить</button></div>
   <div className="chips learn-suggest">{suggestions.map(item=><Link key={item} className="chip" to="/mentor" state={mentorState(`Что делать, если ребёнок ${item}?`)}>{item}</Link>)}</div>
  </form>
 </section>;
}

export function AcademyPage(){
 const query=usePreparation();
 const assignments=query.data?.assignments??[];
 const current=assignments.find(item=>!item.completed&&trackSteps(item).length>0);
 const open=assignments.filter(item=>!item.completed&&item!==current),completed=assignments.filter(item=>item.completed);
 const step=current&&nextStep(current),steps=current?trackSteps(current):[];
 const lessonNumber=current&&step?current.lessons.findIndex(lesson=>lesson.id===step.id)+1:0;
 const started=current?.lessons.some(lesson=>lesson.completed);
 const lessons:LessonLink[]=[...new Map(assignments.flatMap(item=>item.lessons.map(lesson=>[lesson.lesson_id,{key:lesson.lesson_id,title:lesson.title,href:lessonHref(lesson.id,item.id)}] as const))).values()];
 return <div className="learn-page">
  <div className="page-head"><h1 className="h1">Обучение</h1></div>
  {query.isPending?<LoadingState label="Загружаем твои курсы…"/>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:<>
   {current&&step&&<section className="card-hero learn-hero">
    <div className="hero-grid">
     <div className="hero-copy">
      <p className="eyebrow">{step.id==='assessment'?`Курс «${current.title}», тест по материалам`:`Курс «${current.title}», урок ${lessonNumber} из ${current.lessons.length}`}</p>
      <h2 className="hero-title">{step.title}</h2>
      <div className="actions"><Link className="btn btn-primary btn-lg" to={step.href}>{step.id==='assessment'?'Пройти тест':started?'Продолжить урок':'Начать урок'}</Link></div>
     </div>
     <span className="hero-art" aria-hidden="true"><Icon name="academy"/></span>
    </div>
   </section>}
   <section className="sec">
    <div className="sec-head"><h2 className="h2">Мои курсы</h2></div>
    {assignments.length?null:<EmptyState title="Курсов пока нет" description="Координатор подберёт материалы для твоей роли."/>}
    <div className="grid-3">
     {current&&steps.length>0&&<TrackCourse item={current} current/>}
     {open.map(item=><TrackCourse key={item.id} item={item} current={false}/>)}
     <SimulatorCourse/>
     {completed.map(item=><TrackCourse key={item.id} item={item} current={false}/>)}
    </div>
   </section>
  </>}
  <Broadcasts/>
  <Library lessons={lessons}/>
  <AskBox/>
 </div>;
}

export function LessonPage(){
 const params=useParams(),[search]=useSearchParams();const id=params.id??params.versionId??'';
 const prep=usePreparation(),lesson=useLesson(id!=='assessment'?id:undefined),command=useLearningCommand(),[saved,setSaved]=useState(false);
 const assignment=prep.data?.assignments.find(item=>item.id===search.get('assignment'))??prep.data?.assignments.find(item=>item.lessons.some(l=>l.id===id));
 useEffect(()=>setSaved(false),[id,assignment?.id]);
 async function complete(){if(!assignment)return;try{await command.mutateAsync({path:`/learning/progress/${id}/complete`,body:{assignment_id:assignment.id}});await command.mutateAsync({path:'/policy-acknowledgements',body:{assignment_id:assignment.id}});setSaved(true);}catch{/* command.error is rendered below */}}
 if(prep.isPending)return <LoadingState/>;
 if(prep.error)return <ErrorState error={prep.error} retry={()=>void prep.refetch()}/>;
 if(!assignment)return <EmptyState title="Этот урок тебе пока не назначен" action={<Link className="btn btn-secondary" to="/academy">К обучению</Link>}/>;
 const assessment=id==='assessment';
 const steps=trackSteps(assignment).map(step=>step.id===id&&saved?{...step,done:true}:step);
 const index=steps.findIndex(step=>step.id===id),current=steps[index];
 const previous=index>0?steps[index-1]:undefined,next=index>=0?steps[index+1]:undefined;
 const done=steps.filter(step=>step.done).length;
 const title=lesson.data?.title??current?.title??'';
 return <div className="learn-page learn-lesson">
  <Link className="back" to="/academy"><Icon name="chevron-left"/>{assignment.title}</Link>
  {!assessment&&<div className="page-head"><h1 className="h1">{title}</h1></div>}
  <div className="split-panel">
   <div className="main">
    {assessment?<AssessmentPlayer key={assignment.id} assignment={assignment}/>
     :lesson.isPending?<div className="card"><LoadingState/></div>
     :lesson.error?<div className="card"><ErrorState error={lesson.error} retry={()=>void lesson.refetch()}/></div>
     :lesson.data&&<>
      <article className="card lesson-body"><div className="a-blocks">{lesson.data.blocks.map((raw,i)=>{const block=raw as unknown as Block;return <LessonBlock key={`${assignment.id}:${id}:${block.id??i}`} block={block} lessonId={id} assignmentId={assignment.id}/>;})}</div></article>
      <div className="learn-nav">
       {previous?<Link className="btn btn-ghost" to={previous.href}>Назад</Link>:<span/>}
       {current?.done?<Link className="btn btn-primary btn-lg" to={next?.href??'/academy'}>Дальше</Link>:<Button size="lg" loading={command.isPending} onClick={()=>void complete()}>Отметить урок прочитанным</Button>}
      </div>
     </>}
    {saved&&<p role="status" className="sr-only">Прогресс сохранён.</p>}
    {command.error&&<ErrorState error={command.error}/>}
   </div>
   <aside className="panel lesson-side">
    {index>=0&&<span className="big">{index+1} из {steps.length}</span>}
    <div className="bar bar-green learn-progress" aria-hidden="true"><i style={{width:`${steps.length?Math.round(done/steps.length*100):0}%`}}/></div>
    <nav className="lesson-steps" aria-label="Уроки курса">{steps.map((step,i)=><Link key={step.id} to={step.href} className={cx(step.id===id&&'is-on',step.done&&'done')} aria-current={step.id===id?'page':undefined}>
     <span className="n" aria-hidden="true">{step.done?<Icon name="check"/>:i+1}</span><span className="grow">{step.title}</span>{step.done&&<span className="sr-only">, пройден</span>}
    </Link>)}</nav>
    <Link className="btn btn-ai btn-block learn-mentor" to="/mentor"><Icon name="sparkle"/>Спросить наставника</Link>
   </aside>
  </div>
 </div>;
}
