import {useEffect,useState} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {Button,Card,Dialog,EmptyState,ErrorState,Icon,LoadingState,PageSection,SectionTabs,Segmented,useToast} from '../../ui';
import {getSession} from '../../api/transport';
import {appPath} from '../../basePath';
import {learningTabs} from '../../app/sectionTabs';
import {useWebinars,useStudioCommand,type Webinar,type StudioSession} from '../studio/api';
import {WebinarCreateDialog} from '../studio/WebinarCreateDialog';
import {SummaryDialog} from '../studio/SummaryDialog';
import {useRecordingProjects,type RecordingProject} from '../lesson-recording/api';
import {CreateRecordingDialog} from '../lesson-recording/CreateRecordingDialog';
import {AttachLessonDialog} from '../lesson-recording/AttachLessonDialog';
import {lessonTitle} from '../lesson-recording/model';
import {useAuthorTracks} from '../learning/authorApi';
import {dateChip,dayMonth,enrolledLabel,fullWhen,nextLabel,shortWhen,videoLength} from './format';
import './broadcasts.css';

export type RecordKind='live'|'lesson';
/** A webinar that has not finished yet and can still be prepared or published. */
export const isUpcoming=(item:Webinar,now=Date.now())=>['draft','published'].includes(item.state)&&Date.parse(item.starts_at)+item.duration_minutes*60000>now;

/** «Эфиры и записи»: the nearest webinar, the ones after it, and recordings of webinars and lesson videos. */
export function BroadcastsPage({kind}:{kind?:RecordKind}){
 const permissions=getSession()?.permissions??[],canSchedule=permissions.includes('studio.manage'),canRecord=permissions.includes('recordings.manage');
 const webinars=useWebinars(),[scheduling,setScheduling]=useState(false),[recording,setRecording]=useState(false),[openId,setOpenId]=useState<string|null>(null),[summaryId,setSummaryId]=useState<string|null>(null);
 const rows=webinars.data??[],upcoming=rows.filter(item=>isUpcoming(item)),[next,...later]=upcoming,open=rows.find(item=>item.id===openId),summary=rows.find(item=>item.id===summaryId);
 const head=canRecord||canSchedule?<>{canRecord&&<Button variant="secondary" onClick={()=>setRecording(true)}><Icon name="record"/>Записать видео для урока</Button>}{canSchedule&&<Button variant="secondary" onClick={()=>setScheduling(true)}><Icon name="plus"/>Запланировать эфир</Button>}</>:undefined;
 return <div className="broadcasts-page">
  <SectionTabs label="Обучение" tabs={learningTabs} actions={head}/>
  {webinars.isPending?<LoadingState label="Загружаем эфиры…"/>:webinars.error?<ErrorState error={webinars.error} retry={()=>{void webinars.refetch();}}/>:next?<NextWebinar webinar={next}/>:<Card tone="soft" className="bc-none"><h2 className="h3">Ближайших эфиров нет</h2><p className="meta">{canSchedule?'Запланируйте эфир, и он появится здесь.':'Новые эфиры появятся здесь.'}</p></Card>}
  {later.length>0&&<PageSection className="section" title="Потом"><div className="ev-list">{later.map(item=><button type="button" className="ev-row" key={item.id} onClick={()=>setOpenId(item.id)}><DateChip value={item.starts_at}/><span><span className="h3">{item.title}</span><span className="meta">{shortWhen(item.starts_at)}{item.host_name&&`, ведёт ${item.host_name}`}</span></span>{item.state==='draft'?<span className="dot bc-count">Черновик</span>:<span className="p bc-count">{enrolledLabel(item.enrolled_count)}</span>}<Icon name="chevron-right"/></button>)}</div></PageSection>}
  <Records kind={kind} webinars={rows} canRecord={canRecord} onSummary={setSummaryId}/>
  {open&&<WebinarDialog key={open.id} webinar={open} onClose={()=>setOpenId(null)}/>}
  {summary&&<SummaryDialog webinarId={summary.id} title={summary.title} onClose={()=>setSummaryId(null)}/>}
  {scheduling&&<WebinarCreateDialog open onClose={()=>setScheduling(false)}/>}
  {recording&&<CreateRecordingDialog open onClose={()=>setRecording(false)}/>}
 </div>;
}

