import {useCallback,useEffect,useRef,useState,type MutableRefObject,type ReactNode} from 'react';
import {Link,Navigate,useNavigate,useParams,useSearchParams} from 'react-router-dom';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {Button,Combobox,Dialog,EmptyState,ErrorState,Field,Icon,Input,LoadingState,SectionTabs,Segmented,cx,type IconName} from '../../ui';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import {learningTabs} from '../../app/sectionTabs';
import {BlockCard,BlockIcon,QuestionBody,blankQuestion,blockKinds,newBlock,type EditableBlock,type EditableQuestion} from './BlockEditor';
import {putLesson,putTrack,useAuthorCommand,useAuthorTracks,useTrackCommand,useUpcomingWebinars,type AuthorLesson,type Draft,type Track} from './authorApi';
import {RecordingDraftImport} from './RecordingDraftImport';
import './learning.css';
import './builder.css';
import './courses.css';

type Assessment=NonNullable<Track['assessment']>;
type Stage={title:string|null;lessons:AuthorLesson[]};
const plural=(n:number,one:string,few:string,many:string)=>{const form=new Intl.PluralRules('ru-RU').select(n);return form==='one'?one:form==='few'?few:many;};
const shortKey=(prefix:string)=>`${prefix}-${crypto.randomUUID().slice(0,8)}`;
/** Consecutive lessons with the same stage title are one stage, exactly as the server groups them. */
export function groupStages(lessons:AuthorLesson[]){const stages:Stage[]=[];for(const lesson of lessons){const title=lesson.stage_title??null,last=stages.at(-1);if(last&&last.title===title)last.lessons.push(lesson);else stages.push({title,lessons:[lesson]});}return stages;}
const shape=(track:Track)=>groupStages(track.lessons.filter(lesson=>!lesson.archived)).map(stage=>({title:stage.title,lesson_ids:stage.lessons.map(lesson=>lesson.id)}));
function courseMeta(track:Track){
 const live=track.lessons.filter(lesson=>!lesson.archived),stages=groupStages(live).length,parts:string[]=[];
 if(track.required)parts.push(track.audience==='new'?'Обязательный для новых':'Обязательный до первого выхода');else if(track.audience==='new')parts.push('Для всех новых волонтёров');
 if(stages>1)parts.push(`${stages} ${plural(stages,'ступень','ступени','ступеней')}`);
 parts.push(live.length?`${live.length} ${plural(live.length,'урок','урока','уроков')}${track.has_simulator?' и тренажёр':''}`:'Пока без уроков');
 return parts.join(', ');
}
const arts:[string,IconName][]=[['art-y','book'],['art-b','message'],['art-o','palette'],['art-g','heart'],['art-v','academy']];
const courseArt=(track:Track)=>track.key==='introduction'?arts[0]:arts[[...track.id].reduce((sum,char)=>sum+char.charCodeAt(0),0)%arts.length];
function Problem({error}:{error:unknown}){
 const details=error instanceof ApiError?Object.values(error.field_errors??{}).flatMap(value=>Array.isArray(value)?value:[value]).map(String):[];
 return <div className="bld-errors" role="alert"><p className="strong">{error instanceof Error?error.message:'Не удалось выполнить действие'}</p>{details.map((item,i)=><p className="p" key={i}>{item}</p>)}</div>;
}

