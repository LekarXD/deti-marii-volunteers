import {useState} from 'react';
import {Button,Card,Dialog,ErrorState,Textarea} from '../../ui';
import {useDobroQuery,dobroStates,type DobroTeam} from './api';
import './dobro.css';
export function DobroTeamPanel({occurrenceId}:{occurrenceId:string}){
 const query=useDobroQuery<DobroTeam>('team',`/fund/events/${occurrenceId}/dobro-team`),[reminder,setReminder]=useState(''),[copied,setCopied]=useState(false),[copyError,setCopyError]=useState(false);
 if(query.error)return <ErrorState error={query.error} retry={()=>void query.refetch()}/>;
 if(!query.data?.activity)return null;
 const view=query.data;
 return <Card className="dobro-section"><div className="dobro-split"><h3 className="h3">Добро.рф</h3><a href={view.activity!.url} target="_blank" rel="noopener noreferrer">{view.activity!.title}</a></div>{(view.people??[]).map(person=><div className="dobro-link-row" key={person.user_id}><strong>{person.display_name}</strong><div className="actions">{person.state!=='not_needed'&&<span className={`tag ${person.state==='approved'?'dobro-approved':''}`}>{person.state==='approved'?'Добро.рф ✓':dobroStates[person.state]}</span>}{person.state==='none'&&<Button variant="ghost" size="sm" onClick={()=>{setReminder(person.reminder_text);setCopied(false);setCopyError(false);}}>Напомнить</Button>}</div></div>)}<Dialog open={!!reminder} onClose={()=>setReminder('')} title="Напомнить про Добро.рф" footer={<><Button onClick={()=>{void navigator.clipboard.writeText(reminder).then(()=>{setCopied(true);setCopyError(false);}).catch(()=>setCopyError(true));}}>{copied?'Текст скопирован':'Скопировать текст'}</Button><Button variant="ghost" onClick={()=>setReminder('')}>Закрыть</Button></>}><p>Проверьте текст и отправьте его человеку привычным способом. Опора сама его не отправляет.</p><Textarea aria-label="Текст напоминания" value={reminder} onChange={e=>{setReminder(e.target.value);setCopied(false);}} rows={6}/>{copyError&&<p className="err" role="alert">Не удалось скопировать. Выделите текст и скопируйте вручную.</p>}</Dialog></Card>;
}
