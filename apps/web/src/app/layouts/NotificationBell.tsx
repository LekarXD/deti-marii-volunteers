import {useEffect,useRef,useState} from 'react';
import {Link,useLocation} from 'react-router-dom';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import {Icon,cx,type IconName} from '../../ui';

export type Inbox=components['schemas']['InboxView'];
type Kind=components['schemas']['InboxItem']['kind'];
const POLL=60_000;
const SHOWN=8;
const ZONE='Europe/Moscow';
/** Icon and its tint per kind: a status is an icon, never a word. */
const looks:Record<Kind,[IconName,string]>={
 invitation:['calendar','y'],place_confirmed:['check','g'],occurrence_cancelled:['x','off'],question_answered:['message','b'],
 reflection_review:['sparkle','v'],prize_issued:['award','y'],prize_rejected:['award','off'],gratitude:['heart','p'],
};
const part=(value:Date,options:Intl.DateTimeFormatOptions)=>new Intl.DateTimeFormat('ru-RU',{timeZone:ZONE,...options}).format(value);
const dayOf=(value:Date)=>part(value,{year:'numeric',month:'2-digit',day:'2-digit'});
/** «сегодня, 14:00», «вчера» or «12 октября» (with the year when it is not this one), Moscow time. */
export function relativeDate(stamp:string,now=new Date()){
 const at=new Date(stamp);
 if(dayOf(at)===dayOf(now))return `сегодня, ${part(at,{hour:'2-digit',minute:'2-digit'})}`;
 if(dayOf(at)===dayOf(new Date(now.getTime()-86_400_000)))return 'вчера';
 return part(at,part(at,{year:'numeric'})===part(now,{year:'numeric'})?{day:'numeric',month:'long'}:{day:'numeric',month:'long',year:'numeric'}).replace(/\s*г\.$/,'');
}
const inboxKey=()=>keys.self('notifications-inbox');

/** The bell left of the account button: what changed for the volunteer since they last looked. */
export function NotificationBell(){
 const client=useQueryClient();const {pathname}=useLocation();const [open,setOpen]=useState(false);const [fresh,setFresh]=useState(0);
 const root=useRef<HTMLDivElement>(null);const trigger=useRef<HTMLButtonElement>(null);
 const inbox=useQuery({queryKey:inboxKey(),queryFn:({signal})=>api<Inbox>('/me/notifications',{signal}),refetchInterval:POLL,refetchIntervalInBackground:false});
 const seen=useMutation({mutationFn:(at:string)=>api<Inbox>('/me/notifications/seen',{method:'POST',body:{at}}),onSuccess:value=>client.setQueryData(inboxKey(),value)});
 useEffect(()=>setOpen(false),[pathname]);
 useEffect(()=>{const outside=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))setOpen(false);};document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside);},[]);
 const items=inbox.data?.items??[];const unread=inbox.data?.unread??0;
 const toggle=()=>{
  if(open){setOpen(false);return;}
  setOpen(true);setFresh(unread);
  // Seen up to the newest item shown, so anything that arrives meanwhile stays new.
  if(unread>0&&items[0]){client.setQueryData<Inbox>(inboxKey(),value=>value&&{...value,unread:0});seen.mutate(items[0].at);}
 };
 return <div className="bell" ref={root} onKeyDown={event=>{if(event.key==='Escape'&&open){event.preventDefault();setOpen(false);trigger.current?.focus();}}}>
  <button ref={trigger} type="button" className="bellbtn" aria-label={unread>0?'Уведомления, есть новые':'Уведомления'} aria-expanded={open} aria-controls="opora-bell-panel" onClick={toggle}><Icon name="bell"/>{unread>0&&<span className="pip" aria-hidden="true"/>}</button>
  {open&&<section className="bell-panel" id="opora-bell-panel" aria-labelledby="opora-bell-title">
   <h2 className="bell-title" id="opora-bell-title">Уведомления</h2>
   {inbox.isPending?<p className="bell-empty">Загружаем…</p>:inbox.isError&&!inbox.data?<p className="bell-empty">Не получилось загрузить. Попробуй чуть позже.</p>:items.length===0?<p className="bell-empty">Всё прочитано</p>:
   <ul className="bell-list">{items.slice(0,SHOWN).map((item,index)=>{const [icon,tone]=looks[item.kind]??['bell','off'];return <li key={item.key}><Link className={cx('bell-row',index<fresh&&'is-new')} to={item.href} onClick={()=>setOpen(false)}>
    <span className={`bell-ic bell-ic-${tone}`} aria-hidden="true"><Icon name={icon}/></span>
    <span className="bell-body"><b className="bell-row-title">{item.title}</b>{item.text&&<span className="bell-row-text">{item.text}</span>}<time className="bell-row-when" dateTime={item.at}>{relativeDate(item.at)}</time></span>
    {index<fresh&&<><span className="bell-new" aria-hidden="true"/><span className="sr-only">, новое</span></>}
   </Link></li>;})}</ul>}
  </section>}
 </div>;
}