/** «Курсы»: every course of the foundation with its state and how many finished it. */
export function BuilderPage(){
 const query=useAuthorTracks(),[search]=useSearchParams(),[filter,setFilter]=useState('all'),[creating,setCreating]=useState(false);
 const legacy=search.get('track');
 if(legacy)return <Navigate to={`/fund/learning/courses/${legacy}`} replace/>;
 const courses=(query.data??[]).filter(track=>!track.archived),shown=courses.filter(track=>filter==='all'||(filter==='pub'?!!track.current_release_id:!track.current_release_id));
 return <div className="courses-page">
  <SectionTabs label="Обучение" tabs={learningTabs} actions={<Button onClick={()=>setCreating(true)}><Icon name="plus"/>Новый курс</Button>}/>
  <div className="toolbar"><Segmented label="Какие курсы показать" value={filter} onChange={setFilter} options={[{value:'all',label:'Все'},{value:'pub',label:'Опубликованные'},{value:'draft',label:'Черновики'}]}/></div>
  {query.isPending?<LoadingState label="Загружаем курсы…"/>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:!shown.length?<EmptyState title={!courses.length?'Курсов пока нет':filter==='pub'?'Опубликованных курсов нет':'Черновиков нет'} description={!courses.length?'Создайте первый курс: ступени, уроки и вопросы.':undefined}/>:
  <div className="grid-3">{shown.map(track=>{const [art,icon]=courseArt(track),done=track.stats?.completed??0;return <Link key={track.id} className="course-card" to={`/fund/learning/courses/${track.id}`}>
   <span className={`art ${art}`} aria-hidden="true"><Icon name={icon}/></span>
   <span><span className="h3">{track.title}</span><span className="meta">{courseMeta(track)}</span></span>
   <span className="course-foot"><span className={track.current_release_id?'meta':'dot'}>{track.current_release_id?'':'Черновик'}</span><span className="p">{track.current_release_id&&done?`${done} ${plural(done,'прошёл','прошли','прошли')}`:''}</span></span>
  </Link>;})}</div>}
  <NextLive/>
  <NewCourse open={creating} onClose={()=>setCreating(false)}/>
 </div>;
}
function NextLive(){
 const query=useUpcomingWebinars();
 if(query.isError)return null;
 const now=Date.now(),next=(query.data??[]).filter(item=>!['ended','cancelled'].includes(item.state)&&new Date(item.starts_at).getTime()+item.duration_minutes*60000>now).sort((a,b)=>new Date(a.starts_at).getTime()-new Date(b.starts_at).getTime())[0];
 const part=(options:Intl.DateTimeFormatOptions)=>next?new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',...options}).format(new Date(next.starts_at)):'';
 const weekday=part({weekday:'short'}),state=next?.state==='published'?['dot dot-green','Запись открыта']:next?.state==='draft'?['dot','Черновик']:['dot dot-orange','Идёт сейчас'];
 return <section className="section" aria-labelledby="next-live">
  <div className="sec-head"><h2 className="h2" id="next-live">Ближайший эфир</h2><Link className="btn btn-ghost btn-sm" to="/fund/webinars">Все эфиры и записи</Link></div>
  {query.isPending?<LoadingState/>:next?<Link className="ev-row" to="/fund/webinars">
   <span className="date-chip"><b>{part({day:'numeric'})}</b><span>{part({month:'short'}).replace('.','')}</span></span>
   <span><span className="h3">{next.title}</span><span className="meta">{weekday.charAt(0).toUpperCase()+weekday.slice(1)}, {part({hour:'2-digit',minute:'2-digit'})}, {next.duration_minutes} {plural(next.duration_minutes,'минута','минуты','минут')}</span></span>
   <span className={`${state[0]} ev-state`}>{state[1]}</span>
   <Icon name="chevron-right"/>
  </Link>:<p className="meta">Ближайших эфиров нет</p>}
 </section>;
}
function NewCourse({open,onClose}:{open:boolean;onClose:()=>void}){
 const navigate=useNavigate(),client=useQueryClient(),[title,setTitle]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null);
 async function create(){
  if(!title.trim()||busy)return;setBusy(true);setError(null);
  try{
   const track=await api<Track>('/coord/learning/tracks',{method:'POST',body:{key:shortKey('course'),title:title.trim()},idempotencyKey:crypto.randomUUID()});
   const lesson=await api<AuthorLesson>('/coord/learning/lessons',{method:'POST',body:{track_id:track.id,key:shortKey('lesson'),title:'Новый урок'},idempotencyKey:crypto.randomUUID()});
   await client.invalidateQueries({queryKey:keys.all('learning-author')});
   navigate(`/fund/learning/courses/${track.id}?lesson=${lesson.id}`);
  }catch(e){setError(e);}finally{setBusy(false);}
 }
 return <Dialog open={open} onClose={onClose} title="Новый курс" footer={<Button loading={busy} disabled={!title.trim()} onClick={()=>void create()}>Создать курс</Button>}>
  <Field label="Название курса"><Input value={title} maxLength={300} onChange={e=>setTitle(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')void create();}}/></Field>
  {error!=null&&<Problem error={error}/>}
 </Dialog>;
}

/** Local edits saved to the server draft after a short pause; flush() saves now and throws on failure. */
function useAutosave<T extends {version:number;status:string}>(source:T|null,persist:(value:T,expected:number)=>Promise<T|null|undefined>,ready:(value:T)=>boolean){
 const [local,setLocal]=useState<T|null>(source),[pending,setPending]=useState(false),[error,setError]=useState<unknown>(null);
 const latest=useRef(local),version=useRef(source?.version??0),dirty=useRef(false),running=useRef<Promise<unknown>|null>(null),timer=useRef<number|undefined>(undefined);
 const persistRef=useRef(persist),readyRef=useRef(ready);persistRef.current=persist;readyRef.current=ready;
 useEffect(()=>{if(!dirty.current&&!running.current){latest.current=source;version.current=source?.version??0;setLocal(source);}},[source]);
 const save=useCallback(async()=>{
  window.clearTimeout(timer.current);
  while(running.current)await running.current;
  const snapshot=latest.current;
  if(!dirty.current||!snapshot||!readyRef.current(snapshot)){setPending(dirty.current);return;}
  dirty.current=false;
  const run=persistRef.current(snapshot,version.current);
  running.current=run.catch(()=>undefined);
  try{
   const saved=await run;setError(null);
   if(saved){version.current=saved.version;if(latest.current===snapshot){latest.current=saved;setLocal(saved);}}
  }catch(e){dirty.current=true;setError(e);throw e;}
  finally{running.current=null;setPending(dirty.current);}
 },[]);
 const change=useCallback((update:(value:T)=>T)=>{const base=latest.current;if(!base)return;const next=update(base);latest.current=next;setLocal(next);dirty.current=true;setPending(true);window.clearTimeout(timer.current);timer.current=window.setTimeout(()=>void save().catch(()=>undefined),800);},[save]);
 useEffect(()=>()=>{window.clearTimeout(timer.current);if(dirty.current)void save().catch(()=>undefined);},[save]);
 useEffect(()=>{if(!pending)return;const before=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before);},[pending]);
 return {local,change,flush:save,pending,error,retry:()=>void save().catch(()=>undefined)};
}
type Flush=MutableRefObject<(()=>Promise<void>)|null>;
function SaveError({error,retry}:{error:unknown;retry:()=>void}){return <div className="bld-errors" role="alert"><p className="strong">Не удалось сохранить</p><p className="p">{error instanceof Error?error.message:'Проверьте соединение.'}</p><Button variant="secondary" size="sm" onClick={retry}>Сохранить ещё раз</Button></div>;}
function AddZone({label,open,onToggle,children}:{label:string;open:boolean;onToggle?:()=>void;children?:ReactNode}){return <div className="add-zone"><Button variant="secondary" aria-expanded={children?open:undefined} onClick={onToggle}><Icon name="plus"/>{label}</Button>{open&&children}</div>;}

