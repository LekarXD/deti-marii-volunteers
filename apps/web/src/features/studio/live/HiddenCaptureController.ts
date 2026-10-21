import {parseStudioScene,parseCapturePlan,type StudioScene,type CapturePlan} from '../../../../../../packages/studio-core';
import {RoomController,type CaptureJoinGrant,type MediaOptions} from './RoomController';
/** Private renderer: no local capture, no audience/data channel/chat projection. */
export class HiddenCaptureController extends RoomController {
 constructor(options:MediaOptions){super(options,true);}
 async connect(grant:CaptureJoinGrant,scene:StudioScene,plan:CapturePlan,signal?:AbortSignal){await this.open(grant,scene,plan,signal);}
 updatePlan(scene:StudioScene,plan:CapturePlan){
  const parsed=parseCapturePlan(plan),next=parseStudioScene(scene);
  if(!this.grant||next.take_id!==this.plan?.take_id||parsed.foundation_id!==this.plan?.foundation_id||parsed.resource_id!==this.plan?.resource_id||this.grant.session_id!==next.session_id||this.grant.generation!==parsed.generation||parsed.session_id!==next.session_id||parsed.take_id!==next.take_id||parsed.scene_revision!==next.revision||parsed.foundation_id!==next.foundation_id||parsed.resource_id!==next.resource_id||parsed.render_profile_version!==next.render_profile_version){this.reconnectBlocked=true;this.emit({status:'blocked',tracks:[],error:'Область записи изменилась.'});return;}
  this.scene=next;this.plan=parsed;this.sync();
 }
}

