import type {StudioScene} from '../../../../../../packages/studio-core';
import {api} from '../../../api/transport';
import {RoomController,type CaptureJoinGrant,type MediaOptions} from './RoomController';
export class LiveKitController extends RoomController {
 private desiredCamera=false;private desiredMicrophone=false;
 constructor(private sessionId:string,options:MediaOptions){super({...options,onRefreshRequired:()=>{options.onRefreshRequired?.();void this.reconnect();}},false);}
 async connect(scene:StudioScene,signal?:AbortSignal){
  const grant=await api<CaptureJoinGrant>(`/studio-sessions/${this.sessionId}/join-token`,{method:'POST',signal});
  await this.open(grant,scene,null,signal);
 }
 private async reconnect(){
  const scene=this.scene;if(!scene)return;
  try{await this.connect(scene);if(this.desiredCamera)await this.camera(true);if(this.desiredMicrophone)await this.microphone(true);}
  catch{await this.disconnect();this.emit({error:'Доступ изменился или видеокомната недоступна. Подключитесь заново.'});}
 }
 async camera(enabled:boolean,deviceId?:string){if(!this.room||this.grant?.role!=='host')throw new Error('publish_not_allowed');await this.room.localParticipant.setCameraEnabled(enabled,deviceId?{deviceId}:undefined);this.desiredCamera=enabled;this.sync();}
 async microphone(enabled:boolean,deviceId?:string){if(!this.room||this.grant?.role!=='host')throw new Error('publish_not_allowed');await this.room.localParticipant.setMicrophoneEnabled(enabled,deviceId?{deviceId}:undefined);this.desiredMicrophone=enabled;this.sync();}
 async screen(enabled:boolean){if(!this.room||this.grant?.role!=='host')throw new Error('publish_not_allowed');await this.room.localParticipant.setScreenShareEnabled(enabled,{audio:true});this.sync();}
 async enableAudio(){if(this.room)await this.room.startAudio();}
}