function LessonEditor({lesson,where,tools,flushRef,onTitle,onPending}:{lesson:AuthorLesson;where:string;tools:ReactNode;flushRef:Flush;onTitle:(title:string)=>void;onPending:(pending:boolean)=>void}){
 const client=useQueryClient(),[opening,setOpening]=useState<unknown>(null),[menu,setMenu]=useState(false),ids=useRef<string[]>([]);
 const hasDraft=!!lesson.draft;
 useEffect(()=>{
  // A published lesson is opened as a copy of its current version; that copy is not a change yet.
  if(hasDraft)return;let live=true;
  api<AuthorLesson>(`/coord/learning/lessons/${lesson.id}/edit`,{method:'POST',body:{},idempotencyKey:crypto.randomUUID()}).then(opened=>{if(live)putLesson(client,opened);},error=>{if(live)setOpening(error);});
  return()=>{live=false;};
 },[client,hasDraft,lesson.id]);
 const draft=useAutosave<Draft>(lesson.draft,async(value,expected)=>{const saved=await api<AuthorLesson>(`/coord/learning/lessons/${lesson.id}/draft`,{method:'PUT',body:{expected_version:expected,title:value.title.trim(),minutes:value.minutes,source:value.source,blocks:value.blocks},idempotencyKey:crypto.randomUUID()});putLesson(client,saved);return saved.draft;},value=>!!value.title.trim());
 useEffect(()=>{const flush=draft.flush;flushRef.current=flush;return()=>{if(flushRef.current===flush)flushRef.current=null;};},[draft.flush,flushRef]);
 useEffect(()=>onPending(draft.pending),[draft.pending,onPending]);
 if(!draft.local)return opening?<ErrorState error={opening}/>:<LoadingState label="Открываем урок…"/>;
 const blocks=draft.local.blocks as EditableBlock[];
 while(ids.current.length<blocks.length)ids.current.push(crypto.randomUUID());
 ids.current.length=blocks.length;
 const edit=(update:(list:EditableBlock[])=>EditableBlock[])=>draft.change(value=>({...value,blocks:update(value.blocks as EditableBlock[])}));
 const swap=<T,>(list:T[],i:number,j:number)=>{const copy=[...list];[copy[i],copy[j]]=[copy[j],copy[i]];return copy;};
 return <>
  <div className="lesson-head">
   <div className="lesson-head-top"><p className="eyebrow grow" style={{margin:0}}>{where}</p>{tools}</div>
   <label className="sr-only" htmlFor="lesson-title">Название урока</label>
   <input id="lesson-title" className="lesson-title" type="text" maxLength={300} value={draft.local.title} onChange={e=>{const title=e.target.value;draft.change(value=>({...value,title}));onTitle(title);}}/>
  </div>
  {draft.error!=null&&<SaveError error={draft.error} retry={draft.retry}/>}
  {blocks.map((block,i)=><BlockCard key={ids.current[i]} block={block} index={i} count={blocks.length} lessonId={lesson.id}
   onChange={value=>edit(list=>list.map((item,j)=>j===i?value:item))}
   onMove={direction=>{ids.current=swap(ids.current,i,i+direction);edit(list=>swap(list,i,i+direction));}}
   onDelete={()=>{ids.current=ids.current.filter((_,j)=>j!==i);edit(list=>list.filter((_,j)=>j!==i));}}/>)}
  <AddZone label="Добавить блок" open={menu||!blocks.length} onToggle={()=>setMenu(!menu)}>
   <div className="add-menu">{blockKinds.map(([kind,label,art])=><button type="button" key={kind} onClick={()=>{ids.current=[...ids.current,crypto.randomUUID()];edit(list=>[...list,newBlock(kind)]);setMenu(false);}}><span className={`art ${art}`} aria-hidden="true"><BlockIcon type={kind}/></span>{label}</button>)}</div>
  </AddZone>
 </>;
}
/** The course's own final test (the imported introduction has one) edited like a lesson of questions. */
function AssessmentEditor({track,flushRef,onPending}:{track:Track;flushRef:Flush;onPending:(pending:boolean)=>void}){
 const client=useQueryClient(),ids=useRef<string[]>([]);
 const test=useAutosave<Assessment>(track.assessment??null,async(value,expected)=>{const saved=await api<Track>(`/coord/learning/tracks/${track.id}/assessment`,{method:'PUT',body:{expected_version:expected,title:value.title.trim(),intro:value.intro,questions:value.questions},idempotencyKey:crypto.randomUUID()});putTrack(client,saved);return saved.assessment;},value=>!!value.title.trim());
 useEffect(()=>{const flush=test.flush;flushRef.current=flush;return()=>{if(flushRef.current===flush)flushRef.current=null;};},[test.flush,flushRef]);
 useEffect(()=>onPending(test.pending),[test.pending,onPending]);
 if(!test.local)return null;
 const questions=test.local.questions as EditableQuestion[];
 while(ids.current.length<questions.length)ids.current.push(crypto.randomUUID());
 ids.current.length=questions.length;
 const edit=(update:(list:EditableQuestion[])=>EditableQuestion[])=>test.change(value=>({...value,questions:update(value.questions as EditableQuestion[])}));
 const swap=<T,>(list:T[],i:number,j:number)=>{const copy=[...list];[copy[i],copy[j]]=[copy[j],copy[i]];return copy;};
 return <>
  <div className="lesson-head">
   <p className="eyebrow" style={{margin:0}}>Итоговый тест, {questions.length} {plural(questions.length,'вопрос','вопроса','вопросов')}</p>
   <label className="sr-only" htmlFor="lesson-title">Название теста</label>
   <input id="lesson-title" className="lesson-title" type="text" maxLength={300} value={test.local.title} onChange={e=>{const title=e.target.value;test.change(value=>({...value,title}));}}/>
  </div>
  {test.error!=null&&<SaveError error={test.error} retry={test.retry}/>}
  {questions.map((question,i)=><div className="block" key={ids.current[i]}>
   <div className="block-head"><span className="art art-y" aria-hidden="true"><BlockIcon type="quiz"/></span><span className="block-type">Вопрос {i+1}</span><span className="block-tools">
    <button type="button" className="iconbtn" aria-label={`Поднять вопрос ${i+1}`} disabled={i===0} onClick={()=>{ids.current=swap(ids.current,i,i-1);edit(list=>swap(list,i,i-1));}}><Icon name="chevron-down" style={{transform:'rotate(180deg)'}}/></button>
    <button type="button" className="iconbtn" aria-label={`Опустить вопрос ${i+1}`} disabled={i===questions.length-1} onClick={()=>{ids.current=swap(ids.current,i,i+1);edit(list=>swap(list,i,i+1));}}><Icon name="chevron-down"/></button>
    <button type="button" className="iconbtn" aria-label={`Удалить вопрос ${i+1}`} onClick={()=>{ids.current=ids.current.filter((_,j)=>j!==i);edit(list=>list.filter((_,j)=>j!==i));}}><Icon name="trash"/></button>
   </span></div>
   <div className="block-body"><QuestionBody question={question} index={i} many={false} onChange={value=>edit(list=>list.map((item,j)=>j===i?value:item))}/></div>
  </div>)}
  <AddZone label="Добавить вопрос" open={false} onToggle={()=>{ids.current=[...ids.current,crypto.randomUUID()];edit(list=>[...list,blankQuestion()]);}}/>
 </>;
}

