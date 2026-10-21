/** Epoch/reconnect/subscription mechanics ported from OD LiveKitMediaSession at 38c92cd.
 * Provider surfaces contain no school/session policy. The server grants every join.
 */
import {Room,RoomEvent,Track,type RemoteTrack,type RemoteTrackPublication,type RemoteParticipant} from 'livekit-client';
import {parseStudioScene,parseCapturePlan,type StudioScene,type CapturePlan,type TrackSource} from '../../../../../../packages/studio-core';
import type {StageTrackBinding} from '../../../ui/studio';

export interface CaptureJoinGrant {url:string;token:string;identity:string;session_id:string;generation:number;role?:'host'|'audience';}
export interface MediaSnapshot {status:'connecting'|'connected'|'reconnecting'|'disconnected'|'blocked';tracks:readonly StageTrackBinding[];error:string|null;cameraOn:boolean;microphoneOn:boolean;screenOn:boolean;}
export interface MediaOptions {onChange:(snapshot:MediaSnapshot)=>void;onRefreshRequired?:()=>void;}
const source=(value:Track.Source):TrackSource|null=>({[Track.Source.Camera]:'camera',[Track.Source.Microphone]:'microphone',[Track.Source.ScreenShare]:'screen',[Track.Source.ScreenShareAudio]:'screen_audio'} as Partial<Record<Track.Source,TrackSource>>)[value]||null;
const trackKind=(value:Track.Kind)=>value===Track.Kind.Audio?'audio':'video';
const initial=():MediaSnapshot=>({status:'disconnected',tracks:[],error:null,cameraOn:false,microphoneOn:false,screenOn:false});

