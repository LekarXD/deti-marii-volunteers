import {useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Icon, Button, Field, Input, Textarea, Segmented, SectionTabs, cx, type IconName} from '../../ui';
import {ApiError} from '../../api/transport';
import {eventsTabs} from '../../app/sectionTabs';
import {useActivityCommand, useRoles, type Requirement, type Role} from './api';
import {useMatchingOptions} from './eventsApi';
import {PreparationEditor} from './PreparationEditor';
import {volunteers} from './calendarPresentation';
import './activities.css';
type Draft={title:string;task:string;direction:string;skills:string[];preparation_defaults:Requirement[]};
const blank:Draft={title:'',task:'',direction:'',skills:[],preparation_defaults:[]};
const fromRole=(role:Role):Draft=>({title:role.title,task:role.task??'',direction:role.direction??'',skills:role.skills??[],preparation_defaults:role.preparation_defaults??[]});
/** A role has no picture of its own: its questionnaire direction picks one. */
const arts:Record<string,[string,IconName]>={'Помощь на занятиях':['art-o','hand'],'Творчество':['art-o','palette'],'Ярмарки':['art-y','heart'],'Мероприятия':['art-y','star'],'Фото, видео, соцсети':['art-b','camera'],'Обучение':['art-g','book'],'Психолог, логопед':['art-p','smile'],'Юрист, IT, маркетинг':['art-b','chart']};
const toggled=(list:string[],value:string)=>list.includes(value)?list.filter(item=>item!==value):[...list,value];
export function RolesPage(){
 const [params,setParams]=useSearchParams();const archived=params.get('archive')==='1',q=params.get('q')??'';
 const roles=useRoles(archived),rows=roles.data?.pages.flatMap(p=>p.items)??[],options=useMatchingOptions(),command=useActivityCommand();
 const [open,setOpen]=useState<string|null>(null),[draft,setDraft]=useState<Draft>(blank),[flash,setFlash]=useState(''),[errors,setErrors]=useState<Record<string,string>>({});
 const needle=q.trim().toLocaleLowerCase('ru'),shown=rows.filter(role=>!needle||`${role.title} ${(role.skills??[]).join(' ')}`.toLocaleLowerCase('ru').includes(needle));
 const known=rows.flatMap(role=>role.preparation_defaults??[]),current=rows.find(role=>role.id===open);
 const close=()=>{setOpen(null);setErrors({});command.reset();};
 const start=(id:string|null,next:Draft)=>{setOpen(id);setDraft(next);setErrors({});setFlash('');command.reset();};
 const change=(value:Partial<Draft>)=>{setDraft({...draft,...value});setErrors(old=>Object.fromEntries(Object.entries(old).filter(([key])=>!(key in value))));};
 async function save(){
  if(!draft.title.trim()){setErrors({title:'Введите название роли'});return;}
  try{const body={...draft,title:draft.title.trim(),task:draft.task.trim(),...(current?{approval_policy:current.approval_policy,expected_version:current.version}:{})};
   await command.mutateAsync({path:current?`/coord/roles/${current.id}`:'/coord/roles',method:current?'PATCH':'POST',body,key:crypto.randomUUID()});close();setFlash(`Роль «${body.title}» сохранена`);}
  catch(error){if(error instanceof ApiError)setErrors(error.field_errors);}
 }
 async function archive(role:Role){try{await command.mutateAsync({path:`/coord/roles/${role.id}/${role.archived_at?'restore':'archive'}`,body:{expected_version:role.version},key:crypto.randomUUID()});close();setFlash(role.archived_at?'Роль вернули из архива':'Роль убрана в архив');}catch{/* the form shows the error */}}
 const form=<div className="role-edit">
  <div className="role-edit-col">
   <Field label="Название" error={errors.title}><Input autoFocus={open==='new'} value={draft.title} placeholder="Например, ассистент педагога" onChange={e=>change({title:e.target.value})}/></Field>
   <Field label="Что делает волонтёр" error={errors.task}><Textarea className="role-task" value={draft.task} onChange={e=>change({task:e.target.value})}/></Field>
  </div>
  <div className="role-edit-col">
   <div className="field"><span className="label">Направление из анкеты</span><div className="pick" role="radiogroup" aria-label="Направление">{(options.data?.directions??[]).map(direction=><button type="button" role="radio" key={direction} aria-checked={draft.direction===direction} className={cx(draft.direction===direction&&'is-on')} onClick={()=>change({direction:draft.direction===direction?'':direction})}>{direction}</button>)}</div></div>
   <div className="field"><span className="label">Навыки</span><div className="pick" role="group" aria-label="Навыки">{(options.data?.skills??[]).map(skill=><button type="button" key={skill} aria-pressed={draft.skills.includes(skill)} className={cx(draft.skills.includes(skill)&&'is-on')} onClick={()=>change({skills:toggled(draft.skills,skill)})}>{skill}</button>)}</div></div>
   <PreparationEditor value={draft.preparation_defaults} options={known} onChange={preparation_defaults=>change({preparation_defaults})}/>
  </div>
  {command.isError&&<p className="activity-error full" role="alert">{command.error.message}{command.error instanceof ApiError&&command.error.code==='version_conflict'&&<> <Button variant="ghost" size="sm" onClick={()=>{void roles.refetch();close();}}>Загрузить актуальную версию</Button></>}</p>}
  <div className="full role-edit-actions"><div className="row"><Button loading={command.isPending} onClick={()=>void save()}>Сохранить</Button><Button variant="ghost" onClick={close}>Отмена</Button></div>{current&&<Button variant="ghost" disabled={command.isPending} onClick={()=>void archive(current)}>{current.archived_at?'Вернуть из архива':'В архив'}</Button>}</div>
 </div>;
 const row=(id:string,title:string,task:string,usage:string,art:[string,IconName])=><div key={id} className={cx('role-item',open===id&&'is-open')}>
  <button type="button" className="role-row" aria-expanded={open===id} onClick={()=>open===id?close():start(id,id==='new'?blank:fromRole(rows.find(role=>role.id===id)!))}>
   <span className={`art ${art[0]}`} aria-hidden="true"><Icon name={art[1]}/></span>
   <span className="grow"><span className="h3">{title}</span><span className="p">{task}</span></span>
   <span className="meta">{usage}</span><Icon name="chevron-down" className="chev"/>
  </button>
  {open===id&&form}</div>;
 return <div className="activity-roles">
  <SectionTabs label="Мероприятия" tabs={eventsTabs} actions={<Button variant="secondary" onClick={()=>{if(archived)setParams(p=>{p.delete('archive');return p});start('new',{...blank});}}><Icon name="plus"/>Новая роль</Button>}/>
  <div className="toolbar">
   <label className="search"><span className="sr-only">Найти роль</span><Icon name="search"/><Input type="search" placeholder="Название или навык" value={q} onChange={e=>setParams(p=>{if(e.target.value)p.set('q',e.target.value);else p.delete('q');return p},{replace:true})}/></label>
   <Segmented label="Какие роли показать" value={archived?'archive':'active'} onChange={value=>{close();setParams(p=>{if(value==='archive')p.set('archive','1');else p.delete('archive');return p});}} options={[{value:'active',label:'Действующие'},{value:'archive',label:'Архив'}]}/>
  </div>
  {flash&&<p className="done-note" role="status"><Icon name="check"/>{flash}</p>}
  {roles.isPending?<p role="status">Загружаем роли…</p>:roles.isError?<div role="alert"><p>{roles.error.message}</p><Button variant="secondary" onClick={()=>roles.refetch()}>Повторить</Button></div>:
  <div className="role-list">
   {open==='new'&&row('new',draft.title||'Новая роль',draft.task||'Опишите, что делает волонтёр','пока никого',['art-b','users'])}
   {shown.map(role=>row(role.id,role.title,role.task||'Опишите, что делает волонтёр',role.volunteer_count?volunteers(role.volunteer_count):'пока никого',arts[role.direction??'']??['art-v','users']))}
   {!shown.length&&open!=='new'&&<p className="empty-note">{q?'Ролей не нашли':archived?'В архиве пусто':'Ролей пока нет'}</p>}
   {roles.hasNextPage&&<Button variant="ghost" loading={roles.isFetchingNextPage} onClick={()=>roles.fetchNextPage()}>Показать ещё</Button>}
  </div>}
 </div>;
}