function StageName({value,label,onCommit}:{value:string|null;label:string;onCommit:(title:string)=>void}){
 const [text,setText]=useState(value??'');
 useEffect(()=>setText(value??''),[value]);
 return <input className="tree-stage-name" aria-label={label} placeholder="Без названия" maxLength={200} value={text} onChange={e=>setText(e.target.value)} onBlur={()=>{if(text.trim()!==(value??''))onCommit(text.trim());}} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();if(e.key==='Escape'){setText(value??'');}}}/>;
}
function CourseName({title,onCommit}:{title:string;onCommit:(title:string)=>void}){
 const [text,setText]=useState(title);
 useEffect(()=>setText(title),[title]);
 return <h1 className="h1 course-name"><label className="sr-only" htmlFor="course-title">Название курса</label><input id="course-title" maxLength={300} value={text} onChange={e=>setText(e.target.value)} onBlur={()=>{const value=text.trim();if(!value)setText(title);else if(value!==title)onCommit(value);}} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();if(e.key==='Escape')setText(title);}}/></h1>;
}
function AssignDialog({track,open,onClose}:{track:Track;open:boolean;onClose:()=>void}){
 const recipients=useQuery({queryKey:keys.list('learning-author-recipients'),enabled:open,queryFn:({signal})=>api<{user_id:string|null;application_id:string|null;label:string}[]>('/coord/learning/recipients',{signal})});
 const command=useAuthorCommand(),[owner,setOwner]=useState(''),[assigned,setAssigned]=useState(false);
 return <Dialog open={open} onClose={onClose} title="Назначить курс" footer={<Button loading={command.isPending} disabled={!owner} onClick={()=>void command.mutateAsync({path:'/assignments',body:{release_id:track.current_release_id,...(owner.startsWith('application:')?{application_id:owner.slice(12)}:{user_id:owner.slice(5)})}}).then(()=>setAssigned(true)).catch(()=>undefined)}>Назначить</Button>}>
  <Combobox label="Волонтёр" value={owner} searchable onChange={value=>{setOwner(value);setAssigned(false);}} options={(recipients.data??[]).map(item=>({value:item.application_id?`application:${item.application_id}`:`user:${item.user_id}`,label:item.label}))}/>
  {recipients.isPending&&<LoadingState/>}{recipients.error&&<ErrorState error={recipients.error}/>}
  {assigned&&<p className="dot dot-green" role="status">Курс назначен</p>}
  {command.error&&<Problem error={command.error}/>}
 </Dialog>;
}

