import {Fragment,useState,type ReactNode} from 'react';
import {useParams,useSearchParams} from 'react-router-dom';
import {Button,Dialog,ErrorState,Field,Icon,Input,LoadingState,Segmented,Textarea,cx} from '../../ui';
import {useSimulatorCommand,useSimulatorTest,useStaffScenario,type ScenarioDraft,type ScenarioStaff,type TestCaseResult} from './api';
import {BackLink,Bubble,ScorePick,Toggle} from './parts';
import {emptyDraft,flowOf,initials,isRunning,saveProblem,testsOf,type Stage} from './scenario';
import './simulator.css';

type Draft=Required<ScenarioDraft>;type Case=Draft['evaluation_cases'][number];type Criterion=Draft['criteria'][number];
type Tab='scenario'|'rubric'|'cases';
const METHODS=['TBRI','PACE','SAMHSA','NSPCC','CPI','Studio III'];
const STEPS=['Черновик','Проверка психолога','Прогон эталонов','Опубликован'];
const STEP_INDEX:Record<Stage,number>={draft:0,review:1,approved:2,tested:3,published:4};
const tabs=[{value:'scenario',label:'Сценарий'},{value:'rubric',label:'Оценка'},{value:'cases',label:'Эталоны'}];
const newKey=()=>crypto.randomUUID();
const comparable=(draft:Draft)=>JSON.stringify({...draft,hints:draft.hints.filter(hint=>hint.trim())});

export function ScenarioEditorPage(){
 const {id}=useParams();const query=useStaffScenario(id);
 return <div className="trainer"><BackLink/>{query.isPending?<LoadingState label="Открываем сценарий…"/>:query.isError?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:<Editor key={`${query.data.id}:${query.data.version}`} item={query.data}/>}</div>;
}

/** Scores of the latest test run of this draft revision against the expected ones. */
function useRun(item:ScenarioStaff,testId:string|undefined){
 const run=useSimulatorTest(testId);const cases=(run.data?.cases??[]) as unknown as TestCaseResult[];
 const scored=cases.filter(row=>row.result?.actual_scores);
 const total=scored.reduce((sum,row)=>sum+Object.keys(row.expected_scores).length,0);
 const matches=scored.reduce((sum,row)=>sum+Object.entries(row.expected_scores).filter(([key,value])=>row.result!.actual_scores![key]===value).length,0);
 return {ready:!!run.data,state:run.data?.state,byKey:new Map(cases.map(row=>[row.key,row])),total,matches,everRun:testsOf(item).length>0};
}

