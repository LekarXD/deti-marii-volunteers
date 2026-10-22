import {Link,useLocation} from 'react-router-dom';
import {Button,ErrorState,Icon,LoadingState,SectionTabs} from '../../ui';
import {useSession} from '../../app/layouts';
import {learningTabs} from '../../app/sectionTabs';
import {useScenarios,useSimulatorQueue,type ScenarioStaff} from './api';
import {cardStatus,openItem,passedText,queueSummary,stripDir} from './scenario';
import './simulator.css';

export function ScenariosPage(){
 const {session}=useSession();const permissions=session?.permissions??[];const canManage=permissions.includes('simulator.manage'),canReview=permissions.includes('simulator.review');
 const list=useScenarios(true),appeals=useSimulatorQueue('appeals',canReview),support=useSimulatorQueue('support-requests',canReview);
 const flash=(useLocation().state as {flash?:string}|null)?.flash;
 const rows=((list.data?.pages.flatMap(page=>page.items)??[]) as ScenarioStaff[]).slice().sort((a,b)=>a.draft.title.localeCompare(b.draft.title,'ru'));
 const queue=queueSummary(appeals.data?.filter(openItem)??[],support.data?.filter(openItem)??[]);
 return <div className="trainer">
  <SectionTabs label="Обучение" tabs={learningTabs} actions={canManage&&<Link className="btn btn-secondary" to="/fund/scenarios/new"><Icon name="plus"/>Новый сценарий</Link>}/>
  <p className="lead trainer-lead">Волонтёр переписывается с ребёнком, которого играет ИИ, и получает разбор по критериям до первого выхода.</p>
  {flash&&<div className="done-note" role="status"><Icon name="check"/>{flash}</div>}
  {queue.total>0&&<section className="card-hero compact" aria-labelledby="tries-title"><div className="hero-grid"><div className="hero-copy"><h2 className="hero-title" id="tries-title">{queue.title}</h2><p className="hero-line">{queue.line}</p><div className="actions"><Link className="btn btn-primary btn-lg" to="/fund/simulator/review">Начать разбор</Link></div></div><span className="hero-art" aria-hidden="true"><Icon name="message"/></span></div></section>}
  <section className="section" aria-labelledby="sc-title">
   <div className="sec-head"><h2 className="h2" id="sc-title">Сценарии</h2></div>
   {list.isPending?<LoadingState label="Загружаем сценарии…"/>:list.isError?<ErrorState error={list.error} retry={()=>void list.refetch()}/>:<div className="grid-3">
    {rows.map(item=>{const status=cardStatus(item),quote=stripDir(item.draft.first_turn);return <Link key={item.id} className="sc-card" to={`/fund/scenarios/${item.id}`}>
     <span className="eyebrow">{item.draft.title}</span>
     {quote?<span className="sc-quote">«{quote}»</span>:<span className="sc-quote is-empty">Первой фразы пока нет</span>}
     <span className="sc-foot"><span className="meta">{passedText(item.finished_count)}</span>{status&&<span className={status.dot}>{status.label}</span>}</span>
    </Link>;})}
    {canManage&&<Link className="sc-card add" to="/fund/scenarios/new"><Icon name="plus" className="ic-lg"/>Новый сценарий</Link>}
    {!rows.length&&!canManage&&<p className="meta">Сценариев пока нет.</p>}
   </div>}
   {list.hasNextPage&&<div className="actions"><Button variant="secondary" loading={list.isFetchingNextPage} onClick={()=>void list.fetchNextPage()}>Ещё сценарии</Button></div>}
  </section>
 </div>;
}
