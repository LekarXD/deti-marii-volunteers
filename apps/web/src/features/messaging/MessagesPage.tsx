import {appResourceUrl} from '../../basePath';
import {useEffect,useLayoutEffect,useMemo,useRef,useState,useSyncExternalStore} from 'react';
import {Link} from 'react-router-dom';
import {useInfiniteQuery,useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {getPrincipalKey,initializeSession,onSessionChange} from '../../api/transport';
import {Button,Card,Dialog,EmptyState,ErrorState,Field,Icon,Input,LoadingState,cx} from '../../ui';
import * as chat from './api';
import './messages.css';

const zone='Europe/Moscow';
const initials=(name:string)=>name.split(/\s+/).slice(0,2).map(x=>x[0]).join('').toLocaleUpperCase('ru');
const time=(stamp:string)=>new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:zone}).format(new Date(stamp));
const day=(stamp:string)=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',timeZone:zone}).format(new Date(stamp));
const dateKey=(date:Date)=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:zone}).format(date);
/** «Сегодня», «Вчера» or the date: Moscow has no DST, so yesterday is exactly 24 hours back. */
const relative=(stamp:string)=>{const key=dateKey(new Date(stamp));const now=Date.now();return key===dateKey(new Date(now))?'today':key===dateKey(new Date(now-864e5))?'yesterday':'earlier';};
const dayLabel=(stamp:string)=>({today:'Сегодня',yesterday:'Вчера',earlier:day(stamp)})[relative(stamp)];
const rowTime=(stamp:string)=>({today:time(stamp),yesterday:'вчера',earlier:new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short',timeZone:zone}).format(new Date(stamp))})[relative(stamp)];
const assetLabel=(asset:chat.Message['assets'][number])=>asset.content_type==='application/pdf'?'Документ PDF':'Изображение';
const tones=['av-y','av-g','av-b','av-o','av-v','av-p'];
const tone=(id:string|null)=>tones[[...(id??'')].reduce((sum,ch)=>sum+ch.charCodeAt(0),0)%tones.length];
const subtitle=(c:chat.Conversation)=>c.kind==='group'?`Участников: ${c.members.length}`:c.kind==='system'?'Канал фонда':'';
const poll=(ms:number)=>()=>typeof document==='undefined'||document.visibilityState==='visible'?ms:false;
/** A message group breaks on another author, another day or a pause longer than this. */
const groupGap=10*60*1000;
type PendingFile={id:string;name:string;image:boolean};
type PendingSend={id:string;body:chat.SendBody;key:string;principal:string};
type Block={kind:'day';key:string;label:string}|{kind:'group';key:string;author:string|null;name:string;mine:boolean;messages:chat.Message[]};

/** Above the phone breakpoint of messages.css both panes are on screen at once. */
const wideMedia=()=>typeof window!=='undefined'&&window.matchMedia?window.matchMedia('(min-width: 721px)'):null;
const subscribeWide=(change:()=>void)=>{const media=wideMedia();media?.addEventListener('change',change);return()=>media?.removeEventListener('change',change);};
function useWide(){return useSyncExternalStore(subscribeWide,()=>wideMedia()?.matches??true,()=>true);}
function Avatar({conversation}:{conversation:chat.Conversation}){return conversation.kind==='direct'?<span className="avatar messaging-avatar av-b" aria-hidden="true">{initials(conversation.title)}</span>:<span className={`art messaging-avatar ${conversation.kind==='system'?'art-b':'art-o'}`} aria-hidden="true"><Icon name={conversation.kind==='system'?'bell':'users'}/></span>;}

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
 const client=useQueryClient();const wide=useWide();const [selected,setSelected]=useState<string|null>(null);const [creating,setCreating]=useState(false);const [pane,setPane]=useState<'list'|'chat'>('list');const [query,setQuery]=useState('');
 const [draft,setDraft]=useState('');const [files,setFiles]=useState<PendingFile[]>([]);const [privacy,setPrivacy]=useState(false);const [uploading,setUploading]=useState(false);const [uploadError,setUploadError]=useState<string|null>(null);const [failed,setFailed]=useState<PendingSend|null>(null);const [atBottom,setAtBottom]=useState(true);const [visible,setVisible]=useState(document.visibilityState==='visible');
 const drafts=useRef(new Map<string,{text:string;files:PendingFile[];failed:PendingSend|null}>());
 const fileInput=useRef<HTMLInputElement>(null);const editor=useRef<HTMLTextAreaElement>(null);const controller=useRef<AbortController|null>(null);const log=useRef<HTMLDivElement>(null);const bottom=useRef<HTMLDivElement>(null);const lastRead=useRef<{id:string;seq:number}|null>(null);
 const listKey=keys.all('messaging-conversations');
 const list=useInfiniteQuery({queryKey:listKey,initialPageParam:null as string|null,queryFn:({pageParam,signal})=>chat.conversations(pageParam,signal),getNextPageParam:last=>last.next_cursor??undefined,maxPages:5,refetchInterval:poll(7000),refetchIntervalInBackground:false});
 const allConversations=list.data?.pages.flatMap(page=>page.items)??[];
 const needle=query.trim().toLocaleLowerCase('ru');
 const shown=needle?allConversations.filter(c=>c.title.toLocaleLowerCase('ru').includes(needle)):allConversations;
 const active=allConversations.find(c=>c.id===selected)??(selected===null?allConversations[0]:undefined);
 const activeId=active?.id;
 const reading=wide||pane==='chat';
 const messageKey=keys.detail('messaging-messages',activeId??'none');
 const history=useInfiniteQuery({queryKey:messageKey,initialPageParam:undefined as number|undefined,queryFn:({pageParam,signal})=>chat.messages(activeId!,pageParam,signal),getNextPageParam:last=>last.next_before_seq??undefined,enabled:!!activeId,maxPages:5,refetchInterval:poll(3000),refetchIntervalInBackground:false});
 const items=useMemo(()=>{const map=new Map<string,chat.Message>();history.data?.pages.forEach(p=>p.items.forEach(m=>map.set(m.id,m)));return [...map.values()].sort((a,b)=>a.seq-b.seq);},[history.data]);
 const blocks=useMemo(()=>{const out:Block[]=[];let previous:chat.Message|null=null;for(const message of items){const label=dayLabel(message.created_at);if(!previous||label!==dayLabel(previous.created_at))out.push({kind:'day',key:`day-${message.id}`,label});const group=out.at(-1);if(group?.kind==='group'&&group.author===message.author_user_id&&previous&&Date.parse(message.created_at)-Date.parse(previous.created_at)<groupGap)group.messages.push(message);else out.push({kind:'group',key:message.id,author:message.author_user_id,name:message.author_name,mine:message.author_user_id===userId,messages:[message]});previous=message;}return out;},[items,userId]);
 const latest=items.at(-1)?.seq??0;
 const read=useMutation({mutationFn:({id,seq}:{id:string;seq:number})=>chat.markRead(id,seq),onSuccess:()=>void client.invalidateQueries({queryKey:listKey})});
 const send=useMutation({mutationFn:(pending:PendingSend)=>chat.send(pending.id,pending.body,pending.key),onSuccess:(_value,pending)=>{if(pending.principal!==getPrincipalKey())return;setDraft('');setFiles([]);setPrivacy(false);setFailed(null);void client.invalidateQueries({queryKey:messageKey});void client.invalidateQueries({queryKey:listKey});setAtBottom(true);},onError:(_error,pending)=>{if(pending.principal===getPrincipalKey())setFailed(pending);}});
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{const update=()=>setVisible(document.visibilityState==='visible');document.addEventListener('visibilitychange',update);return()=>document.removeEventListener('visibilitychange',update);},[]);
 useEffect(()=>onSessionChange(()=>{controller.current?.abort();drafts.current.clear();setDraft('');setFiles([]);setPrivacy(false);setFailed(null);setSelected(null);setCreating(false);setPane('list');}),[]);
 useEffect(()=>{setAtBottom(true);lastRead.current=null;},[activeId]);
 useEffect(()=>{if(atBottom)bottom.current?.scrollIntoView?.({block:'nearest'});},[latest,activeId,atBottom,pane]);
 useEffect(()=>{if(!activeId||!latest||!atBottom||!visible||!reading||(lastRead.current?.id===activeId&&lastRead.current.seq>=latest))return;lastRead.current={id:activeId,seq:latest};read.mutate({id:activeId,seq:latest});},[activeId,latest,atBottom,visible,reading]);
 useLayoutEffect(()=>{const node=editor.current;if(!node)return;node.style.height='auto';node.style.height=`${Math.min(node.scrollHeight,200)}px`;},[draft,activeId]);
 const choose=(id:string)=>{if(send.isPending)return;setPane('chat');if(id===activeId)return;if(activeId)drafts.current.set(activeId,{text:draft,files,failed});controller.current?.abort();setUploading(false);const saved=drafts.current.get(id);setDraft(saved?.text??'');setFiles(saved?.files??[]);setPrivacy(false);setFailed(saved?.failed??null);setUploadError(null);setSelected(id);};
 async function attach(file:File){controller.current?.abort();const abort=new AbortController();controller.current=abort;setUploading(true);setUploadError(null);try{const id=await chat.upload(file,abort.signal);if(!abort.signal.aborted)setFiles(old=>[...old,{id,name:file.name,image:file.type.startsWith('image/')}]);}catch(error){if(!abort.signal.aborted)setUploadError(error instanceof Error?error.message:'Не удалось загрузить файл');}finally{if(controller.current===abort)setUploading(false);}}
 const images=files.some(f=>f.image);
 const ready=(!!draft.trim()||files.length>0)&&!uploading&&(!images||privacy);
 function submit(){if(!activeId||send.isPending||uploading)return;if(!failed&&!ready)return;const pending=failed??{id:activeId,body:{text:draft,asset_ids:files.map(f=>f.id),photo_policy:images?'no_people':'not_applicable'},key:crypto.randomUUID(),principal:getPrincipalKey()};send.mutate(pending);}
 const preview=(c:chat.Conversation)=>{const last=c.last_message;if(!last)return 'Пока нет сообщений';return `${last.author_user_id===userId?'Ты: ':''}${last.text||(last.assets[0]?assetLabel(last.assets[0]):'')}`;};
 return <section className="messaging" data-pane={pane} aria-label="Сообщения">
  <aside className="messaging-side">
   <div className="messaging-side-head"><h1 className="messaging-title">Сообщения</h1><button type="button" className="iconbtn messaging-new" aria-label="Написать сообщение" title="Написать сообщение" disabled={send.isPending} onClick={()=>setCreating(true)}><Icon name="plus"/></button></div>
   <div className="messaging-search"><Icon name="search"/><label className="sr-only" htmlFor="messaging-search">Найти диалог</label><input id="messaging-search" className="messaging-search-input" type="search" autoComplete="off" placeholder="Поиск" value={query} maxLength={200} onChange={e=>setQuery(e.target.value)}/></div>
   <nav className="messaging-dialogs" aria-label="Диалоги">{list.isPending?<LoadingState/>:list.isError?<ErrorState error={list.error} retry={()=>void list.refetch()}/>:<>
    {shown.map(conversation=><button type="button" className={cx('messaging-dialog',conversation.id===activeId&&'is-on',conversation.unread_count>0&&'is-unread')} aria-current={conversation.id===activeId?'true':undefined} key={conversation.id} onClick={()=>choose(conversation.id)}><Avatar conversation={conversation}/><span className="messaging-dialog-name">{conversation.title}</span>{conversation.last_message&&<time className="messaging-dialog-time" dateTime={conversation.last_message.created_at}>{rowTime(conversation.last_message.created_at)}</time>}<span className="messaging-dialog-last">{preview(conversation)}</span>{conversation.unread_count>0&&<span className="messaging-unread"><span className="sr-only">Непрочитанных: </span>{conversation.unread_count}</span>}</button>)}
    {allConversations.length===0&&<p className="messaging-no-dialogs">Пока нет диалогов. Напишите координатору, если нужна помощь.</p>}
    {allConversations.length>0&&shown.length===0&&<p className="messaging-no-dialogs">Никого не нашли</p>}
    {list.hasNextPage&&<Button variant="ghost" size="sm" loading={list.isFetchingNextPage} onClick={()=>void list.fetchNextPage()}>Ещё диалоги</Button>}
   </>}</nav>
  </aside>
  <div className="messaging-main">{!active?<EmptyState title="Выберите диалог" description="Здесь будут сообщения команды фонда и координатора."/>:<>
   <header className="messaging-chat-head"><button type="button" className="iconbtn messaging-back" aria-label="К диалогам" onClick={()=>setPane('list')}><Icon name="chevron-left"/></button><Avatar conversation={active}/><div className="messaging-chat-title"><h2 className="messaging-chat-name" id="messaging-title">{active.title}</h2>{subtitle(active)&&<p className="messaging-chat-sub">{subtitle(active)}</p>}</div></header>
   <div ref={log} className="messaging-log" role="log" aria-labelledby="messaging-title" aria-live="polite" aria-relevant="additions" onScroll={()=>{const node=log.current;if(node)setAtBottom(node.scrollHeight-node.scrollTop-node.clientHeight<100);}}>
    <div className="messaging-thread">
     {history.hasNextPage&&<Button className="messaging-more" variant="ghost" size="sm" loading={history.isFetchingNextPage} onClick={()=>{setAtBottom(false);void history.fetchNextPage();}}>Предыдущие сообщения</Button>}
     {history.isPending?<LoadingState label="Загружаем историю…"/>:history.isError?<ErrorState error={history.error} retry={()=>void history.refetch()}/>:items.length===0?<p className="messaging-empty">В диалоге пока нет сообщений. Можно написать первым.</p>:blocks.map(block=>block.kind==='day'?<div key={block.key} className="messaging-date">{block.label}</div>:<div key={block.key} className={cx('messaging-group',block.mine&&'is-mine')}>
      {active.kind==='group'&&!block.mine&&<span className={`avatar avatar-sm messaging-group-avatar ${tone(block.author)}`} aria-hidden="true">{initials(block.name)}</span>}
      <div className="messaging-stack">{active.kind==='group'&&!block.mine&&<p className="messaging-author" aria-hidden="true">{block.name}</p>}{block.messages.map((message,index)=>{const tail=index===block.messages.length-1;return <div key={message.id} className={cx('messaging-bubble',tail&&'is-tail')}><span className="sr-only">{block.mine?'Вы':message.author_name}, {time(message.created_at)}: </span>{message.assets.map(asset=><a key={asset.id} className="messaging-attachment" href={appResourceUrl(asset.content_url)} target="_blank" rel="noreferrer"><span className={`art ${asset.content_type==='application/pdf'?'art-b':'art-y'}`} aria-hidden="true"><Icon name={asset.content_type==='application/pdf'?'file':'image'}/></span><span><span className="messaging-attachment-name">{assetLabel(asset)}</span><span className="messaging-attachment-size">{Math.ceil(asset.size/1024)} КБ</span></span></a>)}{message.text}{tail&&<time className="messaging-time" dateTime={message.created_at} aria-hidden="true">{time(message.created_at)}</time>}</div>;})}</div>
     </div>)}
     <div ref={bottom}/>
    </div>
   </div>
   <div className="messaging-composer">{active.allowed_actions.includes('send')?<div className="messaging-composer-in">
    {files.length>0&&<ul className="messaging-files" aria-label="Вложения">{files.map(file=><li key={file.id} className="messaging-file"><span className={`art ${file.image?'art-y':'art-b'}`} aria-hidden="true"><Icon name={file.image?'image':'file'}/></span><span className="messaging-file-name">{file.name}</span><button type="button" className="iconbtn" aria-label={`Убрать ${file.name}`} disabled={send.isPending||!!failed} onClick={()=>setFiles(old=>old.filter(f=>f.id!==file.id))}><Icon name="x"/></button></li>)}</ul>}
    {images&&<div className="messaging-privacy" role="alert"><h3 className="h3">Фото людей в чат не отправляем</h3><p className="p">Фото детей нельзя публиковать даже в команде. Размывание лиц пока недоступно.</p><label className="check"><input type="checkbox" checked={privacy} disabled={!!failed} onChange={e=>setPrivacy(e.target.checked)}/>Подтверждаю, что на изображениях нет людей</label><Button variant="ghost" size="sm" disabled={!!failed} onClick={()=>{setFiles(old=>old.filter(f=>!f.image));setPrivacy(false);}}>Не отправлять изображения</Button></div>}
    {uploading&&<p className="messaging-status" role="status">Загружаем файл…</p>}
    {uploadError&&<p className="err" role="alert">{uploadError}</p>}
    {read.isError&&<ErrorState error={read.error} retry={()=>activeId&&read.mutate({id:activeId,seq:latest})}/>}
    {send.error&&<div className="messaging-failed" role="alert"><p className="err">{send.error.message}</p>{failed&&<Button variant="secondary" size="sm" loading={send.isPending} onClick={submit}>Проверить отправку</Button>}</div>}
    <div className="messaging-box">
     <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp,application/pdf" hidden onChange={e=>{const file=e.target.files?.[0];if(file)void attach(file);e.target.value='';}}/>
     <button type="button" className="iconbtn" aria-label="Прикрепить файл" title="Фото или PDF" disabled={uploading||send.isPending||!!failed||files.length>=10} onClick={()=>fileInput.current?.click()}><Icon name="clip"/></button>
     <label className="sr-only" htmlFor="messaging-input">Сообщение</label>
     <textarea ref={editor} id="messaging-input" className="messaging-input" rows={1} maxLength={8000} value={draft} disabled={send.isPending||!!failed} placeholder="Сообщение" enterKeyHint="send" onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing&&(wide||e.ctrlKey||e.metaKey)){e.preventDefault();submit();}}}/>
     <button type="button" className="messaging-send" aria-label="Отправить" title="Отправить" aria-busy={send.isPending||undefined} disabled={!ready||send.isPending||!!failed} onClick={submit}><Icon name="send"/></button>
    </div>
   </div>:<div className="messaging-readonly"><span>Канал фонда, ответить здесь нельзя</span><Button variant="secondary" onClick={()=>setCreating(true)}>Написать координатору</Button></div>}</div>
  </>}</div>
  <NewConversation open={creating} onClose={()=>setCreating(false)} canGroup={canGroup} onCreated={id=>{choose(id);void client.invalidateQueries({queryKey:listKey});}}/>
 </section>;
}
export default MessagesPage;
