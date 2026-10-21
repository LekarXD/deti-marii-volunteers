import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {canonicalSerialize} from '../../../../../../packages/studio-core';
import type {components} from '../../../api/generated/schema';
import {fictionPlan,fictionScene} from '../../../ui/studio/fixtures';
import type {RendererViewProps} from './RendererView';
import type {MediaOptions} from '../../studio/live/RoomController';
vi.mock('../../studio/live/HiddenCaptureController',()=>({HiddenCaptureController:class {}}));
import {createRendererRuntime} from './runtime';
type Bootstrap=components['schemas']['RendererBootstrapView'];
type State=components['schemas']['RendererStateView'];
type Input=components['schemas']['RendererReadinessInput'];
const json=(value:unknown)=>new Response(JSON.stringify(value));
async function hash(scene:State['scene'],capture_plan:State['capture_plan']) {
 const bytes=new TextEncoder().encode(canonicalSerialize({scene,capture_plan,resolved_assets:[]}));
 return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),value=>value.toString(16).padStart(2,'0')).join('');
}
async function fixture(kind:'live_event'|'lesson_recording_project'='lesson_recording_project'):Promise<Bootstrap>{
 const scene=fictionScene(kind,{content_kind:'camera',layout:'camera_only',content_asset:null,deck_version_id:null,slide_id:null});
 const plan=fictionPlan(scene),capture_plan={...plan,allowed_tracks:[...plan.allowed_tracks]};
 return {scene,capture_plan,foundation_id:scene.foundation_id,project_id:kind==='live_event'?'10000000-0000-4000-8000-000000000099':scene.resource_id,resource_kind:scene.resource_kind,resource_id:scene.resource_id,take_id:plan.take_id,session_id:scene.session_id,generation:1,
  renderer_state_version:1,projection_hash:await hash(scene,capture_plan),resolved_assets:[],invalidated:false,
  access_token:'fictional-access',expires_at:new Date(Date.now()+60_000).toISOString(),
  provider_grant:{provider:'livekit',url:'wss://fictional-provider.invalid',token:'fictional-room-token',identity:'fictional-renderer',session_id:scene.session_id,generation:1,expires_in:60},
 };
}
beforeEach(()=>{vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-21T12:00:00Z'));vi.stubGlobal('window',{innerWidth:1920,innerHeight:1080,devicePixelRatio:1});});
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();});
async function harness(initial?:Bootstrap){
 const boot=initial??await fixture();let state:State=boot;let mediaOptions:MediaOptions|undefined;
 const reports:Input[]=[];const views:RendererViewProps[]=[];
 let heldReady:((response:Response)=>void)|undefined;let holdReady=false;
 let nextReadinessError:{status:number;code:string}|undefined;
 let heldState:((response:Response)=>void)|undefined,holdState=false;
 const fetch=vi.fn(async(path:string,options?:RequestInit):Promise<Response>=>{
  if(path.endsWith('/bootstrap'))return json(boot);
  if(path.includes('/state?')){if(holdState){holdState=false;return new Promise(resolve=>{const snapshot=state;heldState=()=>resolve(json(snapshot));});}return json(state);}
  if(path.endsWith('/provider-grant'))return json({...state,provider_grant:{...boot.provider_grant,token:'fresh-fictional-room-token'}});
  if(path.endsWith('/readiness')){
   const input=JSON.parse(String(options?.body)) as Input;reports.push(input);
   if(nextReadinessError){const error=nextReadinessError;nextReadinessError=undefined;return new Response(JSON.stringify({code:error.code}),{status:error.status});}
   const ack={ready:input.visual_ready,reasons:input.visual_ready?[]:['visual_frame_unready'],renderer_state_version:input.renderer_state_version,projection_hash:input.projection_hash,
    readiness_sequence:input.readiness_sequence,capture_state:'created',valid_until:input.visual_ready?new Date(Date.now()+10_000).toISOString():null};
   if(holdReady&&input.visual_ready)return new Promise(resolve=>{heldReady=resolve;});
   return json(ack);
  }
  throw new Error('Unexpected private renderer endpoint');
 });vi.stubGlobal('fetch',fetch);
 const connect=vi.fn(async()=>{mediaOptions!.onChange({status:'connected',tracks:[],error:null,cameraOn:false,microphoneOn:false,screenOn:false});});
 const disconnect=vi.fn(async()=>{}),updatePlan=vi.fn();
 const runtime=createRendererRuntime({render:props=>views.push(props),mediaFactory:options=>{mediaOptions=options;return {connect,disconnect,updatePlan};}});
 return {runtime,boot,views,reports,fetch,connect,disconnect,updatePlan,
  setState(value:State){state=value;},refresh(){mediaOptions!.onRefreshRequired?.();},
  rejectReadiness(status=409,code='renderer_state_conflict'){nextReadinessError={status,code};},
  holdState(){holdState=true;},releaseState(){heldState?.(json(state));},
  hold(){holdReady=true;},release(){const input=reports.filter(report=>report.visual_ready).at(-1)!;heldReady?.(json({ready:true,reasons:[],renderer_state_version:input.renderer_state_version,projection_hash:input.projection_hash,readiness_sequence:input.readiness_sequence,capture_state:'created',valid_until:new Date(Date.now()+10_000).toISOString()}));},
  observe(ready:boolean){const view=views.at(-1)!;view.onFrameReadiness!(view.frame!.stamp,{ready,visual_ready:ready,reasons:[]});},
 };
}
it('consumes a one-use ticket, uses only the separate access credential, and reports actual visual preflight without capture commands',async()=>{
 const h=await harness();await h.runtime.start('fictional-one-use-ticket');
 expect(h.views.at(-1)?.phase).toBe('active');expect(h.connect).toHaveBeenCalledTimes(1);
 h.observe(true);await vi.waitFor(()=>expect(h.reports.some(report=>report.visual_ready)).toBe(true));
 expect(h.reports.at(-1)).toMatchObject({renderer_state_version:1,viewport_width:1920,viewport_height:1080,device_pixel_ratio:1,asset_proofs:[],observed_tracks:[]});
 expect(h.fetch.mock.calls[0][1]?.headers instanceof Headers&&h.fetch.mock.calls[0][1].headers.get('Authorization')).toBe('Bearer fictional-one-use-ticket');
 expect(h.fetch.mock.calls.slice(1).every(([,options])=>options?.headers instanceof Headers&&options.headers.get('Authorization')==='Bearer fictional-access')).toBe(true);
 expect(h.fetch.mock.calls.every(([path,options])=>!path.includes('fictional-')&&options?.credentials==='omit')).toBe(true);
 h.runtime.close();expect(h.views.at(-1)?.phase).toBe('stopped');expect(h.reports.at(-1)?.visual_ready).toBe(false);
});
it('revokes with a greater sequence and cannot reopen pixels after a delayed ready ACK arrives after close',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');await vi.waitFor(()=>expect(h.reports.length).toBeGreaterThan(0));
 h.hold();h.observe(true);await vi.waitFor(()=>expect(h.reports.at(-1)?.visual_ready).toBe(true));
 const readySequence=h.reports.at(-1)!.readiness_sequence;h.runtime.close();
 expect(h.reports.at(-1)!.readiness_sequence).toBeGreaterThan(readySequence);expect(h.reports.at(-1)!.visual_ready).toBe(false);
 h.release();await Promise.resolve();expect(h.views.at(-1)?.phase).toBe('stopped');expect(h.views.at(-1)?.frame).toBeUndefined();
});
it('blocks an integrity failure before any media subscription',async()=>{
 const initial=await fixture();const h=await harness({...initial,projection_hash:'0'.repeat(64)});await h.runtime.start('fictional-ticket');
 expect(h.connect).not.toHaveBeenCalled();expect(h.views.at(-1)?.phase).toBe('failed');expect(h.reports.some(report=>report.visual_ready)).toBe(false);
});
it('clears the frame when policy is revoked at a greater state version and rejects stale restoration',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');h.observe(true);
 const revoked={...h.boot,renderer_state_version:2,invalidated:true,capture_plan:{...h.boot.capture_plan,privacy_state:'blocked' as const}};
 h.setState(revoked);await vi.advanceTimersByTimeAsync(1000);
 expect(h.views.at(-1)?.phase).toBe('failed');expect(h.views.at(-1)?.frame).toBeUndefined();
 h.setState(h.boot);await vi.advanceTimersByTimeAsync(3000);expect(h.connect).toHaveBeenCalledTimes(1);expect(h.views.at(-1)?.phase).toBe('failed');
});
it('renews the provider grant through the purpose API and does not create a second media adapter',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');h.refresh();
 await vi.waitFor(()=>expect(h.connect).toHaveBeenCalledTimes(2));
 expect(h.fetch.mock.calls.some(([path])=>path==='/api/v1/recording-renderer/provider-grant')).toBe(true);
 expect(h.views.at(-1)?.phase).toBe('active');h.runtime.close();
});
it('never reports visual readiness at a different capture viewport',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');vi.stubGlobal('window',{innerWidth:390,innerHeight:844,devicePixelRatio:2});h.observe(true);
 await vi.advanceTimersByTimeAsync(3000);expect(h.reports.every(report=>!report.visual_ready)).toBe(true);h.runtime.close();
});
it('revalidates an advanced scene without reconnecting the same approved media and ignores old readiness callbacks',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');const old=h.views.at(-1)!;
 const scene={...h.boot.scene,revision:2,presenter_size:29},capture_plan={...h.boot.capture_plan,scene_revision:2};
 const next={...h.boot,scene,capture_plan,renderer_state_version:2,projection_hash:await hash(scene,capture_plan)};
 h.setState(next);await vi.advanceTimersByTimeAsync(1000);
 await vi.waitFor(()=>expect(h.updatePlan).toHaveBeenCalledTimes(1));expect(h.connect).toHaveBeenCalledTimes(1);expect(h.disconnect).toHaveBeenCalledTimes(1);
 expect(h.views.at(-1)?.frame?.stateVersion).toBe(2);expect(h.views.at(-1)?.phase).toBe('active');
 const before=h.reports.length;old.onFrameReadiness!(old.frame!.stamp,{ready:true,visual_ready:true,reasons:[]});
 expect(h.reports.length).toBe(before);
 h.observe(true);await vi.waitFor(()=>expect(h.reports.at(-1)).toMatchObject({renderer_state_version:2,projection_hash:next.projection_hash,visual_ready:true}));h.runtime.close();
});
it('renews bounded visual receipts with increasing observation sequences every three seconds',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');h.observe(true);
 await vi.waitFor(()=>expect(h.reports.at(-1)?.visual_ready).toBe(true));const first=h.reports.at(-1)!.readiness_sequence;
 await vi.advanceTimersByTimeAsync(3000);expect(h.reports.at(-1)?.visual_ready).toBe(true);expect(h.reports.at(-1)!.readiness_sequence).toBeGreaterThan(first);
 h.observe(false);await vi.waitFor(()=>expect(h.reports.at(-1)?.visual_ready).toBe(false));h.runtime.close();
});
it('holds only the exactly authorized prior frame while verifying a pure scene transition',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');const original=h.views.at(-1)!;
 const scene={...h.boot.scene,revision:2,presenter_size:29},capture_plan={...h.boot.capture_plan,scene_revision:2};
 const next={...h.boot,scene,capture_plan,renderer_state_version:2,projection_hash:await hash(scene,capture_plan),scene_transition:{from_renderer_state_version:1,from_projection_hash:h.boot.projection_hash,expires_at:new Date(Date.now()+5000).toISOString()}};
 let release:()=>void=()=>{};const gate=new Promise<void>(resolve=>{release=resolve;}),digest=crypto.subtle.digest.bind(crypto.subtle);
 vi.spyOn(crypto.subtle,'digest').mockImplementation(async(...args)=>{await gate;return digest(...args);});h.setState(next);await vi.advanceTimersByTimeAsync(1000);
 expect(h.views.at(-1)?.frame?.stateVersion).toBe(1);expect(h.views.at(-1)?.phase).toBe('active');expect(h.views.at(-1)?.isCurrent(original.frame!.stamp)).toBe(true);
 expect(h.reports.at(-1)).toMatchObject({renderer_state_version:2,visual_ready:false,media_state:'connected'});
 release();await vi.waitFor(()=>expect(h.views.at(-1)?.frame?.stateVersion).toBe(2));expect(h.views.at(-1)?.isCurrent(original.frame!.stamp)).toBe(false);expect(h.connect).toHaveBeenCalledTimes(1);h.runtime.close();
});
it('does not retain pixels under a mismatched transition marker',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');const original=h.views.at(-1)!;
 const scene={...h.boot.scene,revision:2},capture_plan={...h.boot.capture_plan,scene_revision:2};
 const next={...h.boot,scene,capture_plan,renderer_state_version:2,projection_hash:await hash(scene,capture_plan),scene_transition:{from_renderer_state_version:1,from_projection_hash:'0'.repeat(64),expires_at:new Date(Date.now()+5000).toISOString()}};
 let release:()=>void=()=>{};const gate=new Promise<void>(resolve=>{release=resolve;}),digest=crypto.subtle.digest.bind(crypto.subtle);
 vi.spyOn(crypto.subtle,'digest').mockImplementation(async(...args)=>{await gate;return digest(...args);});h.setState(next);await vi.advanceTimersByTimeAsync(1000);
 expect(h.views.at(-1)?.phase).toBe('preparing');expect(h.views.at(-1)?.isCurrent(original.frame!.stamp)).toBe(false);release();await vi.waitFor(()=>expect(h.updatePlan).toHaveBeenCalledOnce());h.runtime.close();
});
it('observes a revocation while a new frame digest is pending',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');
 const scene={...h.boot.scene,revision:2},capture_plan={...h.boot.capture_plan,scene_revision:2};
 const next={...h.boot,scene,capture_plan,renderer_state_version:2,projection_hash:await hash(scene,capture_plan),scene_transition:{from_renderer_state_version:1,from_projection_hash:h.boot.projection_hash,expires_at:new Date(Date.now()+2500).toISOString()}};
 let release:()=>void=()=>{};const gate=new Promise<void>(resolve=>{release=resolve;}),digest=crypto.subtle.digest.bind(crypto.subtle);
 vi.spyOn(crypto.subtle,'digest').mockImplementation(async(...args)=>{await gate;return digest(...args);});h.setState(next);await vi.advanceTimersByTimeAsync(1000);
 h.setState({...next,invalidated:true,renderer_state_version:3});await vi.advanceTimersByTimeAsync(1000);
 expect(h.views.at(-1)?.phase).toBe('failed');expect(h.views.at(-1)?.frame).toBeUndefined();release();await Promise.resolve();expect(h.connect).toHaveBeenCalledOnce();
});
it('removes the prior frame when its authorized transition expires',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');
 const scene={...h.boot.scene,revision:2},capture_plan={...h.boot.capture_plan,scene_revision:2};
 const next={...h.boot,scene,capture_plan,renderer_state_version:2,projection_hash:await hash(scene,capture_plan),scene_transition:{from_renderer_state_version:1,from_projection_hash:h.boot.projection_hash,expires_at:new Date(Date.now()+2000).toISOString()}};
 let release:()=>void=()=>{};const gate=new Promise<void>(resolve=>{release=resolve;}),digest=crypto.subtle.digest.bind(crypto.subtle);
 vi.spyOn(crypto.subtle,'digest').mockImplementation(async(...args)=>{await gate;return digest(...args);});h.setState(next);await vi.advanceTimersByTimeAsync(1000);expect(h.views.at(-1)?.phase).toBe('active');
 await vi.advanceTimersByTimeAsync(1100);expect(h.views.at(-1)?.phase).toBe('failed');expect(h.views.at(-1)?.frame).toBeUndefined();release();await Promise.resolve();
});
it('refreshes a conflicted scene observation without retrying the old report or duplicating the poll timer',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');await vi.waitFor(()=>expect(h.reports.length).toBeGreaterThan(0));
 // An already-running poll can have read the prior transaction before the owner save.
 h.holdState();await vi.advanceTimersByTimeAsync(1000);
 const scene={...h.boot.scene,revision:2,presenter_size:29},capture_plan={...h.boot.capture_plan,scene_revision:2};
 const next={...h.boot,scene,capture_plan,renderer_state_version:2,projection_hash:await hash(scene,capture_plan),scene_transition:{from_renderer_state_version:1,from_projection_hash:h.boot.projection_hash,expires_at:new Date(Date.now()+5000).toISOString()}};
 h.setState(next);h.rejectReadiness();h.observe(true);await vi.waitFor(()=>expect(h.reports.at(-1)?.visual_ready).toBe(true));h.releaseState();
 await vi.waitFor(()=>expect(h.views.at(-1)?.frame?.stateVersion).toBe(2));
 expect(h.views.some(view=>view.phase==='failed')).toBe(false);expect(h.connect).toHaveBeenCalledOnce();expect(h.updatePlan).toHaveBeenCalledOnce();
 expect(h.reports.at(-1)).toMatchObject({renderer_state_version:2,visual_ready:false});
 const reads=()=>h.fetch.mock.calls.filter(([path])=>path.includes('/state?')).length;
 expect(reads()).toBe(2);await vi.advanceTimersByTimeAsync(1000);expect(reads()).toBe(3);
 h.observe(true);await vi.waitFor(()=>expect(h.reports.at(-1)).toMatchObject({renderer_state_version:2,visual_ready:true}));h.runtime.close();
});
it('fails closed when a conflict refresh reveals revoked permission',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');await vi.waitFor(()=>expect(h.reports.length).toBeGreaterThan(0));
 h.setState({...h.boot,renderer_state_version:2,invalidated:true});h.rejectReadiness();h.observe(true);
 await vi.waitFor(()=>expect(h.views.at(-1)?.phase).toBe('failed'));expect(h.views.at(-1)?.frame).toBeUndefined();expect(h.connect).toHaveBeenCalledOnce();
});
it('does not loop a conflict when the authoritative fence has not advanced',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');await vi.waitFor(()=>expect(h.reports.length).toBeGreaterThan(0));h.rejectReadiness();h.observe(true);
 await vi.waitFor(()=>expect(h.views.at(-1)?.phase).toBe('failed'));expect(h.fetch.mock.calls.filter(([path])=>path.includes('/state?'))).toHaveLength(1);
});
it.each([[409,'recording_policy_not_approved'],[403,'renderer_state_conflict'],[410,'renderer_state_conflict']])('never refreshes readiness error %s %s as a scene race',async(status,code)=>{
 const h=await harness();await h.runtime.start('fictional-ticket');await vi.waitFor(()=>expect(h.reports.length).toBeGreaterThan(0));h.rejectReadiness(status,code);h.observe(true);
 await vi.waitFor(()=>expect(h.views.at(-1)?.phase).toBe('failed'));expect(h.fetch.mock.calls.some(([path])=>path.includes('/state?'))).toBe(false);expect(h.views.at(-1)?.frame).toBeUndefined();
});
it('expires the authorized old frame even when conflict recovery is still verifying its replacement',async()=>{
 const h=await harness();await h.runtime.start('fictional-ticket');await vi.waitFor(()=>expect(h.reports.length).toBeGreaterThan(0));
 const scene={...h.boot.scene,revision:2},capture_plan={...h.boot.capture_plan,scene_revision:2};
 const next={...h.boot,scene,capture_plan,renderer_state_version:2,projection_hash:await hash(scene,capture_plan),scene_transition:{from_renderer_state_version:1,from_projection_hash:h.boot.projection_hash,expires_at:new Date(Date.now()+1000).toISOString()}};
 let release:()=>void=()=>{};const gate=new Promise<void>(resolve=>{release=resolve;}),digest=crypto.subtle.digest.bind(crypto.subtle);
 vi.spyOn(crypto.subtle,'digest').mockImplementation(async(...args)=>{await gate;return digest(...args);});h.setState(next);h.rejectReadiness();h.observe(true);
 await vi.waitFor(()=>expect(h.reports.at(-1)?.renderer_state_version).toBe(2));expect(h.views.at(-1)?.frame?.stateVersion).toBe(1);
 await vi.advanceTimersByTimeAsync(1100);expect(h.views.at(-1)?.phase).toBe('failed');expect(h.views.at(-1)?.frame).toBeUndefined();release();await Promise.resolve();expect(h.connect).toHaveBeenCalledOnce();
});
it('renders a live-event take through the same media engine with a separately pinned recording project',async()=>{
 const h=await harness(await fixture('live_event'));await h.runtime.start('fictional-ticket');expect(h.views.at(-1)?.phase).toBe('active');expect(h.boot.project_id).not.toBe(h.boot.resource_id);expect(h.connect).toHaveBeenCalledOnce();
 const scene={...h.boot.scene,revision:2,presenter_size:29},capture_plan={...h.boot.capture_plan,scene_revision:2};
 h.setState({...h.boot,scene,capture_plan,renderer_state_version:2,projection_hash:await hash(scene,capture_plan)});await vi.advanceTimersByTimeAsync(1000);
 await vi.waitFor(()=>expect(h.updatePlan).toHaveBeenCalledOnce());expect(h.views.at(-1)?.frame?.scene.revision).toBe(2);expect(h.connect).toHaveBeenCalledOnce();
 h.setState({...h.boot,project_id:h.boot.resource_id,renderer_state_version:3});await vi.advanceTimersByTimeAsync(1000);expect(h.views.at(-1)?.phase).toBe('failed');expect(h.views.at(-1)?.frame).toBeUndefined();
});
it.each(['resource_kind','resource_id','project_id'] as const)('rejects a mismatched solo wrapper %s before subscribing',async(field)=>{
 const initial=await fixture(),h=await harness({...initial,[field]:field==='resource_kind'?'live_event':'10000000-0000-4000-8000-000000000099'});await h.runtime.start('fictional-ticket');expect(h.views.at(-1)?.phase).toBe('failed');expect(h.connect).not.toHaveBeenCalled();
});
