import {parseCapturePlan,parseStudioScene,RENDER_PROFILE,SceneContractError} from '../../../../../../packages/studio-core';
import type {components} from '../../../api/generated/schema';
import {HiddenCaptureController} from '../../studio/live/HiddenCaptureController';
import type {MediaOptions,MediaSnapshot} from '../../studio/live/RoomController';
import type {RendererViewProps} from './RendererView';
import {createRendererTransport,type RendererTransport} from './transport';
import {createRendererFrameFence,type RendererFrame} from './frameFence';
import {verifyProjectionHash} from './projectionHash';
import {verifyRendererAsset,type AssetLease} from './assets';

type State=components['schemas']['RendererStateView'];
type Bootstrap=components['schemas']['RendererBootstrapView'];
type Receipt=components['schemas']['RendererReadinessView'];
type ReadinessInput=components['schemas']['RendererReadinessInput'];
type Media=Pick<HiddenCaptureController,'connect'|'disconnect'>;
export interface RendererRuntimeOptions {
 render:(props:RendererViewProps)=>void;
 /** Test seam for the one shared subscribe-only adapter; never a second RTC client. */
 mediaFactory?:(options:MediaOptions)=>Media;
 transportFactory?:typeof createRendererTransport;
}
const emptyMedia=():MediaSnapshot=>({status:'disconnected',tracks:[],error:null,cameraOn:false,microphoneOn:false,screenOn:false});
/** Called by a verified private launch channel with an in-memory one-use ticket.
 * No URL/window/storage/session reader or capture-start command exists here. */
