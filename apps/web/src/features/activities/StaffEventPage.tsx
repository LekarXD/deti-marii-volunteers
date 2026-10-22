import {useRef,useState} from 'react';
import {Link,useParams,useSearchParams} from 'react-router-dom';
import {Button,Card,Dialog,ErrorState,Icon,LoadingState,type IconName} from '../../ui';
import {DobroOneOffPreparation,DobroTeamPanel,EventOpportunityPicker} from '../dobro';
import {useDobroQuery,type DobroSeries} from '../dobro/api';
import {useActivityCommand,useAwaitingResponses,useEventReserve,useEventTeam,useOpportunity} from './api';
import {useCalendarGroups,useCalendarOccurrence,useCalendarSeries,type CalendarOccurrence} from './calendarApi';
import {labelDate,localParts} from './calendarDates';
import {CalendarEditor} from './CalendarEditor';
import {AssignmentCard} from './Participation';
import {awaitingCoordinator,useAssignmentSuggestions,type AssignmentParticipation,type OpportunityResponse} from './participationApi';
import {Avatar,eventWhen,firstName,plural,useCoordAccess} from './coordEvents';
import './coordEvents.css';
type Need=CalendarOccurrence['staffing_needs'][number];
const art:Record<string,IconName>={activity:'palette',workshop:'scissors',event:'star',trip:'car'};
const reasons={accept:'Координатор принял вашу запись.',decline:'Спасибо, что откликнулись! На эту дату не получится, позовём на другие.',reserve:'Мест на эту дату нет. Вы в резерве: позовём, если кто-то отменит.'};
const failure=(error:unknown)=>error instanceof Error?error.message:'Не удалось выполнить действие.';

