import {useEffect, useRef, useState} from 'react';
import {Link, useNavigate, useSearchParams, useLocation} from 'react-router-dom';
import {Button, Card, ErrorState, LoadingState, Icon} from '../../ui';
import {api, ApiError} from '../../api/transport';
import {Application, Draft, useApplication, useCommand, useDraft, applicationKeys, commandKey} from './api';
import {useQueryClient} from '@tanstack/react-query';
import {Answers, FormContent, visible, label} from './form';
import {FieldRenderer} from './FieldRenderer';
import './applications.css';

export function ApplyPage() {
  const draft=useDraft(), self=useApplication(), [search]=useSearchParams(), edit=useLocation().pathname.endsWith('/edit')||search.has('edit');
  const navigate=useNavigate(), client=useQueryClient();
  const [answers,setAnswers]=useState<Answers>({}),[step,setStep]=useState(0),[errors,setErrors]=useState<Record<string,string>>({}),[saveError,setSaveError]=useState(''),[saveStatus,setSaveStatus]=useState(''),[initialized,setInitialized]=useState(false);
  const baseVersion=useRef(0);
  const version=useRef(0), chain=useRef<Promise<void>>(Promise.resolve()), mounted=useRef(true), latest=useRef({answers,step}), dirty=useRef(false);
  latest.current={answers,step};
  const pendingSave=useRef<{snapshot:typeof latest.current;body:unknown;key:string}|null>(null);
  const submit=useCommand<Application>(edit?'/api/v1/me/application/revisions':'/api/v1/applications/submit');
  const form=draft.data?.form.content as unknown as FormContent|undefined;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{if(initialized||!draft.data||(edit&&self.isPending))return;
    version.current=draft.data.version;baseVersion.current=self.data?.version||0;
    const prior=edit&&self.data?{...self.data.revision.answers,consentPD:self.data.consents.personal_data,consentNews:self.data.consents.news,...(draft.data.id?draft.data.answers:{})}:draft.data.answers;
    setAnswers(prior as Answers);setStep(edit?0:draft.data.step);setInitialized(true);
  },[draft.data,self.data,self.isPending,edit,initialized]);
  async function saveLatest() {
    const snapshot=latest.current;
    setSaveStatus('Сохраняем…');setSaveError('');
    chain.current=chain.current.catch(()=>{}).then(async()=>{
      const write=async(snapshotToSave:typeof latest.current)=>{
        if(!pendingSave.current)pendingSave.current={snapshot:snapshotToSave,body:{expected_version:version.current,...snapshotToSave},key:commandKey()};
        const request=pendingSave.current;
        const saved=await api<Draft>('/api/v1/registration/draft',{method:'PUT',body:request.body,idempotencyKey:request.key,retries:0});
        version.current=saved.version;client.setQueryData(applicationKeys.draft(),saved);pendingSave.current=null;
        return request.snapshot;
      };
      const savedSnapshot=await write(snapshot);
      if(savedSnapshot!==snapshot)await write(snapshot);
      if(mounted.current){dirty.current=latest.current.answers!==snapshot.answers||latest.current.step!==snapshot.step;setSaveStatus(dirty.current?'Сохраняем…':'Черновик сохранён');}
    }).catch(error=>{if(mounted.current){setSaveError(error instanceof Error?error.message:'Не удалось сохранить черновик');setSaveStatus('Есть несохранённые изменения');}throw error;});
    return chain.current;
  }
  useEffect(()=>{if(!initialized||!dirty.current||submit.isPending)return;const timer=setTimeout(()=>{void saveLatest().catch(()=>{});},700);return()=>clearTimeout(timer);},[answers,step,initialized,submit.isPending]);
  useEffect(()=>{const prevent=(event:BeforeUnloadEvent)=>{if(dirty.current){event.preventDefault();event.returnValue='';}};window.addEventListener('beforeunload',prevent);return()=>window.removeEventListener('beforeunload',prevent);},[]);
  if(draft.error)return <ErrorState error={draft.error} retry={()=>void draft.refetch()}/>;
  if(edit&&self.error)return <ErrorState error={self.error} retry={()=>void self.refetch()}/>;
  if(draft.isPending||!initialized||!form)return <LoadingState/>;
  const fields=form.steps[step].fields, last=step===form.steps.length-1;
  function update(id:string,value:Answers[string]){dirty.current=true;setAnswers(old=>{const next={...old,[id]:value};if(id==='directions'&&Array.isArray(old.skills)){const skill=form!.steps.flatMap(part=>part.fields).find(field=>field.id==='skills');const groups=skill?.groups||[],known=groups.flatMap(group=>group.options.map(label)),allowed=groups.filter(group=>visible(group.showIf,next)).flatMap(group=>group.options.map(label));next.skills=old.skills.filter(item=>allowed.includes(item)||!known.includes(item));}return next;});setErrors(old=>{const next={...old};delete next[id];return next;});}
  function focusField(id:string){requestAnimationFrame(()=>document.querySelector<HTMLElement>(`[data-field="${id}"] input,[data-field="${id}"] button,[data-field="${id}"] textarea`)?.focus());}
  async function next(){const missing:Record<string,string>={};for(const field of fields)if(visible(field.showIf,answers)&&field.required&&(!answers[field.id]||(Array.isArray(answers[field.id])&&!(answers[field.id] as string[]).length)))missing[field.id]='Заполните поле';
    if(Object.keys(missing).length){setErrors(missing);focusField(Object.keys(missing)[0]);return;}
    if(!last){dirty.current=true;setStep(step+1);window.scrollTo(0,0);return;}
    try{await chain.current.catch(()=>{});const result=await submit.mutateAsync({body:{expected_version:edit?baseVersion.current:0,answers,consents:{personal_data:answers.consentPD===true,news:answers.consentNews===true,document_version:'4'}}});client.setQueryData(applicationKeys.self(),result);dirty.current=false;navigate('/application'+(edit?'?updated=1':''));}
    catch(error){if(error instanceof ApiError){const fieldErrors=error.field_errors as Record<string,string>|undefined;if(fieldErrors){setErrors(fieldErrors);const fieldId=Object.keys(fieldErrors)[0];const target=form!.steps.findIndex(part=>part.fields.some(field=>field.id===fieldId));if(target>=0)setStep(target);focusField(fieldId);}}}
  }
  return <div className="ap-page">
    {edit&&<Link className="ap-back" to="/application"><Icon name="chevron-left"/>Вернуться в личный кабинет</Link>}
    <div className="head ap-heading"><div><h1 className="h1">{edit?'Моя анкета':form.title}</h1><p className="lead">{edit?'Измените ответы. Знакомство с фондом и запись на встречу сохранятся.':form.intro}</p></div></div>
    <div className="ap-layout"><form className="ap-apply-main" noValidate onSubmit={event=>{event.preventDefault();void next();}}>
      <Card className="ap-form-card"><div className="ap-stephead"><p className="eyebrow">Шаг {step+1} из {form.steps.length}</p><h2 className="h2">{form.steps[step].title}</h2><div className="ap-progress" role="progressbar" aria-label={`Шаг ${step+1} из ${form.steps.length}`} aria-valuenow={step+1} aria-valuemax={form.steps.length}><span style={{width:`${100*(step+1)/form.steps.length}%`}}/></div></div>
      <fieldset disabled={submit.isPending} className="ap-fields">{fields.map(field=><FieldRenderer key={field.id} field={field} answers={answers} onChange={update} error={errors[field.id]}/>)}</fieldset>
      {answers.firstName&&form.shortNames[String(answers.firstName)]&&<p className="ap-hint">Это полное имя? Например, {form.shortNames[String(answers.firstName)]}. Так координатору будет проще найти вас в документах.</p>}
      {submit.error&&<div role="alert" className="ap-error">{submit.error.message}{edit&&submit.error instanceof ApiError&&submit.error.status===409&&<Button variant="ghost" type="button" onClick={()=>{void Promise.all([self.refetch(),draft.refetch()]).then(([latestApplication,latestDraft])=>{if(!latestApplication.data||!latestDraft.data)return;baseVersion.current=latestApplication.data.version;version.current=latestDraft.data.version;pendingSave.current=null;dirty.current=false;setAnswers({...latestApplication.data.revision.answers,consentPD:latestApplication.data.consents.personal_data,consentNews:latestApplication.data.consents.news} as Answers);submit.reset();});}}>Загрузить актуальные ответы — текущий ввод будет заменён</Button>}</div>}
      {saveError&&<div role="alert" className="ap-error">{saveError} <button type="button" onClick={()=>void saveLatest().catch(()=>{})}>Повторить сохранение</button>{saveError.includes('измен')&&<p>Черновик открыт в другой вкладке. Скопируйте новые ответы перед обновлением.</p>}</div>}
      </Card>
      <div className="ap-form-footer">{step>0&&<Button variant="ghost" size="lg" type="button" disabled={submit.isPending} onClick={()=>{dirty.current=true;setStep(step-1);}}><Icon name="chevron-left"/>Назад</Button>}<span className="ap-save-status" role="status">{saveStatus}</span><Button size="lg" type="submit" disabled={submit.isPending}>{submit.isPending?'Отправляем…':last?(edit?'Сохранить изменения':'Отправить анкету'):'Дальше'}<Icon name="chevron-right"/></Button></div>
    </form><aside className="ap-path-card"><Card><h2 className="h3">Как стать волонтёром</h2><ol className="ap-pathlist">{form.path.map((item,index)=>{const pathIcon=(['edit','book','calendar'] as const)[index]||'edit';return <li className={index===0?'is-now':''} key={item.title}><span className="ap-path-icon"><Icon name={pathIcon}/></span><span><b>{item.title}</b><small>{item.meta}</small></span></li>;})}</ol><p className="meta">{form.pathNote}</p></Card></aside></div>
  </div>;
}
