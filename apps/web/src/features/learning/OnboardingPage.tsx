import {useEffect,useRef,useState} from 'react';
import {Link,Navigate,useSearchParams} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import {ArrowLeft, ArrowRight, Sparkles} from 'lucide-react';
import {Button, Card, ErrorState, LoadingState} from '../../ui';
import {ContentBlock, type Block} from './Blocks';
import {useAttempt, useLearningCommand, useLesson, usePreparation, type Assignment, type Attempt, type Feedback} from './api';
import './learning.css';

export function AssessmentPlayer({assignment}:{assignment:Assignment}) {
  const command=useLearningCommand();
  const [localId,setLocalId]=useState<string|null>(null);
  const [starting,setStarting]=useState(false);
  const [questionIndex,setQuestionIndex]=useState<number|null>(null);
  const id=localId??assignment.latest_attempt_id;
  const attempt=useAttempt(id);
  const run=attempt.data;
  const bookings=useQuery({queryKey:keys.list('interviews',{staff:false}),enabled:assignment.track_key==='introduction'&&run?.state==='submitted',queryFn:({signal})=>api<components['schemas']['BookingView'][]>('/api/v1/me/interviews',{signal})});
  const booking=bookings.data?.find(item=>item.status==='booked');
  const score=run?.score??0;
  const scoreLine=assignment.track_key==='introduction'?`${score} из ${run?.total??0} — ${score===run?.total?'отлично!':score>=7?'хорошо!':score>=4?'неплохо!':'для начала нормально'}`:`Правильных ответов: ${score} из ${run?.total??0}`;
  const resultNext=assignment.track_key!=='introduction'?'Ответы сохранены. Можно вернуться к своим трекам.':booking?`Остальному научим. До встречи ${new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',timeZone:'Europe/Moscow'}).format(new Date(booking.starts_at))}!`:bookings.isPending||bookings.error?'Остальному научим. Время встречи — в личном кабинете.':'Остальному научим. Осталось выбрать время встречи';
  const answered=run?.answers??[];
  const firstUnanswered=run?.questions.findIndex(q=>!answered.some(a=>a.question_id===q.id))??0;
  const index=questionIndex??(firstUnanswered<0?Math.max(0,(run?.total??1)-1):firstUnanswered);
  const question=run?.questions[Math.max(0,index)];
  const feedback=question?answered.find(a=>a.question_id===question.id):undefined;
  async function start() {
    // Clear the previous result immediately; the active attempt is server-owned.
    setStarting(true);setQuestionIndex(0);
    try { const result=await command.mutateAsync({path:`/assessments/${assignment.assessment_version_id}/attempts`,body:{assignment_id:assignment.id}}) as Attempt;setLocalId(result.id); }
    catch { /* command.error is rendered below */ }
    finally {setStarting(false);}
  }
  async function pick(selected:number) {
    if(!run||!question)return;
    await command.mutateAsync({path:`/assessment-attempts/${run.id}/answers`,body:{question_id:question.id,selected_option:selected}}) as Feedback;
  }
  async function next() {
    if(!run)return;
    if(index+1<run.total){setQuestionIndex(index+1);window.scrollTo({top:0});}
    else {await command.mutateAsync({path:`/assessment-attempts/${run.id}/submit`,body:{}});setQuestionIndex(null);}
  }
  if(starting)return <LoadingState label="Начинаем новую попытку…"/>;
  if(id&&attempt.isPending)return <LoadingState label="Загружаем сохранённые ответы…"/>;
  if(attempt.error)return <ErrorState error={attempt.error} retry={()=>void attempt.refetch()}/>;
  return <section className="learning-test"><h1>{run?.title??'Тест по материалам'}</h1>{command.error&&<ErrorState error={command.error}/>}
    {!run&&<Card tone="hero" className="action-card"><p className="a-lead">{assignment.track_key==='introduction'?'10 вопросов по тому, что вы прочитали.':'Проверьте, как вы поняли материалы. После ответа будет объяснение.'}</p><div className="actions"><Button size="lg" onClick={()=>void start()}>Начать</Button></div></Card>}
    {run?.state==='submitted'&&<Card tone="hero"><div className="learning-result"><div><p className="eyebrow">{assignment.track_key==='introduction'?'Тест пройден':'Тест завершён'}</p><h2>{scoreLine}</h2><p className="a-lead">{resultNext}</p><div className="actions"><Link className="btn btn-dark" to={assignment.track_key==='introduction'?'/application':'/academy'}>{assignment.track_key==='introduction'?'Перейти в личный кабинет':'Мои треки'}</Link>{assignment.track_key!=='introduction'&&<Button variant="ghost" onClick={()=>void start()}>Пройти тест ещё раз</Button>}</div></div><Sparkles size={100} aria-hidden="true"/></div></Card>}
    {run?.state==='active'&&question&&<><Card><p className="eyebrow">Вопрос {Math.max(0,index)+1} из {run.total}</p><h2 className="h2">{question.prompt}</h2><div className="a-answers">{question.options.map((option,i)=><button key={i} className={`a-answer ${feedback?.selected_option===i?(feedback.correct?'is-right':'is-wrong'):''}`} disabled={command.isPending||Boolean(feedback)} onClick={()=>void pick(i).catch(()=>undefined)}>{option}</button>)}</div></Card>{feedback&&<div className={`a-fb ${feedback.correct?'is-ok':'is-bad'}`} role="status"><h3>{feedback.correct?'Верно!':'Не совсем'}</h3><p>{feedback.explanation}</p><Button size="lg" disabled={command.isPending} onClick={()=>void next().catch(()=>undefined)}>{index+1<run.total?'Следующий вопрос':'Завершить'}</Button></div>}</>}
  </section>;
}
function Journey({assignment,earlierCompleted,hasEarlier}:{assignment:Assignment;earlierCompleted:boolean;hasEarlier:boolean}) {
  const [params,setParams]=useSearchParams();
  const command=useLearningCommand();
  const end=useRef<HTMLDivElement>(null),[read,setRead]=useState<string[]>([]);
  const fallback=assignment.lessons.find(item=>!item.completed)?.id??'test';
  const firstIncomplete=assignment.lessons.findIndex(item=>!item.completed);
  const requested=params.get('assignment')===assignment.id?params.get('lesson'):null;
  const requestedIndex=assignment.lessons.findIndex(item=>item.id===requested);
  const allowed=requested==='test'?firstIncomplete<0:requestedIndex>=0&&(firstIncomplete<0||requestedIndex<=firstIncomplete);
  const current=allowed&&requested?requested:fallback;
  const requestedCard=Number(params.get('card')??1);
  const card=params.get('assignment')===assignment.id&&current===requested&&Number.isSafeInteger(requestedCard)&&requestedCard>0?requestedCard-1:0;
  function checkpoint(id:string,index=0){setParams({assignment:assignment.id,lesson:id,card:String(index+1)},{replace:true});}
  function setCard(index:number){checkpoint(current,index);}
  const summary=assignment.lessons.find(item=>item.id===current);
  const layout=summary?.mode==='cards'?'cards':'longread';
  const lesson=useLesson(summary?.id);
  const step=summary?assignment.lessons.indexOf(summary):assignment.lessons.length;
  const blocks=(lesson.data?.blocks??[]) as unknown as Block[];
  const visibleCard=Math.min(card,Math.max(0,blocks.length-1));
  const unlocked=Boolean(summary?.completed||read.includes(current));
  useEffect(()=>{
    if(layout!=='longread'||!lesson.data)return;
    const check=()=>{if(end.current&&end.current.getBoundingClientRect().top<=window.innerHeight)setRead(value=>value.includes(current)?value:[...value,current]);};
    check();window.addEventListener('scroll',check,{passive:true});window.addEventListener('resize',check);
    return()=>{window.removeEventListener('scroll',check);window.removeEventListener('resize',check);};
  },[current,layout,lesson.data]);
  useEffect(()=>{if(summary&&lesson.data&&(card!==visibleCard||params.get('assignment')!==assignment.id||params.get('lesson')!==current))checkpoint(current,visibleCard);},[current,card,visibleCard,lesson.data,summary]);
  function go(id:string,last=false){checkpoint(id,last?Number.MAX_SAFE_INTEGER-1:0);requestAnimationFrame(()=>document.querySelector('.a-ohead')?.scrollIntoView({block:'start'}));}
  async function complete(){
    if(!summary)return;
    await command.mutateAsync({path:`/learning/progress/${summary.id}/complete`,body:{assignment_id:assignment.id}});
    if(step===assignment.lessons.length-1)await command.mutateAsync({path:'/policy-acknowledgements',body:{assignment_id:assignment.id}});
    go(assignment.lessons[step+1]?.id??'test');
  }
  return <div className={`learning-page learning-${layout}`}>{assignment.change_note&&hasEarlier&&<Card tone="soft" className="action-card"><p>Материалы знакомства обновлены.</p>{earlierCompleted&&<p>Ранее вы уже завершили знакомство. Этот результат сохранён; повторное подтверждение не требуется.</p>}<div className="actions"><Link to="/application">Перейти в личный кабинет</Link></div></Card>}<div className="a-ohead"><p className="eyebrow">Шаг {step+1} из {assignment.lessons.length+1}</p><div className="a-seg" aria-hidden="true">{[...assignment.lessons.map(l=>({id:l.id,done:l.completed})),{id:'test',done:assignment.completed}].map((item,i)=><i key={item.id} className={`${item.done?'is-done':''} ${i===step?'is-on':''}`}/>)}</div></div>
    {command.error&&<ErrorState error={command.error}/>}
    {current==='test'?<AssessmentPlayer assignment={assignment}/>:<>{lesson.isPending?<LoadingState label="Загружаем материалы…"/>:lesson.error?<ErrorState error={lesson.error} retry={()=>void lesson.refetch()}/>:lesson.data&&<><div className="learning-module-title"><h1>{lesson.data.title}</h1>{layout==='cards'&&<span>{visibleCard+1} / {blocks.length}</span>}</div>
      <div className="a-blocks">{layout==='cards'?<Card><ContentBlock key={blocks[visibleCard]?.id} block={blocks[visibleCard]} lessonId={lesson.data.id}/></Card>:blocks.map(block=><ContentBlock key={block.id} block={block} lessonId={lesson.data!.id}/>)}</div>
      <div ref={end} aria-hidden="true"/><div className="actions a-nav">{(step>0||visibleCard>0)&&<Button variant="ghost" size="lg" disabled={command.isPending} onClick={()=>visibleCard>0?setCard(visibleCard-1):go(assignment.lessons[step-1].id,true)}><ArrowLeft size={18}/>Назад</Button>}<span className="grow"/><Button size="lg" disabled={command.isPending||(layout==='longread'&&!unlocked)} onClick={()=>layout==='cards'&&visibleCard<blocks.length-1?setCard(visibleCard+1):void complete().catch(()=>undefined)}>{command.isPending?'Сохраняем…':layout==='cards'?(visibleCard<blocks.length-1?'Дальше':step<assignment.lessons.length-1?'К следующему шагу':'К тесту'):!unlocked?'Дочитайте до конца':step<assignment.lessons.length-1?'Понятно, дальше':'Понятно, к тесту'}<ArrowRight size={18}/></Button></div></> }</>}
    <p className="learning-independent">Можно прерваться и вернуться. Выбрать встречу с координатором можно в личном кабинете в любое время.</p>
  </div>;
}
function Introduction() {
 const preparation=usePreparation();
 if(preparation.isPending)return <LoadingState label="Загружаем знакомство с фондом…"/>;
 if(preparation.error)return <ErrorState error={preparation.error} retry={()=>void preparation.refetch()}/>;
 const assignment=preparation.data?.assignments.find(item=>item.track_key==='introduction');
 const hasEarlier=preparation.data?.assignments.some(item=>item.track_key==='introduction'&&item.id!==assignment?.id)??false;
 const earlierCompleted=preparation.data?.assignments.some(item=>item.track_key==='introduction'&&item.id!==assignment?.id&&item.completed)??false;
 return assignment?<Journey key={assignment.id} assignment={assignment} earlierCompleted={earlierCompleted} hasEarlier={hasEarlier}/>:<p>Материалы ещё не опубликованы.</p>;
}
export function OnboardingPage(){return <Introduction/>;}
export function OnboardingCardsPage(){return <Navigate to="/onboarding" replace/>;}
export function OnboardingListPage(){return <Navigate to="/onboarding" replace/>;}
