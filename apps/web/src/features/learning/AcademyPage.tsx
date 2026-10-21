import {useEffect,useState} from 'react';
import {Link,useParams,useSearchParams} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {BookOpen,CheckCircle,GraduationCap} from 'lucide-react';
import {Button,Card,EmptyState,ErrorState,Field,LoadingState,Textarea} from '../../ui';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import {useLearningCommand,useLesson,usePreparation} from './api';
import {AssessmentPlayer} from './OnboardingPage';
import {ContentBlock,type Block} from './Blocks';
import './learning.css';
import './builder.css';
type Submission=components['schemas']['TaskSubmissionView'];
function TaskAnswer({block,lessonId,assignmentId}:{block:Block;lessonId:string;assignmentId:string}){
 const query=useQuery({queryKey:keys.detail('learning-tasks',assignmentId),queryFn:({signal})=>api<Submission[]>(`/learning/assignments/${assignmentId}/tasks`,{signal})});
 const command=useLearningCommand(),[text,setText]=useState(''),[saved,setSaved]=useState(false),[version,setVersion]=useState(0),[dirty,setDirty]=useState(false);
 const value=query.data?.find(item=>item.block_id===block.id);
 useEffect(()=>{if(!dirty){setText(value?.answer_text??'');setVersion(value?.version??0);}},[value,dirty]);
 async function save(){try{const result=await command.mutateAsync({path:`/learning/lessons/${lessonId}/tasks/${block.id}`,body:{assignment_id:assignmentId,answer_text:text,expected_version:version}}) as Submission;setVersion(result.version);setSaved(true);setDirty(false);}catch{}}
 return <Card><h2>{block.title||'Задание'}</h2><p style={{whiteSpace:'pre-wrap'}}>{block.text}</p>{Boolean((block as unknown as {required?:boolean}).required)&&<p className="tag">Обязательное задание</p>}<Field label="Ваш ответ"><Textarea rows={5} value={text} disabled={query.isPending} onChange={e=>{setText(e.target.value);setDirty(true);setSaved(false);}}/></Field><Button disabled={command.isPending||!text.trim()} onClick={()=>void save()}>Сохранить ответ</Button>{saved&&<p role="status">Ответ сохранён.</p>}{query.error&&<ErrorState error={query.error} retry={()=>void query.refetch()}/ >}{command.error&&<ErrorState error={command.error}/ >}</Card>;
}
export function AcademyPage(){
 const query=usePreparation();
 if(query.isPending)return <LoadingState label="Загружаем ваши треки…"/>;
 if(query.error)return <ErrorState error={query.error} retry={()=>void query.refetch()}/>;
 const assignments=query.data?.assignments??[];
 return <div className="academy-page"><h1>Академия</h1><Card tone="hero"><div className="builder-hero"><div><p className="eyebrow">Подготовка и обучение</p><h2 className="hero-title">Учимся помогать вместе</h2><p className="lead">Материалы фонда, задания и разборы ситуаций. Прогресс сохраняется — можно заниматься в своём темпе.</p></div><GraduationCap size={100} aria-hidden="true"/></div></Card><section className="section"><h2>Мои треки</h2>{!assignments.length?<EmptyState title="Пока нет назначенных треков" description="Координатор подберёт материалы для вашей роли."/>:<div className="academy-tracks">{assignments.map(item=>{const completed=item.lessons.filter(l=>l.completed).length;return <Card className="academy-track" key={item.id}><span className={`art ${item.completed?'art-g':'art-y'}`}>{item.completed?<CheckCircle/>:<GraduationCap/>}</span><h3>{item.title}</h3><p>{item.intro}</p><div className="row"><progress value={completed} max={item.lessons.length||1} aria-label="Пройдено уроков"/><b>{completed} / {item.lessons.length}</b></div><p className="meta">Версия {item.release_number} · {item.completed?'Пройдено':'В процессе'}</p><details><summary>Уроки трека</summary><div className="academy-module-list">{item.lessons.map(lesson=><Link key={lesson.id} to={`/academy/lessons/${lesson.id}?assignment=${item.id}`}>{lesson.completed?'✓':'○'} {lesson.title}</Link>)}{item.assessment_version_id&&<Link to={`/academy/lessons/assessment?assignment=${item.id}`}>Тест по материалам</Link>}</div></details><Link className="btn btn-primary" to={`/academy/lessons/${item.lessons.find(l=>!l.completed)?.id??item.lessons[0]?.id}?assignment=${item.id}`}>Открыть трек</Link></Card>;})}</div>}</section></div>;
}
export function LessonPage(){
 const params=useParams(),[search]=useSearchParams();const id=params.id??params.versionId??'';
 const prep=usePreparation(),lesson=useLesson(id!=='assessment'?id:undefined),command=useLearningCommand(),[saved,setSaved]=useState(false);
 const assignment=prep.data?.assignments.find(item=>item.id===search.get('assignment'))??prep.data?.assignments.find(item=>item.lessons.some(l=>l.id===id));
 async function complete(){if(!assignment)return;try{await command.mutateAsync({path:`/learning/progress/${id}/complete`,body:{assignment_id:assignment.id}});await command.mutateAsync({path:'/policy-acknowledgements',body:{assignment_id:assignment.id}});setSaved(true);}catch{}}
 if(prep.isPending)return <LoadingState/>;
 if(prep.error)return <ErrorState error={prep.error} retry={()=>void prep.refetch()}/>;
 if(!assignment)return <EmptyState title="Этот урок вам пока не назначен" action={<Link to="/academy">К моим трекам</Link>}/>;
 return <div className="academy-lesson"><aside className="academy-outline card"><p className="eyebrow">{assignment.title}</p>{assignment.lessons.map(l=><Link key={l.id} aria-current={id===l.id?'page':undefined} to={`/academy/lessons/${l.id}?assignment=${assignment.id}`}>{l.completed?<CheckCircle size={18}/>:<BookOpen size={18}/>}<span>{l.title}</span></Link>)}{assignment.assessment_version_id&&<Link aria-current={id==='assessment'?'page':undefined} to={`/academy/lessons/assessment?assignment=${assignment.id}`}>Тест по материалам</Link>}<Link to="/academy">Все треки</Link></aside><main className="learning-page">{id==='assessment'?<AssessmentPlayer assignment={assignment}/>:lesson.isPending?<LoadingState/>:lesson.error?<ErrorState error={lesson.error} retry={()=>void lesson.refetch()}/>:lesson.data&&<><p className="eyebrow">{lesson.data.minutes} минут · версия трека {assignment.release_number}</p><h1>{lesson.data.title}</h1><div className="a-blocks">{lesson.data.blocks.map((raw,i)=>{const block=raw as unknown as Block;return block.type==='task'?<TaskAnswer key={block.id} block={block} lessonId={id} assignmentId={assignment.id}/>:<ContentBlock key={i} block={block} lessonId={id}/>;})}</div><div className="actions a-nav"><Button disabled={command.isPending} onClick={()=>void complete()}>Отметить урок прочитанным</Button>{saved&&<p role="status">Прогресс сохранён.</p>}</div>{command.error&&<ErrorState error={command.error}/ >}</>}</main></div>;
}
