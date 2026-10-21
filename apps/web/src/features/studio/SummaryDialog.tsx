import {useEffect,useRef,useState} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import type {components} from '../../api/generated/schema';
import {api,ApiError} from '../../api/transport';
import {Button,Dialog,Field,Input,Textarea,LoadingState,ErrorState} from '../../ui';
import './summary.css';
type Summary=components['schemas']['WebinarSummaryView'];
type Preview=components['schemas']['SummaryAudiencePreviewView'];
type Send=components['schemas']['SummarySendView'];
const reasons:Record<string,string>={no_contact:'Запрет на уведомления',in_app_disabled:'Внутренние уведомления отключены',topic_disabled:'Уведомления об обучении отключены',user_unavailable:'Аккаунт недоступен',already_sent:'Эта версия уже поставлена в очередь'};
export function SummaryDialog({webinarId,title,onClose}:{webinarId:string;title:string;onClose:()=>void}){
 const client=useQueryClient(),queryKey=['webinar-summary',webinarId],path=`/webinars/${webinarId}/summary`;
 const query=useQuery({queryKey,queryFn:({signal})=>api<Summary>(path,{signal})});
 const [heading,setHeading]=useState(''),[body,setBody]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[sent,setSent]=useState<Send|null>(null),pendingKeys=useRef(new Map<string,string>());
 const value=query.data;
 useEffect(()=>{if(value){setHeading(value.draft?.title??`Итоги: ${title}`);setBody(value.draft?.body??'');setPreview(null);setSent(null);}},[value?.version,webinarId]);
 const command=useMutation({mutationFn:async({action,payload}:{action:string;payload:unknown})=>{
  const signature=JSON.stringify([action,payload]),key=pendingKeys.current.get(signature)??crypto.randomUUID();pendingKeys.current.set(signature,key);
  try{const response=await api<Summary|Preview|Send>(action?`${path}/${action}`:path,{method:action?'POST':'PATCH',body:payload,idempotencyKey:key});pendingKeys.current.delete(signature);return response;}
  catch(error){if(error instanceof ApiError&&error.status>=400&&error.status<500&&![408,429].includes(error.status))pendingKeys.current.delete(signature);throw error;}
 },onSuccess:(result,{action})=>{if(action==='audience-preview'){setPreview(result as Preview);setSent(null);}else if(action==='send'){setSent(result as Send);setPreview(null);}else{client.setQueryData(queryKey,result);setPreview(null);setSent(null);}}});
 const changed=!!value&&(heading!==(value.draft?.title??`Итоги: ${title}`)||body!==(value.draft?.body??''));
 const draft=value?.draft,published=value?.published;
 const decide=(action:string)=>draft&&command.mutate({action,payload:{expected_version:value!.version,revision:draft.number}});
 return <Dialog open className="summary-dialog" onClose={onClose} title="Итоги занятия"><div className="summary-panel"><p>{title}</p>
 {query.isLoading?<LoadingState/>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:value&&<>
 <p className="st-meta">{published?`Опубликована версия ${published.number}.`:'Итоги ещё не опубликованы.'} {draft&&`Черновик: версия ${draft.number}.`} Публикация итогов открывает только этот текст участникам занятия.</p>
 <form className="st-form" onSubmit={event=>{event.preventDefault();command.mutate({action:'',payload:{expected_version:value.version,title:heading,body}});}}>
  <Field label="Заголовок итогов"><Input required maxLength={300} value={heading} disabled={!value.can_manage||command.isPending} onChange={event=>setHeading(event.target.value)}/></Field>
  <Field label="Текст для участников"><Textarea required maxLength={7000} rows={8} value={body} disabled={!value.can_manage||command.isPending} onChange={event=>setBody(event.target.value)}/></Field>
  <Button type="submit" variant="secondary" disabled={!value.can_manage||command.isPending||!heading.trim()||!body.trim()||(!changed&&!!draft)}>Сохранить черновик</Button>
 </form>
 {draft&&<section className="summary-preview" aria-label="Проверка итогов"><h3>Предпросмотр версии {draft.number}</h3><strong>{draft.title}</strong><p>{draft.body}</p>
  {changed?<p className="st-meta">Сохраните изменения, чтобы проверить и опубликовать новую версию.</p>:<div className="st-actions"><Button variant="secondary" disabled={!value.can_manage||command.isPending||value.reviewed_revision===draft.number} onClick={()=>decide('review')}>{value.reviewed_revision===draft.number?'Версия проверена':'Проверить версию'}</Button><Button disabled={!value.can_manage||command.isPending||value.reviewed_revision!==draft.number||published?.number===draft.number} onClick={()=>decide('publish')}>Опубликовать итоги</Button></div>}
 </section>}
 {published&&<section className="summary-delivery" aria-label="Отправка итогов"><h3>Отправить опубликованную версию {published.number}</h3><p>Участники получат сообщение внутри «Опоры». Сначала проверьте список получателей.</p>
  {value.can_send?<Button variant="secondary" disabled={command.isPending||changed} onClick={()=>command.mutate({action:'audience-preview',payload:{expected_version:value.version,revision:published.number}})}>Проверить получателей</Button>:<p className="st-meta">Для отправки нужно право на отправку уведомлений.</p>}
  {preview&&<div className="summary-audience"><p><strong>Получат сообщение: {preview.eligible_count}</strong></p><ul>{preview.members.map(member=><li key={member.user_id}><span>{member.display_name}</span><span>{member.eligible?'Получит итоги':reasons[member.reason??'']??'Доставка недоступна'}</span></li>)}</ul>{!preview.members.length&&<p>На занятие никто не записан.</p>}<p className="st-meta">Список действует 15 минут. При изменениях потребуется новая проверка.</p><Button disabled={command.isPending||preview.eligible_count===0} onClick={()=>command.mutate({action:'send',payload:{expected_version:value.version,revision:published.number,preview_id:preview.id,preview_hash:preview.preview_hash}})}>Отправить итоги участникам ({preview.eligible_count})</Button></div>}
  {sent&&<p role="status">Поставлено в очередь: {sent.enqueued}. Сообщения появятся у участников после проверки доставки.</p>}
 </section>}
 </>}
 {command.error&&<ErrorState error={command.error} retry={()=>{command.reset();setPreview(null);void query.refetch();}}/>}
 </div></Dialog>;
}