function useWebinarActions(){
 const command=useStudioCommand<Webinar|StudioSession>(),navigate=useNavigate(),{toast}=useToast(),[copied,setCopied]=useState<string|null>(null);
 useEffect(()=>{if(!copied)return;const timer=setTimeout(()=>setCopied(null),3000);return()=>clearTimeout(timer);},[copied]);
 return {command,copied,
  enter:(item:Webinar)=>item.session_id?navigate(`/studio/${item.session_id}`):command.mutate({path:'/studio-sessions',body:{resource_kind:'live_event',resource_id:item.id}},{onSuccess:value=>{if('scene' in value)navigate(`/studio/${value.id}`);}}),
  publish:(item:Webinar)=>command.mutate({path:`/webinars/${item.id}/publish`,body:{expected_version:item.version}}),
  copy:async(item:Webinar)=>{const link=new URL(appPath('/webinars'),window.location.origin).href;try{if(!navigator.clipboard?.writeText)throw new Error('clipboard unavailable');await navigator.clipboard.writeText(link);setCopied(item.id);}catch{toast(`Не удалось скопировать. Ссылка для волонтёров: ${link}`,'error');}},
 };
}
type WebinarActionsApi=ReturnType<typeof useWebinarActions>;

/** The host prepares and publishes; anyone on staff can share the volunteers' link once it is published. */
const actionable=(webinar:Webinar)=>webinar.can_host||webinar.state==='published';
function WebinarActions({webinar,actions,size}:{webinar:Webinar;actions:WebinarActionsApi;size?:'lg'}){
 const busy=actions.command.isPending,copy=<Button variant="secondary" size={size} onClick={()=>{void actions.copy(webinar);}}>{actions.copied===webinar.id?'Ссылка скопирована':'Скопировать ссылку'}</Button>;
 if(webinar.can_host&&webinar.state==='draft')return <><Button size={size} disabled={busy} onClick={()=>actions.publish(webinar)}>Опубликовать</Button><Button variant="secondary" size={size} disabled={busy} onClick={()=>actions.enter(webinar)}>Подготовить эфир</Button></>;
 if(webinar.can_host)return <><Button size={size} disabled={busy} onClick={()=>actions.enter(webinar)}>Подготовить эфир</Button>{copy}</>;
 return webinar.state==='published'?copy:null;
}
function CommandError({actions}:{actions:WebinarActionsApi}){const error=actions.command.error;return error?<p className="p bc-error" role="alert">{error instanceof Error?error.message:'Не удалось выполнить действие.'}</p>:null;}

function NextWebinar({webinar}:{webinar:Webinar}){
 const actions=useWebinarActions();
 return <section className="card-hero compact" aria-labelledby="bc-next-title"><div className="hero-grid"><div className="hero-copy">
  <p className="eyebrow">{nextLabel(webinar.starts_at)}</p>
  <h2 className="hero-title" id="bc-next-title">{webinar.title}</h2>
  <p className="hero-line">{fullWhen(webinar.starts_at)}{webinar.host_name&&`, ведёт ${webinar.host_name}`}</p>
  {webinar.state==='draft'&&<p className="dot bc-hero-status">Черновик, участники его пока не видят</p>}
  {actionable(webinar)&&<div className="actions"><WebinarActions webinar={webinar} actions={actions} size="lg"/></div>}
  <CommandError actions={actions}/>
 </div><span className="hero-art" aria-hidden="true"><Icon name="video"/></span></div></section>;
}
function WebinarDialog({webinar,onClose}:{webinar:Webinar;onClose:()=>void}){
 const actions=useWebinarActions();
 return <Dialog open onClose={onClose} title={webinar.title} footer={actionable(webinar)?<WebinarActions webinar={webinar} actions={actions}/>:undefined}><div className="bc-dialog">
  <p className="p">{fullWhen(webinar.starts_at)}, {webinar.duration_minutes} минут{webinar.host_name&&`, ведёт ${webinar.host_name}`}</p>
  <p className={webinar.state==='draft'?'dot':'dot dot-green'}>{webinar.state==='draft'?'Черновик, участники его пока не видят':`Опубликован, ${enrolledLabel(webinar.enrolled_count).toLowerCase()}`}</p>
  {webinar.description&&<p className="p">{webinar.description}</p>}
  <CommandError actions={actions}/>
 </div></Dialog>;
}
function DateChip({value}:{value:string}){const chip=dateChip(value);return <span className="date-chip"><b>{chip.day}</b><span>{chip.month}</span></span>;}

