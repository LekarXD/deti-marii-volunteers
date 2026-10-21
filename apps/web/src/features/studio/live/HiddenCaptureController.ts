import {parseStudioScene,parseCapturePlan,type StudioScene,type CapturePlan} from '../../../../../../packages/studio-core';
import {RoomController,type CaptureJoinGrant,type MediaOptions} from './RoomController';
/** Private renderer: no local capture, no audience/data channel/chat projection. */
export class HiddenCaptureController extends RoomController {
 constructor(options:MediaOptions){super(options,true);}
 async connect(grant:CaptureJoinGrant,scene:StudioScene,plan:CapturePlan,signal?:AbortSignal){await this.open(grant,scene,plan,signal);}
 private block(){this.reconnectBlocked=true;this.bindings.clear();for(const participant of this.room?.remoteParticipants.values()??[])for(const publication of participant.trackPublications.values())publication.setSubscribed(false);this.emit({status:'blocked',tracks:[],error:'Область записи изменилась.'});}
 updatePlan(scene:StudioScene,plan:CapturePlan){
  let parsed:CapturePlan,next:StudioScene;try{parsed=parseCapturePlan(plan);next=parseStudioScene(scene);}catch{this.block();return;}
  if(parsed.privacy_state!=='approved'||parsed.recording_policy_id!==next.recording_policy_id||parsed.recording_policy_id!==this.plan?.recording_policy_id||!this.grant||next.take_id!==this.plan?.take_id||parsed.foundation_id!==this.plan?.foundation_id||parsed.resource_id!==this.plan?.resource_id||this.grant.session_id!==next.session_id||this.grant.generation!==parsed.generation||parsed.session_id!==next.session_id||parsed.take_id!==next.take_id||parsed.scene_revision!==next.revision||parsed.foundation_id!==next.foundation_id||parsed.resource_id!==next.resource_id||parsed.render_profile_version!==next.render_profile_version){this.block();return;}
  this.scene=next;this.plan=parsed;this.sync();
 }
}

