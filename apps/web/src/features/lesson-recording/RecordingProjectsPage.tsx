import {useState,type FormEvent} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {Button,Card,Combobox,Dialog,EmptyState,ErrorState,Field,Icon,Input,LoadingState} from '../../ui';
import {useAuthorTracks} from '../learning/authorApi';
import {useRecordingCommand,useRecordingProjects,type RecordingProject} from './api';
import {projectLabels} from './model';
import './recording.css';
export function RecordingProjectsPage() {
 const projects=useRecordingProjects(),tracks=useAuthorTracks(),command=useRecordingCommand<RecordingProject>(),navigate=useNavigate();
 const [creating,setCreating]=useState(false),[title,setTitle]=useState(''),[lesson,setLesson]=useState('');
 const targets=tracks.data?.filter(track=>!track.archived).flatMap(track=>track.lessons.filter(item=>!item.archived).map(item=>({value:item.id,label:`${track.title} · ${item.title}`})))??[];
 async function create(event:FormEvent){event.preventDefault();try{const project=await command.mutateAsync({path:'/recording-projects',body:{title:title.trim(),target_lesson_id:lesson||null,mode:'solo'}});navigate(`/fund/recordings/${project.id}`);}catch{/* command error is visible in the form */}}
 return <div className="recording-page"><div className="head recording-heading"><h1 className="h1">Записи уроков</h1><Button onClick={()=>setCreating(true)}><Icon name="plus"/>Новая запись</Button></div>
 <Card tone="hero"><div className="hero-grid"><div className="hero-copy"><p className="eyebrow">Студия преподавателя</p><h2 className="hero-title">Твой урок — в удобное время</h2><p className="lead">Подготовь материалы и кадр, запиши дубль и посмотри результат перед передачей в урок.</p></div><span className="hero-art" aria-hidden="true"><Icon name="camera"/></span></div></Card>
 <section className="section" aria-labelledby="recording-projects"><h2 className="h2" id="recording-projects">Мои проекты</h2>
 {projects.isPending?<LoadingState label="Загружаем проекты…"/>:projects.error?<ErrorState error={projects.error} retry={()=>{void projects.refetch();}}/>:projects.data?.pages.some(page=>page.items.length)?<div className="grid-2 recording-projects">{projects.data.pages.flatMap(page=>page.items).map(project=><Link className="card recording-project" key={project.id} to={`/fund/recordings/${project.id}`}><span className="art art-y" aria-hidden="true"><Icon name="film"/></span><span><span className="tag">{projectLabels[project.state]??'Проект записи'}</span><h3 className="h3">{project.title}</h3><p className="p">{project.target_lesson_id?'Для урока в Академии':'Урок можно выбрать позднее'}</p></span><Icon name="arrow-right"/></Link>)}</div>:<EmptyState title="Первая запись начинается с проекта" description="Можно подготовить кадр и материалы, а затем выбрать подходящий дубль." action={<Button onClick={()=>setCreating(true)}>Создать проект</Button>}/>}
 {projects.hasNextPage&&<Button variant="secondary" loading={projects.isFetchingNextPage} onClick={()=>{void projects.fetchNextPage();}}>Ещё проекты</Button>}</section>
 <Dialog open={creating} onClose={()=>setCreating(false)} title="Новая запись урока"><form className="recording-form" onSubmit={create}><Field label="Название записи"><Input required maxLength={300} value={title} onChange={event=>setTitle(event.target.value)} placeholder="О чём будет урок"/></Field><Combobox label="Урок в Академии" value={lesson} onChange={setLesson} disabled={tracks.isPending} options={[{value:'',label:'Сначала без урока'},...targets]}/>{tracks.error&&<p className="meta">Не удалось загрузить уроки. Проект можно создать без привязки.</p>}<p className="p">Материалы и выбранный дубль остаются приватными до отдельной проверки и публикации.</p>{command.error&&<ErrorState error={command.error}/>}<Button type="submit" loading={command.isPending} disabled={!title.trim()}>Создать проект</Button></form></Dialog>
 </div>;
}
