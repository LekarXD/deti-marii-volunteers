import {useRef,useState,type FormEvent} from 'react';
import {useInfiniteQuery,useQueryClient} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {ApiError} from '../../api/transport';
import {Button,Card,EmptyState,ErrorState,Field,Input,LoadingState} from '../../ui';
import {channelLabel,command,dateTime,readRecipients,type Audience,type Enqueued,type Readiness,type Template} from './api';
const reasons:Record<string,string>={user_unavailable:'Аккаунт недоступен',no_contact:'Просьба не связываться',email_disabled:'Почта выключена',in_app_disabled:'Уведомления в кабинете выключены',topic_disabled:'Эта тема выключена',news_consent_missing:'Нет согласия на новости',provider_unavailable:'Провайдер недоступен',verified_email_missing:'Нет подтверждённой почты',newsletter_consent_missing:'Нет согласия на новости'};

/** A preview is a server snapshot. A separate human action consumes that exact snapshot. */
export function AudiencePanel({template,readiness}:{template:Template;readiness:Readiness}){
 const client=useQueryClient();const [query,setQuery]=useState(''),[search,setSearch]=useState(''),[selected,setSelected]=useState<Record<string,string>>({}),[preview,setPreview]=useState<Audience|null>(null),[confirmed,setConfirmed]=useState(false),[result,setResult]=useState<Enqueued|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null);
 const sendKey=useRef('');
 const recipients=useInfiniteQuery({queryKey:keys.list('notification-recipients',{q:search}),queryFn:({pageParam,signal})=>readRecipients(search,pageParam,signal),initialPageParam:null as string|null,getNextPageParam:last=>last.next_cursor??undefined,staleTime:0});
 const count=Object.keys(selected).length;
 const available=template.channel==='in_app'?readiness.channels.some(c=>c.channel==='in_app'&&c.state==='available'):readiness.external_send_enabled;
 function reset(){setPreview(null);setConfirmed(false);setResult(null);setError(null);sendKey.current='';}
 function toggle(id:string,name:string){reset();setSelected(old=>{const next={...old};if(next[id])delete next[id];else next[id]=name;return next;});}
 async function inspect(){setBusy(true);setError(null);setConfirmed(false);setPreview(null);try{const value=await command<Audience>('/coord/notifications/audience-preview',{template_version_id:template.published_version_id,recipient_user_ids:Object.keys(selected)});setPreview(value);sendKey.current=crypto.randomUUID();}catch(e){setError(e);}finally{setBusy(false);}}
 async function send(){
  if(!preview||!confirmed||!available||busy)return;
  if(new Date(preview.expires_at).getTime()<=Date.now()){setPreview(null);setConfirmed(false);setError(new Error('Предпросмотр устарел. Проверьте аудиторию ещё раз.'));return;}
  setBusy(true);setError(null);
  try{const value=await command<Enqueued>('/coord/notifications/send',{preview_id:preview.id,preview_hash:preview.preview_hash,confirmed:true},'POST',sendKey.current);setResult(value);setPreview(null);setConfirmed(false);await client.invalidateQueries({queryKey:keys.all('notification-deliveries')});}
  catch(e){setError(e);if(e instanceof ApiError&&e.status===409){setPreview(null);setConfirmed(false);}}
  finally{setBusy(false);}
 }
 function find(event:FormEvent){event.preventDefault();setSearch(query.trim());}
 return <div className="notification-stack"><Card tone="soft"><p className="meta">Опубликованная версия · {channelLabel(template.channel)}</p><h3 className="h3">{template.subject}</h3><p className="notification-body">{template.body}</p><p className="meta">Поля имени волонтёра и фонда подставятся для каждого получателя.</p></Card>
 {!available&&<p className="notification-notice" role="status">{template.channel==='email'?'Внешняя отправка писем пока недоступна. Можно проверить аудиторию и сохранить шаблон.':'Этот канал сейчас недоступен.'}</p>}
 {result?<Card tone="hero"><h3 className="h3">Поставлено в очередь: {result.enqueued}</h3><p>Доставку можно проверить в журнале уведомлений.</p><Button variant="secondary" onClick={()=>{reset();setSelected({});}}>Подготовить новое уведомление</Button></Card>:<>
 <section aria-label="Выбор получателей"><h3 className="h3">Кому отправить</h3><form className="notification-search" onSubmit={find}><Field label="Найти волонтёра"><Input value={query} onChange={e=>setQuery(e.target.value)} maxLength={100} placeholder="Имя"/></Field><Button variant="secondary" type="submit">Найти</Button></form>
 {count>0&&<div className="notification-selection"><p className="meta">Выбрано {count} из 500</p><div className="notification-channels">{Object.entries(selected).map(([id,name])=><Button key={id} variant="subtle" size="sm" disabled={busy} aria-label={`Убрать ${name}`} onClick={()=>toggle(id,name)}>{name} ×</Button>)}</div></div>}
 {recipients.isPending?<LoadingState/>:recipients.error?<ErrorState error={recipients.error} retry={()=>recipients.refetch()}/>:recipients.data.pages[0].items.length?<><div className="notification-recipients">{recipients.data.pages.flatMap(p=>p.items).map(person=><label className="notification-person" key={person.id}><input type="checkbox" checked={!!selected[person.id]} disabled={busy||(!selected[person.id]&&count>=500)} onChange={()=>toggle(person.id,person.display_name)}/><span>{person.display_name}</span></label>)}</div>{recipients.hasNextPage&&<Button variant="ghost" loading={recipients.isFetchingNextPage} onClick={()=>recipients.fetchNextPage()}>Ещё волонтёры</Button>}</>:<EmptyState title="Никого не нашли" description="Попробуйте другое имя."/>}
 <div className="notification-actions"><Button variant="secondary" disabled={!count||busy} loading={busy&&!preview} onClick={inspect}>Проверить аудиторию</Button></div></section>
 {preview&&<section className="notification-preview" aria-label="Проверенная аудитория"><h3 className="h3">Получат уведомление: {preview.eligible_count}</h3><p className="meta">Предпросмотр действует до {dateTime(preview.expires_at)}. Перед отправкой доступ и предпочтения проверяются снова.</p><ul className="notification-members">{preview.members.map(member=><li key={member.user_id}><span>{member.display_name}</span><span className={member.eligible?'notification-eligible':'meta'}>{member.eligible?'Включён':reasons[member.reason??'']??'Исключён текущими правилами'}</span></li>)}</ul><label className="notification-person notification-confirm"><input type="checkbox" checked={confirmed} disabled={busy||!available||!preview.eligible_count} onChange={e=>setConfirmed(e.target.checked)}/><span>Проверил текст и аудиторию. Подтверждаю отправку {preview.eligible_count} получателям.</span></label><Button onClick={send} loading={busy} disabled={!confirmed||!preview.eligible_count||!available}>Подтвердить и поставить в очередь</Button></section>}
 </>}{error?<ErrorState error={error}/>:null}</div>;
}