function Editor({item}:{item:ScenarioStaff}){
 const saved=emptyDraft(item.draft);const can=(action:string)=>item.allowed_actions.includes(action);const canEdit=can('update'),isReviewer=can('review');
 const [draft,setDraft]=useState<Draft>(saved),[warnOn,setWarnOn]=useState(!!saved.warning.trim());
 const [returning,setReturning]=useState(false),[returnText,setReturnText]=useState(''),[confirmWithdraw,setConfirmWithdraw]=useState(false);
 const [params,setParams]=useSearchParams();const tab=(['rubric','cases'].includes(params.get('tab')??'')?params.get('tab'):'scenario') as Tab;
 const setTab=(next:Tab)=>setParams(current=>{if(next==='scenario')current.delete('tab');else current.set('tab',next);return current;},{replace:true});
 const command=useSimulatorCommand();
 const payload:Draft={...draft,warning:warnOn?draft.warning:'',hints:draft.hints.filter(hint=>hint.trim())};
 const dirty=comparable(payload)!==comparable(saved);
 const flow=flowOf(item,payload,dirty),problem=saveProblem(payload);
 const test=dirty?undefined:flow.test;const run=useRun(item,test?.id);
 const next=(item.published_version??0)+1;
 const change=(values:Partial<Draft>)=>setDraft(current=>({...current,...values}));
 const send=(action:string,body:Record<string,unknown>={})=>command.mutateAsync({path:`/coord/simulator/scenarios/${item.id}/${action}`,body:{expected_version:item.version,...body}});
 const save=()=>void command.mutateAsync({path:`/coord/simulator/scenarios/${item.id}`,method:'PATCH',body:{...payload,expected_version:item.version}}).catch(()=>{});
 const decide=(decision:'approved'|'changes_requested',reason:string)=>void send('review',{decision,reason}).then(()=>{setReturning(false);setReturnText('');}).catch(()=>{});
 const runTest=()=>void send('test').catch(()=>{});
 const publish=()=>void send('publish',{review_id:flow.review!.id,test_run_id:test!.id}).catch(()=>{});
 const withdraw=()=>void send('withdraw').then(()=>setConfirmWithdraw(false)).catch(()=>{});

 // One primary action per stage; the note says where the scenario is.
 let note:ReactNode='',noteCls='meta',actions:ReactNode=null;
 if(flow.stage==='draft'){
  if(!canEdit)note='Черновик ещё у координатора';
  else{
   if(problem){note=problem;noteCls='fill-low';}
   else if(flow.returned){note=`Вернули: ${flow.returned}`;noteCls='fill-low';}
   else if(flow.missing.length)note=`Не хватает: ${flow.missing.join(', ')}`;
   else note=`Черновик версии ${next}`;
   // Without unsaved edits a complete draft is already with the psychologist, so here the button waits for a change.
   actions=<Button disabled={!dirty||!!problem} loading={command.isPending} onClick={save}>{dirty&&flow.missing.length?'Сохранить черновик':'Отправить психологу'}</Button>;
  }
 }else if(flow.stage==='review'){
  if(isReviewer){note=`Версия ${next} ждёт вашей проверки`;if(!returning)actions=<><Button loading={command.isPending} onClick={()=>decide('approved','Одобрено без замечаний')}>Одобрить</Button><Button variant="secondary" disabled={command.isPending} onClick={()=>setReturning(true)}>Вернуть с комментарием</Button></>;}
  else{note='У психолога';noteCls='dot dot-orange';}
 }else if(flow.stage==='approved'){
  if(isRunning(flow.test)){note=<><span className="spinner" aria-hidden="true"/>Идёт прогон эталонов</>;noteCls='meta row';}
  else if(can('test')){note='Одобрено психологом';actions=<Button loading={command.isPending} onClick={runTest}>Запустить прогон эталонов</Button>;}
  else note='Одобрено, координатор запустит прогон';
 }else if(flow.stage==='tested'){
  if(!run.ready)note='Открываем результат прогона…';
  else if(!run.total){note='ИИ не ответил, прогон не прошёл';noteCls='dot dot-orange fill-low';if(can('test'))actions=<Button loading={command.isPending} onClick={runTest}>Запустить прогон эталонов</Button>;}
  else{
   const passed=run.state==='succeeded';note=`Совпало ${run.matches} из ${run.total}`;noteCls=passed?'dot dot-green':'dot dot-orange fill-low';
   if(!passed)actions=<Button variant="secondary" onClick={()=>setTab('cases')}>Открыть эталоны</Button>;
   else if(can('publish'))actions=<Button loading={command.isPending} onClick={publish}>{item.archived_at?'Опубликовать снова':`Опубликовать версию ${next}`}</Button>;
  }
 }else note=`Версия ${item.published_version} у волонтёров. Любая правка создаст черновик`;
 const stepIndex=STEP_INDEX[flow.stage];

 return <>
  <div className="page-head trainer-head"><h1 className="h1">{draft.title.trim()||'Без названия'}</h1></div>
  <div className="flow-bar">
   <div className="stepper" role="group" aria-label="Путь сценария">{STEPS.map((label,index)=>{const done=index<stepIndex||flow.stage==='published',now=!done&&index===Math.min(stepIndex,3);return <Fragment key={label}>{index>0&&<span className="sep" aria-hidden="true"/>}<span className={cx('st',done&&'done',now&&'now')} aria-current={now?'step':undefined}><i>{done?<Icon name="check"/>:index+1}</i>{label}</span></Fragment>;})}</div>
   <div className="flow-act"><span className={noteCls}>{note}</span>{actions}{item.publication_id&&can('withdraw')&&<Button variant="ghost" disabled={command.isPending} onClick={()=>setConfirmWithdraw(true)}>Снять с публикации</Button>}</div>
  </div>
  {command.isError&&<p className="err trainer-error" role="alert">{command.error.message}</p>}
  {returning&&flow.stage==='review'&&<div className="fcard trainer-return">
   <Field label="Что поправить"><Textarea className="trainer-return-text" value={returnText} maxLength={5000} onChange={event=>setReturnText(event.target.value)} placeholder="Например, первая фраза слишком резкая для девятилетнего"/></Field>
   <div className="row wrap"><Button variant="secondary" disabled={!returnText.trim()} loading={command.isPending} onClick={()=>decide('changes_requested',returnText.trim())}>Вернуть координатору</Button><Button variant="ghost" onClick={()=>setReturning(false)}>Отмена</Button></div>
  </div>}
  <div className="toolbar"><Segmented label="Раздел сценария" value={tab} onChange={value=>setTab(value as Tab)} options={tabs}/></div>
  {tab==='scenario'&&<ScenarioTab draft={draft} payload={payload} warnOn={warnOn} setWarnOn={setWarnOn} change={change} canEdit={canEdit}/>}
  {tab==='rubric'&&<RubricTab draft={draft} change={change} canEdit={canEdit}/>}
  {tab==='cases'&&<CasesTab draft={draft} change={change} canEdit={canEdit} run={run} checked={!!test&&!isRunning(test)} running={isRunning(test)}/>}
  <Dialog open={confirmWithdraw} onClose={()=>setConfirmWithdraw(false)} title="Снять с публикации?" footer={<><Button variant="ghost" onClick={()=>setConfirmWithdraw(false)}>Отмена</Button><Button variant="danger" loading={command.isPending} onClick={withdraw}>Снять</Button></>}><p className="p">Волонтёры перестанут видеть сценарий. Начатые попытки сохранятся.</p></Dialog>
 </>;
}

