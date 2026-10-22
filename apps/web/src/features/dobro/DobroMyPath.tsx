import {useState} from 'react';
import {Button,Dialog,ErrorState,Field,Icon,Input,LoadingState} from '../../ui';
import {useDobroQuery,useDobroCommand,monthNow,type DobroOwn,type DobroOwnActivity} from './api';
import {useDobroDraft,DobroDraftConflict} from './useDobroDraft';
import './dobro.css';

const stateLabel={none:'Нужен отклик',applied:'Отклик на проверке',approved:'Отклик одобрен',not_needed:'Без переноса часов'};
/** «октябрь» and «ноября»: hours of the current month are entered at the start of the next one. */
function transferMonths(period:string){const [year,month]=period.split('-').map(Number),next=new Date(Date.UTC(year,month,15,9));return {month:new Date(Date.UTC(year,month-1,15,9)).toLocaleDateString('ru-RU',{month:'long',timeZone:'Europe/Moscow'}),next:next.toLocaleDateString('ru-RU',{day:'numeric',month:'long',timeZone:'Europe/Moscow'}).replace(/^\d+\s*/,'')};}
/** One white card on «Мой путь»: what is already in the Добро.рф book, or the one reply that is still missing. */
export function DobroMyPath(){
 const query=useDobroQuery<DobroOwn>('own','/me/dobro');
 const [profileOpen,setProfileOpen]=useState(false),[selected,setSelected]=useState<string|null>(null),[declining,setDeclining]=useState<string|null>(null);
 if(query.isPending)return <section className="sec"><LoadingState label="Загружаем данные Добро.рф…"/></section>;
 if(query.error)return <section className="sec"><ErrorState error={query.error} retry={()=>void query.refetch()}/></section>;
 const view=query.data,current=view.activities.find(item=>item.activity.id===selected),declined=view.activities.find(item=>item.activity.id===declining);
 const reply=view.activities.find(item=>item.state==='none'&&item.can_apply),correction=view.activities.find(item=>item.hours_due<0);
 if(!view.activities.length&&!view.entered_hours&&!view.profile_url)return null;
 const {month,next}=transferMonths(monthNow());
 return <section className="sec dobro-path">
  <div className="card dobro-card">
   <div className="row"><span className="art art-g" aria-hidden="true"><Icon name="book"/></span><h2 className="h3">Книжка Добро.рф</h2></div>
   {reply?<>
    <p className="p grow dobro-card-text">Чтобы часы попали в книжку, откликнись один раз на доброе дело фонда.</p>
    <div className="row wrap"><Button variant="secondary" aria-haspopup="dialog" onClick={()=>setSelected(reply.activity.id)}>Откликнуться</Button><Button variant="ghost" aria-haspopup="dialog" onClick={()=>setDeclining(reply.activity.id)}>Мне не нужно</Button></div>
   </>:<>
    <div className="dobro"><div className="figs"><div><b>{view.entered_hours} ч</b><span>уже внесли</span></div>{view.hours_due>0&&<div><b>{view.hours_due} ч</b><span>за {month}, перенесём в начале {next}</span></div>}</div></div>
    <div className="row">{view.profile_url?<a className="btn btn-secondary" href={view.profile_url} target="_blank" rel="noopener noreferrer">Открыть Добро.рф</a>:<Button variant="secondary" aria-haspopup="dialog" onClick={()=>setProfileOpen(true)}>Открыть Добро.рф</Button>}{view.profile_url&&<button type="button" className="iconbtn-soft" aria-label="Профиль Добро.рф" aria-haspopup="dialog" onClick={()=>setProfileOpen(true)}><Icon name="settings"/></button>}</div>
   </>}
   {correction&&<button type="button" className="dobro-path-correction" aria-haspopup="dialog" onClick={()=>setSelected(correction.activity.id)}><Icon name="alert"/><span>Есть уточнение по часам</span><Icon name="chevron-right"/></button>}
  </div>
  <ProfileDialog open={profileOpen} close={()=>setProfileOpen(false)} view={view}/>
  {current&&<ActivityDialog item={current} close={()=>setSelected(null)}/>}
  {declined&&<DeclineDialog item={declined} close={()=>setDeclining(null)}/>}
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
 async function change(next:'none'|'applied'){try{await action.mutateAsync({state:next,expected_version:item.enrollment_version});}catch{}}
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
 </Dialog>{opting&&<DeclineDialog item={item} close={()=>setOpting(false)}/>}</>;
}
/** «Мне не нужно»: the volunteer's own declaration; participation never depends on it. */
function DeclineDialog({item,close}:{item:DobroOwnActivity;close:()=>void}){
 const action=useDobroCommand('/me/dobro-enrollments/'+item.activity.id);
 return <Dialog open onClose={()=>!action.isPending&&close()} title="Не переносить часы?" footer={<><Button loading={action.isPending} onClick={()=>void action.mutateAsync({state:'not_needed',expected_version:item.enrollment_version}).then(close).catch(()=>{})}>Да, мне это не нужно</Button><Button variant="ghost" onClick={close}>Отмена</Button></>}><p>Это не отменит участие в занятиях. Подтверждённые часы останутся в Опоре, а прежние переносы — в журнале.</p>{action.error&&<ErrorState error={action.error}/>}</Dialog>;
}
