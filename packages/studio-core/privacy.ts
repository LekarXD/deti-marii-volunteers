import type {StudioScene,CapturePlan,ObservedTrack,Readiness,AllowedTrack} from './types';
import {parseCapturePlan,parseStudioScene} from './scene';
export function sameTrack(a:Pick<AllowedTrack,'identity'|'track_id'|'source'|'kind'>,b:Pick<AllowedTrack,'identity'|'track_id'|'source'|'kind'>){return a.identity===b.identity&&a.track_id===b.track_id&&a.source===b.source&&a.kind===b.kind;}
/** Observed means actually subscribed/captured, not every participant advertised by a room. */
export function captureReadiness(sceneValue:StudioScene,planValue:CapturePlan,observed:readonly ObservedTrack[]):Readiness {
 const scene=parseStudioScene(sceneValue),plan=parseCapturePlan(planValue);const reasons:string[]=[];
 if(scene.foundation_id!==plan.foundation_id||scene.resource_id!==plan.resource_id||scene.session_id!==plan.session_id||scene.take_id!==plan.take_id||scene.recording_policy_id!==plan.recording_policy_id||scene.revision!==plan.scene_revision||scene.render_profile_version!==plan.render_profile_version)reasons.push('capture_scope_mismatch');
 if(plan.privacy_state!=='approved')reasons.push('policy_not_approved');
 const seen=new Set<string>();for(const track of observed){if(seen.has(track.track_id))reasons.push('duplicate_observation');seen.add(track.track_id);if(!plan.allowed_tracks.some(allowed=>sameTrack(allowed,track)))reasons.push('track_not_allowed');if(track.privacy_state!=='approved')reasons.push('track_privacy_unknown');}
 for(const required of plan.allowed_tracks.filter(track=>track.required)){if(!observed.some(track=>sameTrack(required,track)&&(track.state==='ready'||track.state==='muted')))reasons.push('required_track_missing');}
 if(scene.presenter_camera&&!observed.some(track=>track.identity===scene.presenter_identity&&track.source==='camera'&&track.kind==='video'&&track.state==='ready'))reasons.push('presenter_camera_missing');
 if(scene.content_kind==='screen'&&!observed.some(track=>track.identity===scene.presenter_identity&&track.track_id===scene.screen_track_id&&track.source==='screen'&&track.kind==='video'&&track.state==='ready'))reasons.push('screen_track_missing');
 return Object.freeze({ready:reasons.length===0,reasons:Object.freeze([...new Set(reasons)])});
}
/** Only these visual slots enter the stage; no audience grid, controls or chat projection. */
export function sceneTracks(scene:StudioScene,plan:CapturePlan,observed:readonly ObservedTrack[]){if(!captureReadiness(scene,plan,observed).ready)return Object.freeze([]);return Object.freeze(observed.filter(track=>track.kind==='audio'||(track.identity===scene.presenter_identity&&(track.source==='camera'||track.track_id===scene.screen_track_id))));}