function ScenarioTab({draft,payload,warnOn,setWarnOn,change,canEdit}:{draft:Draft;payload:Draft;warnOn:boolean;setWarnOn:(on:boolean)=>void;change:(values:Partial<Draft>)=>void;canEdit:boolean}){
 const hints=draft.hints;
 return <div className="sc-layout">
  <fieldset className="sc-form trainer-fields" disabled={!canEdit}>
   <legend className="sr-only">Сценарий</legend>
   <section className="fcard" aria-labelledby="f-who">
    <h2 className="h3" id="f-who">Кто и где</h2>
    <Field label="Название"><Input value={draft.title} maxLength={200} onChange={event=>change({title:event.target.value})}/></Field>
    <div className="form-grid"><Field label="Имя ребёнка"><Input value={draft.character_name} maxLength={100} onChange={event=>change({character_name:event.target.value})}/></Field><Field label="Возраст и история"><Input value={draft.character_profile} maxLength={5000} onChange={event=>change({character_profile:event.target.value})}/></Field></div>
    <Field label="Ситуация"><Textarea className="trainer-short" value={draft.situation} maxLength={5000} onChange={event=>change({situation:event.target.value})}/></Field>
    <Field label="Первая фраза ребёнка"><Textarea className="trainer-short" value={draft.first_turn} maxLength={5000} placeholder="[действие в скобках] Сама фраза" onChange={event=>change({first_turn:event.target.value})}/></Field>
   </section>
   <section className="fcard" aria-labelledby="f-warn">
    <span className="toggle-line"><Toggle on={warnOn} label="Предупреждать перед началом" onChange={setWarnOn}/><span className="h3" id="f-warn">Предупреждать перед началом</span></span>
    {warnOn&&<><label className="sr-only" htmlFor="f-warn-text">Текст предупреждения</label><Textarea id="f-warn-text" className="trainer-shorter" value={draft.warning} maxLength={2000} placeholder="Тяжёлая тема. Можно остановиться и попросить поддержки." onChange={event=>change({warning:event.target.value})}/></>}
   </section>
   <section className="fcard" aria-labelledby="f-hints">
    <h2 className="h3" id="f-hints">Подсказки волонтёру</h2>
    <div className="list-edit">{hints.map((hint,index)=><div className="row" key={index}>
     <span className="tree-n" aria-hidden="true">{index+1}</span><label className="sr-only" htmlFor={`hint-${index}`}>Подсказка {index+1}</label>
     <Input id={`hint-${index}`} value={hint} maxLength={1000} onChange={event=>change({hints:hints.map((row,i)=>i===index?event.target.value:row)})}/>
     <button type="button" className="iconbtn" aria-label={`Удалить подсказку ${index+1}`} onClick={()=>change({hints:hints.filter((_,i)=>i!==index)})}><Icon name="trash"/></button>
    </div>)}</div>
    {canEdit&&hints.length<30&&<div><Button variant="ghost" size="sm" className="trainer-add" onClick={()=>change({hints:[...hints,'']})}><Icon name="plus"/>Добавить подсказку</Button></div>}
   </section>
  </fieldset>
  <TryPanel draft={payload}/>
 </div>;
}

