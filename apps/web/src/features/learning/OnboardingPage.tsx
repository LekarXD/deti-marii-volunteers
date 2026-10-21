import {useState} from 'react';
import {Link} from 'react-router-dom';
import {ArrowLeft, ArrowRight, Sparkles} from 'lucide-react';
import {Button, Card, ErrorState, LoadingState} from '../../ui';
import {ContentBlock, TopicBlocks, type Block} from './Blocks';
import {useAttempt, useLearningCommand, useLesson, usePreparation, type Assignment, type Attempt, type Feedback} from './api';
import './learning.css';

type Layout = 'longread'|'cards'|'list';
function Test({assignment}:{assignment:Assignment}) {
  const command=useLearningCommand();
  const [localId,setLocalId]=useState<string|null>(null);
  const [starting,setStarting]=useState(false);
  const [questionIndex,setQuestionIndex]=useState<number|null>(null);
  const id=localId??assignment.latest_attempt_id;
  const attempt=useAttempt(id);
  const run=attempt.data;
  const answered=run?.answers??[];
  const firstUnanswered=run?.questions.findIndex(q=>!answered.some(a=>a.question_id===q.id))??0;
  const index=questionIndex??(firstUnanswered<0?Math.max(0,(run?.total??1)-1):firstUnanswered);
  const question=run?.questions[Math.max(0,index)];
  const feedback=question?answered.find(a=>a.question_id===question.id):undefined;
  async function start() {
    // Clear the previous result immediately; the active attempt is server-owned.
    setStarting(true);setQuestionIndex(0);
    try { const result=await command.mutateAsync({path:`/assessments/${assignment.assessment_version_id}/attempts`,body:{}}) as Attempt;setLocalId(result.id); }
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
  return <section className="learning-test"><h1>{'Небольшой тест'}</h1>{command.error&&<ErrorState error={command.error}/>}
    {!run&&<Card tone="hero"><p className="a-lead">10 вопросов по тому, что вы прочитали.</p><Button size="lg" onClick={()=>void start()}>Начать</Button></Card>}
    {run?.state==='submitted'&&<Card tone="hero"><div className="learning-result"><div><p className="eyebrow">{assignment.completed?'Знакомство с фондом пройдено':'Тест завершён'}</p><h2>Правильных ответов: {run.score} из {run.total}</h2><p className="a-lead">Дальше — встреча с координатором. Выбрать время можно в личном кабинете.</p><div className="actions"><Link className="btn btn-dark" to="/application">Перейти в личный кабинет</Link><Button variant="ghost" onClick={()=>void start()}>Пройти тест ещё раз</Button></div></div><Sparkles size={100} aria-hidden="true"/></div></Card>}
    {run?.state==='active'&&question&&<><Card><p className="eyebrow">Вопрос {Math.max(0,index)+1} из {run.total}</p><h2 className="h2">{question.prompt}</h2><div className="a-answers">{question.options.map((option,i)=><button key={i} className={`a-answer ${feedback?.selected_option===i?(feedback.correct?'is-right':'is-wrong'):''}`} disabled={command.isPending||Boolean(feedback)} onClick={()=>void pick(i)}>{option}</button>)}</div></Card>{feedback&&<div className={`a-fb ${feedback.correct?'is-ok':'is-bad'}`} role="status"><h3>{feedback.correct?'Верно!':'Не совсем'}</h3><p>{feedback.explanation}</p><Button size="lg" disabled={command.isPending} onClick={()=>void next()}>{index+1<run.total?'Следующий вопрос':'Завершить'}</Button></div>}</>}
  </section>;
}
function Journey({assignment,layout}:{assignment:Assignment;layout:Layout}) {
  const [selection,setSelection]=useState<string|null>(null),[card,setCard]=useState(0);
  const command=useLearningCommand();
  const fallback=assignment.lessons.find(item=>!item.completed)?.id??'test';
  const current=selection??fallback;
  const summary=assignment.lessons.find(item=>item.id===current);
  const lesson=useLesson(summary?.id);
  const step=summary?assignment.lessons.indexOf(summary):assignment.lessons.length;
  const blocks=(lesson.data?.blocks??[]) as unknown as Block[];
  function go(id:string){setSelection(id);setCard(0);window.scrollTo({top:0});}
  async function complete(){
    if(!summary)return;
    await command.mutateAsync({path:`/learning/progress/${summary.id}/complete`,body:{assignment_id:assignment.id}});
    if(step===assignment.lessons.length-1)await command.mutateAsync({path:'/policy-acknowledgements',body:{assignment_id:assignment.id}});
    go(assignment.lessons[step+1]?.id??'test');
  }
  return <div className={`learning-page learning-${layout}`}><div className="learning-view-switch" aria-label="Представление материалов"><Link to="/onboarding">Лента</Link><Link to="/onboarding/cards">Карточки</Link><Link to="/onboarding/list">Темы</Link></div><div className="a-ohead"><p className="eyebrow">Знакомство с фондом · шаг {step+1} из {assignment.lessons.length+1}</p><div className="a-seg" aria-label="Шаги знакомства">{[...assignment.lessons.map(l=>({id:l.id,done:l.completed})),{id:'test',done:assignment.completed}].map((item,i)=><button key={item.id} className={`${item.done?'is-done':''} ${i===step?'is-on':''}`} onClick={()=>go(item.id)} aria-label={`Шаг ${i+1}`} aria-current={i===step?'step':undefined}/>)}</div></div>
    {command.error&&<ErrorState error={command.error}/>}
    {current==='test'?<Test assignment={assignment}/>:<>{lesson.isPending?<LoadingState label="Загружаем материалы…"/>:lesson.error?<ErrorState error={lesson.error} retry={()=>void lesson.refetch()}/>:lesson.data&&<><div className="learning-module-title"><h1>{lesson.data.title}</h1>{layout==='cards'&&<span>{card+1} / {blocks.length}</span>}</div>
      <div className="a-blocks">{layout==='list'?<TopicBlocks key={summary?.id} blocks={blocks} lessonId={lesson.data.id}/>:layout==='cards'?<Card><ContentBlock key={blocks[card]?.id} block={blocks[card]} lessonId={lesson.data.id}/></Card>:blocks.map(block=><ContentBlock key={block.id} block={block} lessonId={lesson.data!.id}/>)}</div>
      <div className="actions a-nav">{(step>0||card>0)&&<Button variant="ghost" size="lg" disabled={command.isPending} onClick={()=>card>0?setCard(card-1):go(assignment.lessons[step-1].id)}><ArrowLeft size={18}/>Назад</Button>}<span className="grow"/><Button size="lg" disabled={command.isPending} onClick={()=>layout==='cards'&&card<blocks.length-1?setCard(card+1):void complete()}>{command.isPending?'Сохраняем…':layout==='cards'&&card<blocks.length-1?'Дальше':step<assignment.lessons.length-1?'Понятно, дальше':'Понятно, к тесту'}<ArrowRight size={18}/></Button></div></> }</>}
    <p className="learning-independent">Можно прерваться и вернуться. Выбрать встречу с координатором можно в личном кабинете в любое время.</p>
  </div>;
}
function Introduction({layout}:{layout:Layout}) {
 const preparation=usePreparation();
 if(preparation.isPending)return <LoadingState label="Загружаем знакомство с фондом…"/>;
 if(preparation.error)return <ErrorState error={preparation.error} retry={()=>void preparation.refetch()}/>;
 const assignment=preparation.data?.assignments[0];
 return assignment?<Journey key={assignment.id} assignment={assignment} layout={layout}/>:<p>Материалы ещё не опубликованы.</p>;
}
export function OnboardingPage(){return <Introduction layout="longread"/>;}
export function OnboardingCardsPage(){return <Introduction layout="cards"/>;}
export function OnboardingListPage(){return <Introduction layout="list"/>;}
