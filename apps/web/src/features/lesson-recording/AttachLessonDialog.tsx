import {useState,type FormEvent} from 'react';
import {Button,Combobox,Dialog,ErrorState} from '../../ui';
import {useAuthorTracks} from '../learning/authorApi';
import {useRecordingCommand,type RecordingProject} from './api';
import {lessonChoices} from './model';
import './recording.css';
/** Chooses the lesson a recording is meant for: the same versioned project edit as the project settings. */
export function AttachLessonDialog({project,onClose}:{project:RecordingProject|null;onClose:()=>void}) {
 return <Dialog open={!!project} onClose={onClose} title="Добавить в курс">{project&&<AttachForm key={project.id} project={project} onDone={onClose}/>}</Dialog>;
}
function AttachForm({project,onDone}:{project:RecordingProject;onDone:()=>void}) {
 const tracks=useAuthorTracks(),command=useRecordingCommand<RecordingProject>(),[lesson,setLesson]=useState('');
 async function save(event:FormEvent){event.preventDefault();try{await command.mutateAsync({path:`/recording-projects/${project.id}`,method:'PATCH',body:{expected_version:project.version,target_lesson_id:lesson}});onDone();}catch{/* command error is visible in the form */}}
 return <form className="recording-form" onSubmit={save}><p className="p">{project.title}</p><Combobox label="Урок" value={lesson} onChange={setLesson} disabled={tracks.isPending} options={lessonChoices(tracks.data)}/>{tracks.error&&<p className="meta">Не удалось загрузить уроки. Попробуйте позже.</p>}<p className="meta">Видео попадёт в урок после проверки записи.</p>{command.error&&<ErrorState error={command.error}/>}<Button type="submit" loading={command.isPending} disabled={!lesson}>Добавить</Button></form>;
}
