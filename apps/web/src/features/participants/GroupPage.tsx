import {useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {Button, Card, EmptyState, ErrorState, LoadingState} from '../../ui';
import {readAssignmentBriefing} from './api';
import {ParticipantAvatar, ParticipantSafeCard} from './ParticipantsPage';
/** The server rechecks current P09 ownership and confirmed assignment on every read. */
export function GroupPage() {
  const [params]=useSearchParams(),[selected,setSelected]=useState('');
  const assignment=params.get('assignment_id')??'';
  const people=useQuery({queryKey:keys.detail('assignment-group-briefing',assignment),queryFn:({signal})=>readAssignmentBriefing(assignment,signal),enabled:!!assignment,retry:false,staleTime:0,refetchInterval:15000});
  if(!assignment)return <EmptyState title="Откройте памятку из своего назначения" description="Здесь будут участники конкретного занятия после проверки доступа."/>;
  if(people.isPending)return <LoadingState/>;
  if(people.error)return <ErrorState error={people.error} retry={()=>people.refetch()}/>;
  const person=people.data.items.find(p=>p.id===selected);
  return <><div className="head"><h1 className="h1">Кто будет на занятии</h1>{person&&<Button variant="ghost" onClick={()=>setSelected('')}>К группе</Button>}</div>{people.data.groups.length>0 && <Card tone="hero"><p className="eyebrow">Твоя группа</p><h2 className="hero-title">{people.data.groups.map(group=>group.title).join(', ')}</h2><p className="lead">Практическая памятка к подтверждённому занятию.</p></Card>}{person?<ParticipantSafeCard person={person} assignmentId={assignment}/>:people.data.items.length?<div className="participants-grid participant-section">{people.data.items.map(p=><button className="card participant-row" key={p.id} onClick={()=>setSelected(p.id)}><ParticipantAvatar person={p} assignmentId={assignment}/><span className="participant-copy"><span className="h3">{p.display_name}</span><p>{p.about}</p></span><span aria-hidden="true">→</span></button>)}</div>:<EmptyState title="Состав занятия уточняется"/>}</>;
}