/** Coordinator event page (Event.dc.html): the team by role, responses waiting for an answer and invitations. */
export function StaffEventPage(){
 const {id}=useParams(),[params,setParams]=useSearchParams(),access=useCoordAccess();
 const detail=useCalendarOccurrence(id),item=detail.data,team=useEventTeam(id,access.assign),reserve=useEventReserve(id,access.assign),groups=useCalendarGroups();
 const link=useDobroQuery<DobroSeries>('event-opportunity',`/fund/event-series/${item?.series_id}/dobro-opportunity`,access.opportunities&&!!item),opportunityId=link.data?.opportunity_id??undefined;
 const opportunity=useOpportunity(opportunityId,true),responses=useAwaitingResponses(opportunityId,access.assign);
 const command=useActivityCommand(),[panel,setPanel]=useState(''),[flash,setFlash]=useState(''),[error,setError]=useState(''),[person,setPerson]=useState<string|null>(null),[allResponses,setAllResponses]=useState(false),panelRef=useRef<HTMLElement>(null);
 const returnContext=params.get('return');
 const back=returnContext!==null?<Link className="cev-back" to={`/fund/schedule${returnContext?`?${returnContext}`:''}`}><Icon name="chevron-left"/>Расписание</Link>:<Link className="cev-back" to="/fund/opportunities"><Icon name="chevron-left"/>Мероприятия</Link>;
 if(detail.isPending)return <div className="cev">{back}<LoadingState label="Загружаем мероприятие…"/></div>;
 if(detail.isError||!item)return <div className="cev">{back}<ErrorState error={detail.error} retry={()=>void detail.refetch()}/></div>;
 const now=Date.now(),open=item.status==='scheduled'&&Date.parse(item.ends_at)>now,signUpOpen=item.status==='scheduled'&&Date.parse(item.starts_at)>now;
 const rows=team.data??[],pending=rows.filter(awaitingCoordinator),inTeam=rows.filter(row=>row.status==='confirmed'||row.status==='invited'&&!awaitingCoordinator(row));
 const needs=item.staffing_needs.filter(need=>need.required>0);
 const people=(need:Need)=>inTeam.filter(row=>row.staffing_need_id===need.id),taken=(need:Need)=>access.assign?people(need).length:need.confirmed+need.invited,free=(need:Need)=>Math.max(0,need.required-taken(need));
 const total=needs.reduce((sum,need)=>sum+need.required,0),got=needs.reduce((sum,need)=>sum+Math.min(taken(need),need.required),0);
 const eyebrow=item.status==='cancelled'?'Отменено':!open?'Прошло':!needs.length?'Волонтёры не нужны':needs.some(need=>need.confirmed<need.required)?'Идёт набор, видно волонтёрам в ленте':'Команда собрана';
 const canInvite=access.assign&&open&&needs.length>0,inviteNeed=needs.find(need=>need.id===panel);
 const date=labelDate(localParts(item.starts_at,item.timezone).date);
 const showPanel=(needId:string)=>{setPanel(needId);setFlash('');setError('');setTimeout(()=>panelRef.current?.scrollIntoView?.({block:'nearest',behavior:'smooth'}),0);};
 const post=(path:string,body:unknown)=>command.mutateAsync({path,body,key:crypto.randomUUID()});
 const run=(work:()=>Promise<string>)=>{setError('');void work().then(setFlash).catch(reason=>{setFlash('');setError(failure(reason));});};
 const roles=opportunity.data?.role_ids??[];
 const needFor=()=>needs.find(need=>roles.includes(need.role_id)&&free(need)>0)??needs.find(need=>free(need)>0)??needs.find(need=>roles.includes(need.role_id))??needs[0];
 const own=(open?pending:[]).map(row=>{const need=needs.find(n=>n.id===row.staffing_need_id),name=firstName(row.display_name);return {key:row.id,userId:row.user_id,name:row.display_name,meta:row.origin==='reserve'?`${row.role_title}, из резерва`:row.role_title,text:String(row.history.find(entry=>entry.command==='sign_up')?.reason??''),place:row.origin==='reserve'||!need||free(need)>0,
  accept:()=>run(async()=>{const result=await post(`/coord/assignments/${row.id}/approve`,{expected_version:row.version,reason:reasons.accept}) as AssignmentParticipation;return result.status==='confirmed'?`${name} в составе. Подтверждение ушло в сообщения`:`${name} в составе, ждём подтверждения`;}),
  reserve:()=>run(async()=>{await post(`/coord/staffing-needs/${row.staffing_need_id}/reserve`,{expected_version:need?.version,user_id:row.user_id,expected_assignment_version:row.version});return `${name} в резерве`;}),
  decline:()=>run(async()=>{await post(`/coord/assignments/${row.id}/cancel`,{expected_version:row.version,reason:reasons.decline});return '';})};});
 const answers=(signUpOpen&&needs.length?responses.data??[]:[]).map((response:OpportunityResponse)=>{const need=needFor(),name=firstName(response.display_name),existing=rows.find(row=>row.user_id===response.user_id),active=existing&&['invited','confirmed'].includes(existing.status);return {key:response.id,userId:response.user_id,name:response.display_name,meta:need.role_title,text:String(response.history[0]?.reason??''),place:free(need)>0||!!active,
  accept:()=>run(async()=>{if(!active)await post(`/coord/staffing-needs/${need.id}/invitations`,{user_id:response.user_id,expected_version:need.version,...(existing?{expected_assignment_version:existing.version}:{})});await post(`/coord/responses/${response.id}/approve`,{expected_version:response.version,reason:`Приглашаем на «${item.title}», ${date}. Подтвердите участие в приглашении.`});return `${name}: приглашение отправлено`;}),
  reserve:()=>run(async()=>{await post(`/coord/staffing-needs/${need.id}/reserve`,{expected_version:need.version,user_id:response.user_id});await post(`/coord/responses/${response.id}/approve`,{expected_version:response.version,reason:reasons.reserve});return `${name} в резерве`;}),
  decline:()=>run(async()=>{await post(`/coord/responses/${response.id}/decline`,{expected_version:response.version,reason:'Спасибо за отклик! Сейчас не получится, позовём, когда появится подходящее место.'});return '';})};});
 const waiting=[...own,...answers],waitingReserve=(reserve.data??[]).filter(row=>row.state==='waiting');
 const prep=[...new Set(needs.flatMap(need=>need.preparation_requirements.map(requirement=>requirement.title)))];
 const group=groups.data?.pages.flatMap(page=>page.items).find(row=>row.id===item.group_id)?.title;
 const facts=[['Кому помогаем',item.audience||group],['Группа',item.audience?group:''],['Что делать',opportunity.data?.task],['Подготовка',prep.join(', ')]].filter(([,value])=>value) as [string,string][];
 const chosen=rows.find(row=>row.id===person);
 return <div className="cev">{back}
  <section className="card-hero cev-hero" aria-labelledby="cev-title"><div className="hero-grid"><div className="hero-copy"><p className="eyebrow">{eyebrow}</p><h1 className="hero-title" id="cev-title">{item.title}</h1><p className="cev-hero-line">{eventWhen(item,true)}</p><div className="actions">{canInvite&&<Button size="lg" onClick={()=>showPanel((needs.find(need=>free(need)>0)??needs[0]).id)}>Пригласить волонтёров</Button>}{item.allowed_actions.includes('edit')&&<Button variant="secondary" size="lg" onClick={()=>setParams(p=>{p.set('edit','1');return p})}>Изменить</Button>}</div></div><span className="hero-art" aria-hidden="true"><Icon name={art[item.kind]??'calendar'}/></span></div></section>
  <div className="cev-split"><div className="cev-main">
   <div className="cev-sec-head"><h2 className="h2">Состав</h2>{total>0&&<span className="meta">{got} из {total} {plural(total,'места','мест','мест')} заняты</span>}</div>
   <Card>{needs.length?needs.map(need=>{const short=free(need);return <div className="cev-role" key={need.id}><div className="cev-role-head"><div className="row" style={{gap:12}}><h3 className="h3">{need.role_title}</h3><span className={short?'cev-low':'meta'}>{taken(need)} из {need.required}</span></div></div>
    {people(need).map(row=><div className="cev-slot" key={row.id}><Avatar id={row.user_id} name={row.display_name}/><span className="grow"><button type="button" className="cev-name" onClick={()=>setPerson(row.id)}>{row.display_name}</button></span>{row.status==='confirmed'?<Icon name="check" className="cev-ok" role="img" aria-label="Участие подтверждено" aria-hidden={false}/>:<span className="dot dot-orange cev-low">ждём ответа</span>}</div>)}
    {Array.from({length:short},(_,index)=><div className="cev-slot" key={`free-${index}`}><span className="cev-slot-empty" aria-hidden="true"><Icon name="plus"/></span><span className="grow meta">Свободное место</span>{canInvite&&<Button variant="ghost" size="sm" onClick={()=>showPanel(need.id)}>Пригласить</Button>}</div>)}
   </div>;}):<p className="p">Волонтёры на это мероприятие не нужны.</p>}
    {waitingReserve.length>0&&<div className="cev-role"><div className="cev-role-head"><h3 className="h3">Резерв</h3><span className="meta">позовём, если кто-то отменит</span></div>{waitingReserve.map(row=><div className="cev-slot" key={row.id}><Avatar id={row.user_id} name={row.display_name}/><span className="grow"><span className="cev-name">{row.display_name}</span><span className="meta">{row.role_title}</span></span></div>)}</div>}
   </Card>
   {team.isError&&<ErrorState error={team.error} retry={()=>void team.refetch()}/>}
   <details className="card cev-details"><summary className="h3">Описание и подготовка</summary>{facts.length?<dl className="cev-dl">{facts.flatMap(([label,value])=>[<dt key={`${label}-t`}>{label}</dt>,<dd key={`${label}-d`}>{value}</dd>])}</dl>:<p className="p" style={{marginTop:18}}>Описание пока не заполнено.</p>}{access.opportunities&&<EventOpportunityPicker seriesId={item.series_id}/>}</details>
   <DobroOneOffPreparation occurrenceId={item.id}/><DobroTeamPanel occurrenceId={item.id}/>
  </div>
  {access.assign&&<aside className="cev-panel" ref={panelRef}>{inviteNeed&&canInvite?<InvitePanel event={item} need={inviteNeed} team={rows} date={date} onClose={()=>setPanel('')}/>:<>
   <div className="cev-panel-head"><div className="row" style={{gap:12}}><h2 className="h3">Отклики</h2>{waiting.length>0&&<span className="cev-count">{waiting.length}</span>}</div></div>
   {flash&&<p role="status" className="cev-done"><Icon name="check"/>{flash}</p>}
   {error&&<p role="alert" className="activity-error">{error}</p>}
   {(allResponses?waiting:waiting.slice(0,4)).map(row=><div className="cev-resp-card" key={row.key}><span className="cev-person"><Avatar id={row.userId} name={row.name}/><span style={{minWidth:0}}><span className="cev-name">{row.name}</span><span className="meta">{row.meta}</span></span></span>{row.text&&<p className="p">{row.text}</p>}{row.place?<Button variant="secondary" size="sm" disabled={command.isPending} onClick={row.accept}>Принять</Button>:<Button variant="secondary" size="sm" disabled={command.isPending} onClick={row.reserve}>Мест нет — в резерв</Button>}<Button variant="ghost" size="sm" disabled={command.isPending} onClick={row.decline}>Отклонить</Button></div>)}
   {!allResponses&&waiting.length>4&&<button type="button" className="cev-more" onClick={()=>setAllResponses(true)}>Показать все</button>}
   {!waiting.length&&(team.isPending&&team.fetchStatus!=='idle'?<LoadingState/>:<p className="p">Все отклики разобраны.</p>)}
  </>}</aside>}
  </div>
  {chosen&&<Dialog open title={chosen.display_name} onClose={()=>setPerson(null)}><AssignmentCard staff item={chosen}/></Dialog>}
  {params.get('edit')&&item.allowed_actions.includes('edit')&&<EditDialog item={item} onClose={()=>setParams(p=>{p.delete('edit');return p})}/>}
 </div>;
}