function CourseEditor({track,selected,onSelect}:{track:Track;selected:string|null;onSelect:(id:string)=>void}){
 const client=useQueryClient(),tracks=useAuthorTracks(),command=useTrackCommand(),[search]=useSearchParams();
 const flushRef=useRef<(()=>Promise<void>)|null>(null);
 const [pending,setPending]=useState(false),[busy,setBusy]=useState(false),[publishing,setPublishing]=useState(false),[error,setError]=useState<unknown>(null),[liveTitle,setLiveTitle]=useState<{id:string;title:string}|null>(null),[archiving,setArchiving]=useState<AuthorLesson|null>(null),[assigning,setAssigning]=useState(false);
 const live=track.lessons.filter(lesson=>!lesson.archived),stages=groupStages(live);
 const current=selected==='test'&&track.assessment?'test':live.find(lesson=>lesson.id===selected)?.id??live[0]?.id??(track.assessment?'test':null);
 const lesson=live.find(item=>item.id===current),index=lesson?live.indexOf(lesson):-1,stageIndex=lesson?stages.findIndex(stage=>stage.lessons.includes(lesson)):-1;
 const changed=pending||track.publish_state==='changed'||live.some(item=>item.draft&&item.draft.status!=='published')||!!(track.assessment&&track.assessment.status!=='published');
 const [stateClass,stateText]=!track.current_release_id?['dot','Черновик']:changed?['dot dot-orange','Есть неопубликованные изменения']:['dot dot-green','Всё опубликовано'];
 const fresh=()=>client.getQueryData<Track[]>(keys.list('learning-author'))?.find(item=>item.id===track.id)??track;
 const onPending=useCallback((value:boolean)=>setPending(value),[]);
 async function run(action:()=>Promise<void>){setBusy(true);setError(null);try{await action();}catch(e){setError(e);}finally{setBusy(false);}}
 const structure=(next:{title:string|null;lesson_ids:string[]}[])=>command.mutateAsync({path:`/tracks/${track.id}/structure`,method:'PUT',body:{expected_version:fresh().version,stages:next.filter(stage=>stage.lesson_ids.length)}});
 const patch=(body:Record<string,unknown>)=>run(async()=>{await command.mutateAsync({path:`/tracks/${track.id}`,method:'PATCH',body:{expected_version:fresh().version,...body}});});
 const createLesson=(stage_title:string|null)=>api<AuthorLesson>('/coord/learning/lessons',{method:'POST',body:{track_id:track.id,key:shortKey('lesson'),title:'Новый урок',stage_title},idempotencyKey:crypto.randomUUID()});
 const addLesson=(si:number)=>run(async()=>{
  const created=await createLesson(shape(fresh())[si]?.title??null);
  const after=(await tracks.refetch()).data?.find(item=>item.id===track.id);
  if(after){const before=shape(after),next=before.map(stage=>({...stage,lesson_ids:stage.lesson_ids.filter(id=>id!==created.id)}));if(next[si]){next[si].lesson_ids.push(created.id);if(JSON.stringify(next.filter(stage=>stage.lesson_ids.length))!==JSON.stringify(before))await structure(next);}}
  onSelect(created.id);
 });
 const addStage=()=>run(async()=>{const titles=new Set(stages.map(stage=>stage.title));let title='Новая ступень';for(let n=2;titles.has(title);n++)title=`Новая ступень ${n}`;const created=await createLesson(title);await tracks.refetch();onSelect(created.id);});
 const renameStage=(si:number,title:string)=>run(async()=>{const next=shape(fresh());next[si]={...next[si],title:title||null};await structure(next);});
 const moveLesson=(id:string,direction:number)=>run(async()=>{
  const next=shape(fresh()),si=next.findIndex(stage=>stage.lesson_ids.includes(id)),stage=next[si],li=stage.lesson_ids.indexOf(id),target=li+direction;
  if(target>=0&&target<stage.lesson_ids.length){[stage.lesson_ids[li],stage.lesson_ids[target]]=[stage.lesson_ids[target],stage.lesson_ids[li]];}
  else if(next[si+direction]){stage.lesson_ids.splice(li,1);if(direction<0)next[si-1].lesson_ids.push(id);else next[si+1].lesson_ids.unshift(id);}
  else return;
  await structure(next);
 });
 const archive=(item:AuthorLesson)=>run(async()=>{const next=live.find(other=>other.id!==item.id);await api(`/coord/learning/lessons/${item.id}/archive`,{method:'POST',body:{expected_version:item.publication_revision},idempotencyKey:crypto.randomUUID()});setArchiving(null);await tracks.refetch();if(next)onSelect(next.id);});
 const publish=()=>run(async()=>{
  setPublishing(true);
  try{
  await flushRef.current?.();
  let latest=(await tracks.refetch()).data?.find(item=>item.id===track.id);if(!latest)return;
  // The board publishes in one step: review each changed draft, then publish the course version.
  for(const item of latest.lessons.filter(other=>!other.archived&&other.draft?.status==='draft')){
   try{await api(`/coord/learning/lessons/${item.id}/review`,{method:'POST',body:{expected_version:item.draft!.version},idempotencyKey:crypto.randomUUID()});}catch(e){onSelect(item.id);throw e;}
  }
  if(latest.assessment?.status==='draft'){try{await api(`/coord/learning/tracks/${latest.id}/assessment/review`,{method:'POST',body:{expected_version:latest.assessment.version},idempotencyKey:crypto.randomUUID()});}catch(e){onSelect('test');throw e;}}
  latest=(await tracks.refetch()).data?.find(item=>item.id===track.id);if(!latest)return;
  const lessons=latest.lessons.filter(other=>!other.archived);
  await command.mutateAsync({path:`/tracks/${latest.id}/publish`,body:{expected_version:latest.version,lesson_ids:lessons.map(other=>other.id),lesson_draft_versions:Object.fromEntries(lessons.map(other=>[other.id,other.draft?.version??0])),lesson_publication_revisions:Object.fromEntries(lessons.map(other=>[other.id,other.publication_revision])),assessment_draft_version:latest.assessment?.version??null,intro:String(latest.releases.find(release=>release.id===latest!.current_release_id)?.intro??'')}});
  }finally{setPublishing(false);}
 });
 const stats=track.stats??{completed:0,learning:0,stuck:0},total=stats.completed+stats.learning;
 const lessonTitle=(item:AuthorLesson)=>(liveTitle?.id===item.id?liveTitle.title:item.draft?.title??item.title)||'Без названия';
 let number=0;
 return <div className="course-editor">
  <Link className="back" to="/fund/learning"><Icon name="chevron-left"/>Курсы</Link>
  <div className="page-head">
   <CourseName title={track.title} onCommit={title=>void patch({title})}/>
   <div className="page-actions"><span className={stateClass}>{stateText}</span><Button loading={publishing} disabled={busy||!live.length||(!!track.current_release_id&&!changed)} onClick={()=>void publish()}>{track.current_release_id?'Опубликовать изменения':'Опубликовать курс'}</Button></div>
  </div>
  {error!=null&&<Problem error={error}/>}
  <div className="bld">
   <nav className="bld-tree" aria-label="Ступени и уроки">
    {stages.map((stage,si)=><div className="tree-stage" key={`${si}:${stage.lessons[0].id}`}>
     <div className="tree-stage-head"><b><span>Ступень {si+1}.</span><StageName value={stage.title} label={`Название ступени ${si+1}`} onCommit={title=>void renameStage(si,title)}/></b><button type="button" className="iconbtn" aria-label={`Добавить урок в ступень «${stage.title||`Ступень ${si+1}`}»`} disabled={busy} onClick={()=>void addLesson(si)}><Icon name="plus"/></button></div>
     {stage.lessons.map(item=>{number+=1;const on=item.id===current;return <button type="button" key={item.id} className={cx('tree-item',on&&'is-on')} aria-current={on?'page':undefined} onClick={()=>onSelect(item.id)}><span className="tree-n">{number}</span><span className="grow">{lessonTitle(item)}</span></button>;})}
    </div>)}
    {track.assessment&&<div className="tree-stage"><button type="button" className={cx('tree-item',current==='test'&&'is-on')} aria-current={current==='test'?'page':undefined} onClick={()=>onSelect('test')}><span className="tree-n"><Icon name="check"/></span><span className="grow">{track.assessment.title||'Итоговый тест'}</span></button></div>}
    <button type="button" className="tree-add" disabled={busy} onClick={()=>void addStage()}><Icon name="plus"/>Новая ступень</button>
   </nav>
   <div className="bld-main">
    {lesson&&search.get('recording_render_id')&&<RecordingDraftImport lessonId={lesson.id} draftVersion={lesson.draft?.version??0} disabled={pending} onApplied={value=>putLesson(client,value)}/>}
    {current==='test'?<AssessmentEditor key="test" track={track} flushRef={flushRef} onPending={onPending}/>:lesson?<LessonEditor key={lesson.id} lesson={lesson} flushRef={flushRef} onPending={onPending} onTitle={title=>setLiveTitle({id:lesson.id,title})}
     where={`Ступень ${stageIndex+1}, урок ${index+1} из ${live.length}`}
     tools={<span className="block-tools">
      <button type="button" className="iconbtn" aria-label="Поднять урок" disabled={busy||index===0} onClick={()=>void moveLesson(lesson.id,-1)}><Icon name="chevron-down" style={{transform:'rotate(180deg)'}}/></button>
      <button type="button" className="iconbtn" aria-label="Опустить урок" disabled={busy||index===live.length-1} onClick={()=>void moveLesson(lesson.id,1)}><Icon name="chevron-down"/></button>
      <button type="button" className="iconbtn" aria-label="Убрать урок" disabled={busy} onClick={()=>setArchiving(lesson)}><Icon name="trash"/></button>
     </span>}/>:<EmptyState title="В курсе пока нет уроков" description="Добавьте ступень, в ней появится первый урок."/>}
   </div>
   <div className="bld-side">
    <div className="side-card">
     <h2 className="h3">Кому и когда</h2>
     <div className="side-stack">
      <span className="toggle-line"><button type="button" className={cx('toggle',track.required&&'is-on')} role="switch" aria-checked={track.required} aria-label="Обязательный до первого выхода" disabled={busy} onClick={()=>void patch({required:!track.required})}/>Обязательный до первого выхода</span>
      <div className="field"><span className="label">Назначать</span><div className="pick" role="radiogroup" aria-label="Кому назначать">{[['new','Всем новым волонтёрам'],['manual','Вручную']].map(([value,label])=><button type="button" key={value} role="radio" aria-checked={track.audience===value} className={track.audience===value?'is-on':''} disabled={busy} onClick={()=>{if(track.audience!==value)void patch({audience:value});}}>{label}</button>)}</div></div>
      {track.audience==='manual'&&track.current_release_id&&<Button variant="ghost" size="sm" onClick={()=>setAssigning(true)}>Назначить волонтёру</Button>}
     </div>
    </div>
    <div className="side-card">
     <h2 className="h3">Прохождение</h2>
     <div className="row" style={{gap:10,alignItems:'baseline'}}><span className="kpi-num" style={{fontSize:40}}>{stats.completed}</span><span className="p">{plural(stats.completed,'прошёл курс','прошли курс','прошли курс')}</span></div>
     <div className="bar bar-green" style={{margin:'16px 0 10px'}} aria-hidden="true"><i style={{width:`${total?Math.round(stats.completed/total*100):0}%`}}/></div>
     <p className="p" style={{margin:0}}>{stats.learning} {plural(stats.learning,'учится','учатся','учатся')} сейчас{track.assessment?`, ${stats.stuck} ${plural(stats.stuck,'застрял','застряли','застряли')} на тесте`:''}</p>
    </div>
   </div>
  </div>
  <Dialog open={!!archiving} onClose={()=>setArchiving(null)} title="Убрать урок?" footer={<><Button variant="danger" loading={busy} onClick={()=>archiving&&void archive(archiving)}>Убрать урок</Button><Button variant="ghost" onClick={()=>setArchiving(null)}>Оставить</Button></>}>
   <p className="p">«{archiving&&lessonTitle(archiving)}» пропадёт из курса. У тех, кто уже проходит курс, урок останется до новой публикации.</p>
  </Dialog>
  {track.current_release_id&&<AssignDialog track={track} open={assigning} onClose={()=>setAssigning(false)}/>}
 </div>;
}
function CourseWorkspace({trackId,lessonId}:{trackId?:string;lessonId?:string}){
 const query=useAuthorTracks(),[search,setSearch]=useSearchParams(),navigate=useNavigate();
 if(query.isPending)return <LoadingState label="Загружаем курс…"/>;
 if(query.error)return <ErrorState error={query.error} retry={()=>void query.refetch()}/>;
 const track=trackId?query.data.find(item=>item.id===trackId):query.data.find(item=>item.lessons.some(lesson=>lesson.id===lessonId));
 if(!track)return <div className="course-editor"><Link className="back" to="/fund/learning"><Icon name="chevron-left"/>Курсы</Link><EmptyState title="Курс не найден" description="Возможно, ссылка устарела."/></div>;
 const selected=search.get('lesson')??lessonId??null;
 const select=(id:string)=>{if(trackId)setSearch(params=>{const next=new URLSearchParams(params);next.set('lesson',id);next.delete('recording_render_id');return next;},{replace:true});else navigate(`/fund/learning/courses/${track.id}?lesson=${id}`);};
 return <CourseEditor key={track.id} track={track} selected={selected} onSelect={select}/>;
}
/** /fund/learning/courses/:id — the course editor. */
export function CoursePage(){const {id}=useParams();return <CourseWorkspace trackId={id}/>;}
/** /fund/learning/lessons/:id — kept for links from recordings; opens the lesson's course. */
export function BuilderLessonPage(){const {id}=useParams();return <CourseWorkspace lessonId={id}/>;}
