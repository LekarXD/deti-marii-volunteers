import {useState} from 'react';
import {Button, Card, Combobox, Dialog, Field, Textarea, LoadingState, ErrorState} from '../../ui';
import {CandidateRequest, useCommand, useRequests} from './api';
const kindLabels={question:'Вопрос координатору',alternate_time:'Другое время встречи',road_help:'Помощь с дорогой'};
const states:Record<string,string>={open:'Ждёт ответа',answered:'Координатор ответил',resolved:'Вопрос решён'};
export function RequestHistory({items}:{items:CandidateRequest[]}) {return <div className="ap-request-list">{items.map(item=><article className="ap-request" key={item.id}><div className="ap-row"><strong>{kindLabels[item.kind as keyof typeof kindLabels]||item.kind}</strong><span className="ap-tag">{states[item.state]}</span></div><p>{item.text}</p>{item.responses.map(reply=><div className="ap-public-reply" key={reply.id}><small>Ответ координатора · {new Date(reply.created_at).toLocaleDateString('ru')}</small><p>{reply.text}</p></div>)}</article>)}</div>;}
export function CandidateRequestsPanel() {
  const requests=useRequests(), send=useCommand<CandidateRequest>('/api/v1/me/candidate-requests');
  const [open,setOpen]=useState(false),[kind,setKind]=useState('question'),[text,setText]=useState('');
  return <section className="ap-section"><div className="ap-section-head"><h2>Связь с координатором</h2><Button variant="secondary" onClick={()=>setOpen(true)}>Задать вопрос</Button></div>
    {requests.isPending?<LoadingState/>:requests.error?<ErrorState error={requests.error} retry={()=>void requests.refetch()}/>:requests.data?.length?<Card><RequestHistory items={requests.data}/></Card>:<p className="ap-muted">Можно задать вопрос, попросить другое время или помощь с дорогой. Ответ останется здесь.</p>}
    <Dialog open={open} onClose={()=>!send.isPending&&setOpen(false)} title="Написать координатору" footer={<><Button disabled={!text.trim()||send.isPending} onClick={()=>{void send.mutateAsync({body:{kind,text}}).then(()=>{setText('');setOpen(false);}).catch(()=>{});}}>{send.isPending?'Передаём…':'Передать координатору'}</Button><Button variant="ghost" onClick={()=>setOpen(false)} disabled={send.isPending}>Отмена</Button></>}>
      <Combobox label="О чём хотите написать" value={kind} onChange={setKind} options={Object.entries(kindLabels).map(([value,label])=>({value,label}))}/><Field label="Ваше сообщение" htmlFor="candidate-request"><Textarea id="candidate-request" value={text} onChange={e=>setText(e.target.value)} maxLength={4000}/></Field>{send.error&&<p role="alert" className="ap-error">{send.error.message}</p>}
    </Dialog>
  </section>;
}
export function CoordinatorRequest({request}:{request:CandidateRequest}) {
  const [reply,setReply]=useState('');
  const respond=useCommand<CandidateRequest>(`/api/v1/coord/candidate-requests/${request.id}/respond`),resolve=useCommand<CandidateRequest>(`/api/v1/coord/candidate-requests/${request.id}/resolve`);
  return <Card><RequestHistory items={[request]}/>{request.state!=='resolved'&&<><Field label="Ответ кандидату" htmlFor={'reply-'+request.id} hint="Этот ответ будет виден в личном кабинете кандидата."><Textarea id={'reply-'+request.id} value={reply} onChange={e=>setReply(e.target.value)} maxLength={4000}/></Field><div className="ap-actions"><Button disabled={!reply.trim()||respond.isPending||resolve.isPending} onClick={()=>void respond.mutateAsync({body:{text:reply,expected_version:request.version}}).then(()=>setReply('')).catch(()=>{})}>Ответить</Button><Button variant="ghost" disabled={respond.isPending||resolve.isPending} onClick={()=>resolve.mutate({body:{expected_version:request.version}})}>Отметить решённым</Button></div></>}{(respond.error||resolve.error)&&<p className="ap-error" role="alert">{(respond.error||resolve.error)?.message}</p>}</Card>;
}
