import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import type {StudioScene} from '../../../../../packages/studio-core';
import {Button,Card,ErrorState,LoadingState} from '../../ui';
import type {StageTrackBinding} from '../../ui/studio';
import type {StudioSession} from '../studio/api';
import {useRecordingCommand,useRecordingProject,useRecordingTakes,type RecordingProject,type RecordingTake} from './api';
import {RecordingPolicy,policyMatches} from './RecordingPolicy';
import {activeTake,recordingLimit,takeLabels} from './model';
import './recording.css';
interface Props {session:StudioSession;scene:StudioScene;tracks:readonly StageTrackBinding[];connected:boolean;onCaptureActive:(active:boolean)=>void;}
/** Operator controls reuse the already connected live room. No media client lives here. */
export function LiveRecordingControls(props:Props) {
 if(!props.session.can_host||props.session.resource_kind!=='live_event')return null;
 return <HostRecording key={props.session.id} {...props}/>;
}
function HostRecording(props:Props) {
 const {session,scene}=props,command=useRecordingCommand<RecordingProject>(),[projectId,setProjectId]=useState<string>(),project=useRecordingProject(projectId);
 const closed=['closing','closed','failed'].includes(session.state);
 return <section className="section" aria-labelledby="live-recording-title"><Card><h2 className="h2" id="live-recording-title">Запись занятия</h2><p className="p">В запись входят только согласованные источники ведущего и материалы в кадре. Участники и чат остаются за пределами записи.</p>
 {!projectId?<Button variant="secondary" loading={command.isPending} disabled={closed||command.isPending} onClick={()=>{void command.mutateAsync({path:`/webinars/${session.resource_id}/recording-project`,body:{studio_session_id:session.id,expected_scene_revision:session.scene_revision}}).then(value=>setProjectId(value.id)).catch(()=>{});}}>Подготовить запись занятия</Button>:project.isPending?<LoadingState label="Проверяем проект записи…"/>:project.error?<ErrorState error={project.error} retry={()=>{void project.refetch();}}/>:project.data?<LiveTakeControls {...props} project={project.data}/>:null}
 {command.error&&<ErrorState error={command.error}/>}</Card></section>;
}
function LiveTakeControls({session,scene,tracks,connected,onCaptureActive,project}:Props & {project:RecordingProject}) {
 const takes=useRecordingTakes(project.id),command=useRecordingCommand<RecordingTake>(),current=activeTake(takes.data?.pages.flatMap(page=>page.items)??[]);
 const valid=project.mode==='live'&&project.live_event_id===session.resource_id&&project.studio_session_id===session.id;
 const closed=project.state==='archived'||['closing','closed','failed'].includes(session.state),busy=command.isPending;
 const locked=valid&&(busy||!!current&&['starting','capturing','stopping'].includes(current.state));
 useEffect(()=>{onCaptureActive(locked);return()=>onCaptureActive(false);},[locked,onCaptureActive]);
 if(!valid)return <ErrorState error={new Error('Проект записи не относится к этому занятию. Обновите данные.')}/>;
 const limit=recordingLimit(current?.max_duration_seconds??project.capabilities.max_duration_seconds);
 return <div className="recording-form">{limit&&<p className="meta">Один дубль — до {limit}. {project.capabilities.capture_limit_reason}</p>}{!project.capabilities.capture_available&&<p className="meta">{project.capabilities.capture_reason}</p>}
 {takes.isPending?<LoadingState label="Проверяем дубли…"/>:takes.error?<ErrorState error={takes.error} retry={()=>{void takes.refetch();}}/>:current?<>
 <RecordingPolicy take={current} scene={scene} tracks={tracks} connected={connected&&!closed} busy={busy} onCommand={body=>command.mutateAsync({path:`/recording-takes/${current.id}/policy`,body})}/>
 <p className="recording-status" role="status">{current.state==='stopping'&&current.stop_reason==='duration_limit'?'Достигнут лимит — завершаем запись':current.state==='capturing'&&!current.started_at?'Подтверждаем начало записи':takeLabels[current.state]??'Проверяем дубль'}</p>
 <div className="recording-actions">{current.state==='created'&&<Button disabled={closed||busy||!connected||!project.capabilities.capture_available||!policyMatches(current,scene,tracks)} onClick={()=>{void command.mutateAsync({path:`/recording-takes/${current.id}/start`,body:{expected_version:current.version}}).catch(()=>{});}}>Начать запись занятия</Button>}{['starting','capturing'].includes(current.state)&&<Button variant="danger" loading={busy} onClick={()=>{void command.mutateAsync({path:`/recording-takes/${current.id}/stop`,body:{expected_version:current.version}}).catch(()=>{});}}>Завершить запись занятия</Button>}</div></>:<><p className="p">Подготовь дубль, затем проверь и согласуй источники ведущего. Запись начнётся после подтверждения сервером.</p><Button variant="secondary" disabled={closed||busy||!connected} loading={busy} onClick={()=>{void command.mutateAsync({path:`/recording-projects/${project.id}/takes`,body:{expected_version:project.version,expected_scene_revision:session.scene_revision}}).catch(()=>{});}}>Подготовить дубль занятия</Button></>}
 <Link className="btn btn-ghost" to={`/fund/recordings/${project.id}`} aria-disabled={locked} tabIndex={locked?-1:undefined} onClick={event=>{if(locked)event.preventDefault();}}>Просмотр и проверка дублей</Link>{locked&&<p className="meta">Заверши запись и дождись подтверждения перед выходом из комнаты или сменой устройств.</p>}{command.error&&<ErrorState error={command.error}/>}</div>;
}