/** Drafts are not played by the AI (sessions start only from a published version), so the preview shows the start and the hints. */
function TryPanel({draft}:{draft:Draft}){
 const [shown,setShown]=useState(0);const hints=draft.hints;
 return <aside className="sc-side try" aria-labelledby="try-title">
  <div className="try-head"><span className="ph ph-sm ph-o" aria-hidden="true">{initials(draft.character_name).slice(0,1)}</span><div className="try-who"><h2 className="h3" id="try-title">Попробовать самому</h2>{draft.character_profile.trim()&&<span className="meta">{draft.character_profile}</span>}</div></div>
  {draft.situation.trim()&&<p className="try-sit">{draft.situation}</p>}
  {draft.warning.trim()&&<p className="try-sit is-warn">{draft.warning}</p>}
  <div className="try-log" role="log" aria-label="Диалог с ребёнком">
   {draft.first_turn.trim()?<Bubble line={draft.first_turn}/>:<p className="meta try-empty">Здесь появится первая фраза ребёнка</p>}
   {hints.slice(0,shown).map((hint,index)=><p className="try-hint" key={index}>{hint}</p>)}
  </div>
  <div className="try-compose"><label className="sr-only" htmlFor="try-input">Ваш ответ</label><textarea id="try-input" className="textarea" rows={1} disabled placeholder="Ребёнок ответит после публикации"/><button type="button" className="ch-send" aria-label="Отправить" disabled><Icon name="send"/></button></div>
  <div className="try-tools"><Button variant="ghost" size="sm" disabled={shown>=hints.length} onClick={()=>setShown(count=>count+1)}>Подсказка</Button><Button variant="secondary" size="sm" disabled>Завершить</Button></div>
 </aside>;
}

