import {useState} from 'react';
import {Button,Dialog,Field,LoadingState,Textarea} from '../../ui';
import {Consent,DataRequest,useProfileList,useProfileCommand,downloadAsset,requestLabels} from './api';

const failureText=(error:unknown)=>error instanceof Error&&error.message?error.message:'Не получилось. Попробуй ещё раз.';
const when=(value:string)=>new Date(value).toLocaleDateString('ru',{day:'numeric',month:'long',year:'numeric'}).replace(/\s?г\.$/,'');

export function ConsentPanel(){
 const query=useProfileList<Consent>('consents','/me/profile/consents'),save=useProfileCommand<Consent>('/me/profile/consents');
 const events=Array.isArray(query.data)?query.data:[],latest=(purpose:string)=>events.filter(e=>e.purpose===purpose).at(-1),personal=latest('personal_data');
 return <section className="card" id="profile-consents">
  <h2 className="h3 prof-card-title">Согласия</h2>
  {query.isPending?<LoadingState/>:query.error?<p className="err" role="alert">{failureText(query.error)}</p>:<>
   <label className="set-row prof-set-label"><span className="grow"><b>Хочу получать новости фонда</b><span className="meta">Можно отказаться в любой момент</span></span><input type="checkbox" className="prof-switch" aria-label="Хочу получать новости фонда" checked={latest('news')?.granted||false} disabled={save.isPending} onChange={e=>save.mutate({purpose:'news',granted:e.target.checked,document_version:'4'})}/></label>
   {personal&&<div className="set-row"><div className="grow"><b>Обработка персональных данных</b><span className="meta">{personal.granted?'Согласие дано':'Согласие отозвано'}</span></div>{personal.granted&&<Button variant="ghost" size="sm" disabled={save.isPending} onClick={()=>save.mutate({purpose:'personal_data',granted:false,document_version:'4'})}>Отозвать</Button>}</div>}
   {events.length>0&&<details className="prof-details"><summary>История согласий</summary><div className="rows">{events.map(event=><div className="rowi" key={event.id}><div className="grow"><span className="rowi-title">{event.purpose==='news'?'Новости фонда':'Обработка данных'}</span><span className="meta">{when(event.created_at)}, {event.granted?'дано':'отозвано'}</span></div></div>)}</div></details>}
  </>}
  {save.error&&<p className="err" role="alert">{failureText(save.error)}</p>}
 </section>;
}

export function OwnDataPanel(){
 const query=useProfileList<DataRequest>('data','/me/profile/data-requests'),request=useProfileCommand<DataRequest>('/me/profile/data-requests'),[asking,setAsking]=useState(false),[reason,setReason]=useState(''),[downloadError,setDownloadError]=useState<unknown>(null);
 const rows=Array.isArray(query.data)?query.data:[];
 return <section className="card">
  <h2 className="h3 prof-card-title">Мои данные</h2>
  <div className="set-row"><div className="grow"><b>Архив моих данных</b><span className="meta">Анкета, часы, расписание, согласия и документы одним файлом</span></div><Button variant="secondary" size="sm" disabled={request.isPending} onClick={()=>request.mutate({kind:'export'})}>Подготовить архив</Button></div>
  <div className="set-row"><div className="grow"><b>Удалить аккаунт</b><span className="meta">Запрос рассмотрит сотрудник фонда и расскажет, что придётся сохранить</span></div><Button variant="danger" size="sm" onClick={()=>setAsking(true)}>Запросить удаление</Button></div>
  {request.error&&!asking&&<p className="err" role="alert">{failureText(request.error)}</p>}
  {query.isPending?<LoadingState/>:query.error?<p className="err" role="alert">{failureText(query.error)}</p>:rows.length>0&&<div className="rows prof-requests">{rows.map(row=><DataRow key={row.id} row={row} onDownloadError={setDownloadError}/>)}</div>}
  {!!downloadError&&<p className="err" role="alert">{failureText(downloadError)}</p>}
  <Dialog open={asking} onClose={()=>!request.isPending&&setAsking(false)} title="Запросить удаление аккаунта?" footer={<><Button variant="danger" disabled={request.isPending} onClick={()=>void request.mutateAsync({kind:'deletion',reason}).then(()=>setAsking(false)).catch(()=>{})}>Отправить запрос</Button><Button variant="ghost" onClick={()=>setAsking(false)}>Отмена</Button></>}>
   <p className="p">Сотрудник поможет завершить участие и объяснит, как будет обработан запрос. Аккаунт не исчезнет сразу после отправки.</p>
   <Field label="Что важно учесть (по желанию)"><Textarea value={reason} onChange={e=>setReason(e.target.value)} maxLength={4000}/></Field>
   {request.error&&<p className="err" role="alert">{failureText(request.error)}</p>}
  </Dialog>
 </section>;
}

function DataRow({row,onDownloadError}:{row:DataRequest;onDownloadError:(e:unknown)=>void}){
 const cancel=useProfileCommand<DataRequest>(`/me/profile/data-requests/${row.id}/cancel`);
 const ready=!!row.asset_id&&row.state==='ready',open=row.kind==='deletion'&&['requested','in_review','approved'].includes(row.state);
 return <div className="rowi">
  <div className="grow">
   <span className="rowi-title">{row.kind==='export'?'Архив данных':'Удаление аккаунта'}</span>
   <span className="meta">{requestLabels[row.state]??row.state}, {when(row.created_at)}</span>
   {row.public_response&&<span className="p prof-row-text">{row.public_response}</span>}
   {row.retention_note&&<span className="meta">{row.retention_note}</span>}
   {row.scheduled_for&&<span className="meta">Плановая дата: {when(row.scheduled_for)}</span>}
   {cancel.error&&<span className="err" role="alert">{failureText(cancel.error)}</span>}
  </div>
  {(ready||open)&&<span className="rowi-end">
   {ready&&<Button variant="secondary" size="sm" onClick={()=>void downloadAsset(row.asset_id!,'мои-данные.zip').catch(onDownloadError)}>Скачать архив</Button>}
   {open&&<Button variant="ghost" size="sm" disabled={cancel.isPending} onClick={()=>cancel.mutate({expected_version:row.version})}>Отменить запрос</Button>}
  </span>}
 </div>;
}
