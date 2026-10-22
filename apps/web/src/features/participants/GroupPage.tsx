import {useEffect,useId,useRef,useState,type KeyboardEvent as ReactKeyboardEvent,type RefObject} from 'react';
import {createPortal} from 'react-dom';
import {Link,useSearchParams} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {appPath} from '../../basePath';
import {EmptyState, ErrorState, Icon, LoadingState} from '../../ui';
import {readPreparation} from '../followups/api';
import {isFirstExit,leadContact,useOwnHours,whenLong} from '../followups/volunteerApi';
import {firstNameOf,nameWords} from '../../ui/names';
import {readAssignmentBriefing, type Participant} from './api';
import './group.css';

const tints=['ph-a','ph-b2','ph-c','ph-d'],mateTints=['ph-a','ph-d','ph-c','ph-b2'];
const tagsOf=(value:string)=>value.split(/[,;\n]+/).map(item=>item.trim()).filter(Boolean);
const moscowYear=(now:Date)=>Number(new Intl.DateTimeFormat('en-US',{year:'numeric',timeZone:'Europe/Moscow'}).format(now));
/** «Саша, 14»: this year in Moscow minus the birth year; the name alone when the year is unknown. */
/** A volunteer sees a child's first name only, never the surname (a numbered placeholder keeps its number). */
export function kidName(displayName:string){const words=nameWords(displayName);if(!words.length)return displayName;return words.length>1&&/^\d+$/.test(words[1])?`${words[0]} ${words[1]}`:words[0];}
export function nameLine(person:Pick<Participant,'display_name'|'birth_year'>,now=new Date()){
  const age=person.birth_year?moscowYear(now)-person.birth_year:null;
  const name=kidName(person.display_name);
  return age!==null&&age>0&&age<100?`${name}, ${age}`:name;
}

/** The server rechecks current P09 ownership and confirmed assignment on every read. */
export function GroupPage() {
  const [params]=useSearchParams(),[selected,setSelected]=useState('');
  const assignment=params.get('assignment_id')??'';
  const people=useQuery({queryKey:keys.detail('assignment-group-briefing',assignment),queryFn:({signal})=>readAssignmentBriefing(assignment,signal),enabled:!!assignment,retry:false,staleTime:0,refetchInterval:15000});
  const preparation=useQuery({queryKey:keys.detail('assignment-preparation',assignment),queryFn:({signal})=>readPreparation(assignment,signal),enabled:!!assignment,staleTime:0});
  const hours=useOwnHours();
  const cards=useRef(new Map<string,HTMLButtonElement>());
  if(!assignment)return <EmptyState title="Откройте памятку из своего назначения" description="Здесь будут участники конкретного занятия после проверки доступа."/>;
  if(people.isPending)return <LoadingState/>;
  if(people.error)return <ErrorState error={people.error} retry={()=>people.refetch()}/>;
  const kids=people.data.items,prep=preparation.data;
  const index=kids.findIndex(person=>person.id===selected);
  const title=people.data.groups.map(group=>group.title).join(', ')||prep?.title||'';
  const lead=leadContact(prep?.contacts);
  const contacts=prep?.contacts??[];
  const close=()=>{const id=selected;setSelected('');requestAnimationFrame(()=>cards.current.get(id)?.focus());};
  return <div className="group-page">
    <Link className="back" to={`/my/assignments/${assignment}/preparation`}><Icon name="chevron-left"/>{isFirstExit(hours.data,assignment)?'Первый выход':'Ближайшее занятие'}</Link>
    <div className="page-head"><h1 className="h1">Кто будет на занятии</h1></div>
    {title&&<section className="card-hero"><div className="hero-grid"><div className="hero-copy">
      <p className="eyebrow">Твоя группа</p>
      <h2 className="hero-title">{title}</h2>
      {prep&&<p className="hero-sub">{[whenLong(prep.starts_at,prep.timezone),prep.location.trim()].filter(Boolean).join(', ')}</p>}
      {lead&&<div className="actions"><Link className="btn btn-primary btn-lg" to="/messages">Написать ведущему</Link></div>}
    </div><span className="hero-art" aria-hidden="true"><Icon name="users"/></span></div></section>}

    <section className="sec" aria-labelledby="group-kids">
      <div className="sec-head"><h2 className="h2" id="group-kids">Ребята</h2></div>
      {kids.length?<div className="kids">{kids.map((person,n)=><button type="button" className="kid-card" key={person.id} aria-haspopup="dialog" ref={node=>{if(node)cards.current.set(person.id,node);else cards.current.delete(person.id);}} onClick={()=>setSelected(person.id)}>
        <KidPhoto person={person} assignmentId={assignment} tint={tints[n%tints.length]}/>
        <span className="kid-name">{nameLine(person)}</span>
        {(person.about||person.interests)&&<span className="kid-about">{person.about||person.interests}</span>}
      </button>)}</div>:<div className="card-soft group-empty"><p className="p">Состав занятия уточняется</p></div>}
    </section>

    {contacts.length>0&&<section className="sec" aria-labelledby="group-mates">
      <div className="sec-head"><h2 className="h2" id="group-mates">Коллеги в команде</h2></div>
      <div className="mates">{contacts.map((contact,n)=><div className="mate" key={`${contact.role}-${n}`}>
        <span className={`photo ${mateTints[n%mateTints.length]}`} aria-hidden="true"><Silhouette/></span>
        <div className="grow"><b>{firstNameOf(contact.display_name)||contact.display_name}</b><span className="meta">{contact.role}</span><Link className="btn btn-secondary btn-sm" to="/messages">Написать</Link></div>
      </div>)}</div>
    </section>}

    {index>=0&&<KidProfile person={kids[index]} assignmentId={assignment} tint={tints[index%tints.length]} many={kids.length>1} onClose={close}
      onPrev={()=>setSelected(kids[(index+kids.length-1)%kids.length].id)} onNext={()=>setSelected(kids[(index+1)%kids.length].id)}/>}
  </div>;
}