interface RecordItem {key:string;kind:RecordKind;title:string;at:number;meta:string;length:string|null;project?:RecordingProject;webinar?:Webinar;}
/** Recordings newest first. A finished webinar the user can write a summary for stays listed even without a recording. */
export function recordItems(projects:readonly RecordingProject[],webinars:readonly Webinar[]):RecordItem[]{
 const byId=new Map(webinars.map(item=>[item.id,item])),recorded=new Set<string>();
 const items:RecordItem[]=projects.map(project=>{const webinar=project.live_event_id?byId.get(project.live_event_id):undefined;if(webinar)recorded.add(webinar.id);return {key:project.id,kind:project.mode==='live'?'live':'lesson',title:project.title,at:Date.parse(webinar?.starts_at??project.created_at??'')||0,meta:project.mode!=='live'?'Видео для урока':webinar?`Эфир ${dayMonth(webinar.starts_at)}`:'Запись эфира',length:videoLength(project.duration_ms),project,webinar};});
 for(const webinar of webinars)if(webinar.state==='ended'&&webinar.can_manage_summary&&!recorded.has(webinar.id))items.push({key:webinar.id,kind:'live',title:webinar.title,at:Date.parse(webinar.starts_at),meta:`Эфир ${dayMonth(webinar.starts_at)}`,length:null,webinar});
 return items.sort((a,b)=>b.at-a.at);
}
const recordFilters=[{value:'all',label:'Все'},{value:'live',label:'Эфиры'},{value:'lesson',label:'Видео для уроков'}];
const emptyTitles:Record<string,string>={all:'Записей пока нет',live:'Записей эфиров пока нет',lesson:'Видео для уроков пока нет'};

function Records({kind,webinars,canRecord,onSummary}:{kind?:RecordKind;webinars:readonly Webinar[];canRecord:boolean;onSummary:(id:string)=>void}){
 const [filter,setFilter]=useState<string>(kind??'all'),projects=useRecordingProjects(canRecord),[attaching,setAttaching]=useState<RecordingProject|null>(null);
 const items=recordItems(projects.data?.pages.flatMap(page=>page.items)??[],webinars).filter(item=>filter==='all'||item.kind===filter);
 return <PageSection className="section" title="Записи" actions={<Segmented label="Какие записи показать" value={filter} onChange={setFilter} options={recordFilters}/>}>
  {canRecord&&projects.isPending?<LoadingState label="Загружаем записи…"/>:canRecord&&projects.error?<ErrorState error={projects.error} retry={()=>{void projects.refetch();}}/>:items.length?<div className="grid-3">{items.map(item=><RecordCard key={item.key} item={item} canRecord={canRecord} onAttach={setAttaching} onSummary={onSummary}/>)}</div>:<EmptyState title={emptyTitles[filter]} description={filter==='live'?'Записи эфиров появятся здесь после окончания.':'Запишите видео, и его можно будет добавить в урок.'}/>}
  {projects.hasNextPage&&<Button className="bc-more" variant="secondary" loading={projects.isFetchingNextPage} onClick={()=>{void projects.fetchNextPage();}}>Ещё записи</Button>}
  <AttachLessonDialog project={attaching} onClose={()=>setAttaching(null)}/>
 </PageSection>;
}
function RecordCard({item,canRecord,onAttach,onSummary}:{item:RecordItem;canRecord:boolean;onAttach:(project:RecordingProject)=>void;onSummary:(id:string)=>void}){
 const {project,webinar}=item,summary=webinar?.state==='ended'&&webinar.can_manage_summary;
 return <article className="rec-card">
  {project?<Link className="rec-thumb" to={`/fund/recordings/${project.id}`} aria-label={`Открыть запись «${item.title}»`}><Icon name="play"/>{item.length&&<span className="rec-len">{item.length}</span>}</Link>:<div className="rec-thumb is-empty" role="img" aria-label="Эфир без записи"><Icon name="video"/></div>}
  <h3 className="h3">{item.title}</h3>
  <span className="meta">{item.meta}</span>
  {(project||summary)&&<div className="rec-actions">
   {project&&(project.target_lesson_id?<LessonLink id={project.target_lesson_id}/>:canRecord&&project.state!=='archived'&&<Button variant="secondary" size="sm" onClick={()=>onAttach(project)}>Добавить в курс</Button>)}
   {summary&&<Button variant={project?'ghost':'secondary'} size="sm" onClick={()=>onSummary(webinar.id)}>Итоги эфира</Button>}
  </div>}
 </article>;
}
function LessonLink({id}:{id:string}){const tracks=useAuthorTracks(),title=lessonTitle(tracks.data,id);return <Link className="btn btn-ghost btn-sm" to={`/fund/learning/lessons/${encodeURIComponent(id)}`}><Icon name="book"/>{title?`В уроке «${title}»`:'Открыть урок'}</Link>;}
