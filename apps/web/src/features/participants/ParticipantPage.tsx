import {useState, type FormEvent} from 'react';
import {Link, useParams} from 'react-router-dom';
import {useQuery, useQueryClient} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {ApiError} from '../../api/errors';
import {getSession} from '../../api/transport';
import {Button, ErrorState, Field, Icon, LoadingState, PageSection, Textarea} from '../../ui';
import {command, readNotes, readParticipant, readParticipantSessions, type Ward, type WardSession} from './api';
import {MemoCards, WardPhoto, ageLabel, initials, toneOf} from './wards';
import './participants.css';

const SHOWN=4;
const denied=(error:unknown)=>error instanceof ApiError&&error.status===403;
const part=(date:Date,timeZone:string,options:Intl.DateTimeFormatOptions)=>new Intl.DateTimeFormat('ru-RU',{timeZone,...options}).format(date);
const firstName=(name:string)=>name.trim().split(/\s+/)[0]??name;
/** «Анна», «Анна и Тимур», «Анна, Тимур и Полина». */
export const namesLine=(names:string[])=>names.length<2?names.join(''):`${names.slice(0,-1).join(', ')} и ${names.at(-1)}`;
const heroLine=(ward:Ward)=>[ageLabel(ward.birth_year),ward.groups.length?`${ward.groups.length>1?'группы':'группа'} ${ward.groups.map(g=>g.title).join(', ')}`:''].filter(Boolean).join(', ');
const noteDate=(value:string)=>{
  const at=new Date(value),day=(d:Date)=>part(d,'Europe/Moscow',{year:'numeric',month:'2-digit',day:'2-digit'});
  if(day(at)===day(new Date()))return 'сегодня';
  return part(at,'Europe/Moscow',{day:'numeric',month:'long',...(day(at).slice(-4)!==day(new Date()).slice(-4)?{year:'numeric'}:{})});
};

/** `/fund/participants/:id`: the ward card; «Как видит волонтёр» hides everything a volunteer never gets. */
export function ParticipantPage() {
  const {id=''}=useParams();
  const [volunteer,setVolunteer]=useState(false);
  const ward=useQuery({queryKey:keys.detail('participants',id),queryFn:({signal})=>readParticipant(id,signal)});
  const permissions=getSession()?.permissions??[];
  const canSchedule=permissions.includes('schedule.read')||permissions.includes('schedule.manage');
  return <>
    <Link className="ward-back" to="/fund/participants"><Icon name="chevron-left"/>Подопечные</Link>
    {ward.isPending ? <LoadingState/> : ward.error ? <ErrorState error={ward.error} retry={()=>void ward.refetch()}/> : <>
      <section className="card-hero ward-hero" aria-labelledby="ward-name"><div className="hero-grid">
        <div className="hero-copy">
          <p className="eyebrow">{volunteer?'Так карточку видит волонтёр':'Подопечный'}</p>
          <h1 className="hero-title" id="ward-name">{ward.data.display_name}</h1>
          {heroLine(ward.data)&&<p className="ward-hero-line">{heroLine(ward.data)}</p>}
          {ward.data.about&&<p className="lead">{ward.data.about}</p>}
          <div className="actions">{volunteer
            ? <Button size="lg" onClick={()=>setVolunteer(false)}>Вернуться к карточке</Button>
            : <><Link className="btn btn-primary btn-lg" to={`/fund/participants/${id}/edit`}>Изменить карточку</Link><Button variant="secondary" size="lg" onClick={()=>setVolunteer(true)}><Icon name="eye"/>Как видит волонтёр</Button></>}</div>
        </div>
        <WardPhoto person={ward.data} size="xl" alt={`Фото: ${ward.data.display_name}`}/>
      </div></section>
      <PageSection title="Как помочь на занятии" className="ward-section"><MemoCards person={ward.data}/></PageSection>
      {canSchedule&&<WardSessions id={id}/>}
      {!volunteer&&permissions.includes('participants.private_notes')&&<WardNotes id={id}/>}
    </>}
  </>;
}

