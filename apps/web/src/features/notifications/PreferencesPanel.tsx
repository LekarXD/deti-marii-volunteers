import {useRef,useState,type FormEvent} from 'react';
import {Link} from 'react-router-dom';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {ApiError} from '../../api/transport';
import {Button,Card,ErrorState,Field,Input,LoadingState,TimePicker,useToast,normalizeTime} from '../../ui';
import {minuteTime,readPreferences,savePreferences,timeMinute,topics,type Preferences} from './api';
import './notifications.css';

export function PreferencesPanel(){
 const value=useQuery({queryKey:keys.self('notification-preferences'),queryFn:({signal})=>readPreferences(signal),staleTime:0});
 if(value.isPending)return <LoadingState label="Загружаем настройки уведомлений…"/>;
 if(value.error)return <ErrorState error={value.error} retry={()=>value.refetch()}/>;
 return <PreferencesEditor key={value.data.version} value={value.data}/>;
}
function PreferencesEditor({value}:{value:Preferences}){
 const client=useQueryClient(),{toast}=useToast();
 const [email,setEmail]=useState(value.email_enabled),[inApp,setInApp]=useState(value.in_app_enabled),[noContact,setNoContact]=useState(value.no_contact),[selected,setSelected]=useState(value.topics),[quiet,setQuiet]=useState(value.quiet_enabled),[from,setFrom]=useState(minuteTime(value.quiet_from)),[to,setTo]=useState(minuteTime(value.quiet_to)),[timezone,setTimezone]=useState(value.timezone),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null);
 const form=useRef<HTMLFormElement>(null);
 const receipt=useRef({payload:'',key:''});
 async function save(event:FormEvent){
  event.preventDefault();const start=normalizeTime(from),end=normalizeTime(to);if(quiet&&(!start||!end)){form.current?.querySelector<HTMLElement>('[aria-invalid="true"],input:invalid')?.focus();return;}setBusy(true);setError(null);
  const body={expected_version:value.version,no_contact:noContact,email_enabled:email,in_app_enabled:inApp,topics:selected,quiet_enabled:quiet,quiet_from:timeMinute(start??minuteTime(value.quiet_from)),quiet_to:timeMinute(end??minuteTime(value.quiet_to)),timezone};
  const payload=JSON.stringify(body);if(receipt.current.payload!==payload)receipt.current={payload,key:crypto.randomUUID()};
  try{const updated=await savePreferences(body,receipt.current.key);client.setQueryData(keys.self('notification-preferences'),updated);toast('Настройки уведомлений сохранены');}
  catch(e){setError(e);if(e instanceof ApiError&&e.status===409){toast('Настройки изменились в другой сессии. Загружена текущая версия.','info');await client.invalidateQueries({queryKey:keys.self('notification-preferences')});}}
  finally{setBusy(false);}
 }
 return <Card className="notification-preferences"><form ref={form} onSubmit={save}>
  <h2 className="h3">Куда присылать</h2><div className="notification-channels" role="group" aria-label="Каналы уведомлений"><Button variant={inApp?'accent':'secondary'} aria-pressed={inApp} onClick={()=>setInApp(v=>!v)}>В личном кабинете</Button><Button variant={email?'accent':'secondary'} aria-pressed={email} onClick={()=>setEmail(v=>!v)}>Электронная почта</Button></div>
  {value.email_provider_state!=='available'&&<p className="meta notification-hint">{value.email_provider_state==='development_only'?'Почта работает только в локальном режиме. Внешние письма пока не отправляются.':'Отправка писем пока недоступна. Предпочтение можно сохранить.'}</p>}
  <hr className="notification-divider"/><h2 className="h3">О чём</h2>
  {Object.entries(topics).map(([key,label])=><div className="notification-setrow" key={key}><span><b>{label}</b>{key==='news'&&!value.news_consent&&<span className="notification-consent">Сначала нужно <Link to="/profile?tab=privacy#profile-consents">согласие на новости</Link>.</span>}</span><Switch label={label} checked={selected[key as keyof typeof selected]} disabled={key==='news'&&!value.news_consent} onChange={()=>setSelected(old=>({...old,[key]:!old[key as keyof typeof old]}))}/></div>)}
  <hr className="notification-divider"/><div className="notification-setrow"><span><b>Тихие часы</b><span className="notification-consent">Уведомления дождутся окончания этого периода.</span></span><Switch label="Тихие часы" checked={quiet} onChange={()=>setQuiet(v=>!v)}/></div>
  {quiet&&<div className="notification-quiet"><TimePicker onDraftChange={setFrom} label="Начало тихих часов" value={from} onChange={setFrom}/><TimePicker onDraftChange={setTo} label="Конец тихих часов" value={to} onChange={setTo}/><Field label="Часовой пояс" hint="Например, Europe/Moscow или Asia/Yekaterinburg."><Input value={timezone} onChange={e=>setTimezone(e.target.value)} maxLength={80} required/></Field></div>}
  <hr className="notification-divider"/><div className="notification-setrow"><span><b>Не связываться со мной</b><span className="notification-consent">Приостановить уведомления и обращения команды.</span></span><Switch label="Не связываться со мной" checked={noContact} onChange={()=>setNoContact(v=>!v)}/></div>
  {value.effective_no_contact&&!value.no_contact&&<p className="notification-notice" role="status">Команда уже зафиксировала просьбу не связываться. Этот запрет продолжит действовать после сохранения настроек.</p>}
  {error?<ErrorState error={error}/>:null}<div className="notification-actions"><Button type="submit" loading={busy} disabled={!timezone.trim()}>Сохранить настройки</Button></div>
 </form></Card>;
}
function Switch({label,checked,onChange,disabled=false}:{label:string;checked:boolean;onChange:()=>void;disabled?:boolean}){return <button type="button" role="switch" aria-label={label} aria-checked={checked} disabled={disabled} className={`notification-switch${checked?' is-on':''}`} onClick={onChange}><span/></button>;}
