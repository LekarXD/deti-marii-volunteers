import {appResourceUrl} from '../../basePath';
import {useEffect,useMemo,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {useInfiniteQuery,useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {getPrincipalKey,initializeSession,onSessionChange} from '../../api/transport';
import {Button,Card,Dialog,EmptyState,ErrorState,Field,Input,LoadingState,Textarea} from '../../ui';
import * as chat from './api';
import './messages.css';

const initials=(name:string)=>name.split(/\s+/).slice(0,2).map(x=>x[0]).join('').toLocaleUpperCase('ru');
const time=(stamp:string)=>new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/Moscow'}).format(new Date(stamp));
const day=(stamp:string)=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',timeZone:'Europe/Moscow'}).format(new Date(stamp));
const poll=(ms:number)=>()=>typeof document==='undefined'||document.visibilityState==='visible'?ms:false;
const label=(kind:chat.Conversation['kind'])=>kind==='group'?'Групповой диалог':kind==='system'?'Канал фонда, только чтение':'Личный диалог';
type PendingFile={id:string;name:string;image:boolean};
type PendingSend={id:string;body:chat.SendBody;key:string;principal:string};

function Glyph({kind='send'}:{kind?:'send'|'attach'|'group'|'bell'}){return <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">{kind==='send'?<path d="M21 3 10 14M21 3l-7 18-4-7-7-4z"/>:kind==='attach'?<><rect x="3" y="3.5" width="18" height="17" rx="3"/><circle cx="9" cy="9" r="1.8"/><path d="m21 15-5-5-9 10"/></>:kind==='bell'?<><path d="M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 21a2 2 0 0 0 4 0"/></>:<><path d="M12 3a9 9 0 0 0 0 18c1.2 0 1.8-.8 1.8-1.8 0-.5-.2-.9-.5-1.3-.3-.3-.5-.8-.5-1.2 0-1 .8-1.7 1.8-1.7H17a4 4 0 0 0 4-4C21 6.5 17 3 12 3z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7" r="1"/></>}</svg>;}
function Avatar({conversation}:{conversation:chat.Conversation}){return conversation.kind==='direct'?<span className="avatar av-b" aria-hidden="true">{initials(conversation.title)}</span>:<span className={`art art-sm ${conversation.kind==='system'?'art-b':'art-o'}`}><Glyph kind={conversation.kind==='system'?'bell':'group'}/></span>;}

function NewConversation({open,onClose,onCreated,canGroup}:{open:boolean;onClose:()=>void;onCreated:(id:string)=>void;canGroup:boolean}){
 const requestKey=useRef(crypto.randomUUID());
 const [search,setSearch]=useState('');const [selected,setSelected]=useState<string[]>([]);const [isGroup,setGroup]=useState(false);const [title,setTitle]=useState('');
 const people=useQuery({queryKey:keys.list('messaging-contacts',{search}),queryFn:({signal})=>chat.contacts(search,signal),enabled:open});
 const create=useMutation({mutationFn:()=>isGroup?chat.group(title,selected,requestKey.current):chat.direct(selected[0],requestKey.current),onSuccess:value=>{onCreated(value.id);onClose();setSelected([]);setTitle('');requestKey.current=crypto.randomUUID();}});
 return <Dialog open={open} onClose={onClose} title={isGroup?'Новый групповой диалог':'Написать сообщение'} footer={<Button loading={create.isPending} disabled={!selected.length||(isGroup&&!title.trim())} onClick={()=>create.mutate()}>Открыть диалог</Button>}>
  {canGroup&&<label className="check"><input type="checkbox" checked={isGroup} onChange={e=>{setGroup(e.target.checked);setSelected([]);requestKey.current=crypto.randomUUID();}}/>Групповой диалог</label>}
  {isGroup&&<Field label="Название"><Input value={title} maxLength={200} onChange={e=>{setTitle(e.target.value);requestKey.current=crypto.randomUUID();}}/></Field>}
  <Field label="Найти собеседника"><Input value={search} maxLength={200} onChange={e=>setSearch(e.target.value)} placeholder="Имя"/></Field>
  {people.isPending?<LoadingState/>:people.isError?<ErrorState error={people.error} retry={()=>void people.refetch()}/>:<div className="messaging-contact-list" role="group" aria-label="Собеседники">{people.data?.items.map(person=><label className="messaging-contact" key={person.user_id}><input type={isGroup?'checkbox':'radio'} name="recipient" checked={selected.includes(person.user_id)} onChange={()=>{requestKey.current=crypto.randomUUID();setSelected(old=>isGroup?old.includes(person.user_id)?old.filter(id=>id!==person.user_id):[...old,person.user_id]:[person.user_id]);}}/><span className="avatar avatar-sm av-y" aria-hidden="true">{initials(person.display_name)}</span><span><b>{person.display_name}</b>{person.is_coordinator&&<small>Координатор</small>}</span></label>)}{people.data?.items.length===0&&<p className="meta">Не нашли собеседника. Попробуйте другое имя.</p>}{people.data?.next_cursor&&<p className="meta">Уточните имя, чтобы найти остальных собеседников.</p>}</div>}
  {create.error&&<p className="err" role="alert">{create.error.message}</p>}
 </Dialog>;
}

export function MessagesPage(){
 const session=useQuery({queryKey:keys.session(),queryFn:()=>initializeSession(),staleTime:Infinity});
 if(session.isPending)return <LoadingState label="Открываем сообщения…"/>;
 if(session.isError)return <ErrorState error={session.error} retry={()=>void session.refetch()}/>;
 if(!session.data.user_id)return <Card><EmptyState title="Подтвердите почту" description="После подтверждения почты здесь появятся диалоги с координатором и командой фонда." action={<Link className="btn btn-primary" to="/login?next=%2Fmessages">Войти в Опору</Link>}/></Card>;
 return <Messages key={getPrincipalKey()} userId={session.data.user_id} canGroup={session.data.permissions.includes('messaging.manage')}/>;
}
function Messages({userId,canGroup}:{userId:string;canGroup:boolean}){
 const client=useQueryClient();const [selected,setSelected]=useState<string|null>(null);const [creating,setCreating]=useState(false);
 const [draft,setDraft]=useState('');const [files,setFiles]=useState<PendingFile[]>([]);const [privacy,setPrivacy]=useState(false);const [uploading,setUploading]=useState(false);const [uploadError,setUploadError]=useState<string|null>(null);const [failed,setFailed]=useState<PendingSend|null>(null);const [atBottom,setAtBottom]=useState(true);const [visible,setVisible]=useState(document.visibilityState==='visible');
 const drafts=useRef(new Map<string,{text:string;files:PendingFile[];privacy:boolean;failed:PendingSend|null}>());
 const fileInput=useRef<HTMLInputElement>(null);const controller=useRef<AbortController|null>(null);const log=useRef<HTMLDivElement>(null);const bottom=useRef<HTMLDivElement>(null);const lastRead=useRef<{id:string;seq:number}|null>(null);
 const listKey=keys.all('messaging-conversations');
 const list=useInfiniteQuery({queryKey:listKey,initialPageParam:null as string|null,queryFn:({pageParam,signal})=>chat.conversations(pageParam,signal),getNextPageParam:last=>last.next_cursor??undefined,maxPages:5,refetchInterval:poll(7000),refetchIntervalInBackground:false});
 const allConversations=list.data?.pages.flatMap(page=>page.items)??[];
 const active=allConversations.find(c=>c.id===selected)??(selected===null?allConversations[0]:undefined);
 const activeId=active?.id;
 const messageKey=keys.detail('messaging-messages',activeId??'none');
 const history=useInfiniteQuery({queryKey:messageKey,initialPageParam:undefined as number|undefined,queryFn:({pageParam,signal})=>chat.messages(activeId!,pageParam,signal),getNextPageParam:last=>last.next_before_seq??undefined,enabled:!!activeId,maxPages:5,refetchInterval:poll(3000),refetchIntervalInBackground:false});
 const items=useMemo(()=>{const map=new Map<string,chat.Message>();history.data?.pages.forEach(p=>p.items.forEach(m=>map.set(m.id,m)));return [...map.values()].sort((a,b)=>a.seq-b.seq);},[history.data]);
 const latest=items.at(-1)?.seq??0;
 const read=useMutation({mutationFn:({id,seq}:{id:string;seq:number})=>chat.markRead(id,seq),onSuccess:()=>void client.invalidateQueries({queryKey:listKey})});
 const send=useMutation({mutationFn:(pending:PendingSend)=>chat.send(pending.id,pending.body,pending.key),onSuccess:(_value,pending)=>{if(pending.principal!==getPrincipalKey())return;setDraft('');setFiles([]);setPrivacy(false);setFailed(null);void client.invalidateQueries({queryKey:messageKey});void client.invalidateQueries({queryKey:listKey});setAtBottom(true);},onError:(_error,pending)=>{if(pending.principal===getPrincipalKey())setFailed(pending);}});
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{const update=()=>setVisible(document.visibilityState==='visible');document.addEventListener('visibilitychange',update);return()=>document.removeEventListener('visibilitychange',update);},[]);
 useEffect(()=>onSessionChange(()=>{controller.current?.abort();drafts.current.clear();setDraft('');setFiles([]);setFailed(null);setSelected(null);setCreating(false);}),[]);
 useEffect(()=>{setAtBottom(true);lastRead.current=null;},[activeId]);
 useEffect(()=>{if(atBottom)bottom.current?.scrollIntoView?.({block:'nearest'});},[latest,activeId,atBottom]);
 useEffect(()=>{if(!activeId||!latest||!atBottom||!visible||(lastRead.current?.id===activeId&&lastRead.current.seq>=latest))return;lastRead.current={id:activeId,seq:latest};read.mutate({id:activeId,seq:latest});},[activeId,latest,atBottom,visible]);
 const choose=(id:string)=>{if(send.isPending)return;if(activeId)drafts.current.set(activeId,{text:draft,files,privacy,failed});controller.current?.abort();setUploading(false);const saved=drafts.current.get(id);setDraft(saved?.text??'');setFiles(saved?.files??[]);setPrivacy(saved?.privacy??false);setFailed(saved?.failed??null);setUploadError(null);setSelected(id);};
 async function attach(file:File){controller.current?.abort();const abort=new AbortController();controller.current=abort;setUploading(true);setUploadError(null);try{const id=await chat.upload(file,abort.signal);if(!abort.signal.aborted)setFiles(old=>[...old,{id,name:file.name,image:file.type.startsWith('image/')}]);}catch(error){if(!abort.signal.aborted)setUploadError(error instanceof Error?error.message:'Не удалось загрузить файл');}finally{if(controller.current===abort)setUploading(false);}}
 function submit(){if(!activeId||send.isPending||uploading)return;const pending=failed??{id:activeId,body:{text:draft,asset_ids:files.map(f=>f.id),photo_policy:files.some(f=>f.image)?'no_people':'not_applicable'},key:crypto.randomUUID(),principal:getPrincipalKey()};send.mutate(pending);}
 return <section className="messaging"><div className="head"><h1 className="h1">Сообщения</h1><Button variant="secondary" disabled={send.isPending} onClick={()=>setCreating(true)}>Написать сообщение</Button></div>
  <div className="messaging-layout">
   <nav className="card messaging-dialogs" aria-label="Диалоги">{list.isPending?<LoadingState/>:list.isError?<ErrorState error={list.error} retry={()=>void list.refetch()}/>:<>{allConversations.map(conversation=><button type="button" className={`messaging-dialog ${conversation.id===activeId?'is-on':''}`} aria-current={conversation.id===activeId?'true':undefined} key={conversation.id} onClick={()=>choose(conversation.id)}><Avatar conversation={conversation}/><span className="messaging-dialog-name">{conversation.title}<small>{label(conversation.kind)}</small></span>{conversation.unread_count>0&&<span className="messaging-unread" aria-label={`${conversation.unread_count} непрочитанных`}>{conversation.unread_count}</span>}</button>)}{allConversations.length===0&&<p className="meta messaging-no-dialogs">Пока нет диалогов. Напишите координатору, если нужна помощь.</p>}{list.hasNextPage&&<Button variant="ghost" size="sm" loading={list.isFetchingNextPage} onClick={()=>void list.fetchNextPage()}>Ещё диалоги</Button>}</>}</nav>
   <div className="stack messaging-main">
    <aside className="ai-box messaging-summary"><div className="row"><h2 className="h3">Пока тебя не было</h2><span className="ai-tag">ИИ</span></div><p className="meta">Краткое содержание переписки пока недоступно. Все сообщения сохранены в диалогах.</p></aside>
    {!active?<Card><EmptyState title="Выберите диалог" description="Здесь будут сообщения команды фонда и координатора."/></Card>:<section className="card messaging-chat" aria-labelledby="messaging-title"><header className="messaging-chat-head"><Avatar conversation={active}/><div className="grow"><h2 className="h3" id="messaging-title">{active.title}</h2><p className="meta">{label(active.kind)}</p></div><div className="messaging-team" aria-label="Участники диалога">{active.members.slice(0,4).map((member,i)=><span key={member.user_id} className={`avatar avatar-sm ${['av-y','av-g','av-b','av-o'][i]}`} title={member.display_name}>{initials(member.display_name)}</span>)}</div></header>
     <div ref={log} className="messaging-log" role="log" aria-label="История сообщений" aria-live="polite" aria-relevant="additions" onScroll={()=>{const node=log.current;if(node)setAtBottom(node.scrollHeight-node.scrollTop-node.clientHeight<100);}}>
      {history.hasNextPage&&<Button className="messaging-more" variant="ghost" size="sm" loading={history.isFetchingNextPage} onClick={()=>{setAtBottom(false);void history.fetchNextPage();}}>Предыдущие сообщения</Button>}
      {history.isPending?<LoadingState label="Загружаем историю…"/>:history.isError?<ErrorState error={history.error} retry={()=>void history.refetch()}/>:items.length===0?<p className="meta">В диалоге пока нет сообщений. Можно написать первым.</p>:items.map((message,index)=><div key={message.id}>{(index===0||day(message.created_at)!==day(items[index-1].created_at))&&<div className="messaging-date"><span>{day(message.created_at)}</span></div>}<article className={`messaging-message ${message.author_user_id===userId?'is-mine':''}`}>{message.author_user_id!==userId&&<span className="avatar avatar-sm av-y" aria-hidden="true">{initials(message.author_name)}</span>}<div className="messaging-message-body"><div className="messaging-message-meta">{message.author_user_id!==userId&&<b>{message.author_name}</b>}<time dateTime={message.created_at}>{time(message.created_at)}</time></div>{message.text&&<p className="bubble">{message.text}</p>}{message.assets.map(asset=><a key={asset.id} className="messaging-attachment" href={appResourceUrl(asset.content_url)} target="_blank" rel="noreferrer"><Glyph kind="attach"/><span>{asset.content_type==='application/pdf'?'Документ PDF':'Изображение'}<small>{Math.ceil(asset.size/1024)} КБ, открыть файл</small></span></a>)}</div></article></div>)}<div ref={bottom}/>
     </div>
     {active.allowed_actions.includes('send')?<div className="messaging-composer">{files.length>0&&<ul className="messaging-files">{files.map(file=><li key={file.id}><span>{file.name}</span><button type="button" className="iconbtn" aria-label={`Убрать ${file.name}`} disabled={send.isPending||!!failed} onClick={()=>setFiles(old=>old.filter(f=>f.id!==file.id))}>×</button></li>)}</ul>}
      {files.some(f=>f.image)&&<div className="messaging-privacy" role="alert"><h3 className="h3">Фото людей в чат не отправляем</h3><p className="p">Фото детей нельзя публиковать даже в команде. Размывание лиц пока недоступно.</p><label className="check"><input type="checkbox" checked={privacy} disabled={!!failed} onChange={e=>setPrivacy(e.target.checked)}/>Подтверждаю, что на изображениях нет людей</label><Button variant="ghost" size="sm" disabled={!!failed} onClick={()=>{setFiles(old=>old.filter(f=>!f.image));setPrivacy(false);}}>Не отправлять изображения</Button></div>}
      <div className="messaging-composer-row"><input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp,application/pdf" hidden onChange={e=>{const file=e.target.files?.[0];if(file)void attach(file);e.target.value='';}}/><button type="button" className="iconbtn" aria-label="Прикрепить файл" disabled={uploading||send.isPending||!!failed||files.length>=10} onClick={()=>fileInput.current?.click()}><Glyph kind="attach"/></button><label className="sr" htmlFor="messaging-input">Сообщение</label><Textarea id="messaging-input" rows={1} maxLength={8000} value={draft} disabled={send.isPending||!!failed} placeholder={active.kind==='direct'?`Написать: ${active.title}`:'Написать в чат'} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();submit();}}}/><Button disabled={(!draft.trim()&&!files.length)||uploading||(files.some(f=>f.image)&&!privacy)} loading={send.isPending} onClick={submit}><Glyph/>{failed?'Проверить отправку':'Отправить'}</Button></div>
      {read.isError&&<ErrorState error={read.error} retry={()=>activeId&&read.mutate({id:activeId,seq:latest})}/>}{uploading&&<p className="meta" role="status">Проверяем и загружаем файл…</p>}{uploadError&&<p className="err" role="alert">{uploadError}</p>}{send.error&&<p className="err" role="alert">{send.error.message} Повторная проверка использует тот же ключ и не создаст второе сообщение.</p>}<p className="messaging-delivery meta">Сообщения сохраняются в Опоре. Внешняя доставка не подключена.</p>
     </div>:<footer className="messaging-readonly"><span>Канал фонда, только чтение</span><Button variant="subtle" size="sm" onClick={()=>setCreating(true)}>Написать координатору</Button></footer>}
    </section>}
   </div>
  </div><NewConversation open={creating} onClose={()=>setCreating(false)} canGroup={canGroup} onCreated={id=>{choose(id);void client.invalidateQueries({queryKey:listKey});}}/>
 </section>;
}
export default MessagesPage;