function SessionRow({item}:{item:WardSession}) {
  const start=new Date(item.starts_at),end=new Date(item.ends_at),tz=item.timezone;
  const weekday=part(start,tz,{weekday:'short'}).replace('.',''),time=(d:Date)=>part(d,tz,{hour:'2-digit',minute:'2-digit'});
  const meta=[`${weekday.charAt(0).toLocaleUpperCase('ru')}${weekday.slice(1)}, ${time(start)}–${time(end)}`,item.location].filter(Boolean).join(', ');
  return <Link className="ward-session" to={`/fund/events/${item.id}`}>
    <span className="ward-date"><b>{part(start,tz,{day:'numeric'})}</b><span>{part(start,tz,{month:'short'}).replace('.','')}</span></span>
    <span className="ward-session-copy"><span className="h3">{item.title}</span><span className="meta">{meta}</span></span>
    {item.volunteers.length ? <span className="row ward-session-team">{item.volunteers.slice(0,3).map(v=><span key={v.id} className={`avatar av-${toneOf(v.id)}`} aria-hidden="true">{initials(v.display_name)}</span>)}<span className="p">{namesLine(item.volunteers.map(v=>firstName(v.display_name)))}</span></span>
      : <span className="ward-unstaffed">Волонтёр не назначен</span>}
    <Icon name="arrow-right"/>
  </Link>;
}

function WardSessions({id}:{id:string}) {
  const [all,setAll]=useState(false);
  const sessions=useQuery({queryKey:keys.detail('participant-sessions',id),queryFn:({signal})=>readParticipantSessions(id,signal),retry:false});
  if(denied(sessions.error))return null;
  const items=sessions.data?.items??[];
  return <PageSection title="Ближайшие занятия" className="ward-section">
    {sessions.isPending ? <LoadingState/> : sessions.error ? <ErrorState error={sessions.error} retry={()=>void sessions.refetch()}/> : items.length ? <div className="ward-sessions">
      {(all?items:items.slice(0,SHOWN)).map(item=><SessionRow key={item.id} item={item}/>)}
      {items.length>SHOWN&&!all&&<button type="button" className="ward-more" onClick={()=>setAll(true)}>Показать все</button>}
    </div> : <p className="meta">Ближайших занятий пока нет.</p>}
  </PageSection>;
}

function WardNotes({id}:{id:string}) {
  const client=useQueryClient();
  const [draft,setDraft]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[all,setAll]=useState(false);
  const notes=useQuery({queryKey:keys.detail('participant-private-notes',id),queryFn:({signal})=>readNotes(id,signal),retry:false});
  if(denied(notes.error))return null;
  async function add(e:FormEvent) {
    e.preventDefault();
    if(!draft.trim())return;
    setBusy(true);setError('');
    try{await command(`/coord/participants/${id}/private-notes`,{text:draft.trim()});setDraft('');await client.invalidateQueries({queryKey:keys.detail('participant-private-notes',id)});}
    catch(e){setError(e instanceof Error?e.message:'Не удалось добавить заметку.');}
    finally{setBusy(false);}
  }
  const items=notes.data?.items??[];
  return <PageSection title={<span className="ward-lock-title"><Icon name="lock" className="ic-lg"/>Для координатора</span>} className="ward-section">
    <div className="ward-split">
      <div className="ward-main card">{notes.isPending ? <LoadingState/> : notes.error ? <ErrorState error={notes.error} retry={()=>void notes.refetch()}/> : items.length ? <>
        {(all?items:items.slice(0,SHOWN)).map(note=><div className="ward-note" key={note.id}><p className="p">{note.text}</p><span className="meta">{[note.author_name,noteDate(note.created_at)].filter(Boolean).join(', ')}</span></div>)}
        {items.length>SHOWN&&!all&&<button type="button" className="ward-more" onClick={()=>setAll(true)}>Показать все</button>}
      </> : <p className="meta">Заметок пока нет.</p>}</div>
      <form className="ward-panel" onSubmit={add}>
        <Field label="Новая заметка"><Textarea className="ward-note-input" maxLength={20000} placeholder="Что важно знать другим координаторам" value={draft} onChange={e=>setDraft(e.target.value)}/></Field>
        {error&&<p className="err" role="alert">{error}</p>}
        <div className="ward-actions-row"><Button type="submit" variant="secondary" loading={busy} disabled={!draft.trim()}>Добавить заметку</Button></div>
      </form>
    </div>
  </PageSection>;
}