function InvitePanel({event,need,team,date,onClose}:{event:CalendarOccurrence;need:Need;team:AssignmentParticipation[];date:string;onClose:()=>void}){
 const suggestions=useAssignmentSuggestions(need.id),command=useActivityCommand(),[sent,setSent]=useState<string[]>([]),[all,setAll]=useState(false),[error,setError]=useState('');
 const list=(suggestions.data??[]).filter(row=>row.invitation_status!=='confirmed');
 const invite=(userId:string)=>{const existing=team.find(row=>row.user_id===userId);setError('');void command.mutateAsync({path:`/coord/staffing-needs/${need.id}/invitations`,body:{user_id:userId,expected_version:need.version,...(existing?{expected_assignment_version:existing.version}:{})},key:crypto.randomUUID()}).then(()=>setSent(current=>[...current,userId])).catch(reason=>setError(failure(reason)));};
 const note=(row:typeof list[number])=>row.reasons[0]??(row.facts?.attended?`${row.facts.attended} ${plural(row.facts.attended,'посещение','посещения','посещений')}`:'Ещё не участвовал в занятиях');
 return <>
  <div className="cev-panel-head"><div><p className="eyebrow">Пригласить на роль</p><h2 className="h3">{need.role_title}</h2></div><button type="button" className="cev-iconbtn" aria-label="Закрыть" onClick={onClose}><Icon name="x"/></button></div>
  <p className="p" style={{marginBottom:8}}>Подходят по роли и свободны {date}:</p>
  {error&&<p role="alert" className="activity-error">{error}</p>}
  {suggestions.isPending?<LoadingState/>:suggestions.isError?<ErrorState error={suggestions.error} retry={()=>void suggestions.refetch()}/>:list.length?(all?list:list.slice(0,4)).map(row=><div className="cev-resp-card" key={row.user_id}><span className="cev-person"><Avatar id={row.user_id} name={row.display_name}/><span style={{minWidth:0}}><span className="cev-name">{row.display_name}</span><span className="meta">{note(row)}</span></span></span>{sent.includes(row.user_id)||row.invitation_status==='invited'?<span className="cev-sent"><Icon name="check"/>Приглашение отправлено</span>:<Button variant="secondary" size="sm" disabled={command.isPending||event.status!=='scheduled'} onClick={()=>invite(row.user_id)}>Пригласить</Button>}</div>):<p className="p">Свободных подходящих волонтёров не нашли.</p>}
  {!all&&list.length>4&&<button type="button" className="cev-more" onClick={()=>setAll(true)}>Показать все</button>}
  <div className="cev-actions-row"><Button variant="ghost" onClick={onClose}>Вернуться к откликам</Button></div>
 </>;
}

function EditDialog({item,onClose}:{item:CalendarOccurrence;onClose:()=>void}){const series=useCalendarSeries(item.series_id);return <Dialog open onClose={onClose} className="activity-editor-dialog" title="Изменить мероприятие">{series.isPending?<LoadingState/>:series.isError?<ErrorState error={series.error}/>:<CalendarEditor key={`${item.id}:${item.version}`} occurrence={item} series={series.data} onClose={onClose} onSaved={onClose}/>}</Dialog>;}
