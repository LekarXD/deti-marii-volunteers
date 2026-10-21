import {describe,it,expect,vi,beforeEach} from 'vitest';
import {RoomEvent,Track} from 'livekit-client';
import {HiddenCaptureController} from './HiddenCaptureController';
import type {MediaSnapshot} from './RoomController';
import {fictionScene,fictionPlan} from '../../../ui/studio/fixtures';
const state=vi.hoisted(()=>({rooms:[] as any[],pending:[] as Promise<void>[]}));
vi.mock('livekit-client',async()=>{
 const actual=await vi.importActual<typeof import('livekit-client')>('livekit-client');
 return {...actual,Room:class {
  handlers=new Map<string,Function[]>();remoteParticipants=new Map();
  localParticipant={identity:'renderer',trackPublications:new Map(),getTrackPublication:()=>undefined,setCameraEnabled:vi.fn(),setMicrophoneEnabled:vi.fn(),setScreenShareEnabled:vi.fn()};
  connect=vi.fn(async()=>{await (state.pending.shift()||Promise.resolve());});disconnect=vi.fn(async()=>{});
  constructor(){state.rooms.push(this);}
  on(name:string,fn:Function){this.handlers.set(name,[...(this.handlers.get(name)||[]),fn]);return this;}
  emit(name:string){this.handlers.get(name)?.forEach(fn=>fn());}
  removeAllListeners(){this.handlers.clear();}
 }};
});
function fixture(){const scene=fictionScene();const plan=fictionPlan(scene);return {scene,plan,grant:{url:'wss://rtc.example.test',token:'test-transport-pass',identity:'renderer',session_id:scene.session_id,generation:plan.generation}};}
beforeEach(()=>{state.rooms.length=0;state.pending.length=0;});
describe('private capture controller privacy and epochs',()=>{
 it('blocks an unknown or unrecognized publication before it has a subscribed media track',async()=>{
  const {scene,plan,grant}=fixture();const controller=new HiddenCaptureController({onChange:()=>{}});
  await controller.connect(grant,scene,plan);const room=state.rooms[0];
  for(const source of [Track.Source.Microphone,Track.Source.Unknown]){
   const publication={source,kind:Track.Kind.Audio,trackSid:'TR_unapproved',track:undefined,setSubscribed:vi.fn(),isMuted:false};
   room.remoteParticipants.set('other',{identity:'unapproved-participant',trackPublications:new Map([['unknown',publication]])});room.emit(RoomEvent.TrackPublished);
   expect(publication.setSubscribed).toHaveBeenLastCalledWith(false);expect(controller.snapshot.status).toBe('blocked');expect(controller.snapshot.tracks).toEqual([]);
  }
  expect(room.localParticipant.setMicrophoneEnabled).not.toHaveBeenCalled();await controller.disconnect();
 });
 it('manually subscribes only approved tracks and never captures devices or attaches audio itself',async()=>{
  const {scene,plan,grant}=fixture();const values:MediaSnapshot[]=[];const controller=new HiddenCaptureController({onChange:value=>values.push(value)});
  await controller.connect(grant,scene,{...plan,allowed_tracks:[{identity:scene.presenter_identity,track_id:'TR_approved',source:'microphone',kind:'audio',required:true}]});
  const room=state.rooms[0];expect(room.connect.mock.calls[0][2]).toEqual({autoSubscribe:false});
  const approved={source:Track.Source.Microphone,kind:Track.Kind.Audio,trackSid:'TR_approved',track:{kind:Track.Kind.Audio,attach:vi.fn(),detach:vi.fn()},setSubscribed:vi.fn(),isMuted:false};
  const unknown={...approved,trackSid:'TR_unknown',track:{kind:Track.Kind.Audio,attach:vi.fn(),detach:vi.fn()},setSubscribed:vi.fn()};
  room.remoteParticipants.set('presenter',{identity:scene.presenter_identity,trackPublications:new Map([['approved',approved],['unknown',unknown]])});room.emit(RoomEvent.TrackPublished);
  expect(approved.setSubscribed).toHaveBeenLastCalledWith(true);expect(unknown.setSubscribed).toHaveBeenLastCalledWith(false);
  expect(controller.snapshot.status).toBe('blocked');expect(controller.snapshot.tracks.some(track=>track.privacy_state==='unknown')).toBe(true);
  expect(approved.track.attach).not.toHaveBeenCalled();expect(unknown.track.attach).not.toHaveBeenCalled();expect(room.localParticipant.setMicrophoneEnabled).not.toHaveBeenCalled();expect(room.handlers.has(RoomEvent.DataReceived)).toBe(false);
  await controller.disconnect();
 });
 it('fences a late connection completion after a newer connection',async()=>{
  const {scene,plan,grant}=fixture();let finish!:()=>void;state.pending.push(new Promise<void>(resolve=>{finish=resolve;}));
  const controller=new HiddenCaptureController({onChange:()=>{}});const pending=controller.connect(grant,scene,plan).catch(error=>error);
  await vi.waitFor(()=>expect(state.rooms).toHaveLength(1));await controller.disconnect();const signal=new AbortController();await controller.connect(grant,scene,plan,signal.signal);finish();
  expect((await pending).name).toBe('AbortError');expect(controller.snapshot.status).toBe('connected');expect(state.rooms[0].disconnect).toHaveBeenCalled();signal.abort();await vi.waitFor(()=>expect(controller.snapshot.status).toBe('disconnected'));
 });
 it('blocks reconnect until a fresh signed grant and rejects take/scope changes',async()=>{
  const {scene,plan,grant}=fixture();const refresh=vi.fn();const controller=new HiddenCaptureController({onChange:()=>{},onRefreshRequired:refresh});await controller.connect(grant,scene,plan);
  state.rooms[0].emit(RoomEvent.Reconnecting);state.rooms[0].emit(RoomEvent.Reconnected);expect(controller.snapshot.status).toBe('blocked');expect(controller.snapshot.tracks).toHaveLength(0);expect(refresh).toHaveBeenCalledOnce();
  controller.updatePlan({...scene,take_id:'10000000-0000-4000-8000-000000000099'},{...plan,take_id:'10000000-0000-4000-8000-000000000099'});expect(controller.snapshot.status).toBe('blocked');await controller.disconnect();
 });
 it.each(['unknown','blocked'] as const)('rejects %s privacy before creating a provider connection',async privacy_state=>{
  const {scene,plan,grant}=fixture();const controller=new HiddenCaptureController({onChange:()=>{}});
  await expect(controller.connect(grant,scene,{...plan,privacy_state})).rejects.toThrow('capture_scope_mismatch');expect(state.rooms).toHaveLength(0);
 });
 it('rejects policy mismatches before joining and unsubscribes immediately on unsafe plan update',async()=>{
  const {scene,plan,grant}=fixture();const controller=new HiddenCaptureController({onChange:()=>{}});
  await expect(controller.connect(grant,scene,{...plan,recording_policy_id:'10000000-0000-4000-8000-000000000088'})).rejects.toThrow('capture_scope_mismatch');expect(state.rooms).toHaveLength(0);
  await controller.connect(grant,scene,plan);const publication={setSubscribed:vi.fn()};state.rooms[0].remoteParticipants.set('host',{trackPublications:new Map([['camera',publication]])});
  controller.updatePlan(scene,{...plan,privacy_state:'unknown'});expect(publication.setSubscribed).toHaveBeenLastCalledWith(false);expect(controller.snapshot.tracks).toHaveLength(0);expect(controller.snapshot.status).toBe('blocked');await controller.disconnect();
 });

});
