import {useEffect,useRef,useState,type FormEvent} from 'react';
import {Link,useLocation,useNavigate} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {BookOpen,MessageCircle,Send} from 'lucide-react';
import {Button,Card,Dialog,ErrorState,Icon,LoadingState,cx} from '../../ui';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import {useHistory,useKnowledgeCommand,useMentorRun,type Fragment,type MentorRun} from './api';
import './knowledge.css';
export function FragmentDialog({fragment,onClose}:{fragment:Fragment;onClose:()=>void}){
 const query=useQuery({queryKey:keys.detail('knowledge-fragment',fragment.id),queryFn:({signal})=>api<Fragment>(`/knowledge/fragments/${fragment.id}`,{signal}),staleTime:0});
 return <Dialog open onClose={onClose} title={fragment.title}>{query.isFetching?<LoadingState label="Проверяем доступ к источнику…"/>:query.error?<ErrorState error={query.error}/>:<p className="knowledge-source-text">{query.data?.text}</p>}</Dialog>;
}
export function MentorAnswer({run}:{run:MentorRun}){
 const command=useKnowledgeCommand(),[fragment,setFragment]=useState<Fragment|null>(null),[sent,setSent]=useState(false),[reported,setReported]=useState(false);
 const pending=['queued','calling'].includes(run.state),unavailable=['unavailable','budget_exceeded','unknown','failed','cancelled'].includes(run.state);
 async function forward(kind:'escalate'|'report'){try{await command.mutateAsync({path:`/mentor/runs/${run.id}/${kind}`,body:{}});kind==='report'?setReported(true):setSent(true);}catch{}}
 return <><Card className="mentor-answer"><p className="eyebrow">Ваш вопрос</p><h2>{run.question}</h2>{pending?<LoadingState label="Готовим ответ по материалам фонда…"/>:run.answer?<><p className="mentor-answer-text">{run.answer}</p><p className="meta">{run.state==='answered_by_coordinator'?'Ответ координатора':'Ответ ИИ по опубликованным материалам'}</p><div className="mentor-citations">{run.citations.map(item=><Button variant="secondary" size="sm" key={item.id} onClick={()=>setFragment(item)}><BookOpen size={16}/>{item.title}</Button>)}</div></>:<div className="mentor-fallback"><MessageCircle size={32}/><h3>{run.state==='unknown'?'В материалах нет достаточного ответа':run.state==='sources_unavailable'?'Источник ответа больше недоступен':'ИИ-наставник сейчас недоступен'}</h3><p>{run.question_id?'Вопрос в очереди координатора. Его ответ появится здесь.':'Можно посмотреть найденные материалы или передать вопрос координатору.'}</p></div>}{run.fragments.length>0&&!run.answer&&<div className="mentor-found"><h3>Материалы по теме</h3>{run.fragments.map(item=><button key={item.id} onClick={()=>setFragment(item)}><BookOpen size={18}/><span><b>{item.title}</b><small>{item.text.slice(0,150)}…</small></span></button>)}</div>}<div className="actions">{!run.question_id&&!sent&&<Button variant="ghost" onClick={()=>void forward('escalate')} disabled={command.isPending}><Send size={18}/>Спросить координатора</Button>}{(sent||run.question_id)&&<p className="meta" role="status">Вопрос передан в очередь координатора.</p>}{run.answer&&!reported&&<Button variant="ghost" onClick={()=>void forward('report')} disabled={command.isPending}>В ответе ошибка</Button>}{reported&&<p role="status">Замечание сохранено для проверки.</p>}</div>{command.error&&<ErrorState error={command.error}/>}</Card>{fragment&&<FragmentDialog fragment={fragment} onClose={()=>setFragment(null)}/>}</>;
}
/** Splits a mentor answer into the canvas parts: bold first sentence, numbered steps, «Можно сказать так» quote. */
export type AnswerPart={kind:'p';text:string}|{kind:'steps';items:string[]}|{kind:'say';text:string};
const stepLine=/^(?:\d{1,2}[.)]|[-–—•*])\s+(.+)$/;
const sayLine=/^можно сказать(?:\s+так)?\s*[:—–-]?\s*(.*)$/i;
const quoted=/^[«"„“].+[»"“”]$/;
export function answerParts(text:string):{lead:string;parts:AnswerPart[]}{
 const parts:AnswerPart[]=[];let quote=false,joined=false;
 for(const raw of text.replace(/\r/g,'').split('\n')){
  const line=raw.trim();
  if(!line){joined=false;continue;}
  const last=parts[parts.length-1],step=stepLine.exec(line),say=sayLine.exec(line);
  if(step){quote=false;joined=false;if(last?.kind==='steps')last.items.push(step[1]);else parts.push({kind:'steps',items:[step[1]]});continue;}
  if(say){joined=false;if(say[1])parts.push({kind:'say',text:say[1]});else quote=true;continue;}
  if(quote||quoted.test(line)){quote=false;joined=false;parts.push({kind:'say',text:line});continue;}
  if(joined&&last?.kind==='p')last.text=`${last.text} ${line}`;else parts.push({kind:'p',text:line});
  joined=true;
 }
 const first=parts[0];
 if(first?.kind!=='p')return {lead:'',parts};
 const match=/^(.+?[.!?…])(?:\s+(.*))?$/s.exec(first.text);
 const lead=match?match[1]:first.text,rest=match?.[2]?.trim();
 return {lead,parts:rest?[{kind:'p',text:rest},...parts.slice(1)]:parts.slice(1)};
}
function AnswerText({text}:{text:string}){
 const {lead,parts}=answerParts(text);
 return <>{lead&&<p className="strong ask-lead">{lead}</p>}{parts.map((part,i)=>part.kind==='steps'
  ?<ol className="steps-list" key={i}>{part.items.map((item,n)=><li key={n}><span aria-hidden="true">{n+1}</span>{item}</li>)}</ol>
  :part.kind==='say'?<div className="say" key={i}>{part.text}</div>
  :<p className="ask-text" key={i}>{part.text}</p>)}</>;
}
/** Steps from the «Срочная ситуация» board; shown when the server flags a child-safety disclosure. */
const urgentSteps=['Выслушай и скажи: «Ты не виноват»','Не расспрашивай дальше и не обещай хранить секрет','Запиши его слова, без своих выводов'];
function UrgentCard(){
 return <section className="card-hero alarm ask-urgent" aria-labelledby="ask-urgent-title">
  <p className="eyebrow">Это важно сделать сразу</p>
  <h2 className="h2" id="ask-urgent-title">Скажи ведущей прямо сейчас</h2>
  <ol className="steps-list">{urgentSteps.map((step,n)=><li key={step}><span aria-hidden="true">{n+1}</span>{step}</li>)}</ol>
  <div className="actions"><Link className="btn btn-primary btn-lg" to="/messages">Написать координатору</Link><a className="btn btn-secondary btn-lg" href="tel:112">Позвонить 112</a></div>
 </section>;
}
const unavailableTitle=(state:string)=>state==='unknown'?'В материалах нет достаточного ответа':state==='sources_unavailable'?'Источник ответа больше недоступен':'ИИ-наставник сейчас недоступен';
/** Volunteer chat view of one question; the staff preview keeps MentorAnswer above. */
function MentorReply({run}:{run:MentorRun}){
 const command=useKnowledgeCommand(),[fragment,setFragment]=useState<Fragment|null>(null),[sent,setSent]=useState(false),[reported,setReported]=useState(false);
 const pending=['queued','calling'].includes(run.state);
 const sources=[...new Map((run.answer?run.citations:run.fragments).map(item=>[item.source_id,item])).values()];
 async function forward(kind:'escalate'|'report'){try{await command.mutateAsync({path:`/mentor/runs/${run.id}/${kind}`,body:{}});if(kind==='report')setReported(true);else setSent(true);}catch{/* command.error is rendered below */}}
 return <>
  <div className="bubble bubble-me">{run.question}</div>
  {run.urgent&&<UrgentCard/>}
  {pending?<div className="ai-box ask-answer"><LoadingState label="Ищу ответ в материалах фонда…"/></div>
   :run.answer?<div className="ai-box ask-answer">{run.state==='answered_by_coordinator'&&<p className="eyebrow">Ответ координатора</p>}<AnswerText text={run.answer}/></div>
   :<div className="ai-box ask-answer"><h2 className="h3">{unavailableTitle(run.state)}</h2><p className="ask-text">{run.question_id?'Вопрос у координатора. Его ответ появится здесь.':'Посмотри материалы по теме или спроси координатора.'}</p></div>}
  {sources.length>0&&<div className="chips">{sources.map(item=><button type="button" className="cite" key={item.id} onClick={()=>setFragment(item)}>{item.title}</button>)}</div>}
  <div className="row wrap ask-actions">
   {!run.question_id&&!sent&&<Button variant="ghost" onClick={()=>void forward('escalate')} disabled={command.isPending}>Спросить координатора</Button>}
   {sent&&<p className="ask-note" role="status">Вопрос передан в очередь координатора.</p>}
   {run.answer&&!reported&&<button type="button" className="quiet-link" onClick={()=>void forward('report')} disabled={command.isPending}>В ответе ошибка</button>}
   {reported&&<p className="ask-note" role="status">Замечание сохранено для проверки.</p>}
  </div>
  {command.error&&<ErrorState error={command.error}/>}
  {fragment&&<FragmentDialog fragment={fragment} onClose={()=>setFragment(null)}/>}
 </>;
}
export function MentorPage(){
 const location=useLocation(),navigate=useNavigate(),prefill=(location.state as {question?:string}|null)?.question??'';
 const history=useHistory(),command=useKnowledgeCommand(),[selected,setSelected]=useState<string|null>(null),[question,setQuestion]=useState(prefill);
 const input=useRef<HTMLInputElement>(null);
 useEffect(()=>{if(prefill){setQuestion(prefill);input.current?.focus();}},[prefill]);
 const items=history.data??[];
 const active=selected??(prefill?null:items[0]?.id??null);
 const current=useMentorRun(active);const run=current.data;
 async function ask(event:FormEvent){
  event.preventDefault();
  try{const result=await command.mutateAsync({path:'/mentor/runs',body:{question}}) as MentorRun;setSelected(result.id);setQuestion('');if(prefill)navigate('/mentor',{replace:true,state:null});}catch{/* command.error is rendered below */}
 }
 return <div className="ask-page">
  <Link className="back" to="/academy"><Icon name="chevron-left"/>Обучение</Link>
  <div className="page-head"><h1 className="h1">Что делать, если…</h1></div>
  <div className="chat-grid">
   <div className="threads" role="group" aria-label="Мои вопросы">
    {history.isPending?<LoadingState/>:history.error?<ErrorState error={history.error} retry={()=>void history.refetch()}/>:items.length?items.map(item=><button type="button" key={item.id} className={cx('thread',item.id===active&&'is-on')} aria-pressed={item.id===active} onClick={()=>setSelected(item.id)}><span className="grow">{item.question}</span></button>):<p className="ask-empty">Здесь будут твои вопросы.</p>}
   </div>
   <div className="chat">
    <div className="chat-feed" aria-live="polite">
     {active&&current.isPending?<LoadingState/>:current.error?<ErrorState error={current.error} retry={()=>void current.refetch()}/>:run?<MentorReply key={run.id} run={run}/>
      :<div className="ai-box ask-answer"><h2 className="h3">Спроси о том, что важно на занятии</h2><p className="ask-text">Наставник отвечает по материалам фонда и показывает источники. Если ответа не хватает, поможет координатор.</p></div>}
    </div>
    {command.error&&<div className="ask-error"><ErrorState error={command.error}/></div>}
    <form className="chat-compose" onSubmit={event=>void ask(event)}>
     <label className="sr-only" htmlFor="mentor-question">Вопрос</label>
     <input ref={input} id="mentor-question" className="input" placeholder="Что делать, если ребёнок…" maxLength={3000} value={question} onChange={event=>setQuestion(event.target.value)}/>
     <button type="submit" className="btn btn-ai" disabled={question.trim().length<2||command.isPending} aria-busy={command.isPending||undefined}>Спросить</button>
    </form>
   </div>
  </div>
  {!run?.urgent&&<p className="ask-safety"><Icon name="alert"/><span>Если есть угроза жизни или здоровью, сразу зови ведущую, при необходимости звони <a href="tel:112">112</a>.</span></p>}
 </div>;
}
