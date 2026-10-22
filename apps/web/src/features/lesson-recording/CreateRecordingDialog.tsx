import {useState,type FormEvent} from 'react';
import {useNavigate} from 'react-router-dom';
import {Button,Combobox,Dialog,ErrorState,Field,Input} from '../../ui';
import {useAuthorTracks} from '../learning/authorApi';
import {useRecordingCommand,type RecordingProject} from './api';
import {lessonChoices} from './model';
import './recording.css';
/** Creates a solo recording project, optionally for a lesson, and opens its studio. */
export function CreateRecordingDialog({open,onClose}:{open:boolean;onClose:()=>void}) {
 const tracks=useAuthorTracks(),command=useRecordingCommand<RecordingProject>(),navigate=useNavigate();
 const [title,setTitle]=useState(''),[lesson,setLesson]=useState('');
 async function create(event:FormEvent){event.preventDefault();try{const project=await command.mutateAsync({path:'/recording-projects',body:{title:title.trim(),target_lesson_id:lesson||null,mode:'solo'}});navigate(`/fund/recordings/${project.id}`);}catch{/* command error is visible in the form */}}
 return <Dialog open={open} onClose={onClose} title="Новая запись урока"><form className="recording-form" onSubmit={create}><Field label="Название записи"><Input required maxLength={300} value={title} onChange={event=>setTitle(event.target.value)} placeholder="О чём будет урок"/></Field><Combobox label="Урок в Академии" value={lesson} onChange={setLesson} disabled={tracks.isPending} options={[{value:'',label:'Сначала без урока'},...lessonChoices(tracks.data)]}/>{tracks.error&&<p className="meta">Не удалось загрузить уроки. Проект можно создать без привязки.</p>}<p className="p">Материалы и выбранный дубль остаются приватными до отдельной проверки и публикации.</p>{command.error&&<ErrorState error={command.error}/>}<Button type="submit" loading={command.isPending} disabled={!title.trim()}>Создать проект</Button></form></Dialog>;
}
