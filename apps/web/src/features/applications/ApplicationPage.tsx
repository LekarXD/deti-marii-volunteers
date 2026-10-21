import {useState} from 'react';
import {Link} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {BookOpen, CalendarDays, CheckCircle2, PenLine} from 'lucide-react';
import {Button, Card, EmptyState, ErrorState, LoadingState, Dialog, Field, Textarea} from '../../ui';
import {keys} from '../../api/keys';
import {api, ApiError} from '../../api/transport';
import type {components} from '../../api/generated/schema';
import {BookingPicker, useInterviews} from '../interviews';
import {Application, useApplication, useCommand, useDraft} from './api';
import {CandidateRequestsPanel} from './Requests';
import type {FormContent} from './form';
import './applications.css';
const reviewLabels:Record<string,string>={new:'Анкета получена',reviewing:'Координатор знакомится с анкетой',discussed:'Анкета обсуждена',paused:'Пауза по договорённости',closed:'Рассмотрение завершено'};
type Booking=components['schemas']['BookingView'];
type Preparation=components['schemas']['PreparationView'];
export function ApplicationPage() {
  const application=useApplication(), draft=useDraft(),[picker,setPicker]=useState(false),[withdrawing,setWithdrawing]=useState(false);
  const meetings=useInterviews(false);
  const preparation=useQuery({queryKey:keys.self('learning'),queryFn:({signal})=>api<Preparation>('/api/v1/me/preparation',{signal}),enabled:!!application.data,refetchInterval:15000});
  const withdraw=useCommand<Application>('/api/v1/me/application/withdraw');
  if(application.isPending)return <LoadingState/>;
  if(application.error instanceof ApiError&&application.error.status===404)return <EmptyState title="Заявки пока нет" description="Сначала заполните анкету волонтёра — её ответы попадут сюда и к координатору." action={<Link className="btn btn-primary" to="/apply">Заполнить анкету</Link>}/>;
  if(application.error||!application.data)return <ErrorState error={application.error} retry={()=>void application.refetch()}/>;
  const app=application.data,answers=app.revision.answers,form=draft.data?.form.content as unknown as FormContent|undefined;
  const booking=meetings.data?.find(item=>item.status==='booked'),completed=meetings.data?.find(item=>item.status==='completed');
  const introduction=preparation.data?.assignments[0],done=introduction?.lessons.filter(item=>item.completed).length||0,total=introduction?.lessons.length||0;
  return <div className="ap-page"><div className="ap-heading"><h1>Здравствуйте, {String(answers.firstName||'волонтёр')}!</h1><span className="ap-tag">{app.submission_state==='withdrawn'?'Анкета отозвана':reviewLabels[app.review_state]}</span></div>
    {app.submission_state==='submitted'&&<><Card tone="hero"><div className="ap-hero"><div><p className="ap-eyebrow">Следующий шаг</p><h2>{booking?new Date(booking.starts_at).toLocaleString('ru',{timeZone:'Europe/Moscow',day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'}):completed?'Встреча состоялась':'Встреча с координатором'}</h2><p>{booking?booking.venue:completed?String(completed.result?.public_agreement||''):'Познакомимся, обсудим ваши интересы и выберем, как помогать фонду.'}</p>{booking&&<p className="ap-muted">Московское время</p>}
      {meetings.isPending?<LoadingState/>:meetings.error?<ErrorState error={meetings.error} retry={()=>void meetings.refetch()}/>:<div className="ap-actions">{booking?.join_url&&<a className="btn btn-primary" href={booking.join_url} target="_blank" rel="noreferrer">Открыть встречу</a>}<Button onClick={()=>setPicker(!picker)}>{booking?'Перенести встречу':completed?'Выбрать время ещё одной встречи':'Выбрать время'}</Button>{booking&&<Link className="btn btn-ghost" to="/interviews">Управление записью</Link>}</div>}</div><CalendarDays size={92} strokeWidth={1.2}/></div></Card>
    {picker&&<section className="ap-section"><BookingPicker booking={booking} onClose={()=>setPicker(false)} onBooked={()=>{setPicker(false);void meetings.refetch();}}/></section>}
    <section className="ap-section"><h2>Знакомство с фондом</h2><Card><div className="ap-onboarding"><span className="ap-path-icon"><BookOpen size={26}/></span><div className="ap-grow"><h3>Познакомиться с фондом {preparation.data?.introduction_completed&&<CheckCircle2 size={18}/>}</h3><p>Что мы делаем, кто наши участники и как мы помогаем друг другу.</p>{preparation.isPending?<LoadingState/>:preparation.error?<ErrorState error={preparation.error} retry={()=>void preparation.refetch()}/>:<><div className="ap-progress"><span style={{width:total?`${100*done/total}%`:'0%'}}/></div><small>{done} из {total} шагов · {preparation.data?.introduction_completed?'Знакомство завершено':'Можно проходить в своём темпе'}</small></>}</div><Link className="btn btn-secondary" to="/onboarding">{preparation.data?.introduction_completed?'Открыть материалы':'Продолжить'}</Link></div></Card><p className="ap-muted">Знакомство и запись на встречу идут параллельно. Вы можете выбрать удобное время уже сейчас.</p></section></>}
    {app.history.filter(item=>item.public_message&&item.kind==='reviewed').map(item=><Card key={item.id}><p className="ap-eyebrow">Сообщение координатора</p><p>{item.public_message}</p></Card>)}
    <section className="ap-section"><details className="card ap-answers"><summary><h2>Ваши ответы</h2><PenLine size={18}/></summary>{form?.steps.map(section=><div key={section.id}><h3>{section.title}</h3><dl>{section.fields.filter(field=>answers[field.id]!==undefined).map(field=><div key={field.id}><dt>{field.label}</dt><dd>{formatAnswer(answers[field.id])}</dd></div>)}</dl></div>)}<p className="ap-muted">Согласие на новости: {app.consents.news?'Да':'Нет'}</p>{app.submission_state==='submitted'&&<Link className="btn btn-secondary" to="/application/edit">Изменить ответы</Link>}</details></section>
    <CandidateRequestsPanel/>{app.submission_state==='submitted'&&<div className="ap-section"><Button variant="ghost" onClick={()=>setWithdrawing(true)}>Отозвать анкету</Button></div>}
    <Dialog open={withdrawing} title="Отозвать анкету?" onClose={()=>!withdraw.isPending&&setWithdrawing(false)} footer={<><Button variant="danger" disabled={withdraw.isPending} onClick={()=>void withdraw.mutateAsync({body:{expected_version:app.version}}).then(()=>setWithdrawing(false)).catch(()=>{})}>Отозвать анкету</Button><Button variant="ghost" onClick={()=>setWithdrawing(false)}>Вернуться</Button></>}><p>Координатор увидит, что вы отозвали анкету. Если встреча уже назначена, отмените её отдельно в разделе встреч.</p>{withdraw.error&&<p className="ap-error" role="alert">{withdraw.error.message}</p>}</Dialog>
  </div>;
}
export function formatAnswer(value:unknown){if(Array.isArray(value))return value.join(', ');if(typeof value==='boolean')return value?'Да':'Нет';return String(value??'');}