export class RoomController {
 protected room:Room|null=null;
 protected epoch=0;
 protected mediaRevision=0;
 protected value=initial();
 protected scene:StudioScene|null=null;
 protected plan:CapturePlan|null=null;
 protected grant:CaptureJoinGrant|null=null;
 protected reconnectBlocked=false;
 protected abortCleanup:(()=>void)|null=null;
 protected bindings=new Map<string,{track:RemoteTrack|Track;binding:StageTrackBinding}>();
 constructor(protected options:MediaOptions,protected hidden:boolean){}
 get snapshot(){return this.value;}
 protected emit(patch:Partial<MediaSnapshot>={}){this.value={...this.value,...patch};this.options.onChange(this.value);}
 protected permitted(identity:string,publication:RemoteTrackPublication){
  const src=source(publication.source);if(!src)return false;
  if(this.hidden)return !!this.plan?.allowed_tracks.some(item=>item.identity===identity&&item.track_id===publication.trackSid&&item.source===src&&item.kind===trackKind(publication.kind));
  return identity===this.scene?.presenter_identity;
 }
 protected bind(identity:string,track:Track,sid:string,src:TrackSource,approved:boolean,state:'ready'|'muted'){
  const old=this.bindings.get(sid);
  if(old?.track===track&&old.binding.state===state&&old.binding.privacy_state===(approved?'approved':'unknown'))return old.binding;
  const binding:StageTrackBinding={identity,track_id:sid,source:src,kind:trackKind(track.kind),privacy_state:approved?'approved':'unknown',state,media_revision:++this.mediaRevision,
   attach:(element)=>{if(!approved)throw new Error('track_not_allowed');track.attach(element);return()=>{track.detach(element);};}};
  this.bindings.set(sid,{track,binding});return binding;
 }
 protected sync(){
  const room=this.room;
  if(!room||this.reconnectBlocked)return;
  const tracks:StageTrackBinding[]=[];const seen=new Set<string>();let unexpected=false;
  for(const participant of room.remoteParticipants.values())for(const publication of participant.trackPublications.values()){
   const allowed=this.permitted(participant.identity,publication);publication.setSubscribed(allowed);
   if(!publication.track)continue;
   const src=source(publication.source);
   if(!src){unexpected=true;continue;}
   if(this.hidden&&!allowed)unexpected=true;
   if(!allowed&&!this.hidden)continue;
   seen.add(publication.trackSid);tracks.push(this.bind(participant.identity,publication.track,publication.trackSid,src,allowed,publication.isMuted?'muted':'ready'));
  }
  if(!this.hidden){
   for(const publication of room.localParticipant.trackPublications.values())if(publication.track){
    const src=source(publication.source);if(!src)continue;
    const sid=publication.trackSid||publication.track.sid||`local-${src}`;seen.add(sid);tracks.push(this.bind(room.localParticipant.identity,publication.track,sid,src,true,publication.isMuted?'muted':'ready'));
   }
  }
  for(const sid of this.bindings.keys())if(!seen.has(sid))this.bindings.delete(sid);
  const local=room.localParticipant;
  this.emit({tracks,status:unexpected?'blocked':'connected',error:unexpected?'Получена неподтверждённая медиадорожка.':null,cameraOn:!!local.getTrackPublication(Track.Source.Camera)?.track&&!local.getTrackPublication(Track.Source.Camera)?.isMuted,microphoneOn:!!local.getTrackPublication(Track.Source.Microphone)?.track&&!local.getTrackPublication(Track.Source.Microphone)?.isMuted,screenOn:!!local.getTrackPublication(Track.Source.ScreenShare)?.track});
 }
 protected async open(grant:CaptureJoinGrant,scene:StudioScene,plan:CapturePlan|null,signal?:AbortSignal){
  await this.disconnect();const epoch=++this.epoch;this.scene=parseStudioScene(scene);this.plan=plan?parseCapturePlan(plan):null;
  if((plan&&(plan.privacy_state!=='approved'||plan.recording_policy_id!==scene.recording_policy_id))||grant.session_id!==scene.session_id||(plan&&(grant.generation!==plan.generation||plan.session_id!==scene.session_id||plan.foundation_id!==scene.foundation_id||plan.resource_id!==scene.resource_id||plan.take_id!==scene.take_id||plan.scene_revision!==scene.revision||plan.render_profile_version!==scene.render_profile_version)))throw new Error('capture_scope_mismatch');
  if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  this.grant=grant;this.reconnectBlocked=false;this.emit({status:'connecting',error:null,tracks:[]});
  const room=new Room({adaptiveStream:false,dynacast:!this.hidden});this.room=room;
  const current=()=>this.epoch===epoch&&this.room===room;
  const sync=()=>{if(current())this.sync();};
  [RoomEvent.TrackPublished,RoomEvent.TrackUnpublished,RoomEvent.TrackSubscribed,RoomEvent.TrackUnsubscribed,RoomEvent.TrackMuted,RoomEvent.TrackUnmuted,RoomEvent.ParticipantConnected,RoomEvent.ParticipantDisconnected,RoomEvent.LocalTrackPublished,RoomEvent.LocalTrackUnpublished].forEach(event=>room.on(event,sync));
  room.on(RoomEvent.Reconnecting,()=>{if(current()){this.reconnectBlocked=true;this.bindings.clear();this.emit({status:'reconnecting',tracks:[]});}});
  room.on(RoomEvent.Reconnected,()=>{if(current()){this.reconnectBlocked=true;this.emit({status:'blocked',tracks:[],error:'Подтверждаем доступ после переподключения.'});this.options.onRefreshRequired?.();}});
  room.on(RoomEvent.Disconnected,()=>{if(current()){this.bindings.clear();this.emit({status:'disconnected',tracks:[]});}});
  const abort=()=>{if(current())void this.disconnect();};signal?.addEventListener('abort',abort,{once:true});const cleanup=()=>signal?.removeEventListener('abort',abort);this.abortCleanup=cleanup;
  try{
   await room.connect(grant.url,grant.token,{autoSubscribe:false});
   if(!current()||signal?.aborted){await room.disconnect();throw new DOMException('Aborted','AbortError');}
   this.sync();
  }catch(error){if(current()){this.room=null;this.emit({status:'disconnected',error:'Не удалось подключиться к видеокомнате.',tracks:[]});}await room.disconnect();throw error;}
  finally{if(!current()){cleanup();if(this.abortCleanup===cleanup)this.abortCleanup=null;}}
 }
 updateScene(scene:StudioScene){this.scene=parseStudioScene(scene);this.sync();}
 async disconnect(){
  ++this.epoch;this.abortCleanup?.();this.abortCleanup=null;const room=this.room;this.room=null;this.bindings.clear();this.reconnectBlocked=false;this.emit(initial());
  if(room){room.removeAllListeners();await room.disconnect();}
 }
}

