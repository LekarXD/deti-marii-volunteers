import {useRef,useState} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {Button,ErrorState,Field,Icon,Input,LoadingState,cx,type IconName} from '../../ui';
import {useScenarioExamples,useScenarios,useSimulatorCommand,type ScenarioStaff} from './api';
import {BackLink} from './parts';
import {stripDir} from './scenario';
import './simulator.css';

type Way='case'|'ready'|'blank';
const ways:{id:Way;title:string;text:string;art:string;icon:IconName}[]=[
 {id:'case',title:'Из случая с занятия',text:'Опишите, что произошло. Рассказ станет ситуацией черновика.',art:'art-v',icon:'sparkle'},
 {id:'ready',title:'Из готовых',text:'Шесть сценариев фонда. Перед публикацией их проверит психолог.',art:'art-y',icon:'book'},
 {id:'blank',title:'С чистого листа',text:'Пустой черновик, всё заполните сами.',art:'art-b',icon:'pen'},
];
/** The first sentence of the story, short enough for a card title. */
export function caseTitle(text:string){const first=text.trim().split(/(?<=[.!?…])\s/)[0]?.trim()??'';return first.length>80?`${first.slice(0,79).trimEnd()}…`:first;}

export function ScenarioNewPage(){
 const [way,setWay]=useState<Way>('case');const refs=useRef<(HTMLButtonElement|null)[]>([]);
 function move(index:number,key:string){const step=key==='ArrowRight'||key==='ArrowDown'?1:key==='ArrowLeft'||key==='ArrowUp'?-1:0;if(!step)return;const next=(index+step+ways.length)%ways.length;setWay(ways[next].id);refs.current[next]?.focus();}
 return <div className="trainer">
  <BackLink/>
  <div className="page-head"><h1 className="h1">Новый сценарий</h1></div>
  <div className="grid-3" role="radiogroup" aria-label="С чего начать">{ways.map((item,index)=><button key={item.id} ref={node=>{refs.current[index]=node;}} type="button" role="radio" aria-checked={way===item.id} tabIndex={way===item.id?0:-1} className={cx('choice-card',way===item.id&&'is-on')} onClick={()=>setWay(item.id)} onKeyDown={event=>{if(event.key.startsWith('Arrow')){event.preventDefault();move(index,event.key);}}}>
   <span className={`art ${item.art}`} aria-hidden="true"><Icon name={item.icon}/></span><span className="h3">{item.title}</span><span className="p">{item.text}</span>
  </button>)}</div>
  {way==='case'&&<FromCase/>}{way==='ready'&&<FromExamples/>}{way==='blank'&&<FromBlank/>}
 </div>;
}

function useCreate(){const command=useSimulatorCommand(),navigate=useNavigate();return {command,create:(path:string,body:unknown)=>void command.mutateAsync({path,body}).then(result=>navigate(`/fund/scenarios/${(result as ScenarioStaff).id}`)).catch(()=>{})};}

/** There is no AI endpoint that drafts a scenario from a story yet: the story becomes the situation, the rest is filled in the editor. */
function FromCase(){
 const [text,setText]=useState(''),[built,setBuilt]=useState(false);const {command,create}=useCreate();const title=caseTitle(text);
 return <section className="section" aria-labelledby="case-title"><div className="sc-layout">
  <div className="sc-form fcard">
   <h2 className="h3" id="case-title">Что произошло на занятии</h2>
   <label className="sr-only" htmlFor="case-text">Что произошло на занятии</label>
   <textarea id="case-text" className="textarea trainer-case-text" value={text} maxLength={5000} onChange={event=>{setText(event.target.value);setBuilt(false);}} placeholder="Кто, где, что сказал ребёнок и как отреагировал волонтёр"/>
   <div className="row wrap">{built?<Button variant="ghost" onClick={()=>setBuilt(false)}>Собрать заново</Button>:<Button disabled={!text.trim()} onClick={()=>setBuilt(true)}>Собрать черновик</Button>}</div>
  </div>
  {built&&<aside className="sc-side fcard trainer-built" aria-labelledby="draft-title">
   <h2 className="h3" id="draft-title">Черновик сценария</h2>
   <dl className="dl"><dt>Название</dt><dd>{title}</dd><dt>Ситуация</dt><dd className="pre">{text.trim()}</dd></dl>
   <p className="p">Ребёнка, первую фразу, критерии и подсказки заполните в редакторе. Настоящие имена замените на вымышленные.</p>
   <div className="row wrap"><Button loading={command.isPending} onClick={()=>create('/coord/simulator/scenarios',{title,situation:text.trim()})}>Открыть в редакторе</Button></div>
   {command.isError&&<p className="err" role="alert">{command.error.message}</p>}
  </aside>}
 </div></section>;
}

function FromExamples(){
 const examples=useScenarioExamples(),list=useScenarios(true);const {command,create}=useCreate();const [taking,setTaking]=useState<number>();
 const existing=new Map(((list.data?.pages.flatMap(page=>page.items)??[]) as ScenarioStaff[]).map(item=>[item.draft.title,item.id]));
 return <section className="section" aria-labelledby="ready-title"><div className="sec-head"><h2 className="h2" id="ready-title">Сценарии фонда</h2></div>
  {examples.isPending?<LoadingState label="Загружаем сценарии фонда…"/>:examples.isError?<ErrorState error={examples.error} retry={()=>void examples.refetch()}/>:<div className="card src-list">
   {examples.data.map((example,index)=>{const id=existing.get(example.title);return <div className="src-row" key={example.title}>
    <span className="src-text"><span className="h3">{example.title}</span><span className="p">«{stripDir(example.first_turn)}»</span></span>
    {id?<Link className="btn btn-ghost btn-sm" to={`/fund/scenarios/${id}`}>Уже есть, открыть</Link>:<Button variant="secondary" size="sm" aria-label={`Взять «${example.title}»`} loading={command.isPending&&taking===index} disabled={command.isPending&&taking!==index} onClick={()=>{setTaking(index);create('/coord/simulator/scenarios/from-example',{example_index:index});}}>Взять</Button>}
   </div>;})}
  </div>}
  {command.isError&&<p className="err" role="alert">{command.error.message}</p>}
 </section>;
}

function FromBlank(){
 const [title,setTitle]=useState(''),[name,setName]=useState('');const {command,create}=useCreate();
 return <section className="section" aria-labelledby="blank-title"><div className="fcard trainer-narrow">
  <h2 className="h3" id="blank-title">С чего начнём</h2>
  <Field label="Название"><Input value={title} maxLength={200} onChange={event=>setTitle(event.target.value)} placeholder="Например, просит обнять"/></Field>
  <Field label="Имя ребёнка"><Input value={name} maxLength={100} onChange={event=>setName(event.target.value)} placeholder="Вымышленное"/></Field>
  <div><Button disabled={!title.trim()} loading={command.isPending} onClick={()=>create('/coord/simulator/scenarios',{title:title.trim(),character_name:name.trim()})}>Создать черновик</Button></div>
  {command.isError&&<p className="err" role="alert">{command.error.message}</p>}
 </div></section>;
}
