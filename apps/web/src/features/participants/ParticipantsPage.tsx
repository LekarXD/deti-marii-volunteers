import {useEffect, useState, type ReactNode} from 'react';
import {Link, useSearchParams} from 'react-router-dom';
import {keepPreviousData, useQuery} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {wardsTabs} from '../../app/sectionTabs';
import {Button, ErrorState, Icon, LoadingState, PageSection, SectionTabs, Segmented, cx} from '../../ui';
import {readParticipants, type Participant} from './api';
import {MemoCards, WardPhoto, ageLabel, initials, wardLine, wardPhotoUrl} from './wards';
import './participants.css';

/** Small photo or initials; also used by the volunteer group page and the groups page. */
export function ParticipantAvatar({person, large=false, assignmentId}: {person: Pick<Participant,'id'|'display_name'|'photo_asset_id'>;large?:boolean;assignmentId?:string}) {
  const cls=cx('participant-avatar',large&&'participant-avatar-large');
  const url=wardPhotoUrl(person,assignmentId);
  return url ? <img className={cls} src={url} alt={person.display_name}/> : <span className={cls} aria-hidden="true">{initials(person.display_name)}</span>;
}
/** The safe memo a volunteer sees: the hero and «Как помочь на занятии», never private notes. */
export function ParticipantSafeCard({person, assignmentId, actions}: {person:Participant;assignmentId?:string;actions?:ReactNode}) {
  const age=ageLabel(person.birth_year);
  return <>
    <section className="card-hero ward-hero"><div className="hero-grid">
      <div className="hero-copy"><p className="eyebrow">Знакомство</p><h2 className="hero-title">{person.display_name}</h2>{age&&<p className="ward-hero-line">{age}</p>}<p className="lead">{person.about || 'Информация о знакомстве пока не добавлена.'}</p>{actions&&<div className="actions">{actions}</div>}</div>
      <WardPhoto person={person} size="xl" alt={person.display_name} assignmentId={assignmentId}/>
    </div></section>
    <PageSection title="Как помочь на занятии" className="ward-section"><MemoCards person={person}/></PageSection>
  </>;
}

const PAGE=100;
export function ParticipantsPage() {
  const [params,setParams]=useSearchParams();
  const archived=params.get('archived')==='1',offset=Number(params.get('offset'))||0;
  const [text,setText]=useState(params.get('q')??''),query=params.get('q')??'';
  const set=(changes:Record<string,string>)=>setParams(current=>{const next=new URLSearchParams(current);Object.entries(changes).forEach(([key,value])=>value?next.set(key,value):next.delete(key));return next;},{replace:true});
  useEffect(()=>{if(text.trim()===query)return;const timer=setTimeout(()=>set({q:text.trim(),offset:''}),250);return()=>clearTimeout(timer);},[text]);
  const people=useQuery({queryKey:keys.list('participants',{query,archived,offset}),queryFn:({signal})=>readParticipants(query,archived,signal,offset),placeholderData:keepPreviousData});
  const items=people.data?.items??[];
  return <>
    <SectionTabs label="Подопечные" tabs={wardsTabs} actions={<Link className="btn btn-primary" to="/fund/participants/new"><Icon name="plus"/>Добавить подопечного</Link>}/>
    <div className="ward-toolbar">
      <label className="ward-search"><span className="sr-only">Найти подопечного</span><Icon name="search"/><input className="input" type="search" placeholder="Имя или группа" value={text} onChange={e=>setText(e.target.value)}/></label>
      <Segmented label="Какие карточки показать" value={archived?'archive':'active'} onChange={value=>set({archived:value==='archive'?'1':'',offset:''})} options={[{value:'active',label:'Активные'},{value:'archive',label:'Архив'}]}/>
    </div>
    {people.isPending ? <LoadingState/> : people.error ? <ErrorState error={people.error} retry={()=>void people.refetch()}/> : items.length ? <>
      <div className="grid-3">{items.map(ward=>{const line=wardLine(ward.birth_year,ward.groups);return <Link className="ward-card" key={ward.id} to={`/fund/participants/${ward.id}`}>
        <WardPhoto person={ward} size="lg"/>
        <span className="grow"><span className="h3">{ward.display_name}</span>{line&&<span className="meta">{line}</span>}</span>
        <Icon name="arrow-right"/>
      </Link>;})}</div>
      {(offset>0||items.length===PAGE)&&<div className="actions">{offset>0&&<Button variant="ghost" onClick={()=>set({offset:String(Math.max(0,offset-PAGE))})}>Предыдущие</Button>}{items.length===PAGE&&<Button variant="ghost" onClick={()=>set({offset:String(offset+PAGE)})}>Следующие</Button>}</div>}
    </> : <div className="card ward-empty">{query ? <><p className="h3">Никого не нашли</p><p className="p">Проверьте имя или посмотрите в архиве.</p></> : archived ? <p className="h3">В архиве пусто</p> : <><p className="h3">Пока нет подопечных</p><p className="p">Добавьте первую карточку, а потом включите человека в группу.</p></>}</div>}
  </>;
}