export function createRendererRuntime(options:RendererRuntimeOptions) {
 const transportFactory=options.transportFactory??createRendererTransport;
 let started=false,closed=true,access:RendererTransport|null=null,bootstrap:RendererTransport|null=null;
 let fence:ReturnType<typeof createRendererFrameFence>|null=null,frame:RendererFrame|undefined,lease:AssetLease|undefined;
 let projectionHash='',media=emptyMedia(),visualReady=false,preparing=true,workEpoch=0;
 let workAbort:AbortController|null=null,poll:ReturnType<typeof setTimeout>|undefined,heartbeat:ReturnType<typeof setInterval>|undefined,expiry:ReturnType<typeof setTimeout>|undefined;
 let latestReport:{body:ReadinessInput;stamp:string}|null=null,reportBusy=false,sequence=0,renewing:Promise<void>|null=null;
 const isCurrent=(stamp:string)=>!closed&&!!fence?.isCurrent(stamp);
 const publish=(phase?:RendererViewProps['phase'])=>options.render({frame,tracks:media.tracks,assetLease:lease,
  phase:phase??(preparing||media.status!=='connected'?'preparing':'active'),isCurrent,
  onFrameReadiness:(stamp,state)=>{if(!isCurrent(stamp))return;const ready=state.ready&&state.visual_ready;if(ready!==visualReady){visualReady=ready;queueReport();}},
 });
 const rtc=(options.mediaFactory??(value=>new HiddenCaptureController(value)))({
  onChange(snapshot){if(closed)return;media=snapshot;visualReady=false;publish();queueReport();},
  onRefreshRequired(){if(!closed)void refreshProvider().catch(()=>fail());},
 });
 function stop(phase:RendererViewProps['phase']) {
  if(closed)return;const finalClient=access,finalReport=frame?reportBody(false):null;
  access=null;closed=true;workEpoch++;workAbort?.abort();workAbort=null;
  clearTimeout(poll);clearInterval(heartbeat);clearTimeout(expiry);latestReport=null;
  bootstrap?.close();bootstrap=null;fence?.close();
  lease?.dispose();lease=undefined;frame=undefined;media=emptyMedia();visualReady=false;
  publish(phase);void rtc.disconnect().catch(()=>{});
  // A greater sequence revokes the receipt even if an earlier ready POST is still
  // finishing. Keep the credential only for this bounded best-effort revocation.
  if(finalClient){if(finalReport)void finalClient.request('readiness',{body:finalReport,timeoutMs:2000}).catch(()=>{}).finally(()=>finalClient.close());else finalClient.close();}
 }
 const fail=()=>stop('failed');
 function reportBody(ready:boolean):ReadinessInput {
  return {renderer_state_version:frame!.stateVersion,projection_hash:projectionHash,
   readiness_sequence:++sequence,visual_ready:ready&&window.innerWidth===RENDER_PROFILE.width&&window.innerHeight===RENDER_PROFILE.height&&window.devicePixelRatio===1,
   viewport_width:window.innerWidth,viewport_height:window.innerHeight,device_pixel_ratio:window.devicePixelRatio,
   render_profile_version:RENDER_PROFILE.version,
   observed_tracks:media.tracks.map(({identity,track_id,source,kind,privacy_state,state})=>({identity,track_id,source,kind,privacy_state,state})),
   asset_proofs:lease?[{asset_id:lease.proof.asset_id,sha256:lease.proof.sha256}]:[],
  };
 }
 function queueReport() {
  if(closed||!access||!frame||!isCurrent(frame.stamp))return;
  latestReport={body:reportBody(visualReady&&!preparing&&media.status==='connected'),stamp:frame.stamp};void flushReports();
 }
 async function flushReports() {
  if(reportBusy||closed)return;reportBusy=true;
  try{while(latestReport&&!closed&&access){
   const report=latestReport;latestReport=null;
   let ack:Receipt;try{ack=await access.request<Receipt>('readiness',{body:report.body,idempotencyKey:crypto.randomUUID()});}
   catch{if(!isCurrent(report.stamp)||report.body.readiness_sequence!==sequence)continue;throw new SceneContractError('renderer_receipt_unavailable');}
   if(!isCurrent(report.stamp)||report.body.readiness_sequence!==sequence)continue;
   if(ack.renderer_state_version!==report.body.renderer_state_version||ack.projection_hash!==report.body.projection_hash||ack.readiness_sequence!==report.body.readiness_sequence)throw new SceneContractError('renderer_receipt_mismatch');
   if(ack.ready&&(!report.body.visual_ready||!ack.valid_until||Date.parse(ack.valid_until)<=Date.now()))throw new SceneContractError('renderer_receipt_invalid');
   // This is a bounded preflight receipt only. It never marks a take capturing.
  }}catch{if(!closed)fail();}finally{reportBusy=false;}
 }
 function parseState(value:State) {
  const scene=parseStudioScene(value.scene),plan=parseCapturePlan(value.capture_plan);
  if(value.foundation_id!==scene.foundation_id||value.project_id!==scene.resource_id||value.take_id!==scene.take_id||value.session_id!==scene.session_id||value.generation!==plan.generation||scene.resource_kind!=='lesson_recording_project')throw new SceneContractError('renderer_scope_mismatch');
  if(value.invalidated!==false||plan.privacy_state!=='approved')throw new SceneContractError('recording_policy_not_approved');
  return {scene,plan};
 }
 async function prepare(value:State,renew=false) {
  if(closed)return;const {scene,plan}=parseState(value);
  if(!fence)fence=createRendererFrameFence(scene,plan,value.renderer_state_version);
  else {
   const change=fence.accept(scene,plan,value.renderer_state_version);
   if(change==='stale')return;
   if(change==='unchanged'&&!renew){if(value.projection_hash!==projectionHash)throw new SceneContractError('renderer_projection_hash_reused');return;}
  }
  frame=fence.current();preparing=true;visualReady=false;projectionHash=value.projection_hash;
  const stamp=frame.stamp,epoch=++workEpoch;workAbort?.abort();workAbort=new AbortController();
  const signal=workAbort.signal,current=()=>!closed&&epoch===workEpoch&&isCurrent(stamp);
  lease?.dispose();lease=undefined;media=emptyMedia();publish();queueReport();
  await rtc.disconnect();
  await verifyProjectionHash(scene,plan,value.resolved_assets,value.projection_hash,{signal,isCurrent:current});
  if(!current())return;
  if(scene.content_asset){
   const blob=await access!.asset(scene.content_asset.asset_id,{signal});
   const candidate=await verifyRendererAsset(scene.content_asset,blob,{signal,isCurrent:current});
   if(!current()){candidate.dispose();return;}lease=candidate;
  }
  const grant=value.provider_grant;
  if(!grant||grant.provider!=='livekit'||grant.session_id!==scene.session_id||grant.generation!==plan.generation||!grant.token||!grant.identity)throw new SceneContractError('renderer_provider_unavailable');
  const url=new URL(grant.url);if(url.username||url.password||url.search||url.hash||!['wss:','ws:'].includes(url.protocol))throw new SceneContractError('renderer_provider_invalid');
  await rtc.connect(grant,scene,plan,signal);if(!current())return;
  preparing=false;publish();queueReport();
 }
 function refreshProvider():Promise<void>{
  if(renewing)return renewing;
  renewing=(async()=>{if(closed||!access)return;preparing=true;visualReady=false;publish();queueReport();
   const value=await access.request<State>('provider-grant');if(!closed)await prepare(value,true);
  })().finally(()=>{renewing=null;});return renewing;
 }
 async function readState(){
  if(closed||!access||!frame)return;
  try{const value=await access.request<State>('state',{afterRevision:frame.stateVersion});if(closed)return;
   const {scene,plan}=parseState(value);const change=fence!.accept(scene,plan,value.renderer_state_version);
   if(change==='advanced'){preparing=true;visualReady=false;frame=fence!.current();projectionHash=value.projection_hash;publish();queueReport();await refreshProvider();}
   else if(change==='unchanged'&&value.projection_hash!==projectionHash)throw new SceneContractError('renderer_projection_hash_reused');
   else if(change==='unchanged'&&preparing)await refreshProvider();
  }catch{if(!closed)fail();}
  if(!closed)poll=setTimeout(()=>{void readState();},1000);
 }
 return Object.freeze({
  async start(oneUseTicket:string){
   if(started)throw new SceneContractError('renderer_already_started');started=true;closed=false;publish('preparing');
   try{bootstrap=transportFactory(oneUseTicket);const initial=await bootstrap.request<Bootstrap>('bootstrap');bootstrap.close();bootstrap=null;
    if(closed)return;const expires=Date.parse(initial.expires_at);if(!Number.isFinite(expires)||expires<=Date.now())throw new SceneContractError('renderer_access_expired');
    access=transportFactory(initial.access_token);expiry=setTimeout(()=>fail(),Math.min(2147483647,expires-Date.now()));
    await prepare(initial);if(closed)return;
    heartbeat=setInterval(queueReport,3000);poll=setTimeout(()=>{void readState();},1000);
   }catch{if(!closed)fail();}
  },
  close(){stop('stopped');},
 });
}
