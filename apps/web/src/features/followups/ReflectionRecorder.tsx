import {appPath} from '../../basePath';
import {useEffect,useRef,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {api,ApiError} from '../../api/transport';
import type {components} from '../../api/generated/schema';
import {Button,ErrorState,Field,Icon,Textarea} from '../../ui';
import {audioCommand,readAudio,readLatestAudio,type ReflectionAudio} from './api';

const MAX_BYTES=10*1024*1024,MAX_MS=180000,CHUNK=1024*1024;
const clock=(seconds:number)=>`${Math.floor(seconds/60)}:${(seconds%60).toString().padStart(2,'0')}`;
type Phase='idle'|'requesting'|'recording'|'recorded'|'uploading'|'processing'|'preview'|'failed';
type Live={recorder:MediaRecorder;stream:MediaStream;chunks:Blob[];bytes:number;cancelled:boolean;started:number;timer:ReturnType<typeof setInterval>|null};
const labels:Record<string,string>={queued:'Запись в очереди распознавания',calling:'Распознаём запись…',processing:'Проверяем запись…',unknown:'Результат распознавания неизвестен. Можно повторить запрос явно.',unavailable:'Распознавание сейчас недоступно. Текст можно написать вручную.',budget_exceeded:'Лимит распознавания исчерпан. Текст можно написать вручную.',failed:'Не удалось обработать запись. Можно повторить или записать заново.'};

export function ReflectionRecorder({id,text,onApply,disabled=false,available=true}:{id:string;text:string;onApply:(text:string)=>void;disabled?:boolean;available?:boolean}){
 const client=useQueryClient();const [phase,setPhase]=useState<Phase>('idle'),[file,setFile]=useState<Blob|null>(null),[url,setUrl]=useState(''),[elapsed,setElapsed]=useState(0),[row,setRow]=useState<ReflectionAudio|null>(null),[transcript,setTranscript]=useState(''),[applied,setApplied]=useState(false),[error,setError]=useState<unknown>(null),[blocked,setBlocked]=useState(false),[cancelling,setCancelling]=useState(false);
 const live=useRef<Live|null>(null),generation=useRef(0),mounted=useRef(true),controller=useRef<AbortController|null>(null),receipt=useRef(crypto.randomUUID()),restored=useRef(false),loaded=useRef(''),pendingIntent=useRef<Promise<ReflectionAudio>|null>(null);
 const latest=useQuery({queryKey:keys.detail('reflection-audio-latest',id),queryFn:({signal})=>readLatestAudio(id,signal),staleTime:0});
 const status=useQuery({queryKey:keys.detail('reflection-audio',`${id}:${row?.asset_id??''}`),queryFn:({signal})=>readAudio(id,row!.asset_id,signal),enabled:!!row&&['processing','preview'].includes(phase),staleTime:0,refetchInterval:phase==='preview'?10000:2000});
 function accept(value:ReflectionAudio){
  setRow(value);
  if(value.state==='ready'){
   const key=`${value.asset_id}:${value.version}`;if(loaded.current!==key){setTranscript(value.transcript??'');setApplied(false);loaded.current=key;}setPhase('preview');
  }else if(['queued','calling','processing'].includes(value.state))setPhase('processing');
  else if(value.state==='cancelled')setPhase('idle');
  else if(value.state==='uploading')setPhase('recorded');
  else setPhase('failed');
 }
 useEffect(()=>{if(latest.data!==undefined&&!restored.current){restored.current=true;if(latest.data&&latest.data.state!=='cancelled')accept(latest.data);}},[latest.data]);
 useEffect(()=>{if(status.data)accept(status.data);},[status.data]);
 useEffect(()=>{if(status.error){setError(status.error);setTranscript('');setPhase('failed');if(status.error instanceof ApiError&&[401,403,404].includes(status.error.status))setBlocked(true);}},[status.error]);
 useEffect(()=>{if(!file){setUrl('');return;}const value=URL.createObjectURL(file);setUrl(value);return()=>URL.revokeObjectURL(value);},[file]);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;generation.current++;controller.current?.abort();const value=live.current;if(value){value.cancelled=true;if(value.timer)clearInterval(value.timer);if(value.recorder.state!=='inactive')value.recorder.stop();value.stream.getTracks().forEach(track=>track.stop());}};},[]);
 function stop(){const value=live.current;if(!value)return;if(value.timer)clearInterval(value.timer);value.timer=null;if(value.recorder.state!=='inactive')value.recorder.stop();value.stream.getTracks().forEach(track=>track.stop());}
 async function cancel(){
  generation.current++;controller.current?.abort();if(live.current)live.current.cancelled=true;stop();setCancelling(true);setError(null);
  try{const source=pendingIntent.current?await pendingIntent.current:row;if(source){const current=await readAudio(id,source.asset_id);await audioCommand(id,`audio/${source.asset_id}/cancel`,{expected_version:current.version},crypto.randomUUID());client.removeQueries({queryKey:keys.detail('reflection-audio',`${id}:${source.asset_id}`)});}setRow(null);setFile(null);setTranscript('');setApplied(false);setPhase('idle');setElapsed(0);}
  catch(e){setError(e);setPhase('failed');}finally{setCancelling(false);}
 }
 async function record(){
  if(disabled||blocked||row||!available)return;
  if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined'){setError(new Error('Этот браузер не поддерживает запись. Можно написать текст.'));setPhase('failed');return;}
  setError(null);setPhase('requesting');setFile(null);setTranscript('');setElapsed(0);setApplied(false);const epoch=++generation.current;
  let opened:MediaStream|null=null;
  try{
   const stream=await navigator.mediaDevices.getUserMedia({audio:true});opened=stream;
   if(!mounted.current||epoch!==generation.current){stream.getTracks().forEach(track=>track.stop());return;}
   const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(value=>MediaRecorder.isTypeSupported(value));
   if(!mime){stream.getTracks().forEach(track=>track.stop());throw new Error('Этот браузер не поддерживает подходящий формат записи. Можно написать текст.');}
   const recorder=new MediaRecorder(stream,{mimeType:mime,audioBitsPerSecond:64000});
   const value:Live={recorder,stream,chunks:[],bytes:0,cancelled:false,started:Date.now(),timer:null};live.current=value;
   recorder.ondataavailable=event=>{if(!event.data.size||value.cancelled)return;value.bytes+=event.data.size;if(value.bytes>MAX_BYTES){value.cancelled=true;setError(new Error('Запись превысила 10 МБ. Попробуйте более короткую запись.'));setPhase('failed');stop();return;}value.chunks.push(event.data);};
   recorder.onerror=()=>{value.cancelled=true;setError(new Error('Не удалось записать звук. Проверьте микрофон или напишите текст.'));setPhase('failed');stop();};
   recorder.onstop=()=>{value.stream.getTracks().forEach(track=>track.stop());if(value.timer)clearInterval(value.timer);if(!value.cancelled&&mounted.current){const blob=new Blob(value.chunks,{type:recorder.mimeType});if(blob.size){setFile(blob);setPhase('recorded');receipt.current=crypto.randomUUID();}else{setError(new Error('В записи нет звука. Можно записать ещё раз или написать текст.'));setPhase('failed');}}live.current=null;};
   recorder.start(1000);setPhase('recording');
   value.timer=setInterval(()=>{setElapsed(Math.min(180,Math.floor((Date.now()-value.started)/1000)));if(Date.now()-value.started>=MAX_MS-500)stop();},250);
  }catch(e){opened?.getTracks().forEach(track=>track.stop());if(epoch===generation.current&&mounted.current){setError(e instanceof DOMException&&e.name==='NotAllowedError'?new Error('Доступ к микрофону не предоставлен. Можно написать текст.'):e);setPhase('failed');}}
 }
 async function upload(){
  if(!file||disabled||blocked||!available)return;const epoch=++generation.current;const abort=new AbortController();controller.current=abort;setPhase('uploading');setError(null);
  try{
   let current=row?await readAudio(id,row.asset_id,abort.signal):null;if(epoch!==generation.current||abort.signal.aborted)return;
   if(!current){const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());const checksum=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');if(epoch!==generation.current||abort.signal.aborted)return;const pending=audioCommand(id,'audio-intent',{content_type:file.type.split(';')[0],expected_size:file.size,checksum},receipt.current);pendingIntent.current=pending;try{current=await pending;}finally{if(pendingIntent.current===pending)pendingIntent.current=null;}if(epoch===generation.current)setRow(current);}
   if(epoch!==generation.current||abort.signal.aborted)return;
   if(current.state!=='uploading'){accept(current);return;}
   let offset=current.received_size;
   while(offset<file.size){if(abort.signal.aborted)throw new Error('upload_cancelled');const part=file.slice(offset,Math.min(offset+CHUNK,file.size));const updated=await api<components['schemas']['AssetView']>(current.upload_url,{method:'PATCH',body:part,signal:abort.signal,headers:{'Content-Type':'application/octet-stream','X-Upload-Offset':String(offset)}});if(updated.received_size!==offset+part.size)throw new Error('Сервер не подтвердил загрузку. Повторите попытку.');offset=updated.received_size;setRow({...current,received_size:offset});}
   await api(`/assets/${current.asset_id}/complete-upload`,{method:'POST',signal:abort.signal});
   if(epoch===generation.current){setRow(current);setPhase('processing');await client.invalidateQueries({queryKey:keys.detail('reflection-audio',`${id}:${current.asset_id}`)});}
  }catch(e){if(epoch===generation.current){setError(e);setPhase('failed');}}finally{if(controller.current===abort)controller.current=null;}
 }
 async function retry(){if(!row||!available)return;setError(null);try{const current=await readAudio(id,row.asset_id);const updated=await audioCommand(id,`audio/${row.asset_id}/retry`,{expected_version:current.version},crypto.randomUUID());setTranscript('');loaded.current='';accept(updated);}catch(e){setError(e);}}
 const combined=[text.trim(),transcript.trim()].filter(Boolean).join('\n\n'),tooLong=combined.length>12000;
 const active=['requesting','recording','uploading','processing'].includes(phase);
 return <section className="reflection-recorder" aria-label="Голосовая заметка"><div className="followup-actions">{!row&&!active&&<Button variant="secondary" disabled={disabled||blocked||latest.isPending||!available} onClick={()=>void record()}><Icon name="mic"/>Записать голосом</Button>}{phase==='recording'&&<><span className="reflection-recording" role="status">Запись {clock(elapsed)} / 3:00</span><Button variant="secondary" onClick={stop}>Остановить запись</Button></>}{phase==='requesting'&&<p role="status">Ожидаем разрешение на микрофон…</p>}{(active||row||file)&&<Button variant="ghost" loading={cancelling} onClick={()=>void cancel()}>Отменить запись</Button>}</div>
 <p className="meta">До 3 минут и 10 МБ. Запись начнётся по нажатию. После распознавания проверьте текст перед добавлением в рефлексию.</p>
 {(url||(row?.state==='ready'))&&<audio aria-label="Прослушать свою запись" controls preload="none" src={url||appPath(`/api/v1/assets/${row!.asset_id}/content`)}/>}
 {phase==='recorded'&&file&&<Button variant="secondary" disabled={disabled||!available} onClick={()=>void upload()}>Распознать запись</Button>}
 {phase==='recorded'&&!file&&<p className="meta">Предыдущая загрузка не завершена. Отмените её, чтобы записать заново.</p>}
 {phase==='uploading'&&<p role="status">Загружаем запись…{row?` ${Math.floor(row.received_size/row.expected_size*100)}%`:''}</p>}
 {phase==='processing'&&<p role="status">{labels[row?.state??'processing']??'Обрабатываем запись…'}</p>}
 {phase==='failed'&&row&&<><p className="meta">{labels[row.state]??'Запись можно отменить и записать заново.'}</p>{file&&row.state==='uploading'&&<Button variant="secondary" onClick={()=>void upload()}>Повторить загрузку</Button>}{row.can_retry&&!blocked&&<Button variant="secondary" disabled={!available} onClick={()=>void retry()}>Повторить распознавание</Button>}</>}
 {phase==='preview'&&!blocked&&<div className="followup-fields"><Field label="Распознанный текст" hint="Можно исправить слова. Исходная рефлексия изменится только по кнопке ниже."><Textarea value={transcript} onChange={e=>{setTranscript(e.target.value);setApplied(false);}} maxLength={12000} disabled={disabled}/></Field>{tooLong&&<p className="err">Вместе с рефлексией получится больше 12 000 символов. Сократите текст.</p>}<Button variant="secondary" disabled={disabled||!transcript.trim()||tooLong||applied} onClick={()=>{onApply(transcript.trim());setApplied(true);}}>Добавить к тексту</Button>{applied&&<p role="status" className="meta">Текст добавлен. Черновик можно проверить и сохранить.</p>}</div>}
 {error?<ErrorState error={error}/>:null}{latest.error?<ErrorState error={latest.error} retry={()=>latest.refetch()}/>:null}
 </section>;
}
