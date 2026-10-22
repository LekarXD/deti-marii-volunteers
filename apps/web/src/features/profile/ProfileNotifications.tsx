import {useRef,useState,type ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import type {components} from '../../api/generated/schema';
import {api,ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import {Button,ErrorState,LoadingState,TimePicker} from '../../ui';
import {minuteTime,readPreferences,savePreferences,timeMinute,topics,type PreferenceCommand,type Preferences} from '../notifications/api';

type Binding=components['schemas']['TelegramBindingView'];
type LinkToken=components['schemas']['TelegramLinkTokenView'];
const telegramPath='/me/notification-channels/telegram';
const failureText=(error:unknown)=>error instanceof ApiError&&error.status===409?'Настройки изменились в другом окне. Мы показали актуальные, попробуй ещё раз.':error instanceof Error&&error.message?error.message:'Не получилось сохранить. Попробуй ещё раз.';

/** «Уведомления»: every toggle is saved at once through the canonical notification preferences. */
export function ProfileNotifications({email}:{email:string|null}){
 const query=useQuery({queryKey:keys.self('notification-preferences'),queryFn:({signal})=>readPreferences(signal),staleTime:0});
 if(query.isPending)return <LoadingState label="Загружаем настройки уведомлений…"/>;
 if(query.error)return <ErrorState error={query.error} retry={()=>void query.refetch()}/>;
 return <NotificationSettings value={query.data} email={email}/>;
}

function SetRow({title,sub,children}:{title:string;sub?:ReactNode;children:ReactNode}){
 return <div className="set-row"><div className="grow"><b>{title}</b>{sub&&<span className="meta">{sub}</span>}</div>{children}</div>;
}
function Toggle({label,on,disabled,onChange}:{label:string;on:boolean;disabled?:boolean;onChange:()=>void}){
 return <button type="button" className={'toggle'+(on?' is-on':'')} aria-pressed={on} aria-label={label} disabled={disabled} onClick={onChange}/>;
}

function NotificationSettings({value,email}:{value:Preferences;email:string|null}){
 const client=useQueryClient(),receipt=useRef({payload:'',key:''});
 const [pending,setPending]=useState<Partial<PreferenceCommand>|null>(null),[failure,setFailure]=useState<unknown>(null);
 const shown={...value,...pending,topics:pending?.topics??value.topics} as Preferences;
 async function save(patch:Partial<PreferenceCommand>){
  if(pending)return;
  const body:PreferenceCommand={expected_version:value.version,no_contact:value.no_contact,email_enabled:value.email_enabled,in_app_enabled:value.in_app_enabled,topics:value.topics,quiet_enabled:value.quiet_enabled,quiet_from:value.quiet_from,quiet_to:value.quiet_to,timezone:value.timezone,...patch};
  const payload=JSON.stringify(body);if(receipt.current.payload!==payload)receipt.current={payload,key:crypto.randomUUID()};
  setPending(patch);setFailure(null);
  try{const updated=await savePreferences(body,receipt.current.key);client.setQueryData(keys.self('notification-preferences'),updated);receipt.current={payload:'',key:''};}
  catch(error){setFailure(error);if(error instanceof ApiError&&error.status===409)await client.invalidateQueries({queryKey:keys.self('notification-preferences')});}
  finally{setPending(null);}
 }
 const busy=!!pending;
 const emailSub=[email,value.email_provider_state==='available'?'':'письма пока не отправляются'].filter(Boolean).join(', ')||'На подтверждённую почту';
 return <div className="prof-stack">
  <div className="card">
   <SetRow title="В кабинете" sub="Приглашения и ответы координатора"><Toggle label="В кабинете" on={shown.in_app_enabled} disabled={busy} onChange={()=>void save({in_app_enabled:!value.in_app_enabled})}/></SetRow>
   <SetRow title="На почту" sub={emailSub}><Toggle label="На почту" on={shown.email_enabled} disabled={busy} onChange={()=>void save({email_enabled:!value.email_enabled})}/></SetRow>
   <TelegramRow/>
   <SetRow title="Тихие часы" sub={shown.quiet_enabled?`С ${minuteTime(shown.quiet_from)} до ${minuteTime(shown.quiet_to)} уведомления подождут`:undefined}><Toggle label="Тихие часы" on={shown.quiet_enabled} disabled={busy} onChange={()=>void save({quiet_enabled:!value.quiet_enabled})}/></SetRow>
   {shown.quiet_enabled&&<div className="prof-quiet">
    <TimePicker label="С" value={minuteTime(value.quiet_from)} disabled={busy} onChange={next=>{if(timeMinute(next)!==value.quiet_from)void save({quiet_from:timeMinute(next)});}}/>
    <TimePicker label="До" value={minuteTime(value.quiet_to)} disabled={busy} onChange={next=>{if(timeMinute(next)!==value.quiet_to)void save({quiet_to:timeMinute(next)});}}/>
   </div>}
  </div>
  <section className="card">
   <h2 className="h3 prof-card-title">О чём сообщать</h2>
   {(Object.keys(topics) as (keyof typeof topics)[]).map(key=>{const locked=key==='news'&&!value.news_consent;return <SetRow key={key} title={topics[key]} sub={locked?<>Сначала нужно <Link to="/profile?tab=privacy#profile-consents">согласие на новости</Link></>:undefined}><Toggle label={topics[key]} on={shown.topics[key]} disabled={busy||locked} onChange={()=>void save({topics:{...value.topics,[key]:!value.topics[key]}})}/></SetRow>;})}
  </section>
  <div className="card">
   <SetRow title="Не связываться со мной" sub="Уведомления и обращения команды будут на паузе"><Toggle label="Не связываться со мной" on={shown.no_contact} disabled={busy} onChange={()=>void save({no_contact:!value.no_contact})}/></SetRow>
   {value.effective_no_contact&&!value.no_contact&&<p className="p prof-note" role="status">Команда уже отметила твою просьбу не связываться, она продолжает действовать.</p>}
  </div>
  {!!failure&&<p className="err" role="alert">{failureText(failure)}</p>}
 </div>;
}

/** The «Подключить» flow of the canonical Telegram binding, folded into one settings row. */
function TelegramRow(){
 const cache=useQueryClient(),query=useQuery({queryKey:keys.self('telegram-binding'),queryFn:({signal})=>api<Binding>(telegramPath,{signal}),retry:false,refetchInterval:value=>value.state.data?.state==='pending'?3000:false});
 const [token,setToken]=useState<LinkToken|null>(null),issueReceipt=useRef(''),disconnectReceipt=useRef({version:-1,key:''});
 const issue=useMutation({mutationFn:async()=>{if(!issueReceipt.current)issueReceipt.current=crypto.randomUUID();const result=await api<LinkToken>(telegramPath+'/link-tokens',{method:'POST',body:{},idempotencyKey:issueReceipt.current,retries:0});issueReceipt.current='';return result;},onSuccess:async value=>{setToken(value);await cache.invalidateQueries({queryKey:keys.self('telegram-binding')});}});
 const disconnect=useMutation({mutationFn:async()=>{const version=query.data?.version??0;if(disconnectReceipt.current.version!==version||!disconnectReceipt.current.key)disconnectReceipt.current={version,key:crypto.randomUUID()};return api<Binding>(telegramPath+'/disconnect',{method:'POST',body:{expected_version:version},idempotencyKey:disconnectReceipt.current.key,retries:0});},onSuccess:value=>{setToken(null);cache.setQueryData(keys.self('telegram-binding'),value);disconnectReceipt.current={version:-1,key:''};},onError:async error=>{if(error instanceof ApiError&&error.status===409)await cache.invalidateQueries({queryKey:keys.self('telegram-binding')});}});
 const current=query.data,state=current?.state,busy=issue.isPending||disconnect.isPending;
 const showLink=state==='pending'&&token?.state==='issued'&&token.id===current?.token_id&&!!token.start_url&&new Date(token.expires_at).getTime()>Date.now();
 const sub=query.isPending?'Проверяем…':query.error?'Не удалось проверить подключение':state==='linked'?(current?.delivery_available?'Подключён':'Подключён, уведомления сюда пока не приходят'):state==='pending'?'Ждём подтверждения в боте':state==='conflict'?(current?.reason||'Нужно проверить подключение'):current?.configured?'Подключить за минуту':'Пока недоступно';
 const error=issue.error||disconnect.error;
 return <>
  <SetRow title="В Telegram" sub={sub}>
   {showLink?<a className="btn btn-primary btn-sm" href={token!.start_url!} target="_blank" rel="noopener noreferrer">Открыть бота</a>
    :state==='linked'?<Button variant="ghost" size="sm" loading={disconnect.isPending} disabled={busy} onClick={()=>disconnect.mutate()}>Отключить</Button>
    :current?.configured&&state!=='unavailable'?<Button variant="secondary" size="sm" loading={issue.isPending} disabled={busy} onClick={()=>issue.mutate()}>{state==='pending'?'Новая ссылка':'Подключить'}</Button>
    :null}
  </SetRow>
  {!!error&&<p className="err" role="alert">{error instanceof Error?error.message:'Не получилось. Попробуй ещё раз.'}</p>}
 </>;
}
