import {useState} from 'react';
import type {StudioScene} from '../../../../../packages/studio-core';
import type {components} from '../../api/generated/schema';
import {Button,Dialog,Icon} from '../../ui';
import type {StageTrackBinding} from '../../ui/studio';
import type {RecordingTake} from './api';
type Policy=components['schemas']['RecordingPolicyCommand'];
const labels:Record<string,string>={camera:'Камера',microphone:'Микрофон',screen:'Экран',screen_audio:'Звук экрана'};
export function ownRecordingSources(scene:StudioScene,tracks:readonly StageTrackBinding[]):Policy['tracks'] {
 return tracks.filter(track=>track.identity===scene.presenter_identity&&track.privacy_state==='approved').map(({identity,track_id,source,kind,state})=>({identity,track_id,source,kind,required:state==='ready'})).sort((a,b)=>a.track_id.localeCompare(b.track_id));
}
function essentialSourcesReady(scene:StudioScene,tracks:readonly StageTrackBinding[]) {
 return (!scene.presenter_camera||tracks.some(track=>track.identity===scene.presenter_identity&&track.source==='camera'&&track.state==='ready'))&&(scene.content_kind!=='screen'||tracks.some(track=>track.track_id===scene.screen_track_id&&track.source==='screen'&&track.state==='ready'));
}
export function policyMatches(take:RecordingTake,scene:StudioScene,tracks:readonly StageTrackBinding[]) {
 const wanted=ownRecordingSources(scene,tracks),approved=[...take.policy_tracks].sort((a,b)=>a.track_id.localeCompare(b.track_id));
 const key=(items:Policy['tracks'])=>JSON.stringify(items.map(({identity,track_id,source,kind,required})=>[identity,track_id,source,kind,required]));
 return take.privacy_state==='approved'&&take.policy_scene_revision===scene.revision&&key(wanted)===key(approved)
  &&tracks.every(track=>track.identity===scene.presenter_identity&&track.privacy_state==='approved'&&track.state!=='missing')
  &&essentialSourcesReady(scene,tracks)
  &&tracks.some(track=>track.identity===scene.presenter_identity&&track.kind==='audio'&&track.state==='ready');
}
export function RecordingPolicy({take,scene,tracks,connected,busy,onCommand}:{take:RecordingTake;scene:StudioScene;tracks:readonly StageTrackBinding[];connected:boolean;busy:boolean;onCommand:(body:Policy)=>Promise<unknown>}) {
 const sources=ownRecordingSources(scene,tracks),[consent,setConsent]=useState(''),[withdrawing,setWithdrawing]=useState(false);
 const signature=JSON.stringify([take.id,take.version,scene.revision,sources]),checked=consent===signature;
 const readyAudio=tracks.some(track=>track.identity===scene.presenter_identity&&track.kind==='audio'&&track.privacy_state==='approved'&&track.state==='ready');
 const allReady=tracks.every(track=>track.identity===scene.presenter_identity&&track.privacy_state==='approved'&&track.state!=='missing')&&essentialSourcesReady(scene,tracks);
 const approved=policyMatches(take,scene,tracks),synchronized=take.policy_scene_revision===scene.revision,canApprove=take.state==='created'&&synchronized&&connected&&readyAudio&&allReady;
 const send=async(approved:boolean)=>{try{await onCommand({expected_version:take.version,expected_scene_revision:scene.revision,approved,tracks:approved?sources:[]});setConsent('');setWithdrawing(false);}catch{/* parent displays the authoritative command error */}};
 return <div className="recording-policy"><h3 className="h3">Источники записи</h3>{sources.length?<ul className="recording-source-list">{sources.map(source=><li key={source.track_id}><Icon name={source.kind==='audio'?'mic':source.source==='screen'?'screen':'camera'}/><span>{labels[source.source]??'Источник'}{tracks.find(track=>track.track_id===source.track_id)?.state!=='ready'?' — выключен':''}</span></li>)}</ul>:<p className="p">Сначала подключись и включи нужные устройства.</p>}
 {!synchronized&&<p className="meta">Кадр обновляется. Дождись синхронизации студии.</p>}{!readyAudio&&<p className="meta">Для урока со звуком включи микрофон или звук демонстрации экрана.</p>}{!allReady&&<p className="meta">Проверь устройства перед согласованием. При необходимости переподключись к студии и включи только нужные источники.</p>}
 {approved?<p className="recording-status"><Icon name="check"/>Текущие источники согласованы</p>:take.state==='created'?<><label className="recording-check"><input type="checkbox" checked={checked} disabled={!canApprove||busy} onChange={event=>setConsent(event.target.checked?signature:'')}/><span>Разрешаю запись перечисленных собственных источников</span></label><p className="meta">Сервер сверит список с источниками в студии перед запуском.</p><Button variant="secondary" disabled={!canApprove||!checked||busy} onClick={()=>{void send(true);}}>Согласовать источники</Button></>:null}
 {take.privacy_state==='approved'&&['created','starting','capturing','stopping'].includes(take.state)&&<div className="recording-actions"><Button variant="ghost" disabled={busy} onClick={()=>setWithdrawing(true)}>Отозвать разрешение</Button></div>}
 <Dialog open={withdrawing} onClose={()=>setWithdrawing(false)} title="Отозвать разрешение на запись?" footer={<><Button variant="danger" loading={busy} onClick={()=>{void send(false);}}>Отозвать разрешение</Button><Button variant="ghost" onClick={()=>setWithdrawing(false)}>Оставить</Button></>}><p className="p">Сервер остановит захват. Перед новым дублем нужно будет снова проверить и согласовать источники.</p></Dialog>
 </div>;
}
