import {useEffect,useMemo,useState} from 'react';
import type {StudioScene} from '../../../../../../packages/studio-core';
import {onSessionChange} from '../../../api/transport';
import {LiveKitController} from './LiveKitController';
import type {MediaSnapshot} from './RoomController';
const empty:MediaSnapshot={status:'disconnected',tracks:[],error:null,cameraOn:false,microphoneOn:false,screenOn:false};
/** Creates no room or device prompt until caller explicitly invokes connect/camera/etc. */
export function useLiveKit(sessionId:string,scene:StudioScene){const [media,setMedia]=useState<MediaSnapshot>(empty);const controller=useMemo(()=>new LiveKitController(sessionId,{onChange:setMedia}),[sessionId]);useEffect(()=>{controller.updateScene(scene);},[controller,scene]);useEffect(()=>{const unsubscribe=onSessionChange(()=>void controller.disconnect());return()=>{unsubscribe();void controller.disconnect();};},[controller]);return {controller,media};}