function RubricTab({draft,change,canEdit}:{draft:Draft;change:(values:Partial<Draft>)=>void;canEdit:boolean}){
 const criteria=draft.criteria;const methods=[...METHODS,...draft.methods.filter(method=>!METHODS.includes(method))];
 const update=(index:number,values:Partial<Criterion>)=>change({criteria:criteria.map((row,i)=>i===index?{...row,...values}:row)});
 const remove=(criterion:Criterion)=>change({criteria:criteria.filter(row=>row.key!==criterion.key),evaluation_cases:draft.evaluation_cases.map(example=>({...example,expected_scores:Object.fromEntries(Object.entries(example.expected_scores).filter(([key])=>key!==criterion.key))}))});
 return <div className="sc-layout">
  <section className="sc-form fcard crit-card" aria-labelledby="f-crit">
   <h2 className="h3" id="f-crit">Что проверяем</h2>
   <fieldset className="trainer-fields" disabled={!canEdit}><legend className="sr-only">Критерии</legend>
    {criteria.map((criterion,index)=><div className="crit" key={criterion.key}>
     <div className="crit-main">
      <label className="sr-only" htmlFor={`crit-t-${index}`}>Критерий {index+1}</label><Input id={`crit-t-${index}`} value={criterion.title} maxLength={300} onChange={event=>update(index,{title:event.target.value})}/>
      <label className="sr-only" htmlFor={`crit-g-${index}`}>Как звучит хорошо</label><Textarea id={`crit-g-${index}`} value={criterion.guidance} maxLength={5000} placeholder="Как звучит хорошо" onChange={event=>update(index,{guidance:event.target.value})}/>
     </div>
     <div className="crit-side">
      <span className="crit-flag"><Toggle on={criterion.critical} label={`Критичный: ${criterion.title}`} onChange={critical=>update(index,{critical})}/>Критичный</span>
      <button type="button" className="iconbtn" aria-label={`Удалить критерий «${criterion.title}»`} onClick={()=>remove(criterion)}><Icon name="trash"/></button>
     </div>
    </div>)}
    {!criteria.length&&<p className="meta">Критериев пока нет.</p>}
    {canEdit&&criteria.length<20&&<div><Button variant="ghost" size="sm" className="trainer-add" onClick={()=>change({criteria:[...criteria,{key:newKey(),title:'Новый критерий',guidance:'',critical:false}]})}><Icon name="plus"/>Добавить критерий</Button></div>}
   </fieldset>
  </section>
  <aside className="sc-side fcard" aria-labelledby="f-methods">
   <h2 className="h3" id="f-methods">На чём основано</h2>
   <div className="pick">{methods.map(method=>{const on=draft.methods.includes(method);return <button key={method} type="button" aria-pressed={on} className={on?'is-on':''} disabled={!canEdit} onClick={()=>change({methods:on?draft.methods.filter(row=>row!==method):[...draft.methods,method]})}>{method}</button>;})}</div>
   <p className="p">ИИ ставит по каждому критерию 0, 1 или 2 и приводит цитату из ответа волонтёра.</p>
  </aside>
 </div>;
}

function CasesTab({draft,change,canEdit,run,checked,running}:{draft:Draft;change:(values:Partial<Draft>)=>void;canEdit:boolean;run:ReturnType<typeof useRun>;checked:boolean;running:boolean}){
 const [fresh,setFresh]=useState<string>();const cases=draft.evaluation_cases;
 const scored=checked&&run.ready&&run.total>0,allMatch=scored&&run.matches===run.total;
 const status=running?{text:'Идёт прогон эталонов',cls:'meta'}:!checked?{text:run.everRun?'Эталоны изменились, прогон ещё не запускали':'Прогон ещё не запускали',cls:'meta'}:!run.ready?{text:'Открываем результат прогона…',cls:'meta'}:!run.total?{text:'ИИ не ответил, прогон не прошёл',cls:'dot dot-orange fill-low'}
  :{text:`Последний прогон: совпало ${run.matches} из ${run.total}${allMatch?'':', поправьте эталон или критерий'}`,cls:allMatch?'dot dot-green':'dot dot-orange fill-low'};
 function add(){const key=newKey();setFresh(key);change({evaluation_cases:[...cases,{key,title:'Новый эталон',turns:[{speaker:'character',content:draft.first_turn},{speaker:'volunteer',content:''}],expected_scores:{}}]});}
 return <>
  <div className="row wrap trainer-cases-head"><span className={status.cls}>{status.text}</span>{canEdit&&cases.length<20&&<Button variant="secondary" size="sm" onClick={add}><Icon name="plus"/>Добавить эталон</Button>}</div>
  {!cases.length&&<div className="fcard"><p className="p">Эталонов пока нет. Нужно хотя бы два: сильный и слабый ответ.</p></div>}
  {cases.map(example=><CaseCard key={example.key} example={example} criteria={draft.criteria} canEdit={canEdit} editing={example.key===fresh} result={checked?run.byKey.get(example.key):undefined}
   onChange={value=>change({evaluation_cases:cases.map(row=>row.key===example.key?value:row)})} onRemove={()=>change({evaluation_cases:cases.filter(row=>row.key!==example.key)})}/>)}
 </>;
}

