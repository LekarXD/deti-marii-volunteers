import {useEffect,useState,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {UndoManager} from 'yjs';
import type {ExcalidrawImperativeAPI} from '@excalidraw/excalidraw/types/types';
import type {BoardStageBinding} from '../../../ui/studio';
import type {StudioScene} from '../../../../../../packages/studio-core';
import {BoardConnection} from './BoardConnection';
import {loadBoardLibraries} from './libraries';
import './board.css';
type Libraries=Awaited<ReturnType<typeof loadBoardLibraries>>;
const UI_OPTIONS={canvasActions:{loadScene:false,saveToActiveFile:false,export:false,saveAsImage:false,toggleTheme:false,changeViewBackgroundColor:false},tools:{image:false}} as const;
/** Ported OD undo policy: only this binding's edits, never other people's strokes. */
function wireUndo(connection:BoardConnection,origin:unknown,host:HTMLElement){const manager=new UndoManager(connection.elements,{trackedOrigins:new Set([origin])});const key=(event:KeyboardEvent)=>{const target=event.target as HTMLElement;if(target.closest('input,textarea,[contenteditable=true]')||!(event.ctrlKey||event.metaKey)||event.altKey)return;const value=event.key.toLowerCase();const action=value==='z'?(event.shiftKey?'redo':'undo'):value==='y'&&!event.shiftKey?'redo':null;if(action){event.preventDefault();event.stopImmediatePropagation();manager[action]();}};host.addEventListener('keydown',key,true);
 const handlers=new Map<Element,EventListener>();const attach=()=>{for(const [selector,action] of [['.undo-button-container button','undo'],['.redo-button-container button','redo']] as const){const button=host.querySelector(selector);if(button&&!handlers.has(button)){const handler=(event:Event)=>{event.preventDefault();event.stopImmediatePropagation();manager[action]();};button.addEventListener('click',handler,true);handlers.set(button,handler);}}};attach();const observer=new MutationObserver(attach);observer.observe(host,{subtree:true,childList:true});return()=>{observer.disconnect();host.removeEventListener('keydown',key,true);handlers.forEach((handler,element)=>element.removeEventListener('click',handler,true));manager.destroy();};}
export function BoardCanvas({connection,readOnly=true,onApi}:{connection:BoardConnection;readOnly?:boolean;onApi?:(api:ExcalidrawImperativeAPI|null)=>void}){
 const host=useRef<HTMLDivElement>(null),[libraries,setLibraries]=useState<Libraries|null>(null),[api,setApi]=useState<ExcalidrawImperativeAPI|null>(null),[error,setError]=useState(false);
 useEffect(()=>{let active=true;loadBoardLibraries().then(value=>{if(active)setLibraries(value);}).catch(()=>{if(active)setError(true);});return()=>{active=false;};},[]);
 useEffect(()=>{onApi?.(api);return()=>onApi?.(null);},[api,onApi]);
 useEffect(()=>{if(!api||!libraries||!connection.awareness||!host.current)return;let dispose:(()=>void)|undefined;const binding=new libraries.ExcalidrawBinding(connection.elements,connection.assets,api,connection.awareness);if(!readOnly)dispose=wireUndo(connection,binding,host.current);let timer:ReturnType<typeof setTimeout>;const fit=()=>{if(timer)clearTimeout(timer);timer=setTimeout(()=>{const elements=api.getSceneElements();if(readOnly&&elements.length)api.scrollToContent(elements,{fitToViewport:true,viewportZoomFactor:.95,animate:false});},100);};connection.elements.observeDeep(fit);fit();return()=>{clearTimeout(timer);connection.elements.unobserveDeep(fit);dispose?.();binding.destroy();};},[api,libraries,connection,connection.state.providers,readOnly]);
 if(error)return <p role="alert">Не удалось загрузить доску. Обновите страницу.</p>;
 const Excalidraw=libraries?.lib.Excalidraw;
 return <div ref={host} className={`studio-board-canvas ${readOnly?'studio-board-readonly':''}`} aria-label={readOnly?'Доска: просмотр':'Совместная доска'}>{Excalidraw?<Excalidraw excalidrawAPI={setApi} viewModeEnabled={readOnly} isCollaborating langCode="ru-RU" theme="light" UIOptions={UI_OPTIONS} detectScroll={false} handleKeyboardGlobally={false} autoFocus={false}/>:<p role="status">Открываем доску…</p>}</div>;
}
/** Dynamic live preview only. Shared Stage blocks capture of this binding until signed replay exists. */
export function boardStageBinding(connection:BoardConnection,scene:StudioScene):BoardStageBinding{
 return {snapshot_id:scene.board_snapshot_id??'',scene_revision:scene.revision,surface_revision:connection.state.surfaceRevision,read_only:true,privacy_state:connection.state.synced?'approved':'unknown',state:connection.state.synced?'ready':connection.state.status==='failed'?'blocked':'connecting',mount(element){const root=createRoot(element);root.render(<BoardCanvas connection={connection}/>);return()=>root.unmount();}};
}
export async function exportBoard(api:ExcalidrawImperativeAPI){const {lib}=await loadBoardLibraries();return lib.exportToBlob({elements:api.getSceneElements(),appState:{...api.getAppState(),exportWithDarkMode:false,exportBackground:true},files:api.getFiles(),mimeType:'image/png',maxWidthOrHeight:1920});}
