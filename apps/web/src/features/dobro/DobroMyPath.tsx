import {useState} from 'react';
import {Button,Card,Dialog,ErrorState,Field,Icon,Input,LoadingState} from '../../ui';
import {useDobroQuery,useDobroCommand,type DobroOwn,type DobroOwnActivity} from './api';
import {useDobroDraft,DobroDraftConflict} from './useDobroDraft';
import './dobro.css';

const stateLabel={none:'Нужен отклик',applied:'Отклик на проверке',approved:'Отклик одобрен',not_needed:'Без переноса часов'};
export function DobroMyPath(){
 const query=useDobroQuery<DobroOwn>('own','/me/dobro');
 const [profileOpen,setProfileOpen]=useState(false),[selected,setSelected]=useState<string|null>(null),[all,setAll]=useState(false);
 if(query.isPending)return <LoadingState label="Загружаем данные Добро.рф…"/>;
 if(query.error)return <ErrorState error={query.error} retry={()=>void query.refetch()}/>;
 const view=query.data,activities=all?view.activities:view.activities.slice(0,4),current=view.activities.find(item=>item.activity.id===selected);
 const correction=view.activities.find(item=>item.hours_due<0),needsReply=view.activities.some(item=>item.state==='none');
 return <section className="section dobro-path"><div className="section-head"><h2 className="h2">Добро.рф</h2><Button variant="ghost" onClick={()=>setProfileOpen(true)}>Настройки <Icon name="chevron-right"/></Button></div>
  <Card className="dobro-path-surface">
   <div className="dobro-path-totals"><div><strong>{view.entered_hours}<span> ч</span></strong><span>Внесено</span></div><div><strong>{view.hours_due}<span> ч</span></strong><span>К переносу</span></div></div>
   {needsReply&&<p className="dobro-path-intro">Чтобы получить часы в книжку, откликнись на доброе дело.</p>}
   {correction&&<button type="button" className="dobro-path-correction" onClick={()=>setSelected(correction.activity.id)}><Icon name="alert"/><span>Есть уточнение по часам</span><Icon name="chevron-right"/></button>}
   {activities.length?<div className="dobro-path-list">{activities.map(item=><button key={item.activity.id} type="button" className={'dobro-path-row '+(item.state==='none'?'needs-reply':'')} aria-label={item.activity.title+' — '+stateLabel[item.state]} aria-haspopup="dialog" onClick={()=>setSelected(item.activity.id)}><span>{item.activity.title}</span><span className="dobro-path-row-end" title={stateLabel[item.state]}><Icon name={item.state==='approved'?'check':item.state==='applied'?'clock':item.state==='not_needed'?'x':'arrow-right'}/><Icon name="chevron-right"/></span></button>)}</div>:<p className="dobro-path-empty">Доброе дело появится здесь после подтверждения участия.</p>}
   {view.activities.length>4&&<Button variant="ghost" onClick={()=>setAll(!all)}>{all?'Свернуть':'Показать все ('+view.activities.length+')'}</Button>}
  </Card>
  <ProfileDialog open={profileOpen} close={()=>setProfileOpen(false)} view={view}/>
  {current&&<ActivityDialog item={current} close={()=>setSelected(null)}/>}
 </section>;
}
function ProfileDialog({open,close,view}:{open:boolean;close:()=>void;view:DobroOwn}){
 const editor=useDobroDraft({profile_url:view.profile_url,version:view.profile_version}),{draft,conflict,dirty}=editor;
 const save=useDobroCommand('/me/external-profiles/dobro','PUT');
 return <Dialog open={open} onClose={()=>!save.isPending&&close()} title="Профиль Добро.рф" className="dobro-path-dialog">
  <p>Координатор переносит часы вручную. Ссылка поможет найти тебя в Добро.рф.</p>
  <form className="dobro-profile-form" onSubmit={event=>{event.preventDefault();void save.mutateAsync({profile_url:draft.profile_url,expected_version:draft.version}).then(close).catch(()=>{});}}>
   <Field label="Ссылка на твой профиль"><Input type="url" value={draft.profile_url} onChange={event=>editor.setDraft({...draft,profile_url:event.target.value})} maxLength={1500} placeholder="https://dobro.ru/volunteers/…"/></Field>
   {conflict&&<DobroDraftConflict useServer={editor.useServer} keepMine={editor.keepMine}/>}
   <div className="actions"><Button type="submit" disabled={!dirty||conflict} loading={save.isPending}>Сохранить</Button>{view.registration_url&&!view.profile_url&&<a className="btn btn-secondary" href={view.registration_url} target="_blank" rel="noopener noreferrer">Зарегистрироваться</a>}</div>
   {save.error&&<ErrorState error={save.error}/>}
  </form>
  <details className="dobro-path-details"><summary>Как учитываются часы</summary><p>{view.rules_note}</p><p>Участие в занятиях доступно независимо от Добро.рф.</p>{view.verified_organization&&<p>Фонд отметил в настройках верификацию на Добро.рф.</p>}</details>
 </Dialog>;
}
function ActivityDialog({item,close}:{item:DobroOwnActivity;close:()=>void}){
 const action=useDobroCommand('/me/dobro-enrollments/'+item.activity.id),[opting,setOpting]=useState(false);
 async function change(next:'none'|'applied'|'not_needed'){try{await action.mutateAsync({state:next,expected_version:item.enrollment_version});setOpting(false);}catch{}}
 return <><Dialog open onClose={()=>!action.isPending&&close()} title={item.activity.title} className="dobro-path-dialog">
  <p className="dobro-path-state"><Icon name={item.state==='approved'?'check-circle':item.state==='applied'?'clock':item.state==='not_needed'?'x':'arrow-right'}/>{stateLabel[item.state]}</p>
  {item.state==='none'?<><p>Откликнись на Добро.рф один раз на сезон. После этого координатор сможет переносить твои часы.</p><div className="actions"><a className="btn btn-secondary" href={item.activity.url} target="_blank" rel="noopener noreferrer">Откликнуться на Добро.рф</a><Button disabled={!item.can_apply} loading={action.isPending} onClick={()=>void change('applied')}>Я откликнулся</Button></div></>:item.state==='not_needed'?<><p>Часы остаются в Опоре. Для этого доброго дела перенос отключён.</p><Button onClick={()=>void change('none')} loading={action.isPending}>Всё-таки нужно</Button></>:<>
   {item.state==='applied'&&<p>Координатор проверит отклик на Добро.рф.</p>}
   <dl className="dobro-path-facts"><div><dt>Внесено</dt><dd>{item.entered_hours} ч</dd></div>{item.hours_due>0&&<div><dt>К переносу</dt><dd>{item.hours_due} ч</dd></div>}{item.carry_minutes>0&&<div><dt>Остаток на следующий раз</dt><dd>{item.carry_minutes} мин</dd></div>}</dl>
   {item.hours_due<0&&<p>После исправления посещения нужно уменьшить сумму на Добро.рф на {-item.hours_due} ч. Это сделает координатор.</p>}
   <div className="actions"><a className="btn btn-secondary" href={item.activity.url} target="_blank" rel="noopener noreferrer">Открыть на Добро.рф</a></div>
  </>}
  {item.state!=='not_needed'&&<details className="dobro-path-details"><summary>Если часы в книжке не нужны</summary><p>Участие в занятиях доступно независимо от Добро.рф.</p><Button variant="ghost" disabled={!item.can_apply||action.isPending} onClick={()=>setOpting(true)}>Не переносить часы</Button></details>}
  {action.error&&<ErrorState error={action.error}/>}
 </Dialog><Dialog open={opting} onClose={()=>!action.isPending&&setOpting(false)} title="Не переносить часы?" footer={<><Button loading={action.isPending} onClick={()=>void change('not_needed')}>Да, мне это не нужно</Button><Button variant="ghost" onClick={()=>setOpting(false)}>Отмена</Button></>}><p>Это не отменит участие в занятиях. Подтверждённые часы останутся в Опоре, а прежние переносы — в журнале.</p></Dialog></>;
}