function CaseCard({example,criteria,canEdit,editing:initial,result,onChange,onRemove}:{example:Case;criteria:Criterion[];canEdit:boolean;editing:boolean;result?:TestCaseResult;onChange:(value:Case)=>void;onRemove:()=>void}){
 const [editing,setEditing]=useState(initial);const actual=result?.result?.actual_scores;
 const status=!result?{text:'ещё не проверяли',cls:'meta'}:result.state==='passed'?{text:'совпало с ИИ',cls:'dot dot-green'}:actual?{text:'расхождение',cls:'dot dot-orange fill-low'}:result.state==='pending'?{text:'проверяется',cls:'meta'}:{text:'ИИ не ответил',cls:'dot dot-orange fill-low'};
 const turns=example.turns;const setTurn=(index:number,values:Partial<Case['turns'][number]>)=>onChange({...example,turns:turns.map((turn,i)=>i===index?{...turn,...values}:turn)});
 return <section className="case" aria-label={example.title}>
  <div className="case-head"><h2 className="h3">{example.title}</h2><span className="row wrap case-head-end"><span className={status.cls}>{status.text}</span>{canEdit&&<Button variant="ghost" size="sm" onClick={()=>setEditing(!editing)}>{editing?'Готово':'Изменить'}</Button>}</span></div>
  <div className="sc-layout">
   <div className="sc-form">{editing?<div className="case-edit">
    <Field label="Название эталона"><Input value={example.title} maxLength={200} onChange={event=>onChange({...example,title:event.target.value})}/></Field>
    {turns.map((turn,index)=>{const id=`case-${example.key}-turn-${index}`;return <div className="case-edit-turn" key={index}>
     <div className="row wrap case-edit-who"><Segmented label={`Чья реплика ${index+1}`} value={turn.speaker} options={[{value:'character',label:'Ребёнок'},{value:'volunteer',label:'Волонтёр'}]} onChange={speaker=>setTurn(index,{speaker:speaker as 'character'|'volunteer'})}/><button type="button" className="iconbtn" aria-label={`Удалить реплику ${index+1}`} disabled={turns.length<=2} onClick={()=>onChange({...example,turns:turns.filter((_,i)=>i!==index)})}><Icon name="trash"/></button></div>
     <label className="sr-only" htmlFor={id}>Реплика {index+1}</label><Textarea id={id} className="trainer-shorter" value={turn.content} maxLength={4000} onChange={event=>setTurn(index,{content:event.target.value})}/>
    </div>;})}
    <div className="row wrap">{turns.length<30&&<Button variant="ghost" size="sm" className="trainer-add" onClick={()=>onChange({...example,turns:[...turns,{speaker:turns.at(-1)?.speaker==='volunteer'?'character':'volunteer',content:''}]})}><Icon name="plus"/>Добавить реплику</Button>}<Button variant="ghost" size="sm" onClick={onRemove}>Удалить эталон</Button></div>
   </div>:<div className="case-turns">{turns.map((turn,index)=><Bubble key={index} line={turn.content} mine={turn.speaker==='volunteer'}/>)}</div>}</div>
   <div className="sc-side">
    <span className="label case-label">Ожидаемая оценка</span>
    {criteria.map(criterion=>{const expected=example.expected_scores[criterion.key],ai=actual?.[criterion.key],miss=ai!==undefined&&ai!==expected;return <ScorePick key={criterion.key} title={criterion.title} value={expected} disabled={!canEdit} miss={miss} note={miss&&<span className="fill-low">ИИ поставил {ai}</span>}
     onChange={score=>onChange({...example,expected_scores:{...example.expected_scores,[criterion.key]:score}})}/>;})}
    {!criteria.length&&<p className="meta">Сначала добавьте критерии на вкладке «Оценка».</p>}
   </div>
  </div>
 </section>;
}
