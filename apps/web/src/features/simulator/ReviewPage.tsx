import {useEffect,useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {Button,Combobox,ErrorState,Field,LoadingState,Textarea,cx} from '../../ui';
import {useSimulatorAppeal,useSimulatorCommand,useSimulatorQueue,type AppealDetail,type ReviewQueueItem,type SimulationAssessment} from './api';
import {BackLink,Bubble,ScoreDots,ScorePick} from './parts';
import {initials,openItem,toneOf,whenText} from './scenario';
import './simulator.css';

type Item=ReviewQueueItem&{kind:'appeals'|'support-requests'};
const DONE='Все попытки разобраны, ответы видны волонтёрам в разборе попытки';

/** One attempt at a time, oldest first: appeals on the AI evaluation, then requests for support. */
export function SimulatorReviewPage(){
 const navigate=useNavigate();const appeals=useSimulatorQueue('appeals'),support=useSimulatorQueue('support-requests');const [done,setDone]=useState<string[]>([]);
 const items:Item[]=[...(appeals.data??[]).filter(openItem).reverse().map(row=>({...row,kind:'appeals' as const})),...(support.data??[]).filter(openItem).reverse().map(row=>({...row,kind:'support-requests' as const}))].filter(row=>!done.includes(row.id));
 const loading=appeals.isPending||support.isPending,current=items[0];
 useEffect(()=>{if(!loading&&done.length&&!items.length)navigate('/fund/scenarios',{state:{flash:DONE}});},[loading,done.length,items.length,navigate]);
 return <div className="trainer">
  <h1 className="sr-only">Разбор попыток</h1>
  <BackLink>Все сценарии</BackLink>
  {loading?<LoadingState label="Загружаем попытки…"/>:appeals.isError||support.isError?<ErrorState error={appeals.error??support.error} retry={()=>{void appeals.refetch();void support.refetch();}}/>
   :current?<Attempt key={current.id} item={current} position={1} total={items.length} last={items.length===1} onDone={()=>setDone(list=>[...list,current.id])}/>
   :!done.length&&<div className="fcard trainer-empty"><h2 className="h3">Все попытки разобраны</h2><p className="p">Новые апелляции и просьбы о поддержке появятся здесь.</p></div>}
 </div>;
}

function Attempt({item,position,total,last,onDone}:{item:Item;position:number;total:number;last:boolean;onDone:()=>void}){
 const detail=useSimulatorAppeal(item.kind==='appeals'?item.id:undefined);const name=item.author_name||'Волонтёр';
 const head=<><p className="eyebrow trainer-pos">Попытка {position} из {total}, сценарий «{item.title}»</p>
  <div className="person"><span className={`ph ph-lg ${toneOf(name)}`} aria-hidden="true">{initials(name)}</span><div><h2 className="h3 trainer-name">{name}</h2><span className="meta">{whenText(item.created_at)}</span></div></div></>;
 if(item.kind==='support-requests')return <div className="sc-layout trainer-review">
  <div className="sc-form"><section className="fcard">{head}<p className="trainer-quote">«{item.text}»</p><p className="meta">Волонтёр просит поддержки. Переписка не передаётся.</p></section></div>
  <aside className="sc-side trainer-side"><Decision item={item} last={last} onDone={onDone}/></aside>
 </div>;
 if(detail.isPending)return <LoadingState label="Открываем попытку…"/>;
 if(detail.isError)return <ErrorState error={detail.error} retry={()=>void detail.refetch()}/>;
 const attempt=detail.data.attempt,result=attempt.evaluation?.result??undefined;const criteria=attempt.scenario.criteria;
 const zeros=result?.criteria.filter(row=>row.score===0&&criteria.find(criterion=>criterion.key===row.criterion_key)?.critical)??[];
 const title=(key:string)=>criteria.find(criterion=>criterion.key===key)?.title??key;
 return <div className="sc-layout trainer-review">
  <div className="sc-form">
   <section className="fcard">{head}<div className="case-turns">{attempt.turns.map(turn=>turn.speaker==='hint'?<p className="try-hint" key={turn.id}>{turn.content}</p>:<Bubble key={turn.id} line={turn.content} mine={turn.speaker==='volunteer'}/>)}</div></section>
   <section className="fcard trainer-eval" aria-labelledby="ai-title">
    <div className="row"><span className="ai-tag">ИИ</span><h2 className="h3" id="ai-title">Оценка</h2></div>
    {result?result.criteria.map(row=>{const critical=!!criteria.find(criterion=>criterion.key===row.criterion_key)?.critical;return <div className="eval-row" key={row.criterion_key}>
     <span className={cx('strong',critical&&row.score===0&&'fill-low')}>{title(row.criterion_key)}{critical&&', критичный'}</span><ScoreDots value={row.score}/>{row.explanation&&<p className="p">{row.explanation}</p>}
    </div>;}):<p className="meta">Оценки ИИ нет.</p>}
   </section>
  </div>
  <aside className="sc-side trainer-side">
   <section className="fcard" aria-labelledby="appeal-title"><h2 className="h3" id="appeal-title">Апелляция</h2><p className="p trainer-ink">«{item.text}»</p></section>
   {zeros.length>0&&<section className="fcard trainer-critical" aria-labelledby="crit-title"><h2 className="h3" id="crit-title">Ошибка в критичном</h2>{zeros.map(row=><p className="p trainer-ink" key={row.criterion_key}>{title(row.criterion_key)}: {row.explanation}{row.suggestion?` ${row.suggestion}`:''}</p>)}</section>}
   <Decision item={item} last={last} onDone={onDone} attempt={detail.data.attempt} result={result} title={title}/>
  </aside>
 </div>;
}

/** The reviewer's fix keeps the AI's evidence; a raised score without one cites the volunteer reply the reviewer picks. */
export function correctedResult(result:SimulationAssessment,scores:Record<string,0|1|2>,evidence:Record<string,string>,turns:{id:string;content:string}[],comment:string):SimulationAssessment{
 return {summary:comment.trim().slice(0,3000)||result.summary,criteria:result.criteria.map(row=>{
  const score=scores[row.criterion_key]??row.score;if(score===row.score)return row;
  const cited=row.evidence?.length?row.evidence:score>0&&evidence[row.criterion_key]?[{turn_id:evidence[row.criterion_key],quote:turns.find(turn=>turn.id===evidence[row.criterion_key])!.content.slice(0,1500)}]:[];
  return {...row,score,evidence:cited,explanation:`Специалист исправил оценку с ${row.score} на ${score} из 2.`};
 })};
}

function Decision({item,last,onDone,attempt,result,title}:{item:Item;last:boolean;onDone:()=>void;attempt?:AppealDetail['attempt'];result?:SimulationAssessment;title?:(key:string)=>string}){
 const command=useSimulatorCommand();const [decision,setDecision]=useState<''|'ok'|'fix'>(''),[comment,setComment]=useState('');
 const [scores,setScores]=useState<Record<string,0|1|2>>({}),[evidence,setEvidence]=useState<Record<string,string>>({});
 const replies=(attempt?.turns??[]).filter(turn=>turn.speaker==='volunteer');const isAppeal=item.kind==='appeals'&&!!result;
 const needsQuote=(key:string)=>{const row=result?.criteria.find(value=>value.criterion_key===key);const score=scores[key];return !!row&&score!==undefined&&score>0&&score!==row.score&&!row.evidence?.length;};
 const quoteOf=(key:string)=>evidence[key]??replies.at(-1)?.id??'';
 function send(){
  const fix=isAppeal&&decision==='fix';const quotes=Object.fromEntries((result?.criteria??[]).map(row=>[row.criterion_key,quoteOf(row.criterion_key)]));
  const response=comment.trim()||(!isAppeal?'Специалист прочитал вашу просьбу.':fix?'Специалист исправил оценку.':'Специалист проверил разбор: оценка верная.');
  void command.mutateAsync({path:`/coord/simulator/${item.kind}/${item.id}/resolve`,body:{expected_version:item.version,response,...(isAppeal?{corrected_result:fix?correctedResult(result!,scores,quotes,replies,comment):null}:{})}}).then(onDone).catch(()=>{});
 }
 const blocked=isAppeal?!decision||(decision==='fix'&&Object.keys(scores).some(key=>needsQuote(key)&&!quoteOf(key))):!comment.trim();
 return <section className="fcard" aria-labelledby="dec-title">
  <h2 className="h3" id="dec-title">{isAppeal?'Решение':'Ответ'}</h2>
  {isAppeal&&<div className="outcome" role="radiogroup" aria-label="Решение">{([['ok','Оценка верная','var(--green)'],['fix','Исправить оценку','var(--yellow)']] as const).map(([value,label,color])=><button key={value} type="button" role="radio" aria-checked={decision===value} className={decision===value?'is-on':''} onClick={()=>setDecision(value)}><i style={{background:color}}/>{label}</button>)}</div>}
  {isAppeal&&decision==='fix'&&<div>{result!.criteria.map(row=><div key={row.criterion_key}>
   <ScorePick title={title!(row.criterion_key)} value={scores[row.criterion_key]??row.score} onChange={score=>setScores(current=>({...current,[row.criterion_key]:score}))}/>
   {needsQuote(row.criterion_key)&&replies.length>0&&<Combobox className="trainer-quote-pick" label="Какой ответ это подтверждает" value={quoteOf(row.criterion_key)} onChange={value=>setEvidence(current=>({...current,[row.criterion_key]:value}))} options={replies.map((turn,index)=>({value:turn.id,label:`Ответ ${index+1}: ${turn.content.slice(0,80)}`}))}/>}
  </div>)}</div>}
  <Field label="Комментарий волонтёру"><Textarea className="trainer-comment" value={comment} maxLength={isAppeal&&decision==='fix'?3000:5000} onChange={event=>setComment(event.target.value)} placeholder="Что получилось и что попробовать иначе"/></Field>
  <div><Button disabled={blocked} loading={command.isPending} onClick={send}>{last?'Отправить':'Отправить и дальше'}</Button></div>
  {command.isError&&<p className="err" role="alert">{command.error.message}</p>}
 </section>;
}
