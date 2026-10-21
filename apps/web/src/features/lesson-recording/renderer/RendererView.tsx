import {useCallback,useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {RENDER_PROFILE} from '../../../../../../packages/studio-core';
import {StudioStage,type StageReadiness,type StageTrackBinding} from '../../../ui/studio/StudioStage';
import type {RendererFrame} from './frameFence';
import type {AssetLease} from './assets';
import './renderer.css';
export interface RendererViewProps {frame?:RendererFrame;tracks?:readonly StageTrackBinding[];assetLease?:AssetLease;phase:'preparing'|'active'|'stopped'|'failed';isCurrent:(stamp:string)=>boolean;onFrameReadiness?:(stamp:string,state:StageReadiness)=>void;}
/** Pure capture pixels only. Network/bootstrap/channel/RTC orchestration is deliberately injected later. */
export function RendererView({frame,tracks=[],assetLease,phase,isCurrent,onFrameReadiness}:RendererViewProps){const [viewport,setViewport]=useState(()=>({width:window.innerWidth,height:window.innerHeight,dpr:window.devicePixelRatio}));useEffect(()=>{const resize=()=>setViewport({width:window.innerWidth,height:window.innerHeight,dpr:window.devicePixelRatio});window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[]);const profileMatches=viewport.width===RENDER_PROFILE.width&&viewport.height===RENDER_PROFILE.height&&viewport.dpr===1;const current=!!frame&&isCurrent(frame.stamp);const expected=frame?.scene.content_asset;const assetVerified=!expected||!!assetLease&&assetLease.proof.asset_id===expected.asset_id&&assetLease.proof.sha256===expected.sha256&&assetLease.proof.byte_length>0;
 const receive=useCallback((state:StageReadiness)=>{if(!frame)return;onFrameReadiness?.(frame.stamp,isCurrent(frame.stamp)&&profileMatches?state:{ready:false,visual_ready:false,reasons:[!isCurrent(frame.stamp)?'renderer_state_stale':'renderer_viewport_mismatch']});},[frame,isCurrent,onFrameReadiness,profileMatches]);
 useEffect(()=>{if(frame&&(phase!=='active'||!current||!assetVerified||!profileMatches))onFrameReadiness?.(frame.stamp,{ready:false,visual_ready:false,reasons:[phase!=='active'?'renderer_inactive':!current?'renderer_state_stale':!assetVerified?'asset_checksum_unverified':'renderer_viewport_mismatch']});},[frame,phase,current,assetVerified,onFrameReadiness,profileMatches]);
 return <main className="opora-private-renderer" aria-label="Кадр записи">{phase==='active'&&frame&&current&&assetVerified&&profileMatches?<StudioStage scene={frame.scene} plan={frame.plan} tracks={tracks} asset={assetLease?.asset} mode="render" onReadiness={receive}/>:<div className="renderer-pending" role="status">{phase==='preparing'?'Подготовка записи':phase==='stopped'?'Рендер остановлен':'Запись недоступна'}</div>}</main>;
}
/** A0 may mount this in a dedicated HTML entry once A1's private launch/bootstrap contract is tested. */
export function mountRendererView(element:HTMLElement,initial:RendererViewProps){const root=createRoot(element);let closed=false;root.render(<RendererView {...initial}/>);return Object.freeze({update(props:RendererViewProps){if(!closed)root.render(<RendererView {...props}/>);},close(){if(!closed){closed=true;root.unmount();}}});}