function KidPhoto({person,assignmentId,tint,alt=''}:{person:Participant;assignmentId:string;tint:string;alt?:string}){
  return person.photo_asset_id
    ?<span className="photo has-img"><img src={appPath(`/api/v1/me/assignments/${assignmentId}/participants/${person.id}/photo`)} alt={alt}/></span>
    :<span className={`photo ${tint}`} aria-hidden="true"><Silhouette/></span>;
}
/** The canvas stand-in for a photo, used for kids and colleagues without one. */
const Silhouette=()=><svg viewBox="0 0 24 24"><circle cx="12" cy="9" r="4.2"/><path d="M3.5 24a8.5 8.5 0 0 1 17 0"/></svg>;

const focusable='a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
/** Modal lifecycle for the profile overlay: lock the page, focus inside, trap Tab, close on Escape. */
function useDialog(ref:RefObject<HTMLDivElement>,first:RefObject<HTMLButtonElement>,onClose:()=>void){
  const close=useRef(onClose);close.current=onClose;
  useEffect(()=>{
    const overflow=document.body.style.overflow;document.body.style.overflow='hidden';
    first.current?.focus();
    const keep=(event:FocusEvent)=>{if(ref.current&&!ref.current.contains(event.target as Node))first.current?.focus();};
    document.addEventListener('focusin',keep);
    return()=>{document.body.style.overflow=overflow;document.removeEventListener('focusin',keep);};
  },[ref,first]);
  return (event:ReactKeyboardEvent)=>{
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close.current();return;}
    if(event.key!=='Tab'||!ref.current)return;
    const items=Array.from(ref.current.querySelectorAll<HTMLElement>(focusable));const head=items[0],tail=items.at(-1);
    if(event.shiftKey&&document.activeElement===head){event.preventDefault();tail?.focus();}
    else if(!event.shiftKey&&document.activeElement===tail){event.preventDefault();head?.focus();}
  };
}

function KidProfile({person,assignmentId,tint,many,onClose,onPrev,onNext}:{person:Participant;assignmentId:string;tint:string;many:boolean;onClose:()=>void;onPrev:()=>void;onNext:()=>void}){
  const id=useId(),ref=useRef<HTMLDivElement>(null),closeRef=useRef<HTMLButtonElement>(null);
  const onKeyDown=useDialog(ref,closeRef,onClose);
  const tags=tagsOf(person.interests);
  return createPortal(<div className="dm group-pf pf-back" onMouseDown={event=>{if(event.target===event.currentTarget)onClose();}}>
    <div className="pf" ref={ref} role="dialog" aria-modal="true" aria-labelledby={`${id}-name`} onKeyDown={onKeyDown}>
      <button type="button" className="pf-close" aria-label="Закрыть" ref={closeRef} onClick={onClose}><Icon name="x"/></button>
      <KidPhoto person={person} assignmentId={assignmentId} tint={tint} alt={kidName(person.display_name)}/>
      <div className="pf-body">
        <h2 id={`${id}-name`}>{nameLine(person)}</h2>
        {person.about&&<p className="p pf-about">{person.about}</p>}
        {tags.length>0&&<div className="chips" aria-label="Интересы">{tags.map(tag=><span className="tag" key={tag}>{tag}</span>)}</div>}
        {person.communication&&<div className="pf-block"><b>Как общаться</b><p>{person.communication}</p></div>}
        {person.support&&<div className="pf-block"><b>Как поддержать</b><p>{person.support}</p></div>}
        {many&&<div className="pf-nav"><button type="button" className="btn btn-ghost" onClick={onPrev}>Предыдущий</button><button type="button" className="btn btn-secondary" onClick={onNext}>Следующий</button></div>}
      </div>
    </div>
  </div>,document.body);
}
